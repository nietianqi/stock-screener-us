from __future__ import annotations

from datetime import date

from app.config import AppSettings
from app.scoring.engine import ScoreEngine


def test_score_engine_builds_total_and_tags() -> None:
    settings = AppSettings.load()
    engine = ScoreEngine(settings)
    metrics = {
        "last_close": 120.0,
        "avg_daily_value_20d": 25_000_000.0,
        "history_bars": 300,
        "trend_score": 90.0,
        "momentum_score": 80.0,
        "rs_score": 75.0,
        "breakout_score": 70.0,
        "price_volume_health_score": 68.0,
        "earnings_gap_score": 66.0,
        "accumulation_score": 72.0,
        "filings_event_score": 70.0,
        "news_topic_score": 55.0,
        "option_activity_score": 65.0,
        "event_score": 64.0,
        "capital_flow_score": 60.0,
        "depth_bias_score": 58.0,
        "trade_aggression_score": 62.0,
        "micro_flow_score": 60.0,
        "risk_score": 85.0,
        "breakout_20d": True,
        "breakout_60d": False,
        "breakout_20d_level": 100.0,
        "distribution_days_10d": 1,
        "recent_filings_count_30d": 3,
        "option_contract_count": 8,
    }
    card = engine.score("AAPL.US", date(2026, 3, 25), "XLK.US", metrics)
    assert card.total_score > 60
    assert "trend_stack" in card.trigger_tags
    assert not card.veto_reasons
