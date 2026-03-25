from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class UniverseMember:
    symbol: str
    industry_etf_proxy: str | None = None
    market: str = "US"


@dataclass(slots=True)
class SymbolScoreCard:
    symbol: str
    scan_date: date
    metrics: dict[str, Any]
    total_score: float
    trigger_tags: list[str] = field(default_factory=list)
    warning_tags: list[str] = field(default_factory=list)
    veto_reasons: list[str] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        record = dict(self.metrics)
        record["symbol"] = self.symbol
        record["scan_date"] = self.scan_date.isoformat()
        record["total_score"] = self.total_score
        record["trigger_tags"] = ",".join(self.trigger_tags)
        record["warning_tags"] = ",".join(self.warning_tags)
        record["veto_reasons"] = ",".join(self.veto_reasons)
        record["passed_filters"] = int(not self.veto_reasons)
        return record


@dataclass(slots=True)
class PipelineResult:
    candidates: Any
    failures: Any
    artifacts: dict[str, str]

