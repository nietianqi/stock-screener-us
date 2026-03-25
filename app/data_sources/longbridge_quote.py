from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

import pandas as pd
from longbridge.openapi import AdjustType, Market, Period, SecurityListCategory
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import AppSettings
from app.utils.dates import ensure_utc, utc_now
from app.utils.mathx import safe_float


def _type_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, type):
        return value.__name__
    return type(value).__name__


class LongbridgeQuoteClient:
    def __init__(self, settings: AppSettings, quote_context: Any) -> None:
        self.settings = settings
        self.ctx = quote_context

    def _retry_call(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        retrying = Retrying(
            stop=stop_after_attempt(self.settings.api_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return func(*args, **kwargs)
        return None

    def _chunk(self, symbols: Sequence[str]) -> Iterable[list[str]]:
        chunk_size = max(1, min(500, self.settings.request_batch_size))
        for index in range(0, len(symbols), chunk_size):
            yield list(symbols[index:index + chunk_size])

    def fetch_static_info(self, symbols: Sequence[str]) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for batch in self._chunk(list(symbols)):
            items = self._retry_call(self.ctx.static_info, batch)
            for item in items:
                symbol = getattr(item, "symbol", None)
                records.append(
                    {
                        "symbol": symbol,
                        "name_en": getattr(item, "name_en", None),
                        "exchange": getattr(item, "exchange", None),
                        "currency": getattr(item, "currency", None),
                        "lot_size": getattr(item, "lot_size", None),
                        "market": symbol.split(".")[-1] if symbol else None,
                        "board": _type_name(getattr(item, "board", None)),
                        "industry_etf_proxy": self.settings.sector_proxy_by_symbol.get(
                            symbol or "", None
                        ),
                        "updated_at": utc_now().isoformat(),
                    }
                )
        return pd.DataFrame(records)

    def fetch_security_list(
        self,
        market: type = Market.US,
        category: type | None = None,
    ) -> pd.DataFrame:
        if category is None:
            items = self._retry_call(self.ctx.security_list, market)
        else:
            items = self._retry_call(self.ctx.security_list, market, category)
        records: list[dict[str, Any]] = []
        for item in items:
            symbol = getattr(item, "symbol", None)
            records.append(
                {
                    "symbol": symbol,
                    "name_en": getattr(item, "name_en", None),
                    "name_cn": getattr(item, "name_cn", None),
                    "name_hk": getattr(item, "name_hk", None),
                    "market": symbol.split(".")[-1] if symbol else None,
                    "category": "overnight" if category is SecurityListCategory.Overnight else None,
                }
            )
        return pd.DataFrame(records)

    def fetch_latest_quotes(self, symbols: Sequence[str]) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for batch in self._chunk(list(symbols)):
            items = self._retry_call(self.ctx.quote, batch)
            for item in items:
                timestamp = ensure_utc(getattr(item, "timestamp", None))
                records.append(
                    {
                        "symbol": getattr(item, "symbol", None),
                        "last_done": safe_float(getattr(item, "last_done", None)),
                        "prev_close": safe_float(getattr(item, "prev_close", None)),
                        "open": safe_float(getattr(item, "open", None)),
                        "high": safe_float(getattr(item, "high", None)),
                        "low": safe_float(getattr(item, "low", None)),
                        "volume": getattr(item, "volume", None),
                        "turnover": safe_float(getattr(item, "turnover", None)),
                        "trade_status": _type_name(getattr(item, "trade_status", None)),
                        "timestamp_utc": timestamp.isoformat() if timestamp else None,
                    }
                )
        return pd.DataFrame(records)

    def fetch_history_bars(
        self,
        symbol: str,
        period: type = Period.Day,
        count: int | None = None,
        anchor_time: datetime | None = None,
    ) -> pd.DataFrame:
        bar_count = min(count or self.settings.lookback_bars, 1000)
        _anchor = anchor_time or utc_now()
        items = self._retry_call(
            self.ctx.history_candlesticks_by_offset,
            symbol,
            period,
            AdjustType.ForwardAdjust,
            False,
            bar_count,
            _anchor,
        )
        records: list[dict[str, Any]] = []
        for item in items:
            timestamp = ensure_utc(getattr(item, "timestamp", None))
            date_value = timestamp.date().isoformat() if timestamp else None
            records.append(
                {
                    "symbol": symbol,
                    "date": date_value,
                    "open": safe_float(getattr(item, "open", None)),
                    "high": safe_float(getattr(item, "high", None)),
                    "low": safe_float(getattr(item, "low", None)),
                    "close": safe_float(getattr(item, "close", None)),
                    "volume": getattr(item, "volume", None),
                    "turnover": safe_float(getattr(item, "turnover", None)),
                    "period": _type_name(period),
                    "timestamp_utc": timestamp.isoformat() if timestamp else None,
                    "trade_session": _type_name(getattr(item, "trade_session", None)),
                }
            )
        return pd.DataFrame(records).sort_values("date").reset_index(drop=True)

    def fetch_intraday(self, symbol: str) -> pd.DataFrame:
        items = self._retry_call(self.ctx.intraday, symbol)
        records: list[dict[str, Any]] = []
        for item in items:
            timestamp = ensure_utc(getattr(item, "timestamp", None))
            records.append(
                {
                    "symbol": symbol,
                    "timestamp_utc": timestamp.isoformat() if timestamp else None,
                    "price": safe_float(getattr(item, "price", None)),
                    "avg_price": safe_float(getattr(item, "avg_price", None)),
                    "volume": getattr(item, "volume", None),
                    "turnover": safe_float(getattr(item, "turnover", None)),
                }
            )
        return pd.DataFrame(records)

    def fetch_trades(self, symbol: str, count: int = 200) -> pd.DataFrame:
        items = self._retry_call(self.ctx.trades, symbol, count)
        records: list[dict[str, Any]] = []
        for item in items:
            timestamp = ensure_utc(getattr(item, "timestamp", None))
            records.append(
                {
                    "symbol": symbol,
                    "timestamp_utc": timestamp.isoformat() if timestamp else None,
                    "price": safe_float(getattr(item, "price", None)),
                    "volume": getattr(item, "volume", None),
                    "trade_type": getattr(item, "trade_type", None),
                    "direction": getattr(getattr(item, "direction", None), "name", None) or str(getattr(item, "direction", None)),
                    "trade_session": _type_name(getattr(item, "trade_session", None)),
                }
            )
        return pd.DataFrame(records)

    def fetch_depth(self, symbol: str) -> pd.DataFrame:
        depth = self._retry_call(self.ctx.depth, symbol)
        records: list[dict[str, Any]] = []
        for side_name in ("asks", "bids"):
            for item in getattr(depth, side_name, []) or []:
                records.append(
                    {
                        "symbol": symbol,
                        "side": side_name[:-1],
                        "position": getattr(item, "position", None),
                        "price": safe_float(getattr(item, "price", None)),
                        "volume": getattr(item, "volume", None),
                        "order_num": getattr(item, "order_num", None),
                    }
                )
        return pd.DataFrame(records)

    def fetch_capital_flow(self, symbol: str) -> pd.DataFrame:
        items = self._retry_call(self.ctx.capital_flow, symbol)
        records: list[dict[str, Any]] = []
        for item in items:
            timestamp = ensure_utc(getattr(item, "timestamp", None))
            records.append(
                {
                    "symbol": symbol,
                    "timestamp_utc": timestamp.isoformat() if timestamp else None,
                    "inflow": safe_float(getattr(item, "inflow", None)),
                }
            )
        return pd.DataFrame(records)

    def fetch_capital_distribution(self, symbol: str) -> pd.DataFrame:
        item = self._retry_call(self.ctx.capital_distribution, symbol)
        timestamp = ensure_utc(getattr(item, "timestamp", None))
        capital_in = getattr(item, "capital_in", None)
        capital_out = getattr(item, "capital_out", None)
        return pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "timestamp_utc": timestamp.isoformat() if timestamp else None,
                    "capital_in_large": safe_float(getattr(capital_in, "large", None)),
                    "capital_in_medium": safe_float(getattr(capital_in, "medium", None)),
                    "capital_in_small": safe_float(getattr(capital_in, "small", None)),
                    "capital_out_large": safe_float(getattr(capital_out, "large", None)),
                    "capital_out_medium": safe_float(getattr(capital_out, "medium", None)),
                    "capital_out_small": safe_float(getattr(capital_out, "small", None)),
                }
            ]
        )
