from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import AppSettings
from app.data_sources.longbridge_quote import LongbridgeQuoteClient


def build_settings() -> AppSettings:
    return AppSettings(project_root=Path.cwd(), longbridge_client_id=None, api_max_retries=1)


def test_fetch_history_bars_concurrent_handles_errors(monkeypatch) -> None:
    client = LongbridgeQuoteClient(build_settings(), quote_context=object())

    def fake_fetch(symbol: str, period=None, count: int | None = None, anchor_time=None) -> pd.DataFrame:
        if symbol == "BAD.US":
            raise RuntimeError("boom")
        return pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "date": "2026-03-20",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1_000_000,
                    "turnover": 100_000_000.0,
                    "period": "Day",
                    "timestamp_utc": None,
                    "trade_session": None,
                }
            ]
        )

    monkeypatch.setattr(client, "fetch_history_bars", fake_fetch)
    result = client.fetch_history_bars_concurrent(["AAPL.US", "BAD.US"], concurrency=4)

    assert len(result["AAPL.US"]) == 1
    assert result["BAD.US"].empty


def test_fetch_history_bars_falls_back_to_lower_count() -> None:
    class FakeCandle:
        def __init__(self) -> None:
            self.timestamp = datetime(2026, 3, 20, tzinfo=timezone.utc)
            self.open = 100.0
            self.high = 101.0
            self.low = 99.0
            self.close = 100.0
            self.volume = 1_000_000
            self.turnover = 100_000_000
            self.trade_session = None

    class FakeContext:
        @staticmethod
        def history_candlesticks_by_offset(
            symbol,
            period,
            adjust_type,
            forward,
            count,
            anchor,
        ):
            if count > 250:
                raise RuntimeError("301607 history kline symbol count out of limit")
            return [FakeCandle()]

    client = LongbridgeQuoteClient(build_settings(), quote_context=FakeContext())
    frame = client.fetch_history_bars("AAPL.US", count=320)
    assert len(frame) == 1
    assert frame.iloc[0]["symbol"] == "AAPL.US"


def test_fetch_history_bars_returns_empty_for_unavailable_symbol() -> None:
    class FakeContext:
        calls = 0

        @classmethod
        def history_candlesticks_by_offset(
            cls,
            symbol,
            period,
            adjust_type,
            forward,
            count,
            anchor,
        ):
            cls.calls += 1
            raise RuntimeError("301607 history kline symbol count out of limit")

    client = LongbridgeQuoteClient(build_settings(), quote_context=FakeContext())
    first = client.fetch_history_bars("NOHIST.US", count=320)
    second = client.fetch_history_bars("NOHIST.US", count=320)
    assert first.empty
    assert second.empty
    assert FakeContext.calls == 2  # first symbol call tries 320 and fallback 250; second call skips entirely
