"""Meal monitoring — batch frame analysis + OBSERVATIONAL post-meal summary.

Split out of ``meal_monitoring.py`` (lifecycle/throttle/persistence) to keep each
file under the complexity budget. This module is the analysis layer:

- dedup foods across 准视频 frames (the same meal sampled repeatedly)
- run the existing vision provider on frames lacking client-side recognition
- compute meal totals once
- produce an OBSERVATIONAL post-meal summary (reusing FuelStrategist for daily
  context), sanitized by ``guidance_validator`` and checked by the SafetyGuardian
  guidance red-line rules

R4: summary is observational/post-hoc, never imperative/prescriptive.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents import audit
from app.models.ambient_wearable import VisualInputEvent
from app.services.guidance_validator import sanitize_guidance

logger = logging.getLogger(__name__)


def frame_recognition(frame: VisualInputEvent) -> Optional[Dict[str, Any]]:
    if isinstance(frame.recognition_result, dict):
        return frame.recognition_result
    return None


def frame_image_base64(frame: VisualInputEvent) -> Optional[str]:
    meta = frame.meta if isinstance(frame.meta, dict) else {}
    b64 = meta.get("image_base64")
    return b64 if isinstance(b64, str) and b64 else None


def dedup_foods(per_frame: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge foods across frames, deduped by normalized name.

    准视频 samples the *same* meal repeatedly — the same dish appears in many
    frames. We keep the highest-confidence observation per food name so the meal
    total is not multiplied by the frame count.
    """
    best: Dict[str, Dict[str, Any]] = {}
    for recognition in per_frame:
        foods = recognition.get("foods") or recognition.get("food_items") or []
        if not isinstance(foods, list):
            continue
        for food in foods:
            if not isinstance(food, dict):
                continue
            name = str(food.get("name") or food.get("food_name") or "").strip()
            if not name:
                continue
            key = name.lower()
            conf = food.get("confidence")
            conf = float(conf) if isinstance(conf, (int, float)) else 0.0
            prev = best.get(key)
            prev_conf = (
                float(prev.get("confidence"))
                if prev and isinstance(prev.get("confidence"), (int, float))
                else -1.0
            )
            if prev is None or conf > prev_conf:
                best[key] = {**food, "name": name}
    return list(best.values())


def sum_nutrient(foods: List[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [
        float(f.get(key))
        for f in foods
        if isinstance(f.get(key), (int, float)) and not isinstance(f.get(key), bool)
    ]
    return round(float(sum(vals)), 1) if vals else None


def meal_totals(foods: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    return {
        "calories": sum_nutrient(foods, "calories"),
        "protein": sum_nutrient(foods, "protein"),
        "carbs": sum_nutrient(foods, "carbs"),
        "fat": sum_nutrient(foods, "fat"),
        "fiber": sum_nutrient(foods, "fiber"),
    }


async def recognize_frame(image_base64: str) -> Optional[Dict[str, Any]]:
    """Run the existing vision provider on one frame. Returns None on failure.

    The provider's ``recognize_food_from_base64`` already returns a dict (with
    ``success=False``) on its own errors rather than raising. We still wrap the
    call defensively: a single frame's provider exception must NOT abort the
    whole ``finish_session`` batch — it's recorded as a failed frame (None) and
    the surrounding ``analyze_frames`` audits ``success=False``, never silently
    pretending the frame succeeded.
    """
    from app.services.ai.food_recognition import food_recognition_service

    try:
        result = await food_recognition_service.recognize_food_from_base64(image_base64)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[meal_monitoring] frame vision raised, treating as failed frame: {e}")
        return None
    if isinstance(result, dict) and result.get("success"):
        return result
    return None


async def analyze_frames(
    db: Session,
    user_id: int,
    session_id: int,
    frames: List[VisualInputEvent],
) -> tuple[List[Dict[str, Any]], int]:
    """Resolve a recognition dict per frame, calling vision where needed.

    Returns ``(per_frame_recognitions, vision_calls)``. Each vision call is
    audited (not a silent batch).
    """
    per_frame: List[Dict[str, Any]] = []
    vision_calls = 0
    for frame in frames:
        recognition = frame_recognition(frame)
        if recognition is None:
            b64 = frame_image_base64(frame)
            if b64:
                recognition = await recognize_frame(b64)
                vision_calls += 1
                audit._write(
                    db,
                    user_id=user_id,
                    agent_type="meal_monitoring",
                    action="vision_analyze",
                    result_summary=f"session {session_id} frame {frame.id} vision",
                    result_detail={
                        "session_id": session_id,
                        "frame_event_id": frame.id,
                        "success": recognition is not None,
                    },
                )
        if isinstance(recognition, dict):
            per_frame.append(recognition)
    return per_frame, vision_calls


def post_meal_observational_summary(
    db: Session,
    user_id: int,
    totals: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    """OBSERVATIONAL post-meal summary, reusing FuelStrategist for daily context.

    Always emits a meal-only line ("这餐约 X kcal"). If the user's real twin
    builds (TDEE / protein target / today's intake), it adds FuelStrategist's
    observational energy/protein lines. Never imperative/prescriptive.
    """
    cals = totals.get("calories")
    protein = totals.get("protein")
    parts: List[str] = []
    if cals is not None:
        parts.append(f"这餐约 {int(cals)} kcal")
    if protein is not None:
        parts.append(f"蛋白约 {int(protein)}g")

    fuel_findings: List[Dict[str, Any]] = []
    fuel_summary = ""
    try:
        from app.agents.fuel_strategist.strategist import FuelStrategistSpecialist
        from app.twin.builder import build_twin

        twin = build_twin(db, user_id, use_cache=False)
        finding = FuelStrategistSpecialist().run(twin, {})
        fuel_findings = finding.findings or []
        fuel_summary = finding.summary or ""
        for f in fuel_findings:
            if f.get("type") == "energy" and f.get("remaining_kcal") is not None:
                rem = int(f["remaining_kcal"])
                if rem > 0:
                    parts.append(f"今日还剩约 {rem} kcal 空间")
                elif rem < 0:
                    parts.append(f"今日已超出约 {-rem} kcal")
            if f.get("type") == "protein":
                tgt = f.get("target_g")
                today = f.get("today_g")
                if tgt is not None and today is not None and today < tgt:
                    parts.append(f"今日蛋白还差约 {int(tgt - today)}g")
    except Exception as e:  # noqa: BLE001
        # Daily context is best-effort; the meal-only summary still stands.
        # WARNING (not INFO): for an authenticated user with diet data this branch
        # should almost always succeed, so a skip is worth surfacing — a silent INFO
        # is how this feature previously died unnoticed (build_twin called with wrong args).
        logger.warning(
            f"[meal_monitoring] daily-context summary skipped (FuelStrategist/twin unavailable): {e}"
        )
        fuel_summary = ""

    base = " · ".join(parts) if parts else "这餐未能估算营养(图像识别为空)"
    text = (
        f"{base}。这是观察性记录, 可作为今日饮食参考; "
        f"具体调整建议请与医生或营养师确认。"
    )
    return {"text": text, "fuel_summary": fuel_summary, "fuel_findings": fuel_findings}


def evaluate_guidance_rules(user_id: int, text: str) -> List[Dict[str, Any]]:
    """纯规则求值:裸 twin + 两条 guidance 红线。**无 db、无审计、无副作用**。

    单一真源:``run_guidance_rules``(求值 + 审计)与主对话的影子探针共用它 ——
    避免第三次复制这段 twin 样板(rokid_pushup_review 已复制过一次 = 已有漂移风险)。
    影子探针**必须**用这个纯函数而非 ``run_guidance_rules``:后者会 ``db.commit()``
    写审计行,插进主回合的 session 会在助手消息落库前 rollback,且误命中会把真实
    safety 评估挤出 /safety/audit 默认窗口(= 审计面 under-alarm)。
    """
    from app.agents.safety_guardian.rules.guidance_red_lines import (
        diet_prescription_red_line,
        movement_imperative_red_line,
    )
    from app.twin.schema import HealthTwin, TwinMeta

    twin = HealthTwin(
        meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc))
    )
    twin.acute.pending_guidance_texts = [text]

    alerts: List[Dict[str, Any]] = []
    for rule in (diet_prescription_red_line, movement_imperative_red_line):
        alert = rule(twin)
        if alert is not None:
            alerts.append(alert.model_dump_for_api())
    return alerts


def run_guidance_rules(db: Session, user_id: int, text: str) -> List[Dict[str, Any]]:
    """Run the SafetyGuardian guidance red-line rules over candidate text.

    Defense-in-depth behind ``sanitize_guidance``: even after the validator
    strips text, we evaluate the candidate so any residual prescriptive/imperative
    token becomes an auditable CRITICAL/HIGH alert.
    """
    alerts = evaluate_guidance_rules(user_id, text)
    if alerts:
        audit.log_safety_evaluation(
            db,
            user_id=user_id,
            alerts_count=len(alerts),
            result_summary=f"meal guidance red-line: {len(alerts)} alert(s)",
            twin_build_ms=0,
            evaluate_ms=0,
            twin_sources=["meal_monitoring_guidance"],
            result_detail={"alerts": alerts},
        )
    return alerts


def draft_diet_record_preview(
    foods: List[Dict[str, Any]],
    totals: Dict[str, Optional[float]],
) -> Optional[Dict[str, Any]]:
    """The DRAFT food record the user will confirm. Preview only — not written."""
    food_items = [str(f.get("name")) for f in foods if f.get("name")]
    if not food_items:
        return None
    return {
        "food_items": food_items,
        "calories": totals.get("calories"),
        "protein": totals.get("protein"),
        "carbs": totals.get("carbs"),
        "fat": totals.get("fat"),
        "fiber": totals.get("fiber"),
    }


def build_finish_summary(
    db: Session,
    user_id: int,
    session_id: int,
    *,
    foods: List[Dict[str, Any]],
    totals: Dict[str, Optional[float]],
    frame_count: int,
    vision_calls: int,
) -> Dict[str, Any]:
    """Assemble the DRAFT finish summary (R4 observational, sanitized)."""
    post_meal = post_meal_observational_summary(db, user_id, totals)
    raw_text = post_meal["text"]
    sanitized = sanitize_guidance(raw_text)
    # Run the guidance red-line rules over the PRE-sanitization text so a
    # flagged-and-stripped prescription still yields a CRITICAL/HIGH alert in the
    # summary + audit. The client still receives the sanitized text below.
    guidance_alerts = run_guidance_rules(db, user_id, raw_text)
    return {
        "session_id": session_id,
        "status": "needs_confirmation",
        "target": "diet_draft",
        "frame_count": frame_count,
        "vision_calls": vision_calls,
        "foods": foods,
        "totals": totals,
        "observational_summary": sanitized.text,
        "guidance_sanitized": sanitized.flagged,
        "guidance_violations": sanitized.violations,
        "guidance_alerts": guidance_alerts,
        "draft_diet_record": draft_diet_record_preview(foods, totals),
        "disclaimer": (
            "以下为观察性记录与事后跟进, 非诊断/处方。份量与营养为 AI 估算, "
            "确认前不会写入饮食记录。相关非因果。"
        ),
    }
