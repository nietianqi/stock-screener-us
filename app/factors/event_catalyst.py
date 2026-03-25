from __future__ import annotations

from datetime import date

import pandas as pd

from app.utils.mathx import clamp

FILING_KEYWORDS = {
    "8-k": 15,
    "10-q": 10,
    "10-k": 12,
    "13d": 14,
    "13g": 12,
    "buyback": 18,
    "repurchase": 18,
    "guidance": 16,
    "earnings": 14,
    "merger": 22,
    "acquisition": 20,
}


def _prepare_dates(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series(dtype="datetime64[ns, UTC]")
    return pd.to_datetime(frame[column], utc=True, errors="coerce")


def compute_event_catalyst_metrics(
    filings: pd.DataFrame,
    news: pd.DataFrame,
    topics: pd.DataFrame,
    option_snapshot: dict[str, float | int | None],
    scan_date: date,
) -> dict[str, float | int | None]:
    scan_ts = pd.Timestamp(scan_date, tz="UTC")
    filings = filings.copy()
    filings["publish_ts"] = _prepare_dates(filings, "publish_at")
    recent_filings = filings[filings["publish_ts"] >= scan_ts - pd.Timedelta(days=30)]
    filings_score = 0.0
    for _, row in recent_filings.iterrows():
        title = f"{row.get('title', '')} {row.get('description', '')}".lower()
        filings_score += 8
        for keyword, weight in FILING_KEYWORDS.items():
            if keyword in title:
                filings_score += weight
    filings_score = clamp(filings_score)

    news = news.copy()
    news["publish_ts"] = _prepare_dates(news, "publish_at")
    recent_news = news[news["publish_ts"] >= scan_ts - pd.Timedelta(days=14)]
    topics = topics.copy()
    topics["publish_ts"] = _prepare_dates(topics, "publish_at")
    recent_topics = topics[topics["publish_ts"] >= scan_ts - pd.Timedelta(days=14)]
    news_topic_score = clamp(len(recent_news) * 10 + len(recent_topics) * 8)

    option_activity_score = option_snapshot.get("option_activity_score")
    option_activity_score = float(option_activity_score) if option_activity_score is not None else 0.0
    event_score = clamp(filings_score * 0.45 + news_topic_score * 0.35 + option_activity_score * 0.20)
    return {
        "recent_filings_count_30d": int(len(recent_filings)),
        "recent_news_count_14d": int(len(recent_news)),
        "recent_topics_count_14d": int(len(recent_topics)),
        "filings_event_score": filings_score,
        "news_topic_score": news_topic_score,
        "event_score": event_score,
    }

