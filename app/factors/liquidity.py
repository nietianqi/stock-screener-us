from __future__ import annotations

import pandas as pd

from app.config import AppSettings
from app.utils.mathx import minmax_score


def compute_liquidity_metrics(bars: pd.DataFrame, settings: AppSettings) -> dict[str, float | bool | None]:
    if bars.empty:
        return {
            "avg_daily_value_20d": None,
            "liquidity_score": 0.0,
            "liquidity_pass": False,
        }
    data = bars.copy()
    data["dollar_value"] = data["turnover"].fillna(data["close"] * data["volume"])
    avg_daily_value_20d = float(data["dollar_value"].tail(20).mean())
    score = minmax_score(
        avg_daily_value_20d,
        settings.min_avg_daily_value_usd,
        settings.min_avg_daily_value_usd * 10,
    ) or 0.0
    return {
        "avg_daily_value_20d": avg_daily_value_20d,
        "liquidity_score": score,
        "liquidity_pass": avg_daily_value_20d >= settings.min_avg_daily_value_usd,
    }

