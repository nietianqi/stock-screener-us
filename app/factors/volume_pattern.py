from __future__ import annotations

import numpy as np
import pandas as pd

from app.utils.mathx import clamp, safe_ratio


def compute_volume_pattern_metrics(bars: pd.DataFrame) -> dict[str, float | int | None]:
    if len(bars) < 25:
        return {
            "vol_ratio_5_20": None,
            "accumulation_score": 0.0,
            "distribution_days_10d": None,
            "price_volume_health_score": 0.0,
        }

    data = bars.copy()
    data["change"] = data["close"].pct_change()
    data["up_volume"] = np.where(data["change"] > 0, data["volume"], 0)
    data["down_volume"] = np.where(data["change"] < 0, data["volume"], 0)
    vol_ratio = safe_ratio(float(data["volume"].tail(5).mean()), float(data["volume"].tail(20).mean()))
    up_volume = float(data["up_volume"].tail(25).sum())
    down_volume = float(data["down_volume"].tail(25).sum())
    accumulation_score = 50.0
    if up_volume or down_volume:
        accumulation_score += min(35.0, ((up_volume - down_volume) / max(up_volume + down_volume, 1)) * 70)
    distribution_days = int(
        ((data["change"].tail(10) < -0.007) & (data["volume"].tail(10) > data["volume"].shift(1).tail(10))).sum()
    )
    health_score = 0.0
    if vol_ratio is not None:
        health_score += clamp((vol_ratio - 0.8) / 1.4 * 45)
    health_score += clamp(accumulation_score * 0.55)
    return {
        "vol_ratio_5_20": vol_ratio,
        "accumulation_score": clamp(accumulation_score),
        "distribution_days_10d": distribution_days,
        "price_volume_health_score": clamp(health_score),
    }

