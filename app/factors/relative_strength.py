from __future__ import annotations

import pandas as pd

from app.utils.mathx import clamp, mean_ignore_none, minmax_score, relative_return


def _close_series(frame: pd.DataFrame) -> pd.Series:
    if frame.empty or "date" not in frame.columns or "close" not in frame.columns:
        return pd.Series(dtype=float)
    return frame.set_index("date")["close"].sort_index()


def compute_relative_strength_metrics(
    bars: pd.DataFrame,
    benchmark_bars: dict[str, pd.DataFrame],
    sector_proxy: str | None,
) -> dict[str, float | None]:
    if bars.empty:
        return {
            "rs_vs_spy": None,
            "rs_vs_qqq": None,
            "rs_vs_sector": None,
            "rs_score": 0.0,
        }
    asset_close = _close_series(bars)
    spy_close = _close_series(benchmark_bars.get("SPY.US", pd.DataFrame()))
    qqq_close = _close_series(benchmark_bars.get("QQQ.US", pd.DataFrame()))
    sector_symbol = sector_proxy or "SPY.US"
    sector_close = _close_series(benchmark_bars.get(sector_symbol, benchmark_bars.get("SPY.US", pd.DataFrame())))

    rs_vs_spy = relative_return(asset_close, spy_close, 60)
    rs_vs_qqq = relative_return(asset_close, qqq_close, 60)
    rs_vs_sector = relative_return(asset_close, sector_close, 60)
    scores = [
        minmax_score(rs_vs_spy, -0.2, 0.2),
        minmax_score(rs_vs_qqq, -0.2, 0.2),
        minmax_score(rs_vs_sector, -0.2, 0.2),
    ]
    rs_score = mean_ignore_none(scores) or 0.0
    return {
        "rs_vs_spy": rs_vs_spy,
        "rs_vs_qqq": rs_vs_qqq,
        "rs_vs_sector": rs_vs_sector,
        "rs_score": clamp(rs_score),
    }
