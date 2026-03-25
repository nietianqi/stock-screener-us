from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from app.storage.sqlite_repo import SQLiteRepository


def test_upsert_dataframe_deduplicates_payload_by_key(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    repo = SQLiteRepository(db_path)

    frame = pd.DataFrame(
        [
            {
                "symbol": "AAPL.US",
                "topic_id": "topic-1",
                "title": "old",
                "summary": "s",
                "publish_at": "2026-03-25T00:00:00Z",
                "raw_payload": "{}",
            },
            {
                "symbol": "AAPL.US",
                "topic_id": "topic-1",
                "title": "new",
                "summary": "s",
                "publish_at": "2026-03-25T00:00:00Z",
                "raw_payload": "{}",
            },
        ]
    )
    repo.upsert_dataframe("topic_table", frame, ["symbol", "topic_id"])

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT symbol, topic_id, title FROM topic_table WHERE symbol = ? AND topic_id = ?",
            ("AAPL.US", "topic-1"),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][2] == "new"
