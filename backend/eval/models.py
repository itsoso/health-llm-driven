"""Eval harness 数据模型 — GoldenCase / CaseResult / SuiteReport."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    """单条 Golden Set case."""
    id: str
    description: str = ""
    suite: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    """单 case 跑完的结果."""
    case_id: str
    suite: str
    passed: bool
    score: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    latency_ms: int = 0


class SuiteReport(BaseModel):
    """一次 suite 跑完的汇总."""
    suite: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    avg_score: float = 0.0
    avg_latency_ms: int = 0
    cases: List[CaseResult] = Field(default_factory=list)
    baseline_path: Optional[str] = None
    regression: List[str] = Field(default_factory=list)  # 比 baseline 退步的 case_id

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_cases if self.total_cases else 0.0

    def summarize(self) -> str:
        return (
            f"{self.suite}: {self.passed}/{self.total_cases} pass "
            f"({self.pass_rate * 100:.1f}%), avg_score={self.avg_score:.3f}, "
            f"avg_latency={self.avg_latency_ms}ms"
            + (f", regressions={len(self.regression)}" if self.regression else "")
        )
