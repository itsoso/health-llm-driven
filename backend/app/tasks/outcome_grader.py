"""
ActionCard outcome grading — Specialist 信任循环.

每天 08:00 (Asia/Shanghai) 跑: 找出所有到期未评分的 ActionCard,
拉取对应 metric, 跟 target_value 对比, 算 0-100 的 accuracy_score.

字段约定:
- metric_key: 'sleep_score' | 'hrv' | 'rhr' | 'weight' | 'spo2_odi' |
              'systolic_bp' | 'diastolic_bp' | 'alt' | 'ldl' | 'hba1c' | ...
              (注意: 'bp' 已废弃, 请显式使用 'systolic_bp' 或 'diastolic_bp')
- baseline_value: str — 卡片创建时的起点值 (如 "82kg")
- target_value:   str — specialist 预测/目标值 (如 "80kg" 或 ">90"  或 "<35")
- check_back_date: 评分日期 (UTC)
- actual_value:   评分时实测
- accuracy_score: 0-100, 100=完全命中, 0=完全反向

评分逻辑 (简化版):
  方向正确 + 距离 target < 30% baseline-target 距离 → 100
  方向正确 + 距离更远                              → 50-90 线性
  方向反了                                        → 0-30 (越反越低)
  数据缺失 or 仅有陈旧数据                         → 跳过, check_back_date 顺延 3 天

陈旧数据定义 — 每类 metric 有 MAX_AGE_DAYS 上限:
- Garmin 日级 (sleep_score/hrv/rhr): 7 天
- 自测 vitals (weight/bp/glucose/bmi/body_fat): 14 天
- 自测血脂 (ldl/hdl/tc/tg): 90 天 (自测少, 检测间隔长)
- 化验项 (MedicalExamItem): 90 天

时区: grader 按 Asia/Shanghai 派生 target_date, 保证"今天"和用户本地日历对齐.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.action_card import ActionCard
from app.tasks.metrics import grade_outcome

logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# 每类 metric 向前能接受的最旧数据窗口 (单位: 天)
MAX_AGE_DAYS = {
    # Garmin 日级
    "sleep_score": 7, "hrv": 7, "rhr": 7,
    # 自测 vitals
    "weight": 14, "bmi": 14, "body_fat": 14,
    "systolic_bp": 14, "diastolic_bp": 14,
    "fasting_glucose": 14, "blood_glucose": 14,
    # 自测 / 化验血脂 — 检测间隔长
    "ldl": 90, "hdl": 90, "tc": 90, "tg": 90,
}
# 化验项 MedicalExamItem 默认 90 天
EXAM_LAB_MAX_AGE = 90


def _max_age_for(metric_key: str) -> int:
    """返回该 metric 的最大数据陈旧度 (天). 未知 metric 默认 30 天."""
    if metric_key in MAX_AGE_DAYS:
        return MAX_AGE_DAYS[metric_key]
    return 30  # 保守默认


def _parse_numeric(s: Optional[str]) -> Optional[float]:
    """把 '82kg' / '<35' / '>90' / '120/80' 解析成主数值."""
    if not s:
        return None
    # 提取首个数字 (含小数 + 负号)
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _parse_direction(target: Optional[str]) -> str:
    """从 target_value 推断目标方向: '>' / '<' / '='. 支持 <=/>=."""
    if not target:
        return "="
    t = target.strip()
    if t.startswith(">") or t.startswith("≥") or t.startswith(">=") or "提高" in t or "增加" in t:
        return ">"
    if t.startswith("<") or t.startswith("≤") or t.startswith("<=") or "降低" in t or "减少" in t or "减重" in t:
        return "<"
    return "="


def _fetch_metric(db, user_id: int, metric_key: str, on_date: datetime) -> Optional[float]:
    """根据 metric_key 拉取实测值 (评分日附近, 有 max_age floor 防陈旧)."""
    from app.models.daily_health import GarminData
    from app.models.basic_health import BasicHealthData
    from app.models.weight import WeightRecord
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    # target_date 从上海本地日期派生, 避免 UTC-Shanghai 跨日歧义
    shanghai_now = on_date.astimezone(SHANGHAI_TZ) if on_date.tzinfo else on_date.replace(tzinfo=timezone.utc).astimezone(SHANGHAI_TZ)
    target_date = shanghai_now.date()

    max_age = _max_age_for(metric_key)
    floor_date = target_date - timedelta(days=max_age)

    # Garmin 日级指标
    if metric_key in {"sleep_score", "hrv", "rhr"}:
        col = {"sleep_score": GarminData.sleep_score,
               "hrv": GarminData.hrv,
               "rhr": GarminData.resting_heart_rate}[metric_key]
        row = db.query(col).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= floor_date,
            GarminData.record_date <= target_date,
            col.isnot(None),
        ).order_by(GarminData.record_date.desc()).first()
        return float(row[0]) if row and row[0] is not None else None

    # 体重 — WeightRecord 优先, 回退 BasicHealthData
    if metric_key == "weight":
        row = db.query(WeightRecord.weight).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date >= floor_date,
            WeightRecord.record_date <= target_date,
        ).order_by(WeightRecord.record_date.desc()).first()
        if row:
            return float(row[0])
        row = db.query(BasicHealthData.weight).filter(
            BasicHealthData.user_id == user_id,
            BasicHealthData.weight.isnot(None),
            BasicHealthData.record_date >= floor_date,
            BasicHealthData.record_date <= target_date,
        ).order_by(BasicHealthData.record_date.desc()).first()
        return float(row[0]) if row else None

    # 血压 / 血脂 / 血糖 — BasicHealthData 列
    #
    # 注意: 'bp' key 已废弃. 新代码请用 'systolic_bp' + 'diastolic_bp' 双指标明确评分.
    # 留 'bp' 作为 systolic_bp 的 legacy alias 仅为向后兼容历史卡片.
    bhd_cols = {
        "bp": BasicHealthData.systolic_bp,  # DEPRECATED: 等价 systolic_bp
        "systolic_bp": BasicHealthData.systolic_bp,
        "diastolic_bp": BasicHealthData.diastolic_bp,
        "ldl": BasicHealthData.ldl_cholesterol,
        "hdl": BasicHealthData.hdl_cholesterol,
        "tc": BasicHealthData.total_cholesterol,
        "tg": BasicHealthData.triglycerides,
        "fasting_glucose": BasicHealthData.blood_glucose,
        "blood_glucose": BasicHealthData.blood_glucose,
        "bmi": BasicHealthData.bmi,
        "body_fat": BasicHealthData.body_fat_percentage,
    }
    if metric_key in bhd_cols:
        col = bhd_cols[metric_key]
        row = db.query(col).filter(
            BasicHealthData.user_id == user_id,
            col.isnot(None),
            BasicHealthData.record_date >= floor_date,
            BasicHealthData.record_date <= target_date,
        ).order_by(BasicHealthData.record_date.desc()).first()
        return float(row[0]) if row else None

    # 化验项 — MedicalExamItem (按 item_code 或 item_name 模糊)
    exam_lab_keys = {
        "alt", "ast", "ggt", "alp", "creatinine", "uric_acid", "urea",
        "hba1c", "tsh", "ft3", "ft4", "vitamin_d", "b12", "ferritin",
        "crp", "esr", "wbc", "rbc", "hgb", "plt", "lp_a", "apo_b",
    }
    if metric_key in exam_lab_keys:
        exam_floor = target_date - timedelta(days=EXAM_LAB_MAX_AGE)
        # item_code 直接匹配 (大写) 或 item_name 含关键字
        upper = metric_key.upper().replace("_", "")
        item = db.query(MedicalExamItem.value).join(MedicalExam).filter(
            MedicalExam.user_id == user_id,
            MedicalExam.exam_date >= exam_floor,
            MedicalExam.exam_date <= target_date,
            MedicalExamItem.value.isnot(None),
            (MedicalExamItem.item_code.ilike(f"%{upper}%") |
             MedicalExamItem.item_name.ilike(f"%{metric_key}%")),
        ).order_by(MedicalExam.exam_date.desc()).first()
        return float(item[0]) if item else None

    return None


def _grade_bp_dual(
    db, user_id: int, baseline_value: str, target_value: str, on_date: datetime,
) -> Tuple[Optional[int], str]:
    """BP 双指标评分: 解析 '120/80' 形式的 baseline/target, 同时评 systolic + diastolic,
    取较差者作为最终分数.

    返回 (score, note). 若数据缺失返回 (None, reason).
    """
    def _parse_pair(s: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
        if not s:
            return None, None
        m = re.match(r"\s*[<>≤≥]*\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", s)
        if m:
            return float(m.group(1)), float(m.group(2))
        # 只有一个值, 认为是 systolic
        single = _parse_numeric(s)
        return single, None

    base_sys, base_dia = _parse_pair(baseline_value)
    tgt_sys, tgt_dia = _parse_pair(target_value)
    direction = _parse_direction(target_value)

    sys_actual = _fetch_metric(db, user_id, "systolic_bp", on_date)
    dia_actual = _fetch_metric(db, user_id, "diastolic_bp", on_date)

    # 至少收缩压要有目标 + 数据
    if sys_actual is None or tgt_sys is None:
        return None, "数据缺失 (BP 需 systolic + diastolic)"

    sys_score, sys_note = _grade(base_sys, tgt_sys, sys_actual, direction)

    if tgt_dia is None or dia_actual is None:
        # 只评 systolic
        return sys_score, f"仅 systolic 评分: {sys_note}"

    dia_score, dia_note = _grade(base_dia, tgt_dia, dia_actual, direction)
    # 取较差者 (不被高分拉高误判)
    if sys_score <= dia_score:
        return sys_score, f"BP systolic={sys_note} | diastolic={dia_note} (按 systolic 较差)"
    return dia_score, f"BP systolic={sys_note} | diastolic={dia_note} (按 diastolic 较差)"


def _grade(baseline: Optional[float], target: Optional[float], actual: Optional[float],
           direction: str) -> Tuple[int, str]:
    """返回 (0-100 分数, 解释字符串)."""
    if actual is None:
        return 0, "数据缺失，无法评分"
    if target is None:
        return 0, "target 未设置，无法评分"

    if baseline is None:
        # 没起点, 只判方向命中
        if direction == ">" and actual >= target:
            return 100, f"达成: 实测 {actual} ≥ 目标 {target}"
        if direction == "<" and actual <= target:
            return 100, f"达成: 实测 {actual} ≤ 目标 {target}"
        if direction == "=" and abs(actual - target) / max(abs(target), 1) < 0.05:
            return 100, f"达成: 实测 {actual} ≈ 目标 {target}"
        return 30, f"未达成: 实测 {actual} vs 目标 {target}"

    # 完整评分: 看实际相对 baseline 走了 baseline→target 距离的多少 %
    span = target - baseline
    if abs(span) < 0.001:
        return 50, "baseline = target，无法判命中度"

    progress_ratio = (actual - baseline) / span  # 1.0 = 完全达成, 0 = 没动, <0 = 反向

    if progress_ratio >= 1.0:
        return 100, f"达成: {baseline} → {actual} (目标 {target})"
    if progress_ratio >= 0.7:
        return 85, f"接近达成: 走了 {progress_ratio*100:.0f}% ({baseline} → {actual})"
    if progress_ratio >= 0.3:
        return 60, f"部分达成: 走了 {progress_ratio*100:.0f}% ({baseline} → {actual})"
    if progress_ratio > 0:
        return 35, f"轻微改善: 走了 {progress_ratio*100:.0f}% ({baseline} → {actual})"
    if progress_ratio == 0:
        return 25, f"原地踏步: {actual} = baseline {baseline}"
    # 反向
    return max(0, int(20 + progress_ratio * 20)), f"反向: {baseline} → {actual} (目标 {target})"


def _derive_adherence_confidence(card: ActionCard) -> Tuple[int, str]:
    """基于卡片状态 + checklist 勾选率 + adherence_kind 派生 0-100 置信度.

    返回 (confidence_0_100, source_kind).

    规则:
    - 若已显式设置 adherence_confidence (非 None) → 直接用, kind 取字段值
    - else 若有 checklist → 勾完成比例 × 50 (自报信号上限 50)
      (50 不是 100 因为只是 self_reported, 不证明真做到)
    - else → None, 按 100 处理 (兼容历史卡, 不降分)
    """
    if card.adherence_confidence is not None:
        return card.adherence_confidence, (card.adherence_kind or "explicit")

    # 从 checklist 派生
    checklist = card.checklist or []
    if isinstance(checklist, list) and checklist:
        done = sum(1 for item in checklist if (isinstance(item, dict) and item.get("done")))
        total = len(checklist)
        if total > 0:
            pct = int(done / total * 50)  # self-report 上限 50
            return pct, "self_reported"

    return 100, "default"


def _apply_adherence(raw_score: int, card: ActionCard) -> Tuple[int, str]:
    """评分公式: final = accuracy × adherence_confidence / 100.

    返回 (final_score, adherence_note).
    confidence < 30 的卡 final_score 会被显著压低, 让 hit-rate 不被"没做却碰巧改善"污染.
    """
    conf, kind = _derive_adherence_confidence(card)
    if conf >= 100 and kind == "default":
        return raw_score, ""  # 未评估依从度, 不改分

    final = int(round(raw_score * conf / 100))
    note = f" [adherence={kind} {conf}%]"
    return final, note


def _notify_prediction_hit(db, card: ActionCard) -> bool:
    """评分命中 → 主动推 APNs, 让用户感知 AI 在押注 + 兑现.

    仅在 accuracy_score >= 70 时推 (hit). 未命中暂不推 (避免负面噪声).
    Severity='info' 因此 quiet hours 会拦, 这是设计上的折中:
    用户睡觉时 AI 押中 HRV 不该吵醒.

    Returns: True 推送成功 (或被 quiet/dedup 静默吞掉, 算正常路径); False 异常.
    """
    from app.services.outcome_safety import is_efficacy_score_eligible_card

    if not is_efficacy_score_eligible_card(card):
        return False
    if card.accuracy_score is None or card.accuracy_score < 70:
        return False
    if not card.creator_specialist:
        return False  # 没归属, 不推 (没法 deep link 到 scorecard)

    try:
        import asyncio

        from app.services.notification.push_service import PushService

        push = PushService(db)
        title = "AI 上次预测命中 ✓"
        # body 用最少必要信息: specialist + 指标 + 实测/目标
        target = card.target_value or "?"
        actual = card.actual_value or "?"
        body = f"{card.creator_specialist}: {card.metric_key} 实测 {actual} (目标 {target})"

        # data 字段给 Mobile 深链到 scorecard
        from app.services.notification.evidence_policy import build_notification_evidence_data
        data = {
            "kind": "prediction_verified",
            "card_id": card.id,
            "specialist": card.creator_specialist,
            "accuracy_score": card.accuracy_score,
            "deep_link": f"/specialist/{card.creator_specialist}",
        }
        data = build_notification_evidence_data(
            notification_type="prediction_verified",
            source="outcome_grader.grade_due_cards",
            existing_data=data,
            evidence_refs=card.evidence_refs or [],
            evidence_domain=card.creator_specialist,
        )

        # 已有事件循环时 (Celery worker) 直接 run; 测试里不应跑真 push
        result = asyncio.run(push.send_notification(
            user_id=card.user_id,
            notification_type="prediction_verified",
            title=title,
            content=body,
            data=data,
            severity="info",
            dedup_window_hours=24,  # 同一卡 24h 内只推一次, 防 grader 重跑
            respect_quiet_hours=True,
        ))
        ok = bool(result.get("success"))
        logger.info(
            f"[OutcomeGrader] hit push card #{card.id} ({card.creator_specialist}): "
            f"ok={ok} reason={result.get('reason') or '-'}"
        )
        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[OutcomeGrader] hit push 异常 (跳过, 不影响评分): {e}")
        return False


def grade_single_card(db, card: ActionCard, now: datetime) -> dict:
    """Grade one due ActionCard in-place.

    Returns:
        {"status": "graded" | "skipped_no_data", "pushed": bool, "note": str}

    This is used by the scheduled batch grader and by interactive opener quick
    replies, where the user answers "做到了/没做" and expects the specific card
    they are looking at to be verified immediately.
    """
    from app.services.outcome_safety import (
        clinician_review_grading_note,
        is_efficacy_score_eligible_card,
    )

    if not is_efficacy_score_eligible_card(card):
        actual = _fetch_metric(db, card.user_id, card.metric_key, now)
        if actual is not None:
            card.actual_value = f"{actual:g}"
        card.accuracy_score = None
        card.outcome = "inconclusive"
        card.effect_size = None
        card.graded_at = now
        card.grading_notes = clinician_review_grading_note(card.metric_key)
        logger.info(
            "[OutcomeGrader] card #%s metric=%s requires clinician review; "
            "excluded from efficacy scoring",
            card.id,
            card.metric_key,
        )
        return {
            "status": "clinician_review",
            "pushed": False,
            "note": card.grading_notes,
        }

    if card.metric_key == "bp" and card.target_value and "/" in card.target_value:
        score, note = _grade_bp_dual(
            db, card.user_id, card.baseline_value or "", card.target_value, now,
        )
        if score is None:
            card.check_back_date = now + timedelta(days=3)
            card.grading_notes = (card.grading_notes or "") + \
                f"\n[{now.strftime('%Y-%m-%d')}] {note}, 复查日期顺延 3 天"
            return {"status": "skipped_no_data", "pushed": False, "note": note}

        final_score, adh_note = _apply_adherence(score, card)
        card.accuracy_score = final_score
        card.graded_at = now
        card.grading_notes = note + adh_note
        sys_actual = _fetch_metric(db, card.user_id, "systolic_bp", now)
        base_sys_num = _parse_numeric((card.baseline_value or "").split("/")[0])
        if sys_actual is not None and base_sys_num is not None:
            card.outcome, card.effect_size = grade_outcome(
                "systolic_bp", str(base_sys_num), sys_actual,
            )
        logger.info(
            f"[OutcomeGrader] card #{card.id} ({card.creator_specialist or 'unknown'}, "
            f"metric=bp-dual): score={final_score} (raw {score}) — {note}{adh_note}"
        )
        pushed = _notify_prediction_hit(db, card)
        return {"status": "graded", "pushed": pushed, "note": note + adh_note}

    actual = _fetch_metric(db, card.user_id, card.metric_key, now)
    if actual is None:
        card.check_back_date = now + timedelta(days=3)
        max_age = _max_age_for(card.metric_key)
        note = f"{card.metric_key} 无 {max_age} 天内数据，复查顺延 3 天"
        card.grading_notes = (card.grading_notes or "") + \
            f"\n[{now.strftime('%Y-%m-%d')}] {note}"
        return {"status": "skipped_no_data", "pushed": False, "note": note}

    baseline = _parse_numeric(card.baseline_value)
    target = _parse_numeric(card.target_value)
    direction = _parse_direction(card.target_value)
    score, note = _grade(baseline, target, actual, direction)

    final_score, adh_note = _apply_adherence(score, card)

    card.actual_value = f"{actual:g}"
    card.accuracy_score = final_score
    card.graded_at = now
    card.grading_notes = note + adh_note
    if baseline is not None:
        card.outcome, card.effect_size = grade_outcome(
            card.metric_key, str(baseline), actual,
        )
    logger.info(
        f"[OutcomeGrader] card #{card.id} ({card.creator_specialist or 'unknown'}, "
        f"metric={card.metric_key}): score={final_score} (raw {score}) — {note}{adh_note}"
    )

    try:
        from app.services.memory_extractor import extract_from_action_card_outcome
        extract_from_action_card_outcome(db, card)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[OutcomeGrader] memory extract 失败 (跳过): {e}")

    pushed = _notify_prediction_hit(db, card)
    return {"status": "graded", "pushed": pushed, "note": note + adh_note}


def _grade_loop(db, now: datetime) -> dict:
    """核心循环, 与 Celery / 测试 都可复用."""
    graded = 0
    skipped_no_data = 0
    pushed = 0

    cards = db.query(ActionCard).filter(
        ActionCard.check_back_date.isnot(None),
        ActionCard.check_back_date <= now,
        ActionCard.graded_at.is_(None),
        ActionCard.metric_key.isnot(None),
        ActionCard.target_value.isnot(None),
    ).all()

    logger.info(f"[OutcomeGrader] {len(cards)} cards 到期待评")

    for card in cards:
        result = grade_single_card(db, card, now)
        if result["status"] == "skipped_no_data":
            skipped_no_data += 1
            continue
        graded += 1
        if result["pushed"]:
            pushed += 1

    db.commit()
    logger.info(
        f"[OutcomeGrader] 完成: graded={graded}, skipped_no_data={skipped_no_data}, pushed={pushed}"
    )
    return {"graded": graded, "skipped_no_data": skipped_no_data, "pushed": pushed}


@celery_app.task(time_limit=300, name="app.tasks.outcome_grader.grade_due_action_cards")
def grade_due_action_cards():
    """每天 08:00 (Asia/Shanghai) 评分所有到期未评分的 ActionCard."""
    with SessionLocal() as db:
        return _grade_loop(db, datetime.now(timezone.utc))
