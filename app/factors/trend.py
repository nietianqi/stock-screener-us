from __future__ import annotations

import pandas as pd

from app.utils.mathx import clamp


def compute_trend_metrics(bars: pd.DataFrame) -> dict[str, float | None]:
    if len(bars) < 200:
        return {"ma20": None, "ma50": None, "ma200": None, "trend_score": 0.0}
    close = bars["close"]
    ma20 = float(close.tail(20).mean())
    ma50 = float(close.tail(50).mean())
    ma200 = float(close.tail(200).mean())
    last_close = float(close.iloc[-1])
    score = 0.0
    if ma50 > ma200:
        score += 55
    if last_close > ma50:
        score += 25
    if last_close > ma200:
        score += 10
    if ma20 > ma50:
        score += 10
    return {
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "trend_score": clamp(score),
    }

