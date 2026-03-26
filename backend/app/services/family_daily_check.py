"""家庭每日健康巡检 — 自动检查所有家庭成员状态并推送提醒

每天早上 8:30 自动执行：
1. 检查每个家庭成员的健康数据异常
2. 检查用药是否按时
3. 检查复查日历（过期 / 即将到期）
4. 检查穿戴设备数据趋势
5. 生成管理员汇总 + 各成员口语化提醒
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_family_daily_check(db: Session, owner_user_id: int) -> Dict[str, Any]:
    """
    执行一次家庭健康巡检。

    Args:
        db: 数据库会话
        owner_user_id: 家庭组创建者的 user_id

    Returns:
        巡检报告 {admin_summary, member_reports: [{user_id, name, alerts, todos}]}
    """
    from app.models.family import FamilyGroup, FamilyMember
    from app.models.user import User

    group = db.query(FamilyGroup).filter(FamilyGroup.owner_id == owner_user_id).first()
    if not group:
        return {"admin_summary": "未找到家庭组", "member_reports": []}

    members = db.query(FamilyMember).filter(FamilyMember.family_group_id == group.id).all()
    today = date.today()

    member_reports = []
    admin_alerts = []

    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        if not user:
            continue

        name = m.nickname or user.name
        report = {
            "user_id": m.user_id,
            "name": name,
            "relationship": m.relationship_type,
            "alerts": [],
            "todos": [],
        }

        # ── 1. 健康数据异常 ──────────────────────────
        try:
            from app.models.daily_health import GarminData
            latest = db.query(GarminData).filter(
                GarminData.user_id == m.user_id
            ).order_by(GarminData.record_date.desc()).first()

            if latest and latest.record_date >= today - timedelta(days=2):
                if latest.spo2_avg and latest.spo2_avg < 95:
                    alert = f"血氧 {latest.spo2_avg}% 偏低"
                    report["alerts"].append(alert)
                    admin_alerts.append(f"{name}: {alert}")

                if latest.resting_heart_rate and latest.resting_heart_rate > 90:
                    alert = f"静息心率 {latest.resting_heart_rate} 偏高"
                    report["alerts"].append(alert)
                    admin_alerts.append(f"{name}: {alert}")

                if latest.sleep_score and latest.sleep_score < 50:
                    alert = f"睡眠评分仅 {latest.sleep_score}"
                    report["alerts"].append(alert)
                    admin_alerts.append(f"{name}: {alert}")

                if latest.hrv and latest.hrv_status == "low":
                    alert = f"HRV {latest.hrv:.0f}ms 偏低"
                    report["alerts"].append(alert)
        except Exception as e:
            logger.warning(f"检查 {name} 健康数据失败: {e}")

        # ── 2. 用药提醒 ──────────────────────────────
        try:
            from app.models.medication import Medication, MedicationLog
            active_meds = db.query(Medication).filter(
                Medication.user_id == m.user_id,
                Medication.is_active == True,
            ).all()

            for med in active_meds:
                taken = db.query(MedicationLog).filter(
                    MedicationLog.medication_id == med.id,
                    MedicationLog.taken_date == today,
                    MedicationLog.status == "taken",
                ).first()
                if not taken:
                    report["todos"].append(f"服药: {med.name} {med.dosage or ''}")
        except Exception as e:
            logger.warning(f"检查 {name} 用药失败: {e}")

        # ── 3. 复查日历 ──────────────────────────────
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
                alert = f"复查过期 {days} 天: {r.item_name}"
                report["alerts"].append(alert)
                admin_alerts.append(f"{name}: {alert}")

            for r in upcoming:
                days = (r.next_due_date - today).days
                report["todos"].append(f"复查将到期({days}天后): {r.item_name}")
        except Exception as e:
            logger.warning(f"检查 {name} 复查日历失败: {e}")

        # ── 4. 未读健康预警 ──────────────────────────
        try:
            from app.models.anomaly_alert import AnomalyAlert
            unread = db.query(AnomalyAlert).filter(
                AnomalyAlert.user_id == m.user_id,
                AnomalyAlert.acknowledged == False,
                AnomalyAlert.detection_date >= today - timedelta(days=3),
            ).count()
            if unread > 0:
                report["todos"].append(f"{unread} 条未读健康预警")
        except Exception:
            pass

        # ── 5. 饮水提醒（下午才提醒） ─────────────────
        try:
            from app.models.daily_health import WaterIntake
            from datetime import datetime, timezone, timedelta as td
            beijing_hour = datetime.now(timezone(td(hours=8))).hour
            if beijing_hour >= 14:
                water = db.query(WaterIntake).filter(
                    WaterIntake.user_id == m.user_id,
                    WaterIntake.record_date == today,
                ).all()
                total_ml = sum(w.amount_ml or 0 for w in water)
                if total_ml < 1000:
                    report["todos"].append(f"今日饮水仅 {total_ml}ml，记得多喝水")
        except Exception:
            pass

        member_reports.append(report)

    # 生成管理员汇总
    if admin_alerts:
        admin_summary = f"⚠️ 今日家庭健康提醒（{len(admin_alerts)} 项需关注）:\n" + "\n".join(f"• {a}" for a in admin_alerts)
    else:
        admin_summary = "✅ 今日家庭成员健康状况良好，无异常。"

    return {
        "admin_summary": admin_summary,
        "admin_alert_count": len(admin_alerts),
        "member_reports": member_reports,
        "check_date": str(today),
    }


def generate_member_message(report: Dict) -> Optional[str]:
    """为单个家庭成员生成口语化提醒消息（发微信用）"""
    name = report["name"]
    alerts = report.get("alerts", [])
    todos = report.get("todos", [])

    if not alerts and not todos:
        return None

    parts = [f"{name}，早上好！"]

    if alerts:
        parts.append("需要注意：")
        for a in alerts:
            parts.append(f"  ⚠️ {a}")

    if todos:
        parts.append("今日待办：")
        for t in todos[:5]:  # 最多 5 条
            parts.append(f"  📋 {t}")

    parts.append("祝您健康平安！")
    return "\n".join(parts)


async def send_family_daily_brief(db: Session, owner_user_id: int):
    """
    执行家庭巡检并推送：
    - 给管理员推送汇总
    - 给每个有微信 openid 的成员推送个人提醒
    """
    report = run_family_daily_check(db, owner_user_id)

    try:
        from app.services.notification.push_service import PushService
        push = PushService(db)

        # 1. 给管理员推送汇总
        await push.send_notification(
            user_id=owner_user_id,
            notification_type="family_daily_brief",
            title="家庭健康日报",
            content=report["admin_summary"][:200],
        )
        logger.info(f"家庭日报已推送给管理员 user_id={owner_user_id}")

        # 2. 给每个成员推送个人提醒
        for mr in report["member_reports"]:
            msg = generate_member_message(mr)
            if msg and mr["user_id"] != owner_user_id:
                try:
                    await push.send_notification(
                        user_id=mr["user_id"],
                        notification_type="family_health_reminder",
                        title="健康提醒",
                        content=msg[:200],
                    )
                    logger.info(f"个人提醒已推送给 {mr['name']} (user_id={mr['user_id']})")
                except Exception as e:
                    logger.warning(f"推送给 {mr['name']} 失败: {e}")

    except Exception as e:
        logger.error(f"家庭日报推送失败: {e}", exc_info=True)

    return report
