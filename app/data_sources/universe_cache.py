from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from app.config import AppSettings

logger = logging.getLogger(__name__)

_CACHE_FILE = "universe_snapshot.csv"
_META_FILE = "universe_snapshot.meta.json"


class UniverseCache:
    """TTL cache for auto-generated universe snapshots."""

    def __init__(self, settings: "AppSettings") -> None:
        self.settings = settings
        self._cache_dir = settings.data_dir
        self._cache_path = self._cache_dir / _CACHE_FILE
        self._meta_path = self._cache_dir / _META_FILE

    @property
    def _ttl_seconds(self) -> int:
        return max(0, int(self.settings.universe_cache_ttl_minutes) * 60)

    def load(self) -> pd.DataFrame | None:
        if self._ttl_seconds <= 0:
            return None
        if not self._cache_path.exists() or not self._meta_path.exists():
            return None
        metadata = self._read_metadata()
        if metadata is None:
            return None
        age_seconds = time.time() - metadata["saved_at"]
        if age_seconds > self._ttl_seconds:
            logger.info(
                "[universe_cache] cache expired (age=%.0fs, ttl=%ds).",
                age_seconds,
                self._ttl_seconds,
            )
            return None
        try:
            frame = pd.read_csv(self._cache_path)
        except Exception as exc:
            logger.warning("[universe_cache] failed to read cache: %s", exc)
            return None
        logger.info("[universe_cache] hit: loaded %d symbols.", len(frame))
        return frame

    def save(self, frame: pd.DataFrame) -> None:
        if frame.empty or self._ttl_seconds <= 0:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            frame.to_csv(self._cache_path, index=False)
            self._meta_path.write_text(
                json.dumps(
                    {"saved_at": time.time(), "rows": int(len(frame))},
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            logger.info("[universe_cache] saved %d symbols.", len(frame))
        except Exception as exc:
            logger.warning("[universe_cache] failed to save cache: %s", exc)

    def invalidate(self) -> None:
        for path in (self._cache_path, self._meta_path):
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    logger.warning("[universe_cache] failed to delete %s", path)

    def _read_metadata(self) -> dict[str, float] | None:
        try:
            payload = json.loads(self._meta_path.read_text(encoding="utf-8"))
            saved_at = float(payload.get("saved_at"))
            return {"saved_at": saved_at}
        except Exception:
            return None
