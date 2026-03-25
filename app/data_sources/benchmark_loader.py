from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from app.data_sources.longbridge_quote import LongbridgeQuoteClient


def load_benchmark_history(
    quote_client: LongbridgeQuoteClient,
    symbols: Sequence[str],
    lookback_bars: int,
) -> dict[str, pd.DataFrame]:
    benchmark_history: dict[str, pd.DataFrame] = {}
    for symbol in dict.fromkeys(symbols):
        benchmark_history[symbol] = quote_client.fetch_history_bars(symbol, count=lookback_bars)
    return benchmark_history
