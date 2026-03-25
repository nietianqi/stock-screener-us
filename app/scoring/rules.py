from __future__ import annotations

from app.config import AppSettings


OPTIONAL_ENHANCEMENT_FIELDS = (
    "analyst_revision_score",
    "institutional_13f_score",
    "short_interest_score",
    "buyback_execution_score",
)


def build_veto_reasons(metrics: dict[str, object], settings: AppSettings) -> list[str]:
    reasons: list[str] = []
    last_close = metrics.get("last_close")
    if isinstance(last_close, (int, float)) and last_close < settings.min_price:
        reasons.append("price_below_minimum")
    avg_value = metrics.get("avg_daily_value_20d")
    if isinstance(avg_value, (int, float)) and avg_value < settings.min_avg_daily_value_usd:
        reasons.append("avg_daily_value_below_threshold")
    history_bars = metrics.get("history_bars")
    if isinstance(history_bars, int) and history_bars < settings.min_history_bars:
        reasons.append("insufficient_history_bars")
    gap_fill_ratio = metrics.get("gap_fill_ratio")
    if isinstance(gap_fill_ratio, (int, float)) and gap_fill_ratio >= 1.0:
        reasons.append("earnings_gap_fully_filled")
    distribution_days = metrics.get("distribution_days_10d")
    if isinstance(distribution_days, int) and distribution_days >= 4:
        reasons.append("excess_distribution_days")
    if metrics.get("breakout_20d") and isinstance(metrics.get("breakout_20d_level"), (int, float)) and isinstance(last_close, (int, float)):
        if last_close < float(metrics["breakout_20d_level"]):
            reasons.append("failed_recent_breakout")
    return reasons


def build_warning_tags(metrics: dict[str, object], sector_proxy: str | None) -> list[str]:
    warnings: list[str] = []
    if sector_proxy in (None, "", "SPY.US"):
        warnings.append("sector_proxy_fallback")
    for field in OPTIONAL_ENHANCEMENT_FIELDS:
        if metrics.get(field) is None:
            warnings.append(f"missing_{field}")
    if metrics.get("option_contract_count") in (None, 0):
        warnings.append("missing_option_activity")
    if metrics.get("recent_filings_count_30d") is None:
        warnings.append("missing_filings")
    return warnings

