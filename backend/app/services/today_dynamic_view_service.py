"""Aheng-composed DynamicView contract for Mobile Today."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.services import agenda_service, daily_artifact_service
from app.services.atomic_capability_registry import (
    attach_action_policy_metadata,
    validate_dynamic_view,
)

logger = logging.getLogger(__name__)

GENERATED_BY = "aheng_today_view_v1"
SURFACE = "mobile.today"
DEFAULT_TTL_SECONDS = 60

# ── R4 安全地板(pin_safety_floor)常量 ──
# 安全 slot 恒钉在 hero(100) 之上;mobile 渲染按 priority 降序排 section。
SAFETY_SLOT_PRIORITY = 120
# 安全卡唯一允许的动作:route.open 到安全告警页(mobile 实际路由,todayAtomicCards 同款)。
SAFETY_ALERTS_ROUTE = "/(tabs)/alerts"
# 整体评估不可用时的确定性 advisory rule_id(与 guardian 的
# safety.evaluation_incomplete 区分:那个是「部分规则崩」,这个是「评估整体没跑成」)。
SAFETY_UNAVAILABLE_RULE_ID = "safety.evaluation_unavailable"
# 与 agent_executor.SAFETY_CARD_BOUNDARY / mobile SafetyCard DEFAULT_BOUNDARY 同文案。
# 本地留一份字面量:评估不可用兜底卡绝不能依赖 agent_executor import 成功。
_SAFETY_BOUNDARY_FALLBACK = "这不是诊断；如出现急性不适或持续症状，请及时就医。"


def build_today_dynamic_view(
    db: Session,
    user_id: int,
    *,
    trigger: str = "open",
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the first DynamicView slice for the Mobile Today tab.

    This only composes governed runtime projections. It does not introduce a
    write path or let generated content choose arbitrary endpoints.
    """
    generated_at = datetime.now(UTC)
    artifact = daily_artifact_service.build_daily_artifact(db, user_id, followup_within_days=7)
    runtime = agenda_service.runtime_range_view(db, user_id, days=7, max_items_per_day=3)
    safety = _pin_safety_floor(db, user_id)
    context_hash = _context_hash(
        artifact, runtime, trigger, client_context or {}, safety["fingerprint"]
    )
    artifact_date = str(artifact.get("artifact_date") or runtime.get("start") or generated_at.date())
    safety_boundary = (
        artifact.get("safety_boundary")
        or _runtime_safety_boundary(runtime)
        or daily_artifact_service.DEFAULT_SAFETY_BOUNDARY
    )

    # 缓存正确性:CRITICAL 活跃或安全评估退化时把 TTL 归零(expires_at=generated_at),
    # 客户端按 expires_at 缓存的视图立即过期 —— 60s TTL 绝不允许藏住一条新 CRITICAL。
    ttl_seconds = 0 if (safety["critical_active"] or safety["degraded"]) else DEFAULT_TTL_SECONDS

    view = {
        "view_id": f"today:{artifact_date}:{context_hash[:12]}",
        "surface": SURFACE,
        "trigger": trigger,
        "generated_by": GENERATED_BY,
        "generated_at": generated_at.isoformat(),
        "expires_at": (generated_at + timedelta(seconds=ttl_seconds)).isoformat(),
        "context_hash": context_hash,
        "safety_boundary": safety_boundary,
        "sections": _compose_sections(artifact, runtime, safety["cards"]),
    }
    _assert_registered_capabilities(view)
    return view


def _evaluate_safety_alerts(db: Session, user_id: int) -> tuple[list[Any], int]:
    """与 write_autonomy._safety_blocks_autonomy 同一条评估调用链。

    evaluate_rules_with_status 返回 (alerts, failed_rule_count) —— 绝不用 lossy 的
    evaluate_rules(会吞掉「某条 CRITICAL 规则崩了」的信号,under-alarm)。区别:此处是
    读侧展示地板(非写自治门),twin 允许走 5min 缓存(use_cache=True);fail-loud 语义
    由调用方 _pin_safety_floor 承担。测试以本函数为 monkeypatch 缝。
    """
    from app.agents.safety_guardian.engine import evaluate_rules_with_status
    from app.twin.builder import build_twin

    return evaluate_rules_with_status(build_twin(db, user_id, use_cache=True))


def _pin_safety_floor(db: Session, user_id: int) -> dict[str, Any]:
    """确定性安全地板:CRITICAL/HIGH 告警映射成钉在 hero 之上的 safety 卡。

    返回 {cards, fingerprint, critical_active, degraded}:
    - cards —— CRITICAL/HIGH 告警的 safety 卡(严重度降序);规则级部分失败沿用
      guardian 的 make_fail_safe_advisory(HIGH) 注入主渲染路径;评估整体抛异常时
      注入确定性「安全评估不可用」advisory 卡 —— fail-loud,绝不静默省略(加层不减层)。
    - fingerprint —— 活跃 CRITICAL/HIGH 的 sorted rule_id:severity,进 _context_hash。
    - critical_active / degraded —— 供调用方跳过 60s TTL 缓存。
    """
    try:
        alerts, failed_rule_count = _evaluate_safety_alerts(db, user_id)
        alerts = list(alerts)
        if failed_rule_count > 0:
            from app.agents.safety_guardian.engine import make_fail_safe_advisory

            logger.error(
                "[today_view] user=%s %s 条安全规则评估失败被跳过 → 注入 fail-safe advisory",
                user_id,
                failed_rule_count,
            )
            alerts.append(make_fail_safe_advisory())

        from app.agents.safety_guardian.schema import Severity

        pinned = sorted(
            (a for a in alerts if a.severity >= Severity.HIGH),
            key=lambda a: (-int(a.severity), str(a.rule_id)),
        )
        return {
            "cards": [_safety_alert_card(alert) for alert in pinned],
            "fingerprint": sorted(f"{a.rule_id}:{a.severity.label}" for a in pinned),
            "critical_active": any(a.severity >= Severity.CRITICAL for a in pinned),
            "degraded": failed_rule_count > 0,
        }
    except Exception as e:  # noqa: BLE001 — fail-loud:评估不可用必须以卡片可见,绝不静默省略
        logger.error("[today_view] user=%s 安全评估不可用 → 注入确定性 advisory 卡: %s", user_id, e)
        return {
            "cards": [_safety_unavailable_card()],
            "fingerprint": [f"{SAFETY_UNAVAILABLE_RULE_ID}:high"],
            "critical_active": False,
            "degraded": True,
        }


def _safety_alert_card(alert: Any) -> dict[str, Any]:
    """把一条 SafetyGuardian Alert 映射成 mobile SafetyCard 契约的卡片。

    data 形状复用 agent_executor._safety_alert_card_descriptor(chat 面 safety 卡的
    单一真源),保证 mobile registry 的 safety CardSpec 两个面吃同一 shape。
    """
    from app.services.agent_executor import _safety_alert_card_descriptor

    descriptor = _safety_alert_card_descriptor(alert)
    if not (isinstance(descriptor, dict) and isinstance(descriptor.get("data"), dict)):
        # 描述器失效不允许静默丢告警 —— 抛给 _pin_safety_floor 的 fail-loud 兜底。
        raise ValueError(
            f"safety_card_descriptor_invalid: rule={getattr(alert, 'rule_id', None)}"
        )
    rule_token = _safe_token(getattr(alert, "rule_id", None)) or "unknown"
    return {
        "id": f"safety-alert:{rule_token}",
        "type": "safety",
        "data": descriptor["data"],
        "actions": [_open_safety_alerts_action()],
        "render": {
            "atom": "safety",
            "priority": SAFETY_SLOT_PRIORITY,
            "dedupe_key": f"safety:{rule_token}",
            "dedupe_keys": [f"safety:{rule_token}"],
            "reason": "pinned_safety_floor",
        },
    }


def _safety_unavailable_card() -> dict[str, Any]:
    """安全评估整体不可用时的确定性 advisory 卡(R4:不诊断,只给动作)。"""
    return {
        "id": "safety-advisory:evaluation-unavailable",
        "type": "safety",
        "data": {
            "title": "安全评估不可用",
            "severity": "high",
            "summary": (
                "本次未能完成自动安全评估,无法确认当前是否存在安全风险。"
                "这不代表安全,只代表系统未能完成评估。"
            ),
            "recommendations": ["如有任何不适请及时就医,情况紧急请拨打 120。"],
            "boundary": _SAFETY_BOUNDARY_FALLBACK,
            "requires_medical_attention": True,
            "rule_id": SAFETY_UNAVAILABLE_RULE_ID,
            "category": "meta",
        },
        "actions": [_open_safety_alerts_action()],
        "render": {
            "atom": "safety",
            "priority": SAFETY_SLOT_PRIORITY,
            "dedupe_key": f"safety:{SAFETY_UNAVAILABLE_RULE_ID}",
            "dedupe_keys": [f"safety:{SAFETY_UNAVAILABLE_RULE_ID}"],
            "reason": "safety_floor_fail_loud",
        },
    }


def _open_safety_alerts_action() -> dict[str, Any]:
    return attach_action_policy_metadata("safety", [{
        "id": "open-safety-alerts",
        "label": "查看安全提醒",
        "action": "route.open",
        "payload": {"route": SAFETY_ALERTS_ROUTE},
        "style": "primary",
    }])[0]


def _assert_registered_capabilities(view: dict[str, Any]) -> None:
    violations = validate_dynamic_view(view)
    if violations:
        raise ValueError(f"invalid_dynamic_view: {'; '.join(violations)}")


def _compose_sections(
    artifact: dict[str, Any],
    runtime: dict[str, Any],
    safety_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    used_keys: set[str] = set()
    sections: list[dict[str, Any]] = []

    if safety_cards:
        # 安全地板钉在 hero 之上(priority 120 > 100);不参与 hero/runtime 去重,
        # 安全卡只会增加内容,绝不抑制既有 hero/runtime 行为(加层不减层)。
        sections.append({
            "slot": "safety",
            "priority": SAFETY_SLOT_PRIORITY,
            "title": "安全提醒",
            "cards": safety_cards,
        })

    daily_card = _daily_artifact_card(artifact)
    sections.append({
        "slot": "hero",
        "priority": 100,
        "title": "今日状态",
        "cards": [daily_card],
    })
    used_keys.update(_card_dedupe_keys(daily_card))

    runtime_card = _runtime_agenda_card(runtime)
    if runtime_card and not used_keys.intersection(_card_dedupe_keys(runtime_card)):
        sections.append({
            "slot": "runtime",
            "priority": 80,
            "title": "健康运行时",
            "cards": [runtime_card],
        })

    return sections


def _daily_artifact_card(artifact: dict[str, Any]) -> dict[str, Any]:
    action = artifact.get("top_action") if isinstance(artifact.get("top_action"), dict) else {}
    artifact_date = str(artifact.get("artifact_date") or "unknown")
    action_id = _safe_token(action.get("id")) or "empty"
    dedupe_key = _primary_dedupe_key(action)
    render = {
        "atom": "daily_artifact",
        "priority": 100,
        "dedupe_key": dedupe_key,
        "dedupe_keys": _action_dedupe_keys(action),
        "reason": "primary_today_action",
    }
    return {
        "id": f"daily-artifact:{artifact_date}:{action_id}",
        "type": "daily_artifact",
        "data": artifact,
        "render": render,
    }


def _runtime_agenda_card(runtime: dict[str, Any]) -> dict[str, Any] | None:
    data = _runtime_agenda_card_data(runtime)
    action = _runtime_action(runtime)
    if not action and not data.get("days"):
        return None
    start = _safe_token(runtime.get("start")) or "unknown"
    action_id = _safe_token(action.get("id")) or "empty"
    # Home 与 Chat 共用同一份受控动作合同，避免一端能完成、另一端只能看。
    from app.services.inline_cards import _runtime_agenda_actions

    return {
        "id": f"runtime-agenda:{start}:{action_id}",
        "type": "runtime_agenda",
        "data": data,
        "actions": attach_action_policy_metadata(
            "runtime_agenda",
            _runtime_agenda_actions(data),
        ),
        "render": {
            "atom": "runtime_agenda",
            "priority": 80,
            "dedupe_key": _primary_dedupe_key(action),
            "dedupe_keys": _action_dedupe_keys(action),
            "reason": "next_runtime_action",
        },
    }


def _runtime_agenda_card_data(runtime: dict[str, Any]) -> dict[str, Any]:
    action = _runtime_action(runtime)
    runtime_context = action.get("runtime_context") if isinstance(action.get("runtime_context"), dict) else {}
    root_context = runtime.get("runtime_context") if isinstance(runtime.get("runtime_context"), dict) else {}
    verification_window = (
        runtime_context.get("verification_window")
        if isinstance(runtime_context.get("verification_window"), dict)
        else {}
    )
    metrics = [
        str(metric)
        for metric in verification_window.get("metrics") or []
        if isinstance(metric, (str, int, float)) and str(metric).strip()
    ][:3]

    return {
        "mode": runtime.get("mode"),
        "presentation_mode": "today",
        "generated_by": runtime.get("generated_by"),
        "horizon_days": runtime.get("horizon_days"),
        "start": runtime.get("start"),
        "end": runtime.get("end"),
        "safety_boundary": root_context.get("safety_boundary") or runtime_context.get("safety_boundary"),
        "next_action": {
            "id": action.get("id"),
            "title": action.get("title"),
            "kind": action.get("type"),
            "source": action.get("source") if isinstance(action.get("source"), dict) else None,
            "time_window": action.get("time_window"),
            "priority_tier": action.get("priority_tier"),
            "current_state_summary": runtime_context.get("current_state_summary"),
            "replan_reason": runtime_context.get("replan_reason"),
            "verification_metrics": metrics,
            "verification_window_days": verification_window.get("window_days"),
        },
        "days": [
            _compact_runtime_day(day)
            for day in (runtime.get("days") or [])[:7]
            if isinstance(day, dict)
        ],
    }


def _runtime_action(runtime: dict[str, Any]) -> dict[str, Any]:
    action = runtime.get("next_action") if isinstance(runtime.get("next_action"), dict) else None
    if action is None:
        for day in runtime.get("days") or []:
            if isinstance(day, dict) and isinstance(day.get("next_action"), dict):
                action = day["next_action"]
                break
    return action if isinstance(action, dict) else {}


def _compact_runtime_day(day: dict[str, Any]) -> dict[str, Any]:
    next_action = day.get("next_action") if isinstance(day.get("next_action"), dict) else None
    item_count = 0
    for window in day.get("time_windows") or []:
        if isinstance(window, dict) and isinstance(window.get("items"), list):
            item_count += len(window["items"])
    return {
        "date": day.get("date"),
        "next_action_title": next_action.get("title") if next_action else None,
        "items_count": item_count,
    }


def _runtime_safety_boundary(runtime: dict[str, Any]) -> str | None:
    context = runtime.get("runtime_context")
    if isinstance(context, dict) and context.get("safety_boundary"):
        return str(context["safety_boundary"])
    return None


def _card_dedupe_keys(card: dict[str, Any]) -> set[str]:
    render = card.get("render") if isinstance(card.get("render"), dict) else {}
    keys = render.get("dedupe_keys")
    if isinstance(keys, list):
        return {str(key) for key in keys if str(key).strip()}
    key = render.get("dedupe_key")
    return {str(key)} if key else set()


def _primary_dedupe_key(action: dict[str, Any]) -> str | None:
    keys = _action_dedupe_keys(action)
    return keys[0] if keys else None


def _action_dedupe_keys(action: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    action_id = _safe_token(action.get("id"))
    if action_id:
        keys.append(f"action:{action_id}")
    title = _title_key(action.get("title"))
    if title:
        keys.append(f"title:{title}")
    return keys


def _safe_token(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", text).strip("-") or None


def _title_key(value: Any) -> str | None:
    text = str(value).strip().lower() if value is not None else ""
    if not text:
        return None
    return re.sub(r"[\s:：,，.。;；]+", "", text) or None


def _context_hash(
    artifact: dict[str, Any],
    runtime: dict[str, Any],
    trigger: str,
    client_context: dict[str, Any],
    safety_fingerprint: list[str],
) -> str:
    payload = {
        "trigger": trigger,
        # 活跃 CRITICAL/HIGH 的 sorted rule_id:severity —— 告警出现/消失/换档必须
        # 翻转 context_hash(与 view_id),否则 60s TTL 会把新 CRITICAL 藏在旧视图里。
        "safety_fingerprint": safety_fingerprint,
        "artifact_date": artifact.get("artifact_date"),
        "artifact_generated_by": artifact.get("generated_by"),
        "artifact_source": artifact.get("source"),
        "top_action_id": (artifact.get("top_action") or {}).get("id")
        if isinstance(artifact.get("top_action"), dict)
        else None,
        "runtime_start": runtime.get("start"),
        "runtime_end": runtime.get("end"),
        "runtime_generated_by": runtime.get("generated_by"),
        "runtime_next_action_id": (runtime.get("next_action") or {}).get("id")
        if isinstance(runtime.get("next_action"), dict)
        else None,
        "client_capabilities": client_context.get("client_capabilities"),
        "timezone": client_context.get("timezone"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
