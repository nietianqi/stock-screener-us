from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class ParquetRepository:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._engine_warning_emitted = False

    def save_dataframe(self, dataset: str, frame: pd.DataFrame) -> Path | None:
        if frame.empty:
            return None
        path = self.base_dir / f"{dataset}.parquet"
        try:
            frame.to_parquet(path, index=False)
            return path
        except ImportError as exc:
            if not self._engine_warning_emitted:
                logger.warning(
                    "Parquet support is unavailable; skipping parquet persistence. "
                    "Install pyarrow or fastparquet to enable it. Detail: %s",
                    exc,
                )
                self._engine_warning_emitted = True
            return None
