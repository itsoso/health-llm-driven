"""
Safety Guardian 的数据模型 —— Alert + Severity。

设计要点：
- Severity 是有序的（INFO < LOW < MEDIUM < HIGH < CRITICAL），前端按此排序
- Alert.rule_id 唯一、稳定，用户可以"忽略这个提醒"并持久化偏好
- data_citation 记录触发这条规则用到的具体数据 —— 审计用
- action 是用户可执行的具体建议，不是抽象建议
- 不绑定 LLM，纯结构化
"""

from datetime import UTC, datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Severity(IntEnum):
    """告警严重程度 —— 整型便于排序。"""

    INFO = 0        # 信息性提示（例如：GLP-1 延迟胃排空的常识提醒）
    LOW = 1         # 低风险（例如：补剂时机建议）
    MEDIUM = 2      # 中风险（例如：肝酶轻度偏高）
    HIGH = 3        # 高风险（例如：GLP-1 与磺脲类合用）
    CRITICAL = 4    # 紧急（例如：严重低血糖等需立即分流的红旗信号）

    @property
    def label(self) -> str:
        return {
            Severity.INFO: "info",
            Severity.LOW: "low",
            Severity.MEDIUM: "medium",
            Severity.HIGH: "high",
            Severity.CRITICAL: "critical",
        }[self]

    @property
    def label_zh(self) -> str:
        return {
            Severity.INFO: "提示",
            Severity.LOW: "关注",
            Severity.MEDIUM: "注意",
            Severity.HIGH: "警告",
            Severity.CRITICAL: "紧急",
        }[self]


class Alert(BaseModel):
    """单条安全告警。"""

    rule_id: str = Field(..., description="规则唯一 ID，稳定不变")
    category: str = Field(..., description="规则类别：vitals/labs/ddi/dsi/pgx/training_load/...")
    severity: Severity = Field(..., description="严重程度")
    title: str = Field(..., description="一句话标题，适合前端卡片头")
    message: str = Field(..., description="详细说明 —— 发生了什么、为什么重要")
    action: Optional[str] = Field(None, description="用户该做什么 —— 可执行、具体")
    data_citation: Dict[str, Any] = Field(
        default_factory=dict,
        description="触发本规则用到的原始数据快照，审计用",
    )
    references: List[str] = Field(
        default_factory=list,
        description="文献或权威来源 URL / DOI",
    )
    requires_medical_attention: bool = Field(
        False,
        description="是否建议联系真人医生 —— CRITICAL 级必 True",
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def model_dump_for_api(self) -> Dict[str, Any]:
        """前端友好的 JSON 输出（severity 带中英文标签）。"""
        d = self.model_dump(mode="json")
        d["severity"] = {
            "value": int(self.severity),
            "label": self.severity.label,
            "label_zh": self.severity.label_zh,
        }
        return d


class SafetyReport(BaseModel):
    """Safety Guardian 一次评估的完整结果。"""

    user_id: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    alerts: List[Alert] = Field(default_factory=list)
    total_rules_evaluated: int = 0
    failed_rule_count: int = Field(
        0,
        description=(
            "本次评估中抛异常被 per-rule try/except 跳过的规则条数。"
            ">0 表示自动安全筛查不完整(fail-loud 信号);此时 alerts 已注入一条 "
            "HIGH 的 safety.evaluation_incomplete advisory,绝不静默冒充安全。"
        ),
    )
    twin_build_ms: int = 0
    evaluate_ms: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity >= Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for a in self.alerts if a.severity == Severity.MEDIUM)

    def model_dump_for_api(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "generated_at": self.generated_at.isoformat(),
            "alerts": [a.model_dump_for_api() for a in self.alerts],
            "summary": {
                "total": len(self.alerts),
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "rules_evaluated": self.total_rules_evaluated,
                "failed_rule_count": self.failed_rule_count,
            },
            "timing": {
                "twin_build_ms": self.twin_build_ms,
                "evaluate_ms": self.evaluate_ms,
            },
        }
