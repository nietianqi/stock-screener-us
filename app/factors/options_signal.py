from __future__ import annotations

from app.utils.mathx import clamp


def compute_option_activity_metrics(option_snapshot: dict[str, float | int | None]) -> dict[str, float | int | None]:
    if not option_snapshot:
        return {
            "option_contract_count": 0,
            "call_put_volume_ratio": None,
            "call_put_oi_ratio": None,
            "avg_implied_volatility": None,
            "option_activity_score": 0.0,
        }
    score = option_snapshot.get("option_activity_score")
    if score is None:
        score = 0.0
    return {
        "option_contract_count": option_snapshot.get("option_contract_count"),
        "call_put_volume_ratio": option_snapshot.get("call_put_volume_ratio"),
        "call_put_oi_ratio": option_snapshot.get("call_put_oi_ratio"),
        "avg_implied_volatility": option_snapshot.get("avg_implied_volatility"),
        "option_activity_score": clamp(float(score)),
    }

