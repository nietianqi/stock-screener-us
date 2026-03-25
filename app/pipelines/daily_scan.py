from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from app.config import AppSettings
from app.data_sources.benchmark_loader import load_benchmark_history
from app.data_sources.longbridge_auth import LongbridgeSessionFactory
from app.data_sources.longbridge_filings import LongbridgeEventClient
from app.data_sources.longbridge_options import LongbridgeOptionsClient
from app.data_sources.longbridge_quote import LongbridgeQuoteClient
from app.factors.breakout import compute_breakout_metrics
from app.factors.earnings_gap import compute_earnings_gap_metrics
from app.factors.event_catalyst import compute_event_catalyst_metrics
from app.factors.liquidity import compute_liquidity_metrics
from app.factors.micro_flow import compute_micro_flow_metrics
from app.factors.momentum import compute_momentum_metrics
from app.factors.options_signal import compute_option_activity_metrics
from app.factors.relative_strength import compute_relative_strength_metrics
from app.factors.risk_control import compute_risk_metrics
from app.factors.trend import compute_trend_metrics
from app.factors.volume_pattern import compute_volume_pattern_metrics
from app.models import PipelineResult, UniverseMember
from app.pipelines.universe_pipeline import load_universe
from app.reports.candidate_report import export_csv
from app.reports.html_export import export_html
from app.scoring.engine import ScoreEngine
from app.storage.parquet_repo import ParquetRepository
from app.storage.sqlite_repo import SQLiteRepository
from app.utils.mathx import safe_float

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScanOptions:
    scan_date: date
    symbols: list[str] | None = None
    universe_file: str | None = None
    top_n: int = 20
    enable_html_report: bool = True


class DailyScanPipeline:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        session_factory = LongbridgeSessionFactory(settings)
        quote_context = session_factory.build_quote_context()
        content_context = session_factory.build_content_context()
        self.quote_client = LongbridgeQuoteClient(settings, quote_context)
        self.event_client = LongbridgeEventClient(settings, quote_context, content_context)
        self.options_client = LongbridgeOptionsClient(settings, quote_context)
        self.score_engine = ScoreEngine(settings)
        self.sqlite_repo = SQLiteRepository(settings.database_path)
        self.parquet_repo = ParquetRepository(settings.parquet_dir)

    def run(self, options: ScanOptions) -> PipelineResult:
        universe = load_universe(self.settings, options.symbols, options.universe_file)
        symbols = universe["symbol"].tolist()
        benchmark_symbols = list(
            dict.fromkeys(
                list(self.settings.benchmark_symbols)
                + universe["industry_etf_proxy"].dropna().tolist()
            )
        )
        master_symbols = list(dict.fromkeys(symbols + benchmark_symbols))

        static_info = self.quote_client.fetch_static_info(master_symbols)
        latest_quotes = self.quote_client.fetch_latest_quotes(master_symbols)
        benchmark_history = load_benchmark_history(self.quote_client, benchmark_symbols, self.settings.lookback_bars)

        self._persist_baseline(static_info, latest_quotes)

        static_map = static_info.set_index("symbol").to_dict("index") if not static_info.empty else {}
        quote_map = latest_quotes.set_index("symbol").to_dict("index") if not latest_quotes.empty else {}

        candidate_records: list[dict[str, Any]] = []
        failure_records: list[dict[str, Any]] = []
        for row in universe.itertuples(index=False):
            member = UniverseMember(symbol=row.symbol, industry_etf_proxy=row.industry_etf_proxy)
            try:
                score_card, artifacts = self._evaluate_symbol(member, options.scan_date, static_map, quote_map, benchmark_history)
                candidate_records.append(score_card.as_record())
                self._persist_symbol_artifacts(artifacts)
            except Exception as exc:
                logger.exception("Failed to scan %s", member.symbol)
                failure_records.append(
                    {
                        "symbol": member.symbol,
                        "scan_date": options.scan_date.isoformat(),
                        "error": str(exc),
                    }
                )

        candidates = pd.DataFrame(candidate_records)
        failures = pd.DataFrame(failure_records)
        if not candidates.empty:
            candidates["payload_json"] = candidates.apply(
                lambda row: json.dumps(row.to_dict(), default=str, ensure_ascii=False),
                axis=1,
            )
            factor_columns = [
                "symbol",
                "scan_date",
                "ma50",
                "ma200",
                "momentum_12_1",
                "rs_vs_spy",
                "rs_vs_qqq",
                "rs_vs_sector",
                "breakout_20d",
                "breakout_60d",
                "vol_ratio_5_20",
                "accumulation_score",
                "earnings_gap_score",
                "filings_event_score",
                "option_activity_score",
                "capital_flow_score",
                "depth_bias_score",
                "risk_score",
                "total_score",
                "trigger_tags",
                "warning_tags",
                "veto_reasons",
                "payload_json",
            ]
            self.sqlite_repo.upsert_dataframe("factor_table", candidates[factor_columns], ["symbol", "scan_date"])
            self.parquet_repo.save_dataframe("factor_table", candidates)

        output_dir = self.settings.output_dir / options.scan_date.isoformat()
        candidates_path = export_csv(
            candidates.sort_values("total_score", ascending=False) if not candidates.empty else candidates,
            output_dir / "candidates.csv",
        )
        failures_path = export_csv(failures, output_dir / "failures.csv")
        artifacts = {
            "candidates_csv": str(candidates_path),
            "failures_csv": str(failures_path),
        }
        if options.enable_html_report and self.settings.enable_html_report and not candidates.empty:
            html_path = export_html(
                candidates.sort_values("total_score", ascending=False),
                output_dir / "candidates.html",
                options.top_n,
            )
            artifacts["candidates_html"] = str(html_path)
        return PipelineResult(candidates=candidates, failures=failures, artifacts=artifacts)

    def _persist_baseline(self, static_info: pd.DataFrame, latest_quotes: pd.DataFrame) -> None:
        self.sqlite_repo.upsert_dataframe("symbol_master", static_info, ["symbol"])
        self.sqlite_repo.upsert_dataframe("realtime_snapshot", latest_quotes, ["symbol"])
        self.parquet_repo.save_dataframe("symbol_master", static_info)
        self.parquet_repo.save_dataframe("realtime_snapshot", latest_quotes)

    def _persist_symbol_artifacts(self, artifacts: dict[str, pd.DataFrame]) -> None:
        if not artifacts["bars"].empty:
            self.sqlite_repo.upsert_dataframe("daily_bar", artifacts["bars"], ["symbol", "date", "period"])
        if not artifacts["filings"].empty:
            self.sqlite_repo.upsert_dataframe("filings_table", artifacts["filings"], ["symbol", "filing_id"])
        if not artifacts["news"].empty:
            self.sqlite_repo.upsert_dataframe("news_table", artifacts["news"], ["symbol", "news_id"])
        if not artifacts["topics"].empty:
            self.sqlite_repo.upsert_dataframe("topic_table", artifacts["topics"], ["symbol", "topic_id"])

    def _evaluate_symbol(
        self,
        member: UniverseMember,
        scan_date: date,
        static_map: dict[str, dict[str, Any]],
        quote_map: dict[str, dict[str, Any]],
        benchmark_history: dict[str, pd.DataFrame],
    ):
        warning_tags: list[str] = []
        bars = self.quote_client.fetch_history_bars(member.symbol, count=self.settings.lookback_bars)
        trades = self._safe_optional(self.quote_client.fetch_trades, member.symbol, warning_tag="trades_unavailable", warning_tags=warning_tags)
        depth = self._safe_optional(self.quote_client.fetch_depth, member.symbol, warning_tag="depth_unavailable", warning_tags=warning_tags)
        capital_flow = self._safe_optional(self.quote_client.fetch_capital_flow, member.symbol, warning_tag="capital_flow_unavailable", warning_tags=warning_tags)
        capital_distribution = self._safe_optional(
            self.quote_client.fetch_capital_distribution,
            member.symbol,
            warning_tag="capital_distribution_unavailable",
            warning_tags=warning_tags,
        )
        filings = self._safe_optional(self.event_client.fetch_filings, member.symbol, warning_tag="filings_unavailable", warning_tags=warning_tags)
        news = self._safe_optional(self.event_client.fetch_news, member.symbol, warning_tag="news_unavailable", warning_tags=warning_tags)
        topics = self._safe_optional(self.event_client.fetch_topics, member.symbol, warning_tag="topics_unavailable", warning_tags=warning_tags)

        quote_row = quote_map.get(member.symbol, {})
        static_row = static_map.get(member.symbol, {})
        underlying_price = safe_float(quote_row.get("last_done")) or (
            float(bars["close"].iloc[-1]) if not bars.empty else None
        )
        option_snapshot = self._safe_optional(
            self.options_client.build_activity_snapshot,
            member.symbol,
            underlying_price,
            warning_tag="options_unavailable",
            warning_tags=warning_tags,
            default={},
        )

        metrics: dict[str, Any] = {
            "name_en": static_row.get("name_en"),
            "exchange": static_row.get("exchange"),
            "currency": static_row.get("currency"),
            "industry_etf_proxy": member.industry_etf_proxy,
            "last_close": underlying_price,
            "history_bars": int(len(bars)),
        }
        for payload in (
            compute_liquidity_metrics(bars, self.settings),
            compute_trend_metrics(bars),
            compute_momentum_metrics(bars),
            compute_breakout_metrics(bars, self.settings.min_breakout_buffer),
            compute_volume_pattern_metrics(bars),
            compute_earnings_gap_metrics(bars),
            compute_relative_strength_metrics(bars, benchmark_history, member.industry_etf_proxy),
            compute_micro_flow_metrics(trades, depth, capital_flow, capital_distribution),
            compute_option_activity_metrics(option_snapshot or {}),
            compute_event_catalyst_metrics(filings, news, topics, option_snapshot or {}, scan_date),
        ):
            metrics.update(payload)

        risk_metrics = compute_risk_metrics(bars, self.settings, metrics.get("event_score"))
        metrics.update(risk_metrics)
        metrics["option_activity_score"] = metrics.get("option_activity_score")
        metrics["capital_flow_score"] = metrics.get("capital_flow_score")
        metrics["depth_bias_score"] = metrics.get("depth_bias_score")
        metrics["micro_flow_score"] = metrics.get("micro_flow_score")

        score_card = self.score_engine.score(
            symbol=member.symbol,
            scan_date=scan_date,
            sector_proxy=member.industry_etf_proxy,
            metrics=metrics,
            inherited_warning_tags=warning_tags,
        )
        return score_card, {
            "bars": bars,
            "filings": filings,
            "news": news,
            "topics": topics,
        }

    def _safe_optional(
        self,
        func,
        *args,
        warning_tag: str,
        warning_tags: list[str],
        default: Any | None = None,
    ) -> Any:
        try:
            return func(*args)
        except Exception:
            logger.warning("Optional fetch failed for %s", warning_tag, exc_info=True)
            warning_tags.append(warning_tag)
            return default if default is not None else pd.DataFrame()

