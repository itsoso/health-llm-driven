"""Protocol YAML registry — Agent-Native v3 三层瘦身架构的"稳定性根".

设计要点:
- Protocol 是版本化 YAML, 带 evidence_id / owner / medical_review_date.
  LLM 不造内容, 只填变量 / 选 branch / 组文案.
- 启动时 load 全部 YAML 到内存. 失败的文件记 warning 跳过, 不阻塞启动.
- 匹配逻辑用简单 DSL: all_of 条件全部满足.
- Pydantic 严格 schema, 构造时验证.

Schema 字段对应 v3 文档第 III 节"对象模型 → Protocol".
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Protocol Pydantic Schema
# ─────────────────────────────────────────────────────────

class ProtocolEvidence(BaseModel):
    id: str
    source: str
    statement: str


class ProtocolMatchCondition(BaseModel):
    field: str
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"]
    value: Any


class ProtocolMatch(BaseModel):
    episode_type: str
    all_of: List[ProtocolMatchCondition] = Field(default_factory=list)
    any_of: List[ProtocolMatchCondition] = Field(default_factory=list)


class ProtocolTimeWindow(BaseModel):
    offset_min_start: int = 0
    offset_min_end: int


class ProtocolCompletionCheck(BaseModel):
    kind: Literal["self_report", "inline_question", "metric"]
    prompt: Optional[str] = None
    questions: Optional[List[Dict[str, Any]]] = None
    metric: Optional[str] = None
    threshold: Optional[float] = None


class ProtocolRiskCondition(BaseModel):
    escalate_if: List[str] = Field(default_factory=list)
    demote_if: List[str] = Field(default_factory=list)


class ProtocolAction(BaseModel):
    sequence: int = 0
    template_id: str
    action_type: str
    icon: Optional[str] = None
    title: str
    body: Optional[str] = None
    evidence_id: Optional[str] = None
    time_window: Optional[ProtocolTimeWindow] = None
    condition_expr: Optional[str] = None
    completion_check: Optional[ProtocolCompletionCheck] = None
    risk_condition: Optional[ProtocolRiskCondition] = None


class ProtocolRedFlag(BaseModel):
    id: str
    condition: str
    risk_level: Literal["L0", "L1", "L2", "L3", "L4"]
    action: str


class Protocol(BaseModel):
    slug: str
    version: str
    title: str
    owner: str
    medical_review_date: Optional[str] = None
    risk_level_hint: Literal["L0", "L1", "L2", "L3", "L4"] = "L0"
    description: Optional[str] = None
    evidence: List[ProtocolEvidence] = Field(default_factory=list)
    match: ProtocolMatch
    actions: List[ProtocolAction] = Field(default_factory=list)
    red_flags: List[ProtocolRedFlag] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────
# Registry — load + match
# ─────────────────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parents[3] / "protocols"


class ProtocolRegistry:
    """启动时 load YAML 集合, 之后只读. 进程内单例."""

    def __init__(self, base_dir: Path = _BASE_DIR):
        self.base_dir = base_dir
        self._protocols: Dict[str, Protocol] = {}
        self._load()

    def _load(self) -> None:
        if not self.base_dir.exists():
            logger.warning("Protocol registry: %s 不存在, 跳过加载", self.base_dir)
            return
        for fp in sorted(self.base_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(fp.read_text(encoding="utf-8"))
                p = Protocol(**data)
                key = f"{p.slug}@{p.version}"
                self._protocols[key] = p
                logger.info("Protocol loaded: %s (risk=%s, actions=%d)",
                            key, p.risk_level_hint, len(p.actions))
            except (yaml.YAMLError, ValidationError) as e:
                logger.error("Protocol 加载失败: %s — %s", fp.name, e)
            except Exception as e:  # noqa: BLE001
                logger.error("Protocol 未知错误: %s — %s", fp.name, e)

    def all(self) -> List[Protocol]:
        return list(self._protocols.values())

    def get(self, slug: str, version: Optional[str] = None) -> Optional[Protocol]:
        """取指定 slug, version 不传时取最新 (按版本字符串字典序)."""
        if version:
            return self._protocols.get(f"{slug}@{version}")
        candidates = [p for p in self._protocols.values() if p.slug == slug]
        if not candidates:
            return None
        return sorted(candidates, key=lambda p: p.version, reverse=True)[0]

    def match(self, episode_type: str, context: Dict[str, Any]) -> Optional[Protocol]:
        """依次尝试每个 protocol, 返回第一个 episode_type 匹配 + 条件命中的.

        约定: 更具体的 protocol 应该排在前面 (按 slug 字典序; hot_weather < normal).
        条件不全匹配的会被跳过, 这样最后落到 normal 这种宽松的兜底.
        """
        for p in sorted(self._protocols.values(), key=lambda x: x.slug):
            if p.match.episode_type != episode_type:
                continue
            if self._matches(p.match, context):
                return p
        return None

    @staticmethod
    def _matches(m: ProtocolMatch, ctx: Dict[str, Any]) -> bool:
        for c in m.all_of:
            if not _eval_condition(c, ctx):
                return False
        if m.any_of:
            return any(_eval_condition(c, ctx) for c in m.any_of)
        return True


def _eval_condition(c: ProtocolMatchCondition, ctx: Dict[str, Any]) -> bool:
    """Field path 形如 'context.weather.temperature_c', 取嵌套值."""
    val = _resolve_path(ctx, c.field)
    if val is None:
        return False
    try:
        if c.op == "eq":
            return val == c.value
        if c.op == "ne":
            return val != c.value
        if c.op == "lt":
            return val < c.value
        if c.op == "lte":
            return val <= c.value
        if c.op == "gt":
            return val > c.value
        if c.op == "gte":
            return val >= c.value
        if c.op == "in":
            return val in c.value
        if c.op == "not_in":
            return val not in c.value
    except TypeError:
        return False
    return False


def _resolve_path(obj: Any, path: str) -> Any:
    parts = path.split(".")
    # 'context.x.y' — 第一段就是 'context', 跳过 (ctx 已经是 context dict).
    if parts and parts[0] == "context":
        parts = parts[1:]
    cur = obj
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            cur = getattr(cur, p, None)
        if cur is None:
            return None
    return cur


# ─────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────

_registry: Optional[ProtocolRegistry] = None


def get_registry() -> ProtocolRegistry:
    global _registry
    if _registry is None:
        _registry = ProtocolRegistry()
    return _registry


def reload_registry() -> ProtocolRegistry:
    """测试用 — 强制重新 load."""
    global _registry
    _registry = ProtocolRegistry()
    return _registry
