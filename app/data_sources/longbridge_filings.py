from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import AppSettings
from app.utils.dates import unix_to_datetime, utc_now


def _object_snapshot(obj: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if callable(value):
            continue
        snapshot[name] = value
    return snapshot


def _first(snapshot: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in snapshot:
            return snapshot[name]
    return None


class LongbridgeEventClient:
    def __init__(self, settings: AppSettings, quote_context: Any, content_context: Any) -> None:
        self.settings = settings
        self.quote_ctx = quote_context
        self.content_ctx = content_context

    def _retry_call(self, func: Callable[..., Any], *args: Any) -> Any:
        retrying = Retrying(
            stop=stop_after_attempt(self.settings.api_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return func(*args)
        return None

    def fetch_filings(self, symbol: str) -> pd.DataFrame:
        items = self._retry_call(self.quote_ctx.filings, symbol)
        records: list[dict[str, Any]] = []
        for item in items:
            publish_at = unix_to_datetime(getattr(item, "publish_at", None))
            file_urls = getattr(item, "file_urls", None)
            records.append(
                {
                    "symbol": symbol,
                    "filing_id": getattr(item, "id", None),
                    "title": getattr(item, "title", None),
                    "description": getattr(item, "description", None),
                    "file_name": getattr(item, "file_name", None),
                    "file_urls": json.dumps(list(file_urls or []), ensure_ascii=False),
                    "publish_at": publish_at.isoformat() if publish_at else None,
                    "fetched_at": utc_now().isoformat(),
                }
            )
        return pd.DataFrame(records)

    def fetch_news(self, symbol: str) -> pd.DataFrame:
        items = self._retry_call(self.content_ctx.news, symbol)
        records: list[dict[str, Any]] = []
        for item in items:
            snapshot = _object_snapshot(item)
            publish_at = unix_to_datetime(_first(snapshot, "publish_at", "published_at", "create_at", "timestamp"))
            records.append(
                {
                    "symbol": symbol,
                    "news_id": _first(snapshot, "id", "news_id"),
                    "title": _first(snapshot, "title", "name"),
                    "summary": _first(snapshot, "summary", "description", "content"),
                    "url": _first(snapshot, "url", "link"),
                    "publish_at": publish_at.isoformat() if publish_at else None,
                    "raw_payload": json.dumps(snapshot, default=str, ensure_ascii=False),
                }
            )
        return pd.DataFrame(records)

    def fetch_topics(self, symbol: str) -> pd.DataFrame:
        items = self._retry_call(self.content_ctx.topics, symbol)
        records: list[dict[str, Any]] = []
        for item in items:
            snapshot = _object_snapshot(item)
            publish_at = unix_to_datetime(_first(snapshot, "publish_at", "created_at", "timestamp"))
            records.append(
                {
                    "symbol": symbol,
                    "topic_id": _first(snapshot, "id", "topic_id"),
                    "title": _first(snapshot, "title", "name"),
                    "summary": _first(snapshot, "summary", "description", "content"),
                    "publish_at": publish_at.isoformat() if publish_at else None,
                    "raw_payload": json.dumps(snapshot, default=str, ensure_ascii=False),
                }
            )
        return pd.DataFrame(records)
