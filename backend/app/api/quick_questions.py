"""动态快速问题 API — 基于用户当前状态实时排序"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.services.health_context_lite_service import _get_time_period

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quick-questions", tags=["quick-questions"])

# 所有候选快速问题
ALL_QUESTIONS = [
    {"id": "morning_briefing", "label": "早间简报", "text": "给我一份今日早间健康简报", "eyebrow": "每日简报", "summary": "综合睡眠、恢复、天气，规划今天的健康节奏。", "periods": ["清晨", "上午"]},
    {"id": "evening_review", "label": "今日总结", "text": "帮我回顾一下今天的健康数据", "eyebrow": "每日总结", "summary": "回顾全天步数、饮食、饮水、运动，给出改进点。", "periods": ["晚上", "深夜"]},
    {"id": "overview", "label": "今日概览", "text": "查一下我今天的健康数据概览", "eyebrow": "实时查询", "summary": "拉取今天的关键数据、打卡状态和待办提醒。", "periods": ["中午", "下午"]},
    {"id": "exercise", "label": "运动建议", "text": "根据我的身体数据和天气，今天适合做什么运动？", "eyebrow": "训练安排", "summary": "结合恢复状态、天气和最近训练，给出最合适的建议。", "periods": []},
    {"id": "sleep", "label": "睡眠分析", "text": "帮我分析一下最近的睡眠质量，有什么改善建议？", "eyebrow": "恢复质量", "summary": "把睡眠、压力和日间表现放到同一个结论里看。", "periods": []},
    {"id": "diet", "label": "饮食建议", "text": "根据我的健康目标，今天午餐吃什么好？", "eyebrow": "营养策略", "summary": "围绕目标和今日已摄入，推荐具体的餐食方案。", "periods": []},
    {"id": "diet_record", "label": "记录饮食", "text": "帮我记录一下刚才吃的东西", "eyebrow": "快速记录", "summary": "快速记录这一餐的内容和热量。", "periods": []},
    {"id": "water", "label": "记录饮水", "text": "记录喝水250ml", "eyebrow": "快速记录", "summary": "一句话完成记录，不用跳页面。", "periods": []},
    {"id": "post_workout", "label": "运动完成", "text": "我刚运动完，帮我同步Garmin数据并分析本次训练，给出恢复建议", "eyebrow": "即时分析", "summary": "触发 Garmin 同步、训练总结和恢复建议。", "periods": []},
    {"id": "weekly_plan", "label": "本周计划", "text": "帮我看看本周计划的完成情况", "eyebrow": "目标追踪", "summary": "检查本周健康计划进度和待完成项。", "periods": []},
    {"id": "supplement", "label": "补剂提醒", "text": "今天的补剂都吃了吗？", "eyebrow": "补剂管理", "summary": "检查今日补剂服用状态，提醒未服用的。", "periods": []},
    {"id": "trend", "label": "健康趋势", "text": "分析我最近一周的健康趋势变化", "eyebrow": "趋势洞察", "summary": "发现指标变化方向，预判潜在问题。", "periods": []},
    {"id": "alert", "label": "查看预警", "text": "有没有需要关注的健康预警？", "eyebrow": "异常检测", "summary": "检查近期异常指标和未确认的预警。", "periods": []},
    {"id": "stress", "label": "压力管理", "text": "今天压力有点大，有什么放松建议？", "eyebrow": "情绪关怀", "summary": "结合压力数据，给出针对性的放松和减压建议。", "periods": []},
    # 病情追踪 — 动态生成，见 _build_illness_questions()
]


def _build_illness_questions(db: Session, user_id: int) -> list:
    """根据用户活跃疾病档案动态生成病情追踪问题"""
    try:
        from app.models.disease_tracking import UserDiseaseProfile
        diseases = db.query(UserDiseaseProfile).filter(
            UserDiseaseProfile.user_id == user_id,
            UserDiseaseProfile.tracking_enabled == True,
            UserDiseaseProfile.status.in_(["chronic", "improving"]),
        ).all()
        questions = []
        for d in diseases:
            questions.append({
                "id": f"illness_{d.id}",
                "label": "病情追踪",
                "text": f"我的{d.disease_name}好些了吗？需要调整什么？",
                "eyebrow": "健康追踪",
                "summary": f"追踪{d.disease_name}的最新状况，检查用药和症状变化。",
                "periods": [],
            })
        return questions
    except Exception:
        return []


@router.get("/me", summary="获取个性化快速问题")
async def get_quick_questions(
    limit: int = 6,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """根据用户当前状态和时段返回排序后的快速问题"""
    today = date.today()
    _, period = _get_time_period()
    scored = []

    # 查询用户状态用于评分
    water_pct = 0
    has_alerts = False
    supplement_pending = False
    plan_pct = 100
    recent_workout = False
    today_steps = 0
    target_steps = 8000
    target_water_ml = 2000
    has_diet_today = False
    stress_high = False

    try:
        from app.models.daily_health import WaterIntake, WorkoutRecord, GarminData, DietRecord
        water_today = db.query(WaterIntake).filter(
            WaterIntake.user_id == current_user.id,
            WaterIntake.record_date == today,
        ).all()
        total_ml = sum(w.amount_ml or w.amount or 0 for w in water_today)

        # 加载用户目标
        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == current_user.id,
        ).first()
        if profile:
            target_water_ml = profile.target_water_ml or 2000
            target_steps = profile.target_steps or 8000
        water_pct = min(100, total_ml * 100 // target_water_ml) if total_ml else 0

        from app.models.anomaly_alert import AnomalyAlert
        has_alerts = db.query(AnomalyAlert).filter(
            AnomalyAlert.user_id == current_user.id,
            AnomalyAlert.detection_date >= today - timedelta(days=3),
            AnomalyAlert.acknowledged == False,
        ).count() > 0

        from app.models.supplement import SupplementDefinition, SupplementRecord
        active_supps = db.query(SupplementDefinition).filter(
            SupplementDefinition.user_id == current_user.id,
            SupplementDefinition.is_active == True,
        ).count()
        taken_supps = db.query(SupplementRecord).filter(
            SupplementRecord.user_id == current_user.id,
            SupplementRecord.record_date == today,
            SupplementRecord.taken == True,
        ).count()
        supplement_pending = active_supps > 0 and taken_supps < active_supps

        recent_workout = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == current_user.id,
            WorkoutRecord.workout_date == today,
        ).count() > 0

        # 今日 Garmin 数据：步数和压力
        garmin_today = db.query(GarminData).filter(
            GarminData.user_id == current_user.id,
            GarminData.record_date == today,
        ).first()
        if garmin_today:
            today_steps = garmin_today.steps or 0
            stress_high = (garmin_today.stress_level or 0) > 60

        # 今日是否有饮食记录
        has_diet_today = db.query(DietRecord).filter(
            DietRecord.user_id == current_user.id,
            DietRecord.record_date == today,
        ).count() > 0
    except Exception:
        pass

    # 动态生成病情追踪问题
    illness_questions = _build_illness_questions(db, current_user.id)
    all_candidates = list(ALL_QUESTIONS) + illness_questions

    for q in all_candidates:
        score = 50  # 基础分

        # 时段匹配加分
        if q["periods"] and period in q["periods"]:
            score += 40
        elif q["periods"] and period not in q["periods"]:
            score -= 20

        # ── 状态驱动评分 ──

        # 饮水：基于用户目标进度
        if q["id"] == "water" and water_pct < 50:
            score += 30
        elif q["id"] == "water" and water_pct >= 80:
            score -= 30

        if q["id"] == "alert" and has_alerts:
            score += 50
        elif q["id"] == "alert" and not has_alerts:
            score -= 30

        if q["id"] == "supplement" and supplement_pending:
            score += 35
        elif q["id"] == "supplement" and not supplement_pending:
            score -= 20

        if q["id"] == "post_workout" and recent_workout:
            score += 30

        # 运动建议：已运动降分，未运动且下午加分
        if q["id"] == "exercise":
            if recent_workout:
                score -= 25
            elif period in ("下午", "晚上") and today_steps < target_steps * 0.5:
                score += 25

        # 步数不足时也给运动建议加分（与上面叠加）
        if q["id"] == "exercise" and today_steps < target_steps * 0.5 and not recent_workout:
            score += 10

        # 饮食记录：今日无记录时加分
        if q["id"] == "diet_record":
            if not has_diet_today:
                score += 25
            else:
                score -= 15

        # 压力管理：Garmin 压力 > 60 时浮现
        if q["id"] == "stress":
            if stress_high:
                score += 35
            else:
                score -= 30

        # 病情追踪：固定中等分数
        if q["id"].startswith("illness_"):
            score += 15

        scored.append((score, q))

    scored.sort(key=lambda x: -x[0])
    result = [q for _, q in scored[:limit]]

    # 移除内部字段
    return [
        {k: v for k, v in q.items() if k != "periods"}
        for q in result
    ]
