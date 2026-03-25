from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from app.config import AppSettings
from app.data_sources.universe_cache import UniverseCache


def build_settings(tmp_path: Path, ttl_minutes: int = 60) -> AppSettings:
    return AppSettings(
        project_root=tmp_path,
        longbridge_client_id=None,
        universe_cache_ttl_minutes=ttl_minutes,
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "outputs",
        log_dir=tmp_path / "logs",
        database_path=tmp_path / "data" / "test.db",
        parquet_dir=tmp_path / "data" / "parquet",
        universe_file=tmp_path / "data" / "universe.csv",
    )


def test_universe_cache_save_and_load(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, ttl_minutes=60)
    cache = UniverseCache(settings)
    frame = pd.DataFrame(
        {
            "symbol": ["AAPL.US", "MSFT.US"],
            "industry_etf_proxy": ["XLK.US", "XLK.US"],
        }
    )
    cache.save(frame)
    loaded = cache.load()
    assert loaded is not None
    assert loaded["symbol"].tolist() == ["AAPL.US", "MSFT.US"]


def test_universe_cache_expires(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, ttl_minutes=1)
    cache = UniverseCache(settings)
    frame = pd.DataFrame({"symbol": ["AAPL.US"], "industry_etf_proxy": ["XLK.US"]})
    cache.save(frame)

    cache._meta_path.write_text(  # noqa: SLF001
        json.dumps({"saved_at": time.time() - 120, "rows": 1}),
        encoding="utf-8",
    )
    assert cache.load() is None
