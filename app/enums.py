from __future__ import annotations

from enum import Enum


class StorageBackend(str, Enum):
    SQLITE = "sqlite"
    PARQUET = "parquet"
    BOTH = "both"


class ScanFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"

