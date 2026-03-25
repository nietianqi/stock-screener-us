from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_csv(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def build_console_summary(candidates: pd.DataFrame, top_n: int) -> str:
    if candidates.empty:
        return "No candidates passed the filters."
    columns = [
        "symbol",
        "total_score",
        "trend_momentum_score",
        "price_volume_score",
        "catalyst_score",
        "micro_flow_score_group",
        "risk_control_score",
        "trigger_tags",
    ]
    available = [column for column in columns if column in candidates.columns]
    ranked = candidates.sort_values("total_score", ascending=False).head(top_n)
    return ranked[available].to_string(index=False)

