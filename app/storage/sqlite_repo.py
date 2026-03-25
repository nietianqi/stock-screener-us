from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class SQLiteRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA journal_mode=WAL;")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS symbol_master (
                    symbol TEXT PRIMARY KEY,
                    name_en TEXT,
                    exchange TEXT,
                    currency TEXT,
                    lot_size INTEGER,
                    market TEXT,
                    board TEXT,
                    industry_etf_proxy TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS daily_bar (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    turnover REAL,
                    period TEXT,
                    timestamp_utc TEXT,
                    trade_session TEXT,
                    PRIMARY KEY (symbol, date, period)
                );
                CREATE TABLE IF NOT EXISTS realtime_snapshot (
                    symbol TEXT PRIMARY KEY,
                    last_done REAL,
                    prev_close REAL,
                    open REAL,
                    high REAL,
                    low REAL,
                    volume INTEGER,
                    turnover REAL,
                    trade_status TEXT,
                    timestamp_utc TEXT
                );
                CREATE TABLE IF NOT EXISTS factor_table (
                    symbol TEXT NOT NULL,
                    scan_date TEXT NOT NULL,
                    ma50 REAL,
                    ma200 REAL,
                    momentum_12_1 REAL,
                    rs_vs_spy REAL,
                    rs_vs_qqq REAL,
                    rs_vs_sector REAL,
                    breakout_20d INTEGER,
                    breakout_60d INTEGER,
                    vol_ratio_5_20 REAL,
                    accumulation_score REAL,
                    earnings_gap_score REAL,
                    filings_event_score REAL,
                    option_activity_score REAL,
                    capital_flow_score REAL,
                    depth_bias_score REAL,
                    risk_score REAL,
                    total_score REAL,
                    trigger_tags TEXT,
                    warning_tags TEXT,
                    veto_reasons TEXT,
                    payload_json TEXT,
                    PRIMARY KEY (symbol, scan_date)
                );
                CREATE TABLE IF NOT EXISTS filings_table (
                    symbol TEXT NOT NULL,
                    filing_id TEXT NOT NULL,
                    title TEXT,
                    description TEXT,
                    file_name TEXT,
                    file_urls TEXT,
                    publish_at TEXT,
                    fetched_at TEXT,
                    PRIMARY KEY (symbol, filing_id)
                );
                CREATE TABLE IF NOT EXISTS news_table (
                    symbol TEXT NOT NULL,
                    news_id TEXT NOT NULL,
                    title TEXT,
                    summary TEXT,
                    url TEXT,
                    publish_at TEXT,
                    raw_payload TEXT,
                    PRIMARY KEY (symbol, news_id)
                );
                CREATE TABLE IF NOT EXISTS topic_table (
                    symbol TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    title TEXT,
                    summary TEXT,
                    publish_at TEXT,
                    raw_payload TEXT,
                    PRIMARY KEY (symbol, topic_id)
                );
                """
            )

    def upsert_dataframe(self, table_name: str, frame: pd.DataFrame, key_columns: list[str]) -> None:
        if frame.empty:
            return
        working = frame.copy()
        if key_columns:
            working = working.drop_duplicates(subset=key_columns, keep="last").reset_index(drop=True)
        with self._connect() as connection:
            if key_columns:
                key_frame = working[key_columns].drop_duplicates()
                placeholders = " AND ".join(f"{column} = ?" for column in key_columns)
                delete_sql = f"DELETE FROM {table_name} WHERE {placeholders}"
                rows = [tuple(row[column] for column in key_columns) for _, row in key_frame.iterrows()]
                connection.executemany(delete_sql, rows)
            working.to_sql(table_name, connection, if_exists="append", index=False)

    def query_bars(
        self,
        symbol: str,
        since: "date",
        until: "date",
        period: str = "Day",
    ) -> pd.DataFrame:
        """读取单支股票的缓存日线 K 线。"""
        sql = (
            "SELECT * FROM daily_bar "
            "WHERE symbol = ? AND period = ? AND date >= ? AND date <= ? "
            "ORDER BY date ASC"
        )
        with self._connect() as connection:
            df = pd.read_sql_query(
                sql,
                connection,
                params=(symbol, period, since.isoformat(), until.isoformat()),
            )
        return df

    def query_bars_bulk(
        self,
        symbols: list[str],
        since: "date",
        until: "date",
        period: str = "Day",
    ) -> pd.DataFrame:
        """批量读取多支股票的缓存日线 K 线，返回合并 DataFrame。"""
        if not symbols:
            return pd.DataFrame()
        placeholders = ",".join("?" for _ in symbols)
        sql = (
            f"SELECT * FROM daily_bar "
            f"WHERE symbol IN ({placeholders}) AND period = ? AND date >= ? AND date <= ? "
            f"ORDER BY symbol, date ASC"
        )
        params = (*symbols, period, since.isoformat(), until.isoformat())
        with self._connect() as connection:
            df = pd.read_sql_query(sql, connection, params=params)
        return df
