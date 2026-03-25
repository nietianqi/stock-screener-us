from __future__ import annotations

from app.config import AppSettings
from app.models import SymbolScoreCard
from app.scoring.rules import build_veto_reasons, build_warning_tags
from app.scoring.weights import GROUP_WEIGHTS
from app.utils.mathx import clamp, mean_ignore_none


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


class ScoreEngine:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def score(
        self,
        symbol: str,
        scan_date,
        sector_proxy: str | None,
        metrics: dict[str, object],
        inherited_warning_tags: list[str] | None = None,
    ) -> SymbolScoreCard:
        trend_momentum_score = mean_ignore_none(
            [
                _as_float(metrics.get("trend_score")),
                _as_float(metrics.get("momentum_score")),
                _as_float(metrics.get("rs_score")),
                _as_float(metrics.get("breakout_score")),
            ]
        ) or 0.0
        price_volume_score = mean_ignore_none(
            [
                _as_float(metrics.get("price_volume_health_score")),
                _as_float(metrics.get("earnings_gap_score")),
                _as_float(metrics.get("accumulation_score")),
            ]
        ) or 0.0
        catalyst_score = mean_ignore_none(
            [
                _as_float(metrics.get("filings_event_score")),
                _as_float(metrics.get("news_topic_score")),
                _as_float(metrics.get("option_activity_score")),
                _as_float(metrics.get("event_score")),
            ]
        ) or 0.0
        micro_flow_score_group = mean_ignore_none(
            [
                _as_float(metrics.get("capital_flow_score")),
                _as_float(metrics.get("depth_bias_score")),
                _as_float(metrics.get("trade_aggression_score")),
            ]
        ) or 0.0
        risk_control_score = _as_float(metrics.get("risk_score")) or 0.0

        metrics["trend_momentum_score"] = trend_momentum_score
        metrics["price_volume_score"] = price_volume_score
        metrics["catalyst_score"] = catalyst_score
        metrics["micro_flow_score_group"] = micro_flow_score_group
        metrics["risk_control_score"] = risk_control_score

        total_score = (
            GROUP_WEIGHTS["trend_momentum_score"] * trend_momentum_score
            + GROUP_WEIGHTS["price_volume_score"] * price_volume_score
            + GROUP_WEIGHTS["catalyst_score"] * catalyst_score
            + GROUP_WEIGHTS["micro_flow_score_group"] * micro_flow_score_group
            + GROUP_WEIGHTS["risk_control_score"] * risk_control_score
        )
        veto_reasons = build_veto_reasons(metrics, self.settings)
        warning_tags = build_warning_tags(metrics, sector_proxy)
        if inherited_warning_tags:
            warning_tags.extend(inherited_warning_tags)
        trigger_tags = self._build_trigger_tags(metrics)
        total_score = clamp(total_score)
        if veto_reasons:
            total_score = min(total_score, 49.0)

        return SymbolScoreCard(
            symbol=symbol,
            scan_date=scan_date,
            metrics=metrics,
            total_score=total_score,
            trigger_tags=sorted(set(trigger_tags)),
            warning_tags=sorted(set(warning_tags)),
            veto_reasons=sorted(set(veto_reasons)),
        )

    @staticmethod
    def _build_trigger_tags(metrics: dict[str, object]) -> list[str]:
        tags: list[str] = []
        if _as_float(metrics.get("trend_score")) and float(metrics["trend_score"]) >= 80:
            tags.append("trend_stack")
        if _as_float(metrics.get("momentum_score")) and float(metrics["momentum_score"]) >= 70:
            tags.append("momentum_12_1")
        if metrics.get("breakout_20d"):
            tags.append("breakout_20d")
        if metrics.get("breakout_60d"):
            tags.append("breakout_60d")
        if _as_float(metrics.get("rs_score")) and float(metrics["rs_score"]) >= 65:
            tags.append("relative_strength")
        if _as_float(metrics.get("earnings_gap_score")) and float(metrics["earnings_gap_score"]) >= 60:
            tags.append("unfilled_gap")
        if _as_float(metrics.get("filings_event_score")) and float(metrics["filings_event_score"]) >= 55:
            tags.append("filings_catalyst")
        if _as_float(metrics.get("option_activity_score")) and float(metrics["option_activity_score"]) >= 60:
            tags.append("option_activity")
        if _as_float(metrics.get("micro_flow_score")) and float(metrics["micro_flow_score"]) >= 60:
            tags.append("micro_flow")
        return tags

