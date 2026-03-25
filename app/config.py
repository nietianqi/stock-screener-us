from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.enums import StorageBackend

try:
    from app.local_credentials import LONG_BRIDGE_LOCAL_CREDENTIALS
except ImportError:
    LONG_BRIDGE_LOCAL_CREDENTIALS = {}

DEFAULT_SYMBOLS = (
    "AAPL.US",
    "MSFT.US",
    "NVDA.US",
    "AMZN.US",
    "META.US",
    "GOOGL.US",
    "TSLA.US",
    "AMD.US",
    "NFLX.US",
    "PLTR.US",
    "AVGO.US",
    "JPM.US",
)

DEFAULT_SECTOR_PROXIES = {
    "AAPL.US": "XLK.US",
    "MSFT.US": "XLK.US",
    "NVDA.US": "XLK.US",
    "AMZN.US": "XLY.US",
    "META.US": "XLC.US",
    "GOOGL.US": "XLC.US",
    "TSLA.US": "XLY.US",
    "AMD.US": "XLK.US",
    "NFLX.US": "XLC.US",
    "PLTR.US": "XLK.US",
    "AVGO.US": "XLK.US",
    "JPM.US": "XLF.US",
}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


def _env_path(name: str, project_root: Path, default: str) -> Path:
    value = os.getenv(name)
    path = Path(value) if value else project_root / default
    return path.resolve()


@dataclass(slots=True)
class AppSettings:
    project_root: Path
    longbridge_client_id: str | None
    longbridge_app_key: str | None = None
    longbridge_app_secret: str | None = None
    longbridge_access_token: str | None = None
    oauth_callback_port: int = 60355
    request_batch_size: int = 500
    request_timeout_seconds: int = 20
    api_max_retries: int = 3
    lookback_bars: int = 320
    min_price: float = 5.0
    min_avg_daily_value_usd: float = 5_000_000
    min_history_bars: int = 250
    min_breakout_buffer: float = 0.005
    max_daily_volatility_warning: float = 0.8
    max_intraday_overheat_pct: float = 0.12
    enable_html_report: bool = True
    storage_backend: StorageBackend = StorageBackend.SQLITE
    data_dir: Path = field(default_factory=lambda: Path("data").resolve())
    output_dir: Path = field(default_factory=lambda: Path("outputs").resolve())
    log_dir: Path = field(default_factory=lambda: Path("logs").resolve())
    database_path: Path = field(default_factory=lambda: Path("data/stock_screener.db").resolve())
    parquet_dir: Path = field(default_factory=lambda: Path("data/parquet").resolve())
    universe_file: Path = field(default_factory=lambda: Path("data/universe_sample.csv").resolve())
    scan_universe: tuple[str, ...] = field(default_factory=lambda: DEFAULT_SYMBOLS)
    benchmark_symbols: tuple[str, ...] = ("SPY.US", "QQQ.US")
    sector_proxy_by_symbol: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SECTOR_PROXIES))

    @classmethod
    def load(cls, project_root: Path | None = None) -> "AppSettings":
        root = Path(project_root or Path.cwd()).resolve()
        load_dotenv(root / ".env")
        backend = StorageBackend(os.getenv("SCREENER_STORAGE_BACKEND", StorageBackend.SQLITE.value))
        settings = cls(
            project_root=root,
            longbridge_client_id=os.getenv("LONGBRIDGE_CLIENT_ID") or LONG_BRIDGE_LOCAL_CREDENTIALS.get("client_id"),
            longbridge_app_key=os.getenv("LONGBRIDGE_APP_KEY") or LONG_BRIDGE_LOCAL_CREDENTIALS.get("app_key"),
            longbridge_app_secret=os.getenv("LONGBRIDGE_APP_SECRET") or LONG_BRIDGE_LOCAL_CREDENTIALS.get("app_secret"),
            longbridge_access_token=os.getenv("LONGBRIDGE_ACCESS_TOKEN") or LONG_BRIDGE_LOCAL_CREDENTIALS.get("access_token"),
            oauth_callback_port=_env_int("LONGBRIDGE_CALLBACK_PORT", 60355),
            request_batch_size=_env_int("SCREENER_REQUEST_BATCH_SIZE", 500),
            request_timeout_seconds=_env_int("SCREENER_REQUEST_TIMEOUT_SECONDS", 20),
            api_max_retries=_env_int("SCREENER_API_MAX_RETRIES", 3),
            lookback_bars=_env_int("SCREENER_LOOKBACK_BARS", 320),
            min_price=_env_float("SCREENER_MIN_PRICE", 5.0),
            min_avg_daily_value_usd=_env_float("SCREENER_MIN_AVG_DAILY_VALUE_USD", 5_000_000),
            min_history_bars=_env_int("SCREENER_MIN_HISTORY_BARS", 250),
            min_breakout_buffer=_env_float("SCREENER_MIN_BREAKOUT_BUFFER", 0.005),
            max_daily_volatility_warning=_env_float("SCREENER_MAX_DAILY_VOLATILITY_WARNING", 0.8),
            max_intraday_overheat_pct=_env_float("SCREENER_MAX_INTRADAY_OVERHEAT_PCT", 0.12),
            enable_html_report=_env_bool("SCREENER_ENABLE_HTML_REPORT", True),
            storage_backend=backend,
            data_dir=_env_path("SCREENER_DATA_DIR", root, "data"),
            output_dir=_env_path("SCREENER_OUTPUT_DIR", root, "outputs"),
            log_dir=_env_path("SCREENER_LOG_DIR", root, "logs"),
            database_path=_env_path("SCREENER_DB_PATH", root, "data/stock_screener.db"),
            parquet_dir=_env_path("SCREENER_PARQUET_DIR", root, "data/parquet"),
            universe_file=_env_path("SCREENER_UNIVERSE_FILE", root, "data/universe_sample.csv"),
        )
        settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
