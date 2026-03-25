from __future__ import annotations

import pandas as pd

from app.config import AppSettings
from app.factors.breakout import compute_breakout_metrics
from app.factors.earnings_gap import compute_earnings_gap_metrics
from app.factors.liquidity import compute_liquidity_metrics
from app.factors.momentum import compute_momentum_metrics
from app.factors.trend import compute_trend_metrics


def build_bars(days: int = 260) -> pd.DataFrame:
    rows = []
    price = 100.0
    for index in range(days):
        price *= 1.002
        rows.append(
            {
                "symbol": "TEST.US",
                "date": f"2025-01-{(index % 28) + 1:02d}",
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": 1_000_000 + index * 1000,
                "turnover": price * (1_000_000 + index * 1000),
            }
        )
    return pd.DataFrame(rows)


def test_trend_and_momentum_metrics() -> None:
    bars = build_bars()
    trend = compute_trend_metrics(bars)
    momentum = compute_momentum_metrics(bars)
    assert trend["ma50"] > trend["ma200"]
    assert trend["trend_score"] > 70
    assert momentum["momentum_12_1"] is not None
    assert momentum["momentum_score"] > 50


def test_breakout_and_liquidity_metrics() -> None:
    bars = build_bars()
    bars.loc[bars.index[-1], "close"] = bars["high"].iloc[-61:-1].max() * 1.02
    breakout = compute_breakout_metrics(bars)
    settings = AppSettings.load()
    liquidity = compute_liquidity_metrics(bars, settings)
    assert breakout["breakout_20d"] is True
    assert liquidity["liquidity_pass"] is True


def test_gap_detection() -> None:
    bars = build_bars(days=40)
    bars.loc[20, "low"] = bars.loc[19, "high"] * 1.08
    bars.loc[20, "close"] = bars.loc[19, "close"] * 1.12
    bars.loc[20:, "low"] = bars.loc[19, "high"] * 1.03
    gap = compute_earnings_gap_metrics(bars)
    assert gap["gap_up_after_earnings"] is True
    assert gap["earnings_gap_score"] > 0
