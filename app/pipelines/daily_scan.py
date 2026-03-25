from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from longbridge.openapi import Market, SecurityListCategory

from app.config import AppSettings
from app.data_sources.api_budget import ENDPOINT_QUOTE, ENDPOINT_SECURITY_LIST, ENDPOINT_STATIC_INFO, ApiBudget
from app.data_sources.bar_cache import BarCacheManager
from app.data_sources.longbridge_auth import LongbridgeSessionFactory
from app.data_sources.longbridge_filings import LongbridgeEventClient
from app.data_sources.longbridge_options import LongbridgeOptionsClient
from app.data_sources.longbridge_quote import LongbridgeQuoteClient
from app.data_sources.universe_cache import UniverseCache
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
from app.enums import StorageBackend
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
        self._optional_warning_emitted: set[str] = set()
        session_factory = LongbridgeSessionFactory(settings)
        quote_context = session_factory.build_quote_context()
        content_context = session_factory.build_content_context()
        self.quote_client = LongbridgeQuoteClient(settings, quote_context)
        self.event_client = LongbridgeEventClient(settings, quote_context, content_context)
        self.options_client = LongbridgeOptionsClient(settings, quote_context)
        self.score_engine = ScoreEngine(settings)
        self.sqlite_repo = SQLiteRepository(settings.database_path)
        self.parquet_repo = ParquetRepository(settings.parquet_dir)
        self.api_budget = ApiBudget(settings)
        self.bar_cache = BarCacheManager(settings, self.sqlite_repo, self.quote_client, self.api_budget)
        self.universe_cache = UniverseCache(settings)

    def run(self, options: ScanOptions) -> PipelineResult:
        self.api_budget.reset()
        self.bar_cache.reset_stats()
        universe, preloaded_bars = self._resolve_universe(options)
        symbols = universe["symbol"].tolist()
        benchmark_symbols = list(
            dict.fromkeys(
                list(self.settings.benchmark_symbols)
                + universe["industry_etf_proxy"].dropna().tolist()
            )
        )
        master_symbols = list(dict.fromkeys(symbols + benchmark_symbols))

        static_info = self._fetch_static_info(master_symbols)
        latest_quotes = self._fetch_latest_quotes(master_symbols)
        benchmark_history = self.bar_cache.get_bars_bulk(
            benchmark_symbols,
            needed_bars=self.settings.lookback_bars,
            as_of=options.scan_date,
        )

        self._persist_baseline(static_info, latest_quotes)

        static_map = static_info.set_index("symbol").to_dict("index") if not static_info.empty else {}
        quote_map = latest_quotes.set_index("symbol").to_dict("index") if not latest_quotes.empty else {}

        candidate_records: list[dict[str, Any]] = []
        failure_records: list[dict[str, Any]] = []
        for row in universe.itertuples(index=False):
            member = UniverseMember(symbol=row.symbol, industry_etf_proxy=row.industry_etf_proxy)
            try:
                score_card, artifacts = self._evaluate_symbol(
                    member,
                    options.scan_date,
                    static_map,
                    quote_map,
                    benchmark_history,
                    preloaded_bars,
                )
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
            if self._use_sqlite:
                self.sqlite_repo.upsert_dataframe("factor_table", candidates[factor_columns], ["symbol", "scan_date"])
            if self._use_parquet:
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

        self.bar_cache.log_stats()
        self.api_budget.log_summary()
        return PipelineResult(candidates=candidates, failures=failures, artifacts=artifacts)

    def _persist_baseline(self, static_info: pd.DataFrame, latest_quotes: pd.DataFrame) -> None:
        if self._use_sqlite:
            self.sqlite_repo.upsert_dataframe("symbol_master", static_info, ["symbol"])
            self.sqlite_repo.upsert_dataframe("realtime_snapshot", latest_quotes, ["symbol"])
        if self._use_parquet:
            self.parquet_repo.save_dataframe("symbol_master", static_info)
            self.parquet_repo.save_dataframe("realtime_snapshot", latest_quotes)

    def _persist_symbol_artifacts(self, artifacts: dict[str, pd.DataFrame]) -> None:
        if self._use_sqlite and not artifacts["bars"].empty:
            self.sqlite_repo.upsert_dataframe("daily_bar", artifacts["bars"], ["symbol", "date", "period"])
        if self._use_sqlite and not artifacts["filings"].empty:
            self.sqlite_repo.upsert_dataframe("filings_table", artifacts["filings"], ["symbol", "filing_id"])
        if self._use_sqlite and not artifacts["news"].empty:
            self.sqlite_repo.upsert_dataframe("news_table", artifacts["news"], ["symbol", "news_id"])
        if self._use_sqlite and not artifacts["topics"].empty:
            self.sqlite_repo.upsert_dataframe("topic_table", artifacts["topics"], ["symbol", "topic_id"])

    def _evaluate_symbol(
        self,
        member: UniverseMember,
        scan_date: date,
        static_map: dict[str, dict[str, Any]],
        quote_map: dict[str, dict[str, Any]],
        benchmark_history: dict[str, pd.DataFrame],
        preloaded_bars: dict[str, pd.DataFrame],
    ):
        warning_tags: list[str] = []
        bars = preloaded_bars.get(member.symbol)
        if bars is None:
            bars = self.bar_cache.get_bars(
                member.symbol,
                needed_bars=self.settings.lookback_bars,
                as_of=scan_date,
            )
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
        except Exception as exc:
            if warning_tag not in self._optional_warning_emitted:
                logger.warning("Optional fetch failed for %s: %s", warning_tag, exc)
                self._optional_warning_emitted.add(warning_tag)
            warning_tags.append(warning_tag)
            return default if default is not None else pd.DataFrame()

    def _resolve_universe(self, options: ScanOptions) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        if options.symbols or options.universe_file:
            return load_universe(self.settings, options.symbols, options.universe_file), {}
        if not self.settings.auto_universe_enabled:
            return load_universe(self.settings, None, None), {}
        cached_universe = self.universe_cache.load()
        if cached_universe is not None and not cached_universe.empty:
            cached_universe = cached_universe.copy()
            if "industry_etf_proxy" not in cached_universe.columns:
                cached_universe["industry_etf_proxy"] = cached_universe["symbol"].map(
                    self.settings.sector_proxy_by_symbol
                )
            cached_universe["industry_etf_proxy"] = cached_universe["industry_etf_proxy"].fillna("SPY.US")
            return cached_universe.drop_duplicates(subset=["symbol"]).reset_index(drop=True), {}
        try:
            return self._build_auto_universe(options.scan_date)
        except Exception as exc:
            logger.warning("Auto universe build failed (%s), fallback to sample universe.", exc)
            return load_universe(self.settings, None, None), {}

    def _build_auto_universe(self, scan_date: date) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        market_map = {
            "US": Market.US,
            "HK": Market.HK,
            "CN": Market.CN,
            "SG": Market.SG,
            "CRYPTO": Market.Crypto,
        }
        market_code = self.settings.auto_universe_market
        market = market_map.get(market_code, Market.US)
        category = SecurityListCategory.Overnight if market_code == "US" else None
        self.api_budget.record(ENDPOINT_SECURITY_LIST, 1)
        security_frame = self.quote_client.fetch_security_list(market=market, category=category)
        if security_frame.empty:
            raise RuntimeError("No symbols returned from Longbridge security_list.")

        security_frame = security_frame.dropna(subset=["symbol"]).copy()
        security_frame["symbol"] = security_frame["symbol"].astype(str).str.upper()
        if market_code == "US":
            security_frame = security_frame[security_frame["symbol"].str.endswith(".US")]
        security_frame = security_frame.drop_duplicates(subset=["symbol"]).reset_index(drop=True)
        symbols = security_frame["symbol"].tolist()
        logger.info("Auto universe raw symbols: %s", len(symbols))
        if not symbols:
            raise RuntimeError("Auto universe symbol list is empty.")

        quote_frame = self._fetch_latest_quotes(symbols)
        if quote_frame.empty:
            raise RuntimeError("Unable to fetch quote snapshot for auto universe.")

        quote_frame["last_done"] = pd.to_numeric(quote_frame["last_done"], errors="coerce")
        quote_frame["turnover"] = pd.to_numeric(quote_frame["turnover"], errors="coerce")
        quote_frame["volume"] = pd.to_numeric(quote_frame["volume"], errors="coerce")
        quote_frame["turnover_proxy"] = quote_frame["turnover"].fillna(
            quote_frame["last_done"] * quote_frame["volume"]
        )
        liquid = quote_frame[
            (quote_frame["last_done"] >= self.settings.min_price)
            & (quote_frame["turnover_proxy"] >= self.settings.auto_universe_min_turnover_usd)
        ].copy()
        if liquid.empty:
            liquid = quote_frame[quote_frame["last_done"] >= self.settings.min_price].copy()
        liquid = liquid.sort_values("turnover_proxy", ascending=False)
        eval_symbols = liquid["symbol"].dropna().astype(str).head(self.settings.auto_universe_eval_limit).tolist()
        logger.info("Auto universe quick liquidity pass symbols: %s", len(eval_symbols))
        if not eval_symbols:
            raise RuntimeError("No symbols passed quick liquidity prefilter.")

        selected_symbols = eval_symbols[: self.settings.auto_universe_max_symbols]
        logger.info("Auto universe selected symbols after liquidity filter: %s", len(selected_symbols))
        if not selected_symbols:
            raise RuntimeError("No symbols selected from auto universe.")

        universe = pd.DataFrame({"symbol": selected_symbols})
        universe["industry_etf_proxy"] = universe["symbol"].map(self.settings.sector_proxy_by_symbol).fillna("SPY.US")
        universe = universe.reset_index(drop=True)
        self.universe_cache.save(universe)
        preloaded_bars = self.bar_cache.get_bars_bulk(
            selected_symbols,
            needed_bars=self.settings.lookback_bars,
            as_of=scan_date,
        )
        return universe, preloaded_bars

    def _fetch_static_info(self, symbols: list[str]) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()
        batch_count = max(1, (len(symbols) + self._effective_batch_size - 1) // self._effective_batch_size)
        self.api_budget.record(ENDPOINT_STATIC_INFO, batch_count)
        return self.quote_client.fetch_static_info(symbols)

    def _fetch_latest_quotes(self, symbols: list[str]) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()
        budgeted_symbols = self._budget_quote_symbols(symbols)
        if not budgeted_symbols:
            return pd.DataFrame()
        return self.quote_client.fetch_latest_quotes(budgeted_symbols)

    def _budget_quote_symbols(self, symbols: list[str]) -> list[str]:
        if not symbols:
            return []
        chunk_size = self._effective_batch_size
        allowed_symbols: list[str] = []
        blocked_batches = 0
        for start in range(0, len(symbols), chunk_size):
            batch = symbols[start:start + chunk_size]
            marker = batch[0] if batch else ""
            if self.api_budget.consume(ENDPOINT_QUOTE, marker):
                allowed_symbols.extend(batch)
            else:
                blocked_batches += 1
        if blocked_batches > 0:
            logger.warning(
                "Quote budget blocked %d batch(es). Requested=%d symbols, allowed=%d symbols.",
                blocked_batches,
                len(symbols),
                len(allowed_symbols),
            )
        return allowed_symbols

    @property
    def _effective_batch_size(self) -> int:
        return max(1, min(500, int(self.settings.request_batch_size)))

    @property
    def _use_sqlite(self) -> bool:
        return self.settings.storage_backend in {StorageBackend.SQLITE, StorageBackend.BOTH}

    @property
    def _use_parquet(self) -> bool:
        return self.settings.storage_backend in {StorageBackend.PARQUET, StorageBackend.BOTH}
