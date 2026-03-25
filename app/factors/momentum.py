from __future__ import annotations

import pandas as pd

from app.utils.mathx import clamp, minmax_score


def compute_momentum_metrics(bars: pd.DataFrame) -> dict[str, float | None]:
    if len(bars) < 252:
        return {"momentum_12_1": None, "momentum_score": 0.0}
    close = bars["close"].reset_index(drop=True)
    momentum_12_1 = float(close.iloc[-22] / close.iloc[-252] - 1)
    score = minmax_score(momentum_12_1, -0.2, 0.8) or 0.0
    recent_month = float(close.iloc[-1] / close.iloc[-22] - 1)
    if recent_month < -0.08:
        score -= 10
    return {
        "momentum_12_1": momentum_12_1,
        "momentum_score": clamp(score),
    }

