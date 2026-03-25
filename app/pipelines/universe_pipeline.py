from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.config import AppSettings

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9\.-]+\.[A-Z]+$")


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for symbol in symbols:
        normalized = symbol.strip().upper()
        if not normalized:
            continue
        if not SYMBOL_PATTERN.match(normalized):
            raise ValueError(f"Invalid Longbridge symbol format: {symbol}")
        cleaned.append(normalized)
    return cleaned


def load_universe(
    settings: AppSettings,
    symbols: list[str] | None = None,
    universe_file: str | None = None,
) -> pd.DataFrame:
    if symbols:
        frame = pd.DataFrame({"symbol": _normalize_symbols(symbols)})
    else:
        file_path = Path(universe_file).resolve() if universe_file else settings.universe_file
        if file_path.exists():
            frame = pd.read_csv(file_path)
        else:
            frame = pd.DataFrame({"symbol": list(settings.scan_universe)})

    if "symbol" not in frame.columns:
        raise ValueError("Universe file must include a 'symbol' column.")
    frame["symbol"] = _normalize_symbols(frame["symbol"].astype(str).tolist())
    if "industry_etf_proxy" not in frame.columns:
        frame["industry_etf_proxy"] = frame["symbol"].map(settings.sector_proxy_by_symbol)
    frame["industry_etf_proxy"] = frame["industry_etf_proxy"].fillna(frame["symbol"].map(settings.sector_proxy_by_symbol))
    frame["industry_etf_proxy"] = frame["industry_etf_proxy"].fillna("SPY.US")
    return frame.drop_duplicates(subset=["symbol"]).reset_index(drop=True)
