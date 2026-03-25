from __future__ import annotations

from pathlib import Path

import pandas as pd


class ParquetRepository:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_dataframe(self, dataset: str, frame: pd.DataFrame) -> Path | None:
        if frame.empty:
            return None
        path = self.base_dir / f"{dataset}.parquet"
        frame.to_parquet(path, index=False)
        return path
