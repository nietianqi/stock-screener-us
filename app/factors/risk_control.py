from __future__ import annotations

import pandas as pd

from app.config import AppSettings
from app.utils.mathx import annualized_volatility, clamp


def compute_risk_metrics(
    bars: pd.DataFrame,
    settings: AppSettings,
    event_score: float | None,
) -> dict[str, float | bool | None]:
    if len(bars) < 25:
        return {
            "volatility_20d": None,
            "daily_change_pct": None,
            "three_day_breakdown": None,
            "risk_score": 0.0,
        }

    close = bars["close"]
    volatility_20d = annualized_volatility(close, window=20)
    daily_change_pct = float(close.iloc[-1] / close.iloc[-2] - 1)
    recent_changes = close.pct_change().tail(3)
    three_day_breakdown = bool((recent_changes < -0.03).sum() >= 2)
    score = 100.0
    if volatility_20d is not None and volatility_20d > settings.max_daily_volatility_warning:
        score -= 30
    if abs(daily_change_pct) > settings.max_intraday_overheat_pct:
        score -= 20
    if three_day_breakdown:
        score -= 25
    if event_score is not None and event_score < 30:
        score -= 10
    return {
        "volatility_20d": volatility_20d,
        "daily_change_pct": daily_change_pct,
        "three_day_breakdown": three_day_breakdown,
        "risk_score": clamp(score),
    }
