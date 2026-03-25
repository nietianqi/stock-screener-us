from __future__ import annotations

import pandas as pd

from app.utils.mathx import clamp


def compute_earnings_gap_metrics(bars: pd.DataFrame) -> dict[str, float | bool | None]:
    if len(bars) < 12:
        return {
            "gap_up_after_earnings": None,
            "gap_fill_ratio": None,
            "earnings_gap_score": 0.0,
        }

    recent = bars.tail(21).reset_index(drop=True)
    best_gap: dict[str, float | bool | None] | None = None
    for index in range(1, len(recent)):
        prev_high = float(recent.loc[index - 1, "high"])
        prev_close = float(recent.loc[index - 1, "close"])
        current_low = float(recent.loc[index, "low"])
        current_close = float(recent.loc[index, "close"])
        gap_pct = current_low / max(prev_high, 0.01) - 1
        day_jump = current_close / max(prev_close, 0.01) - 1
        if gap_pct < 0.03 or day_jump < 0.05:
            continue
        gap_amount = max(current_low - prev_high, 0.0001)
        subsequent_low = float(recent.loc[index:, "low"].min())
        gap_fill_ratio = clamp((current_low - subsequent_low) / gap_amount, 0.0, 1.0)
        score = clamp((1 - gap_fill_ratio) * 100)
        candidate = {
            "gap_up_after_earnings": True,
            "gap_fill_ratio": gap_fill_ratio,
            "earnings_gap_score": score,
        }
        if best_gap is None or score > float(best_gap["earnings_gap_score"] or 0.0):
            best_gap = candidate

    return best_gap or {
        "gap_up_after_earnings": False,
        "gap_fill_ratio": None,
        "earnings_gap_score": 0.0,
    }
