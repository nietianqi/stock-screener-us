from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.config import AppSettings
from app.data_sources.api_budget import ApiBudget
from app.data_sources.bar_cache import BarCacheManager


class FakeSQLiteRepo:
    def __init__(self) -> None:
        self.storage = pd.DataFrame()
        self.last_upsert_keys: list[str] | None = None

    def upsert_dataframe(self, table_name: str, frame: pd.DataFrame, key_columns: list[str]) -> None:
        assert table_name == "daily_bar"
        self.last_upsert_keys = key_columns
        if self.storage.empty:
            self.storage = frame.copy()
            return
        merged = pd.concat([self.storage, frame], ignore_index=True)
        self.storage = merged.drop_duplicates(subset=key_columns, keep="last").reset_index(drop=True)

    def query_bars(self, symbol: str, since: date, until: date, period: str = "Day") -> pd.DataFrame:
        if self.storage.empty:
            return pd.DataFrame()
        mask = (
            (self.storage["symbol"] == symbol)
            & (self.storage["period"] == period)
            & (self.storage["date"] >= since.isoformat())
            & (self.storage["date"] <= until.isoformat())
        )
        return self.storage.loc[mask].sort_values("date").reset_index(drop=True)

    def query_bars_bulk(self, symbols: list[str], since: date, until: date, period: str = "Day") -> pd.DataFrame:
        if self.storage.empty:
            return pd.DataFrame()
        mask = (
            self.storage["symbol"].isin(symbols)
            & (self.storage["period"] == period)
            & (self.storage["date"] >= since.isoformat())
            & (self.storage["date"] <= until.isoformat())
        )
        return self.storage.loc[mask].sort_values(["symbol", "date"]).reset_index(drop=True)


class FakeQuoteClient:
    def __init__(self) -> None:
        self.bulk_calls = 0

    def fetch_history_bars(self, symbol: str, count: int | None = None) -> pd.DataFrame:
        return self._build(symbol, count or 5)

    def fetch_history_bars_concurrent(
        self,
        symbols: list[str],
        period=None,
        count: int | None = None,
        concurrency: int = 8,
    ) -> dict[str, pd.DataFrame]:
        self.bulk_calls += 1
        return {symbol: self._build(symbol, count or 5) for symbol in symbols}

    @staticmethod
    def _build(symbol: str, count: int) -> pd.DataFrame:
        today = date.today()
        rows = []
        for offset in range(count):
            bar_date = today - timedelta(days=count - offset)
            rows.append(
                {
                    "symbol": symbol,
                    "date": bar_date.isoformat(),
                    "open": 100 + offset,
                    "high": 101 + offset,
                    "low": 99 + offset,
                    "close": 100 + offset,
                    "volume": 1_000_000 + offset,
                    "turnover": 100_000_000 + offset,
                    "period": "Day",
                    "timestamp_utc": None,
                    "trade_session": None,
                }
            )
        return pd.DataFrame(rows)


def build_settings() -> AppSettings:
    return AppSettings(
        project_root=Path.cwd(),
        longbridge_client_id=None,
        lookback_bars=5,
        auto_universe_bar_concurrency=4,
    )


def test_bar_cache_bulk_uses_cache_after_first_fetch() -> None:
    settings = build_settings()
    repo = FakeSQLiteRepo()
    quote = FakeQuoteClient()
    budget = ApiBudget(settings)
    manager = BarCacheManager(settings, repo, quote, budget)

    symbols = ["AAA.US", "BBB.US"]
    first = manager.get_bars_bulk(symbols, needed_bars=5, as_of=date.today())
    assert quote.bulk_calls == 1
    assert repo.last_upsert_keys == ["symbol", "date", "period"]
    assert all(len(first[symbol]) == 5 for symbol in symbols)

    second = manager.get_bars_bulk(symbols, needed_bars=5, as_of=date.today())
    assert quote.bulk_calls == 1
    assert all(len(second[symbol]) == 5 for symbol in symbols)
