from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import AppSettings

logger = logging.getLogger(__name__)

ENDPOINT_HISTORY_BARS = "history_bars"
ENDPOINT_QUOTE = "quote"
ENDPOINT_STATIC_INFO = "static_info"
ENDPOINT_SECURITY_LIST = "security_list"
ENDPOINT_OTHER = "other"


class ApiBudget:
    """Tracks per-endpoint API usage and optional call limits."""

    def __init__(self, settings: "AppSettings") -> None:
        self._limits: dict[str, int] = {
            ENDPOINT_HISTORY_BARS: settings.api_budget_history_bars,
            ENDPOINT_QUOTE: settings.api_budget_quote,
            ENDPOINT_STATIC_INFO: 0,
            ENDPOINT_SECURITY_LIST: 0,
            ENDPOINT_OTHER: 0,
        }
        self._counts: dict[str, int] = defaultdict(int)
        self._blocked: dict[str, int] = defaultdict(int)

    def consume(self, endpoint: str, symbol: str = "") -> bool:
        """Consumes one budget unit. Returns False when the endpoint budget is exhausted."""
        key = endpoint if endpoint in self._limits else ENDPOINT_OTHER
        limit = self._limits[key]
        if limit > 0 and self._counts[key] >= limit:
            self._blocked[key] += 1
            blocked = self._blocked[key]
            if blocked == 1 or blocked % 10 == 0:
                logger.warning(
                    "[api_budget] %s budget exhausted (limit=%d, blocked=%d). symbol=%s",
                    key,
                    limit,
                    blocked,
                    symbol,
                )
            return False
        self._counts[key] += 1
        return True

    def record(self, endpoint: str, count: int = 1) -> None:
        """Records known usage without enforcing limits."""
        key = endpoint if endpoint in self._limits else ENDPOINT_OTHER
        self._counts[key] += max(0, int(count))

    def remaining(self, endpoint: str) -> int | None:
        key = endpoint if endpoint in self._limits else ENDPOINT_OTHER
        limit = self._limits[key]
        if limit <= 0:
            return None
        return max(0, limit - self._counts[key])

    def log_summary(self) -> None:
        lines = ["[api_budget] usage summary"]
        all_keys = sorted(set(self._limits) | set(self._counts) | set(self._blocked))
        for key in all_keys:
            limit = self._limits.get(key, 0)
            limit_text = "unlimited" if limit <= 0 else str(limit)
            lines.append(
                "  %-16s calls=%-4d blocked=%-4d limit=%s"
                % (key, self._counts.get(key, 0), self._blocked.get(key, 0), limit_text)
            )
        logger.info("\n".join(lines))

    def reset(self) -> None:
        self._counts.clear()
        self._blocked.clear()

    @property
    def total_calls(self) -> int:
        return sum(self._counts.values())

    @property
    def total_blocked(self) -> int:
        return sum(self._blocked.values())
