from __future__ import annotations

import pandas as pd

from app.utils.mathx import clamp


def compute_micro_flow_metrics(
    trades: pd.DataFrame,
    depth: pd.DataFrame,
    capital_flow: pd.DataFrame,
    capital_distribution: pd.DataFrame,
) -> dict[str, float | None]:
    capital_flow_score = 0.0
    net_inflow = None
    if not capital_flow.empty:
        net_inflow = float(capital_flow["inflow"].dropna().iloc[-1])
        capital_flow_score = clamp(50 + (net_inflow / max(abs(net_inflow), 1.0)) * 30)

    depth_bias_score = 0.0
    depth_bias = None
    if not depth.empty:
        frame = depth.copy()
        frame["notional"] = frame["price"].fillna(0) * frame["volume"].fillna(0)
        bid_value = float(frame.loc[frame["side"] == "bid", "notional"].sum())
        ask_value = float(frame.loc[frame["side"] == "ask", "notional"].sum())
        if bid_value or ask_value:
            depth_bias = (bid_value - ask_value) / max(bid_value + ask_value, 1.0)
            depth_bias_score = clamp(50 + depth_bias * 50)

    trade_aggression_score = 0.0
    trade_aggression = None
    if not trades.empty:
        up_volume = float(trades.loc[trades["direction"].str.contains("Up", na=False), "volume"].sum())
        down_volume = float(trades.loc[trades["direction"].str.contains("Down", na=False), "volume"].sum())
        if up_volume or down_volume:
            trade_aggression = (up_volume - down_volume) / max(up_volume + down_volume, 1.0)
            trade_aggression_score = clamp(50 + trade_aggression * 50)

    if not capital_distribution.empty:
        row = capital_distribution.iloc[-1]
        capital_in = float(
            (row.get("capital_in_large") or 0)
            + (row.get("capital_in_medium") or 0)
            + (row.get("capital_in_small") or 0)
        )
        capital_out = float(
            (row.get("capital_out_large") or 0)
            + (row.get("capital_out_medium") or 0)
            + (row.get("capital_out_small") or 0)
        )
        if capital_in or capital_out:
            distribution_bias = (capital_in - capital_out) / max(capital_in + capital_out, 1.0)
            capital_flow_score = clamp(max(capital_flow_score, 50 + distribution_bias * 50))

    micro_flow_score = clamp((capital_flow_score + depth_bias_score + trade_aggression_score) / 3)
    return {
        "net_capital_inflow": net_inflow,
        "capital_flow_score": capital_flow_score,
        "depth_bias": depth_bias,
        "depth_bias_score": depth_bias_score,
        "trade_aggression": trade_aggression,
        "trade_aggression_score": trade_aggression_score,
        "micro_flow_score": micro_flow_score,
    }

