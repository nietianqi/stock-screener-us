from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def safe_float(value: object, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def mean_ignore_none(values: Iterable[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return float(sum(cleaned) / len(cleaned))


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def minmax_score(value: float | None, floor: float, ceiling: float) -> float | None:
    if value is None:
        return None
    if math.isclose(floor, ceiling):
        return 100.0
    return clamp((value - floor) / (ceiling - floor) * 100.0)


def annualized_volatility(close_series: pd.Series, window: int = 20) -> float | None:
    closes = close_series.dropna()
    if len(closes) < window + 1:
        return None
    returns = np.log(closes / closes.shift(1)).dropna().tail(window)
    if returns.empty:
        return None
    return float(returns.std(ddof=0) * math.sqrt(252))


def relative_return(asset_close: pd.Series, benchmark_close: pd.Series, window: int) -> float | None:
    joined = pd.concat(
        [asset_close.rename("asset"), benchmark_close.rename("benchmark")],
        axis=1,
    ).dropna()
    if len(joined) < window + 1:
        return None
    window_df = joined.tail(window + 1)
    asset_ret = window_df["asset"].iloc[-1] / window_df["asset"].iloc[0] - 1
    bench_ret = window_df["benchmark"].iloc[-1] / window_df["benchmark"].iloc[0] - 1
    return float(asset_ret - bench_ret)
