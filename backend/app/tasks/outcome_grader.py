"""
ActionCard outcome grading — Specialist 信任循环.

每天 08:00 跑: 找出所有到期未评分的 ActionCard,
拉取对应 metric, 跟 target_value 对比, 算 0-100 的 accuracy_score.

字段约定:
- metric_key: 'sleep_score' | 'hrv' | 'rhr' | 'weight' | 'bp' | 'spo2_odi' | 'alt' | 'ldl' | 'hba1c' | ...
- baseline_value: str — 卡片创建时的起点值 (如 "82kg")
- target_value:   str — specialist 预测/目标值 (如 "80kg" 或 ">90"  或 "<35")
- check_back_date: 评分日期
- actual_value:   评分时实测
- accuracy_score: 0-100, 100=完全命中, 0=完全反向

评分逻辑 (简化版):
  方向正确 + 距离 target < 30% baseline-target 距离 → 100
  方向正确 + 距离更远                              → 50-90 线性
  方向反了                                        → 0-30 (越反越低)
  数据缺失                                        → 跳过, check_back_date 顺延 7 天
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.action_card import ActionCard

logger = logging.getLogger(__name__)


def _parse_numeric(s: Optional[str]) -> Optional[float]:
    """把 '82kg' / '<35' / '>90' / '120/80' 解析成主数值."""
    if not s:
        return None
    # 提取首个数字 (含小数 + 负号)
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _parse_direction(target: Optional[str]) -> str:
    """从 target_value 推断目标方向: '>' / '<' / '='."""
    if not target:
        return "="
    t = target.strip()
    if t.startswith(">") or t.startswith("≥") or "提高" in t or "增加" in t:
        return ">"
    if t.startswith("<") or t.startswith("≤") or "降低" in t or "减少" in t or "减重" in t:
        return "<"
    return "="


def _fetch_metric(db, user_id: int, metric_key: str, on_date: datetime) -> Optional[float]:
    """根据 metric_key 拉取实测值 (评分日附近)."""
    from app.models.daily_health import GarminData
    from app.models.basic_health import BasicHealthData
    from app.models.weight import WeightRecord
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    target_date = on_date.date()
    week_window = target_date - timedelta(days=7)

    # Garmin 日级指标
    if metric_key in {"sleep_score", "hrv", "rhr"}:
        col = {"sleep_score": GarminData.sleep_score,
               "hrv": GarminData.hrv,
               "rhr": GarminData.resting_heart_rate}[metric_key]
        row = db.query(col).filter(
            GarminData.user_id == user_id,
            GarminData.record_date >= week_window,
            GarminData.record_date <= target_date,
            col.isnot(None),
        ).order_by(GarminData.record_date.desc()).first()
        return float(row[0]) if row and row[0] is not None else None

    # 体重 — WeightRecord 优先, 回退 BasicHealthData
    if metric_key == "weight":
        row = db.query(WeightRecord.weight).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date <= target_date,
        ).order_by(WeightRecord.record_date.desc()).first()
        if row:
            return float(row[0])
        row = db.query(BasicHealthData.weight).filter(
            BasicHealthData.user_id == user_id,
            BasicHealthData.weight.isnot(None),
            BasicHealthData.record_date <= target_date,
        ).order_by(BasicHealthData.record_date.desc()).first()
        return float(row[0]) if row else None

    # 血压 / 血脂 / 血糖 — BasicHealthData 列
    bhd_cols = {
        "bp": BasicHealthData.systolic_bp,
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
        # item_code 直接匹配 (大写) 或 item_name 含关键字
        upper = metric_key.upper().replace("_", "")
        item = db.query(MedicalExamItem.value).join(MedicalExam).filter(
            MedicalExam.user_id == user_id,
            MedicalExam.exam_date <= target_date,
            MedicalExamItem.value.isnot(None),
            (MedicalExamItem.item_code.ilike(f"%{upper}%") |
             MedicalExamItem.item_name.ilike(f"%{metric_key}%")),
        ).order_by(MedicalExam.exam_date.desc()).first()
        return float(item[0]) if item else None

    return None


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


def _grade_loop(db, now: datetime) -> dict:
    """核心循环, 与 Celery / 测试 都可复用."""
    graded = 0
    skipped_no_data = 0

    cards = db.query(ActionCard).filter(
        ActionCard.check_back_date.isnot(None),
        ActionCard.check_back_date <= now,
        ActionCard.graded_at.is_(None),
        ActionCard.metric_key.isnot(None),
        ActionCard.target_value.isnot(None),
    ).all()

    logger.info(f"[OutcomeGrader] {len(cards)} cards 到期待评")

    for card in cards:
        actual = _fetch_metric(db, card.user_id, card.metric_key, now)
        if actual is None:
            card.check_back_date = now + timedelta(days=3)
            card.grading_notes = (card.grading_notes or "") + \
                f"\n[{now.strftime('%Y-%m-%d')}] 数据缺失，复查日期顺延 3 天"
            skipped_no_data += 1
            continue

        baseline = _parse_numeric(card.baseline_value)
        target = _parse_numeric(card.target_value)
        direction = _parse_direction(card.target_value)
        score, note = _grade(baseline, target, actual, direction)

        card.actual_value = f"{actual:g}"
        card.accuracy_score = score
        card.graded_at = now
        card.grading_notes = note
        graded += 1

        logger.info(
            f"[OutcomeGrader] card #{card.id} ({card.creator_specialist or 'unknown'}, "
            f"metric={card.metric_key}): score={score} — {note}"
        )

    db.commit()
    logger.info(f"[OutcomeGrader] 完成: graded={graded}, skipped_no_data={skipped_no_data}")
    return {"graded": graded, "skipped_no_data": skipped_no_data}


@celery_app.task(time_limit=300, name="app.tasks.outcome_grader.grade_due_action_cards")
def grade_due_action_cards():
    """每天 8:00 评分所有到期未评分的 ActionCard."""
    with SessionLocal() as db:
        return _grade_loop(db, datetime.now(timezone.utc))
