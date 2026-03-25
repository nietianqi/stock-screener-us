from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd

from app.data_sources.api_budget import ENDPOINT_HISTORY_BARS

if TYPE_CHECKING:
    from app.config import AppSettings
    from app.data_sources.api_budget import ApiBudget
    from app.data_sources.longbridge_quote import LongbridgeQuoteClient
    from app.storage.sqlite_repo import SQLiteRepository

logger = logging.getLogger(__name__)

_DATE_COL = "date"
_SYMBOL_COL = "symbol"
_PERIOD_COL = "period"
_DAY_PERIOD_NAME = "Day"


def _empty_bars_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "period",
            "timestamp_utc",
            "trade_session",
        ]
    )


class BarCacheManager:
    """Read-through cache for `daily_bar` with SQLite persistence."""

    def __init__(
        self,
        settings: "AppSettings",
        sqlite_repo: "SQLiteRepository",
        quote_client: "LongbridgeQuoteClient",
        budget: "ApiBudget",
    ) -> None:
        self.settings = settings
        self.sqlite_repo = sqlite_repo
        self.quote_client = quote_client
        self.budget = budget
        self._hits = 0
        self._misses = 0
        self._partial_hits = 0

    def get_bars(
        self,
        symbol: str,
        needed_bars: int | None = None,
        as_of: date | None = None,
    ) -> pd.DataFrame:
        needed = needed_bars or self.settings.lookback_bars
        until = as_of or date.today()
        since = until - timedelta(days=int(needed * 1.8))

        cached = self._read_cache(symbol, since, until)
        if len(cached) >= needed:
            self._hits += 1
            return cached.tail(needed).reset_index(drop=True)

        if len(cached) > 0:
            self._partial_hits += 1
        else:
            self._misses += 1

        if not self.budget.consume(ENDPOINT_HISTORY_BARS, symbol):
            return cached.tail(needed).reset_index(drop=True)

        try:
            fresh = self.quote_client.fetch_history_bars(symbol, count=needed)
        except Exception as exc:
            logger.warning("[bar_cache] failed to fetch %s history bars: %s", symbol, exc)
            return cached.tail(needed).reset_index(drop=True)

        if fresh.empty:
            return cached.tail(needed).reset_index(drop=True)

        self._write_cache(fresh)
        combined = self._merge_frames(cached, fresh)
        return combined.tail(needed).reset_index(drop=True)

    def get_bars_bulk(
        self,
        symbols: list[str],
        needed_bars: int | None = None,
        as_of: date | None = None,
    ) -> dict[str, pd.DataFrame]:
        if not symbols:
            return {}

        needed = needed_bars or self.settings.lookback_bars
        until = as_of or date.today()
        since = until - timedelta(days=int(needed * 1.8))
        cache_map = self._read_cache_bulk(symbols, since, until)

        result: dict[str, pd.DataFrame] = {}
        fetch_symbols: list[str] = []
        for symbol in symbols:
            cached = cache_map.get(symbol, _empty_bars_frame())
            if len(cached) >= needed:
                self._hits += 1
                result[symbol] = cached.tail(needed).reset_index(drop=True)
            else:
                fetch_symbols.append(symbol)
                if len(cached) > 0:
                    self._partial_hits += 1
                else:
                    self._misses += 1
                result[symbol] = cached

        allowed: list[str] = []
        for symbol in fetch_symbols:
            if self.budget.consume(ENDPOINT_HISTORY_BARS, symbol):
                allowed.append(symbol)

        blocked = [symbol for symbol in fetch_symbols if symbol not in allowed]
        if blocked:
            logger.warning(
                "[bar_cache] history_bars budget blocked %d symbols; returning cache-only data.",
                len(blocked),
            )

        if allowed:
            concurrency = max(1, int(getattr(self.settings, "auto_universe_bar_concurrency", 8)))
            fresh_map = self.quote_client.fetch_history_bars_concurrent(
                allowed,
                count=needed,
                concurrency=concurrency,
            )
            for symbol in allowed:
                fresh = fresh_map.get(symbol, _empty_bars_frame())
                if fresh.empty:
                    result[symbol] = result[symbol].tail(needed).reset_index(drop=True)
                    continue
                self._write_cache(fresh)
                result[symbol] = self._merge_frames(result[symbol], fresh).tail(needed).reset_index(drop=True)

        for symbol in symbols:
            result.setdefault(symbol, _empty_bars_frame())
            result[symbol] = result[symbol].tail(needed).reset_index(drop=True)
        return result

    def log_stats(self) -> None:
        total = self._hits + self._partial_hits + self._misses
        hit_rate = (self._hits / total * 100.0) if total else 0.0
        logger.info(
            "[bar_cache] total=%d hit=%d partial=%d miss=%d hit_rate=%.1f%%",
            total,
            self._hits,
            self._partial_hits,
            self._misses,
            hit_rate,
        )

    def reset_stats(self) -> None:
        self._hits = 0
        self._partial_hits = 0
        self._misses = 0

    def _read_cache(self, symbol: str, since: date, until: date) -> pd.DataFrame:
        try:
            return self._normalize_frame(self.sqlite_repo.query_bars(symbol, since, until))
        except Exception as exc:
            logger.debug("[bar_cache] cache read failed for %s: %s", symbol, exc)
            return _empty_bars_frame()

    def _read_cache_bulk(self, symbols: list[str], since: date, until: date) -> dict[str, pd.DataFrame]:
        try:
            frame = self.sqlite_repo.query_bars_bulk(symbols, since, until)
        except Exception as exc:
            logger.debug("[bar_cache] bulk cache read failed: %s", exc)
            return {}
        if frame.empty:
            return {}
        frame = self._normalize_frame(frame)
        return {symbol: group.reset_index(drop=True) for symbol, group in frame.groupby(_SYMBOL_COL)}

    def _write_cache(self, bars: pd.DataFrame) -> None:
        if bars.empty:
            return
        frame = self._normalize_frame(bars)
        try:
            self.sqlite_repo.upsert_dataframe(
                "daily_bar",
                frame,
                [_SYMBOL_COL, _DATE_COL, _PERIOD_COL],
            )
        except Exception as exc:
            logger.warning("[bar_cache] cache write failed: %s", exc)

    def _normalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return _empty_bars_frame()
        normalized = frame.copy()
        if _PERIOD_COL not in normalized.columns:
            normalized[_PERIOD_COL] = _DAY_PERIOD_NAME
        for column in ("open", "high", "low", "close", "turnover"):
            if column in normalized.columns:
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        if "volume" in normalized.columns:
            normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce")
        normalized[_DATE_COL] = pd.to_datetime(normalized[_DATE_COL], errors="coerce").dt.date.astype(str)
        return normalized.drop_duplicates(
            subset=[_SYMBOL_COL, _DATE_COL, _PERIOD_COL],
            keep="last",
        ).sort_values(_DATE_COL).reset_index(drop=True)

    @staticmethod
    def _merge_frames(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
        if left.empty:
            merged = right.copy()
        elif right.empty:
            merged = left.copy()
        else:
            merged = pd.concat([left, right], ignore_index=True)
        if merged.empty:
            return _empty_bars_frame()
        if _PERIOD_COL not in merged.columns:
            merged[_PERIOD_COL] = _DAY_PERIOD_NAME
        for column in ("open", "high", "low", "close", "turnover"):
            if column in merged.columns:
                merged[column] = pd.to_numeric(merged[column], errors="coerce")
        if "volume" in merged.columns:
            merged["volume"] = pd.to_numeric(merged["volume"], errors="coerce")
        merged[_DATE_COL] = pd.to_datetime(merged[_DATE_COL], errors="coerce").dt.date.astype(str)
        return (
            merged.drop_duplicates(subset=[_SYMBOL_COL, _DATE_COL, _PERIOD_COL], keep="last")
            .sort_values(_DATE_COL)
            .reset_index(drop=True)
        )
