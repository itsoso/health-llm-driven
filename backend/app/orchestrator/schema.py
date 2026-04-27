"""Orchestrator 数据模型。"""

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OrchestratorRequest(BaseModel):
    """用户发往 Orchestrator 的一次请求。"""

    query: str = Field(..., description="用户查询的自然语言")
    specialists: Optional[List[str]] = Field(
        None,
        description="可选：强制指定调用哪些 specialist（例如 ['safety_guardian']）。None=自动路由。",
    )
    stream: bool = Field(True, description="是否流式返回 LLM 合并结果")
    # 未来字段：conversation_id、user_mood、priority_level 等


class Intent(BaseModel):
    """意图分类结果 —— 决定调度哪些 specialist。"""

    raw_query: str
    categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class SpecialistFinding(BaseModel):
    """单个 specialist 的结构化输出。"""

    specialist_name: str
    category: str
    summary: str = Field("", description="一句话概括")
    findings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="结构化发现列表。schema 各 specialist 自定，但都可 JSON 序列化",
    )
    raw: Dict[str, Any] = Field(
        default_factory=dict,
        description="原始输出（用于下游合并 / 审计）",
    )
    ms_elapsed: int = 0
    proposed_cards: List["ProposedCard"] = Field(
        default_factory=list,
        description="可选: specialist 提出的可验证假设, orchestrator 自动落地为 ActionCard",
    )


class ProposedCard(BaseModel):
    """Specialist 提出的'可验证假设' — 落地为 ActionCard 进入信任循环."""

    title: str = Field(..., max_length=200)
    content: str = Field(..., description="给用户的具体行动 markdown")
    metric_key: str = Field(..., description="待评分的指标 (hrv/weight/bp/...)")
    baseline_value: str = Field(..., description="起点值, 评分时与 target 比较")
    target_value: str = Field(..., description="目标值, 含方向 ('>42' / '<35' / '78')")
    verification_days: int = Field(..., ge=1, le=90, description="多少天后评分")
    card_type: str = Field("plan", description="plan/insight/recommendation/note")
    priority: int = Field(10, ge=0, le=100)


class OrchestratorResponse(BaseModel):
    """非流式模式下的完整响应。"""

    query: str
    intent: Intent
    findings: List[SpecialistFinding] = Field(default_factory=list)
    synthesis: str = Field("", description="LLM 合并后的自然语言回答")
    used_specialists: List[str] = Field(default_factory=list)
    twin_build_ms: int = 0
    total_ms: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    persisted_card_ids: List[int] = Field(
        default_factory=list,
        description="本次 specialist proposed_cards 落地后的 ActionCard ID 列表",
    )


# Forward-ref resolution for SpecialistFinding.proposed_cards
SpecialistFinding.model_rebuild()
