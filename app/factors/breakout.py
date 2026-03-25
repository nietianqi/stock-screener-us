from __future__ import annotations

import pandas as pd

from app.utils.mathx import clamp


def compute_breakout_metrics(bars: pd.DataFrame, breakout_buffer: float = 0.005) -> dict[str, float | bool | None]:
    if len(bars) < 65:
        return {
            "breakout_20d": None,
            "breakout_60d": None,
            "breakout_20d_level": None,
            "breakout_60d_level": None,
            "breakout_score": 0.0,
        }
    close = float(bars["close"].iloc[-1])
    prior20 = float(bars["high"].iloc[-21:-1].max())
    prior60 = float(bars["high"].iloc[-61:-1].max())
    breakout_20d = close >= prior20 * (1 + breakout_buffer)
    breakout_60d = close >= prior60 * (1 + breakout_buffer)
    score = 0.0
    if breakout_20d:
        score += 40
    if breakout_60d:
        score += 60
    return {
        "breakout_20d": breakout_20d,
        "breakout_60d": breakout_60d,
        "breakout_20d_level": prior20,
        "breakout_60d_level": prior60,
        "breakout_score": clamp(score),
    }

