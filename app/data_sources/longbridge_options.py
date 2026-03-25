from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import AppSettings
from app.utils.mathx import clamp, safe_float


class LongbridgeOptionsClient:
    def __init__(self, settings: AppSettings, quote_context: Any) -> None:
        self.settings = settings
        self.ctx = quote_context

    def _retry_call(self, func: Any, *args: Any) -> Any:
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

    def fetch_option_expiry_dates(self, symbol: str) -> list[Any]:
        return list(self._retry_call(self.ctx.option_chain_expiry_date_list, symbol) or [])

    def fetch_option_chain(self, symbol: str, expiry_date: Any) -> pd.DataFrame:
        items = self._retry_call(self.ctx.option_chain_info_by_date, symbol, expiry_date)
        records: list[dict[str, Any]] = []
        for item in items:
            records.append(
                {
                    "symbol": symbol,
                    "expiry_date": str(expiry_date),
                    "strike_price": safe_float(getattr(item, "price", None)),
                    "call_symbol": getattr(item, "call_symbol", None),
                    "put_symbol": getattr(item, "put_symbol", None),
                    "standard": bool(getattr(item, "standard", False)),
                }
            )
        return pd.DataFrame(records)

    def fetch_option_quotes(self, option_symbols: Sequence[str]) -> pd.DataFrame:
        if not option_symbols:
            return pd.DataFrame()
        items = self._retry_call(self.ctx.option_quote, list(option_symbols))
        records: list[dict[str, Any]] = []
        for item in items:
            direction = getattr(item, "direction", None)
            direction_name = direction.__name__ if isinstance(direction, type) else type(direction).__name__
            records.append(
                {
                    "symbol": getattr(item, "symbol", None),
                    "underlying_symbol": getattr(item, "underlying_symbol", None),
                    "direction": direction_name.lower(),
                    "last_done": safe_float(getattr(item, "last_done", None)),
                    "volume": getattr(item, "volume", None),
                    "turnover": safe_float(getattr(item, "turnover", None)),
                    "open_interest": getattr(item, "open_interest", None),
                    "implied_volatility": safe_float(getattr(item, "implied_volatility", None)),
                    "historical_volatility": safe_float(getattr(item, "historical_volatility", None)),
                    "strike_price": safe_float(getattr(item, "strike_price", None)),
                    "expiry_date": str(getattr(item, "expiry_date", None)),
                }
            )
        return pd.DataFrame(records)

    def build_activity_snapshot(self, symbol: str, underlying_price: float | None) -> dict[str, float | int | None]:
        empty_snapshot = {
            "option_contract_count": 0,
            "call_volume": None,
            "put_volume": None,
            "call_open_interest": None,
            "put_open_interest": None,
            "call_put_volume_ratio": None,
            "call_put_oi_ratio": None,
            "avg_implied_volatility": None,
            "option_activity_score": None,
            "nearest_option_expiry_days": None,
        }
        expiry_dates = self.fetch_option_expiry_dates(symbol)[:2]
        if not expiry_dates:
            return empty_snapshot

        chain_frames = [self.fetch_option_chain(symbol, expiry) for expiry in expiry_dates]
        chain = pd.concat(chain_frames, ignore_index=True) if chain_frames else pd.DataFrame()
        if chain.empty:
            return empty_snapshot

        if underlying_price:
            chain["distance"] = (chain["strike_price"] - underlying_price).abs() / max(underlying_price, 0.01)
            selected = chain.sort_values("distance").head(6)
        else:
            selected = chain.head(6)

        option_symbols = pd.concat(
            [
                selected["call_symbol"].dropna(),
                selected["put_symbol"].dropna(),
            ]
        ).drop_duplicates().tolist()[:12]
        quotes = self.fetch_option_quotes(option_symbols)
        if quotes.empty:
            return empty_snapshot

        calls = quotes[quotes["direction"].str.contains("call", na=False)]
        puts = quotes[quotes["direction"].str.contains("put", na=False)]
        call_volume = float(calls["volume"].fillna(0).sum())
        put_volume = float(puts["volume"].fillna(0).sum())
        call_oi = float(calls["open_interest"].fillna(0).sum())
        put_oi = float(puts["open_interest"].fillna(0).sum())
        call_put_volume_ratio = (call_volume / put_volume) if put_volume else None
        call_put_oi_ratio = (call_oi / put_oi) if put_oi else None
        avg_iv = float(quotes["implied_volatility"].dropna().mean()) if quotes["implied_volatility"].notna().any() else None
        ratio_score = 0.0
        if call_put_volume_ratio is not None:
            ratio_score += clamp((call_put_volume_ratio - 0.8) / 1.7 * 50)
        if call_put_oi_ratio is not None:
            ratio_score += clamp((call_put_oi_ratio - 0.8) / 1.7 * 35)
        if avg_iv is not None:
            ratio_score += clamp((avg_iv - 0.2) / 0.6 * 15)
        return {
            "option_contract_count": int(len(quotes)),
            "call_volume": call_volume,
            "put_volume": put_volume,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "call_put_volume_ratio": call_put_volume_ratio,
            "call_put_oi_ratio": call_put_oi_ratio,
            "avg_implied_volatility": avg_iv,
            "option_activity_score": clamp(ratio_score),
            "nearest_option_expiry_days": None,
        }

