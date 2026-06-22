# -*- coding: utf-8 -*-
"""P6 学习闭环 —— 协议「人体工学」调参的纯策略层(SUGGEST-ONLY)。

聚合每协议的完成/跳过/逾期信号 → 产出对**提醒人体工学**(时间窗/节奏/冷却/曝光面)的
调整建议 + 每协议「轻推节流」整数。**只调提醒好不好用,绝不调医疗效力或剂量**(R4)。
建议而非自动应用(PRD「不劫持」):用户点一下才生效。取经 adherence_watch.py:纯逻辑、
无 DB、无 Celery、可全单测;输入是上游聚合好的 ProtocolCounters。

诚实边界:① 基于「完成 vs 跳过/逾期」的代理信号,绝不下「这条对你的 LDL 有没有效」结论
(临床/R16 领域);只说「跳了 N 次,系统该调了」。② 多剂(BID)药 complete_ref 暂无剂量槽
(timeline_agenda_service.py:165 F5b TODO),两剂塌成一条 → 对用药/补剂域**不下节奏结论**
(MULTI_DOSE_DOMAINS)。③ 主动触达转化置信度天然低(遥测 metric=kind 不带 protocol_id),
只做用户级粗代理,门槛对齐 lag_association(≥3 事件 / ≥10%)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 安全常量(R4 / R13)──────────────────────────────────────────────
# 只允许调这些「人体工学」字段;绝不出现剂量/量/药名相关键。
ALLOWED_FIELDS = ("time_window", "cadence", "cooldown", "surface")
# 用药/补剂域:多剂会塌成一条(F5b)→ 不对其下「节奏」结论(cadence 调整)。
MULTI_DOSE_DOMAINS = ("medication", "supplement")

# 触发门槛(对齐既有自纠偏 _SKIP_THRESHOLD,但本层看 14 天窗)。
_MIN_SKIP_FOR_SUGGEST = 3          # 14 天内跳过/逾期合计 ≥3 才提调整
_HIGH_SKIP_FOR_MEDIUM = 5          # ≥5 → confidence medium
# 主动触达转化:样本/幅度门(对齐 lag_association.meaningful)。
_MIN_PROACTIVE_EVENTS = 3
_MIN_PROACTIVE_PCT = 10.0

# 节流:每协议每周轻推上限的「降幅」。只 SPEND FEWER(抬节流 = 推更少),
# 永不低于 1/周(R15:可以省,但不能彻底静音掉 P1/P2)。
NUDGE_FLOOR_PER_WEEK = 1
NUDGE_DEFAULT_PER_WEEK = 7         # 默认每天一次(到点轻推);链式协议各自计
# 慢性跳过 → 调低到的目标(仍 ≥ floor)。
_THROTTLE_CHRONIC_SKIP = 5         # 跳过/逾期 ≥ 此值 → 收紧轻推
_THROTTLE_TARGET = 2               # 收紧后每周轻推次数(>= floor)


@dataclass(frozen=True)
class ProtocolCounters:
    """单协议 14 天窗的聚合计数(由 DB 层组装后传入,本层不碰 DB)。"""
    protocol_id: int
    domain: str
    name: str
    priority_tier: str                      # "P0"/"P1"/"P2";本层据此守 R15
    time_window: str = "anytime"
    cadence: str = "daily"
    completed: int = 0
    skipped: int = 0
    snoozed: int = 0
    expired: int = 0                        # 议程 HealthEvent.agenda_status='expired' 计数
    dominant_skip_reason: Optional[str] = None
    # 主动触达转化(用户级粗代理,可空)。
    proactive_events: int = 0
    proactive_followed_pct: Optional[float] = None

    @property
    def missed(self) -> int:
        """未完成信号合计(跳过 + 逾期)。snooze 不计 missed(只是延后)。"""
        return self.skipped + self.expired


@dataclass(frozen=True)
class FieldDelta:
    """对单协议单字段的建议调整(SUGGEST-ONLY,applied 恒 False)。"""
    protocol_id: int
    domain: str
    name: str
    field: str                # ALLOWED_FIELDS 之一
    from_value: Any
    to_value: Any
    reason: str
    confidence: str           # "low" / "medium"
    message: str
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "domain": self.domain,
            "name": self.name,
            "field": self.field,
            "from": self.from_value,
            "to": self.to_value,
            "reason": self.reason,
            "confidence": self.confidence,
            "message": self.message,
            "applied": self.applied,
        }


# skip_reason → (建议字段, 计算 to 值的策略键)。只动人体工学,不动量。
# time_window:挪窗;cooldown:加冷却(降频);surface:换曝光面(锚点/显眼位置)。
_REASON_TO_FIELD: Dict[str, str] = {
    "no_time": "time_window",
    "social": "time_window",
    "forgot": "surface",
    "no_supply": "surface",
    "wrong_place": "surface",
    "too_tired": "cooldown",
    "too_hard": "cooldown",
    "unwell": "cooldown",
}

# 非羞辱式文案(系统视角;主语是协议/系统,不是用户意志力)。
_FIELD_MESSAGE: Dict[str, str] = {
    "time_window": "这条总在赶时间——把它挪到你更空的时间窗",
    "surface": "容易忘/不在手边——挂到固定锚点、放到显眼处",
    "cooldown": "可能定太频/太重——拉长间隔,先保住习惯",
    "cadence": "节奏偏密——降一档频率,达成比完美重要",
}

# time_window 拥挤 → 建议挪向相对空闲的窗(经验顺序,非个体化处方)。
_TIME_WINDOW_RELIEF: Dict[str, str] = {
    "morning": "noon",
    "noon": "afternoon",
    "afternoon": "evening",
    "evening": "anytime",
    "bedtime": "anytime",
    "anytime": "anytime",
}


def _suggested_field(counter: ProtocolCounters) -> Optional[str]:
    """据主导跳过原因选建议字段;无主导原因 → 默认 surface(更显眼/更易触发)。"""
    if counter.dominant_skip_reason:
        return _REASON_TO_FIELD.get(counter.dominant_skip_reason, "surface")
    return "surface"


def _to_value_for(counter: ProtocolCounters, fld: str) -> Any:
    """给字段算出建议的 to 值。绝不返回任何量/剂量。"""
    if fld == "time_window":
        return _TIME_WINDOW_RELIEF.get(counter.time_window, "anytime")
    if fld == "cooldown":
        # 冷却以「最短间隔小时」表达(纯节奏,非量)。daily → 隔天(48h 级)。
        return "longer"
    if fld == "surface":
        return "anchor"          # 挂到固定锚点(刷牙后/餐后)+ 显眼放置
    if fld == "cadence":
        return "reduce"
    return None


def _proactive_corroborates(counter: ProtocolCounters) -> bool:
    """主动触达是否「有量且没起效」的粗代理(诚实:遥测 metric=kind 不带 protocol_id)。

    样本不足(<_MIN_PROACTIVE_EVENTS)或转化未知 → False(不臆测)。门槛对齐
    lag_association.meaningful:≥3 事件,且后续完成占比低(< 100-_MIN_PROACTIVE_PCT%)。
    """
    if counter.proactive_events < _MIN_PROACTIVE_EVENTS:
        return False
    pct = counter.proactive_followed_pct
    if pct is None:
        return False
    return pct <= (100.0 - _MIN_PROACTIVE_PCT)


def suggest_field_delta(counter: ProtocolCounters) -> Optional[FieldDelta]:
    """单协议 → 至多一条 field_delta(或 None)。

    R4 硬门:本函数**永不**触碰量/剂量。返回的 field 一定 ∈ ALLOWED_FIELDS;
    cadence 调整对多剂用药/补剂域直接禁掉(F5b 塌剂歧义)。
    """
    if counter.missed < _MIN_SKIP_FOR_SUGGEST:
        return None

    fld = _suggested_field(counter)
    if fld is None or fld not in ALLOWED_FIELDS:
        return None

    # 多剂域不下 cadence 结论(F5b);若策略选了 cadence,降级为 cooldown(纯间隔,不塌剂)。
    if fld == "cadence" and counter.domain in MULTI_DOSE_DOMAINS:
        fld = "cooldown"

    to_value = _to_value_for(counter, fld)
    if to_value is None:
        return None
    from_value = counter.time_window if fld == "time_window" else (
        counter.cadence if fld == "cadence" else None)

    confidence = "medium" if counter.missed >= _HIGH_SKIP_FOR_MEDIUM else "low"
    # 主动触达转化佐证(门槛对齐 lag_association.meaningful):有足够触达样本且转化低
    # → 提醒确实没起效,提一档置信;样本不足(遥测代理,诚实)→ 不抬置信(保 low)。
    if _proactive_corroborates(counter):
        confidence = "medium"
    reason = counter.dominant_skip_reason or "chronic_miss"
    base_msg = _FIELD_MESSAGE.get(fld, "这条最近总没完成,系统也许需要调整")
    message = (
        f"近 14 天「{counter.name}」未完成 {counter.missed} 次(跳过 {counter.skipped}、"
        f"逾期 {counter.expired})。不是你的错——{base_msg}。"
    )
    return FieldDelta(
        protocol_id=counter.protocol_id,
        domain=counter.domain,
        name=counter.name,
        field=fld,
        from_value=from_value,
        to_value=to_value,
        reason=reason,
        confidence=confidence,
        message=message,
    )


def nudge_throttle(counter: ProtocolCounters) -> int:
    """每协议每周轻推上限(R15:只能 SPEND FEWER,永不低于 floor,绝不碰 P0)。

    P0(处方/复查/异常)→ 恒返回默认(本层不收紧关键提醒)。
    慢性跳过(missed ≥ _THROTTLE_CHRONIC_SKIP)→ 收紧到 _THROTTLE_TARGET(仍 ≥ floor)。
    其余 → 默认。
    """
    if (counter.priority_tier or "P1") == "P0":
        return NUDGE_DEFAULT_PER_WEEK
    if counter.missed >= _THROTTLE_CHRONIC_SKIP:
        return max(_THROTTLE_TARGET, NUDGE_FLOOR_PER_WEEK)
    return NUDGE_DEFAULT_PER_WEEK


@dataclass
class LoopResult:
    """单用户一轮学习闭环的产物(纯数据,供任务/审计/agenda 消费)。"""
    deltas: List[FieldDelta] = field(default_factory=list)
    throttles: Dict[int, int] = field(default_factory=dict)   # protocol_id → 周轻推上限

    def deltas_as_dicts(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self.deltas]


def run_loop(counters: List[ProtocolCounters]) -> LoopResult:
    """跑一轮学习闭环:每协议产出至多一条 delta + 一个节流值。纯函数,无副作用。

    R4 后置断言:任何 delta 的 field 必须 ∈ ALLOWED_FIELDS(防回归把量漏出来)。
    """
    out = LoopResult()
    for c in counters:
        d = suggest_field_delta(c)
        if d is not None:
            # R4 防御性后置闸:绝不让非白名单字段(尤其量/剂量)逃出本层。用真 raise
            # 而非 assert —— assert 在 `python -O` 下会被剥掉,R4 是本特性最关键的不变量,
            # 不能依赖断言开启(直调 run_loop 的调用方也受此保护)。
            if d.field not in ALLOWED_FIELDS:
                raise ValueError(f"R4 违规:field={d.field} 不在白名单 {ALLOWED_FIELDS}")
            out.deltas.append(d)
        # 节流对所有活跃协议都算(慢性跳过的会被收紧;其余拿默认)。
        out.throttles[c.protocol_id] = nudge_throttle(c)
    return out
