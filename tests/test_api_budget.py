from __future__ import annotations

from pathlib import Path

from app.config import AppSettings
from app.data_sources.api_budget import ENDPOINT_QUOTE, ApiBudget


def build_settings() -> AppSettings:
    root = Path.cwd()
    return AppSettings(
        project_root=root,
        longbridge_client_id=None,
        api_budget_quote=2,
    )


def test_api_budget_enforces_limits() -> None:
    budget = ApiBudget(build_settings())
    assert budget.consume(ENDPOINT_QUOTE, "AAPL.US") is True
    assert budget.consume(ENDPOINT_QUOTE, "MSFT.US") is True
    assert budget.consume(ENDPOINT_QUOTE, "NVDA.US") is False
    assert budget.total_calls == 2
    assert budget.total_blocked == 1
