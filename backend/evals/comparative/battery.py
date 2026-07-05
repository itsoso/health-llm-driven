"""battery.yaml 加载 + schema 校验 —— 所有臂/judge/测试的单一真源。

为什么单独一个模块:
  - runner / judge / collect / 测试都要读题库,格式校验只写一遍,避免漂移。
  - 校验 fail-loud:题库缺字段 / 家族配比不对 / id 重复,直接抛,不让坏题库静默跑出脏结果。

不引入新依赖:PyYAML + pydantic 都是 backend 既有依赖。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

BATTERY_PATH = Path(__file__).with_name("battery.yaml")

# 六家族 + 每族期望题数(题库改配比时同步这里,校验会强制一致)。
FAMILIES = ("fact", "state_read", "safety_refusal", "root_cause", "honesty", "multi_turn")
FAMILY_QUOTA: Dict[str, int] = {
    "fact": 3,
    "state_read": 4,
    "safety_refusal": 3,
    "root_cause": 2,
    "honesty": 2,
    "multi_turn": 2,
}
EXPECTED_TOTAL = sum(FAMILY_QUOTA.values())  # 16


class Question(BaseModel):
    """单题 schema。"""

    id: str
    family: str
    prompt: str
    requires_personal_data: bool
    scoring_notes: str
    follow_ups: List[str] = Field(default_factory=list)

    @field_validator("family")
    @classmethod
    def _family_known(cls, v: str) -> str:
        if v not in FAMILIES:
            raise ValueError(f"未知 family={v!r},合法值 {FAMILIES}")
        return v

    @field_validator("id", "prompt", "scoring_notes")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id / prompt / scoring_notes 不能为空")
        return v.strip()

    @property
    def is_multi_turn(self) -> bool:
        return self.family == "multi_turn" or bool(self.follow_ups)

    def turns(self) -> List[str]:
        """按顺序返回该题所有轮次的 prompt(首问 + follow_ups)。"""
        return [self.prompt, *self.follow_ups]


class Battery(BaseModel):
    """整个题库。"""

    version: int = 1
    domain: str = ""
    language: str = "zh-CN"
    arms_expected: List[str] = Field(default_factory=list)
    questions: List[Question]

    @field_validator("questions")
    @classmethod
    def _validate_set(cls, qs: List[Question]) -> List[Question]:
        if not qs:
            raise ValueError("题库为空")
        ids = [q.id for q in qs]
        dups = [i for i, c in Counter(ids).items() if c > 1]
        if dups:
            raise ValueError(f"题目 id 重复: {dups}")
        fam_counts = Counter(q.family for q in qs)
        mismatches = {
            fam: (fam_counts.get(fam, 0), quota)
            for fam, quota in FAMILY_QUOTA.items()
            if fam_counts.get(fam, 0) != quota
        }
        if mismatches:
            raise ValueError(
                f"家族配比不符 (实际,期望): {mismatches};题库总数={len(qs)},期望={EXPECTED_TOTAL}"
            )
        # multi_turn 家族必须带 follow_ups,否则测不了多轮记忆
        for q in qs:
            if q.family == "multi_turn" and not q.follow_ups:
                raise ValueError(f"multi_turn 题 {q.id} 缺 follow_ups")
        return qs

    def by_id(self, qid: str) -> Question:
        for q in self.questions:
            if q.id == qid:
                return q
        raise KeyError(qid)

    def by_family(self, family: str) -> List[Question]:
        return [q for q in self.questions if q.family == family]


def load_battery(path: Optional[Path] = None) -> Battery:
    """加载 + 校验题库。fail-loud:文件缺失 / YAML 坏 / schema 不合直接抛。"""
    p = Path(path) if path else BATTERY_PATH
    if not p.exists():
        raise FileNotFoundError(f"题库不存在: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"题库根节点应是 mapping,实际 {type(raw).__name__}")
    meta = raw.get("meta") or {}
    questions = raw.get("questions")
    if questions is None:
        raise ValueError("题库缺 questions 节点")
    return Battery(
        version=int(meta.get("version", 1)),
        domain=str(meta.get("domain", "")),
        language=str(meta.get("language", "zh-CN")),
        arms_expected=list(meta.get("arms_expected", [])),
        questions=[Question.model_validate(q) for q in questions],
    )
