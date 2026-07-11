"""家庭每周健康摘要 — 生成结构化的家庭健康周报并推送

每周日晚 20:00 北京时间自动执行：
- 汇总每个家庭成员本周的健康数据
- 对比上周趋势
- 标注需要关注的事项
- 生成口语化摘要推送给管理员
"""
import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)


def generate_weekly_digest(db: Session, owner_user_id: int) -> Dict[str, Any]:
    """
    生成家庭健康周报。

    Returns:
        {
            "week": "2026-03-20 ~ 2026-03-26",
            "family_name": "李家",
            "members": [{name, summary, highlights, concerns}],
            "digest_text": "口语化的完整周报文本",
        }
    """
    from app.models.family import FamilyGroup, FamilyMember
    from app.models.user import User

    group = db.query(FamilyGroup).filter(FamilyGroup.owner_id == owner_user_id).first()
    if not group:
        return {"digest_text": "未找到家庭组", "members": []}

    members = db.query(FamilyMember).filter(FamilyMember.family_group_id == group.id).all()
    today = date.today()
    week_start = today - timedelta(days=7)

    digest_parts = [f"📊 {group.name}健康周报 ({week_start.strftime('%m/%d')} - {today.strftime('%m/%d')})"]
    digest_parts.append("")

    member_reports = []

    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        if not user:
            continue

        name = m.nickname or user.name
        report = {"name": name, "user_id": m.user_id, "highlights": [], "concerns": []}

        # ── 运动数据（Garmin） ────────────────────
        try:
            from app.models.daily_health import GarminData
            week_data = db.query(GarminData).filter(
                GarminData.user_id == m.user_id,
                GarminData.record_date >= week_start,
                GarminData.record_date <= today,
            ).all()

            if week_data:
                steps = [d.steps for d in week_data if d.steps]
                sleep_scores = [d.sleep_score for d in week_data if d.sleep_score]
                rhr_list = [d.resting_heart_rate for d in week_data if d.resting_heart_rate]

                if steps:
                    avg_steps = sum(steps) // len(steps)
                    report["avg_steps"] = avg_steps
                    if avg_steps >= 8000:
                        report["highlights"].append(f"步数达标 {avg_steps}/天")
                    elif avg_steps < 4000:
                        report["concerns"].append(f"步数偏低 {avg_steps}/天，建议多走动")

                if sleep_scores:
                    avg_sleep = sum(sleep_scores) // len(sleep_scores)
                    report["avg_sleep_score"] = avg_sleep
                    if avg_sleep >= 80:
                        report["highlights"].append(f"睡眠质量好 {avg_sleep}分")
                    elif avg_sleep < 60:
                        report["concerns"].append(f"睡眠质量偏低 {avg_sleep}分")

                if rhr_list:
                    avg_rhr = sum(rhr_list) // len(rhr_list)
                    report["avg_rhr"] = avg_rhr
                    if avg_rhr > 80:
                        report["concerns"].append(f"静息心率偏高 {avg_rhr}bpm")
        except Exception as e:
            logger.warning(f"周报 {name} 运动数据获取失败: {e}")

        # ── 饮水 ────────────────────────────────
        try:
            from app.models.daily_health import WaterIntake
            water_records = db.query(
                WaterIntake.record_date,
                func.sum(WaterIntake.amount_ml).label("total")
            ).filter(
                WaterIntake.user_id == m.user_id,
                WaterIntake.record_date >= week_start,
            ).group_by(WaterIntake.record_date).all()

            if water_records:
                avg_water = sum(r.total or 0 for r in water_records) // len(water_records)
                report["avg_water_ml"] = avg_water
                if avg_water < 1500:
                    report["concerns"].append(f"饮水不足 平均{avg_water}ml/天")
        except Exception:
            pass

        # ── 用药 ────────────────────────────────
        try:
            from app.models.medication import Medication, MedicationLog
            active_meds = db.query(Medication).filter(
                Medication.user_id == m.user_id,
                Medication.is_active == True,
            ).count()

            if active_meds > 0:
                taken_count = db.query(MedicationLog).filter(
                    MedicationLog.user_id == m.user_id,
                    MedicationLog.taken_date >= week_start,
                    MedicationLog.status == "taken",
                ).count()
                expected = active_meds * 7
                rate = taken_count * 100 // expected if expected > 0 else 0
                report["med_compliance"] = rate
                if rate >= 90:
                    report["highlights"].append(f"服药规律 {rate}%")
                elif rate < 70:
                    report["concerns"].append(f"服药不规律 {rate}%，请督促按时服药")
        except Exception:
            pass

        # ── 复查到期 ────────────────────────────
        try:
            from app.models.family_health import ReviewSchedule
            overdue = db.query(ReviewSchedule).filter(
                ReviewSchedule.user_id == m.user_id,
                ReviewSchedule.is_active == True,
                ReviewSchedule.status != "completed",
                ReviewSchedule.next_due_date < today,
            ).all()

            upcoming = db.query(ReviewSchedule).filter(
                ReviewSchedule.user_id == m.user_id,
                ReviewSchedule.is_active == True,
                ReviewSchedule.status != "completed",
                ReviewSchedule.next_due_date >= today,
                ReviewSchedule.next_due_date <= today + timedelta(days=14),
            ).all()

            for r in overdue:
                days = (today - r.next_due_date).days
                report["concerns"].append(f"复查过期 {days} 天: {r.item_name}")
            for r in upcoming:
                days = (r.next_due_date - today).days
                report["highlights"].append(f"复查即将到期({days}天): {r.item_name}")
        except Exception:
            pass

        # ── 体检指标异常 ────────────────────────
        try:
            from app.models.family_health import MedicalIndicator
            recent_abnormal = db.query(MedicalIndicator).filter(
                MedicalIndicator.user_id == m.user_id,
                MedicalIndicator.is_abnormal == True,
            ).order_by(MedicalIndicator.record_date.desc()).limit(3).all()

            for ind in recent_abnormal:
                report["concerns"].append(f"体检异常: {ind.name} {ind.value}{ind.unit or ''} ({ind.record_date})")
        except Exception:
            pass

        # ── 生成成员小结 ────────────────────────
        member_text = f"👤 {name}"
        if report["highlights"]:
            member_text += "\n  ✅ " + " | ".join(report["highlights"])
        if report["concerns"]:
            member_text += "\n  ⚠️ " + "\n  ⚠️ ".join(report["concerns"])
        if not report["highlights"] and not report["concerns"]:
            member_text += "\n  📊 本周数据不足，建议多记录"

        report["summary_text"] = member_text
        member_reports.append(report)
        digest_parts.append(member_text)
        digest_parts.append("")

    # 总结
    total_concerns = sum(len(r["concerns"]) for r in member_reports)
    if total_concerns > 0:
        digest_parts.append(f"📌 本周共 {total_concerns} 项需关注，请及时处理。")
    else:
        digest_parts.append("✅ 本周全家健康状况良好！")

    digest_text = "\n".join(digest_parts)

    return {
        "week": f"{week_start} ~ {today}",
        "family_name": group.name,
        "members": member_reports,
        "digest_text": digest_text,
        "total_concerns": total_concerns,
    }


async def send_weekly_digest(db: Session, owner_user_id: int):
    """生成并推送每周健康摘要"""
    digest = generate_weekly_digest(db, owner_user_id)

    try:
        from app.services.notification.push_service import PushService
        push = PushService(db)
        # §5 推送隐私:digest_text 含"体检异常: {指标名}"(化验/体检项目名可泄露
        # 诊断线索),锁屏推送只给计数级摘要;全文在应用内周报页解锁后查看。
        total_concerns = digest.get("total_concerns", 0)
        if total_concerns > 0:
            push_content = f"本周家庭健康周报已生成,共 {total_concerns} 项需关注,打开查看详情。"
        else:
            push_content = "本周家庭健康周报已生成,全家健康状况良好,打开查看详情。"
        await push.send_notification(
            user_id=owner_user_id,
            notification_type="family_weekly_digest",
            title="家庭健康周报",
            content=push_content,
        )
        logger.info(f"家庭周报已推送 owner={owner_user_id}, concerns={digest['total_concerns']}")
    except Exception as e:
        logger.error(f"家庭周报推送失败: {e}", exc_info=True)

    return digest
