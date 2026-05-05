"""用药管理服务"""
import logging
from typing import Dict, Any, List, Optional
from datetime import date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.medication import Medication, MedicationLog

logger = logging.getLogger(__name__)


class MedicationService:
    """用药管理服务"""

    def add_medication(
        self,
        db: Session,
        user_id: int,
        data: Dict[str, Any],
    ) -> Medication:
        """添加药品"""
        logger.info(f"[Medication] 添加药品: user={user_id}, name={data.get('name')}")

        med = Medication(
            user_id=user_id,
            name=data["name"],
            dosage=data.get("dosage"),
            frequency=data.get("frequency"),
            times_per_day=data.get("times_per_day", 1),
            reminder_times=data.get("reminder_times"),
            category=data.get("category"),
            purpose=data.get("purpose"),
            side_effects=data.get("side_effects"),
            interactions=data.get("interactions"),
            start_date=data.get("start_date", date.today()),
            end_date=data.get("end_date"),
            notes=data.get("notes"),
            is_active=True,
        )
        db.add(med)
        db.commit()
        db.refresh(med)
        logger.info(f"[Medication] 药品已添加: id={med.id}")
        return med

    def get_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
    ) -> Optional[Medication]:
        """获取药品详情"""
        return db.query(Medication).filter(
            Medication.id == medication_id,
            Medication.user_id == user_id,
        ).first()

    def list_medications(
        self,
        db: Session,
        user_id: int,
        active_only: bool = True,
    ) -> List[Medication]:
        """列出用户药品"""
        logger.info(f"[Medication] 列出药品: user={user_id}, active_only={active_only}")
        query = db.query(Medication).filter(Medication.user_id == user_id)
        if active_only:
            query = query.filter(Medication.is_active == True)
        return query.order_by(desc(Medication.created_at)).all()

    def update_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
        data: Dict[str, Any],
    ) -> Optional[Medication]:
        """更新药品信息"""
        logger.info(f"[Medication] 更新药品: id={medication_id}, user={user_id}")
        med = self.get_medication(db, medication_id, user_id)
        if not med:
            return None

        updatable = ["name", "dosage", "frequency", "times_per_day", "reminder_times",
                      "category", "purpose", "side_effects", "interactions",
                      "start_date", "end_date", "notes"]
        for key in updatable:
            if key in data:
                setattr(med, key, data[key])

        db.commit()
        db.refresh(med)
        return med

    def deactivate_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
    ) -> bool:
        """停用药品"""
        logger.info(f"[Medication] 停用药品: id={medication_id}, user={user_id}")
        med = self.get_medication(db, medication_id, user_id)
        if not med:
            return False
        med.is_active = False
        med.end_date = date.today()
        db.commit()
        return True

    def reactivate_medication(
        self,
        db: Session,
        medication_id: int,
        user_id: int,
    ) -> bool:
        """恢复已停用药品 (误点击回滚用).

        不受 is_active=True/False 过滤影响 — 直接查 id + user 所有权.
        恢复后清 end_date, 让药品回到 '在用' 状态.
        """
        logger.info(f"[Medication] 恢复药品: id={medication_id}, user={user_id}")
        med = db.query(Medication).filter(
            Medication.id == medication_id,
            Medication.user_id == user_id,
        ).first()
        if not med:
            return False
        med.is_active = True
        med.end_date = None
        db.commit()
        return True

    def log_medication(
        self,
        db: Session,
        user_id: int,
        medication_id: int,
        taken_time: str,
        status: str = "taken",
        skip_reason: Optional[str] = None,
        actual_dosage: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> MedicationLog:
        """记录服药"""
        logger.info(f"[Medication] 记录服药: user={user_id}, med={medication_id}, status={status}")

        log = MedicationLog(
            user_id=user_id,
            medication_id=medication_id,
            taken_date=date.today(),
            taken_time=taken_time,
            status=status,
            skip_reason=skip_reason,
            actual_dosage=actual_dosage,
            notes=notes,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def get_today_status(
        self,
        db: Session,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """获取今日服药状态"""
        logger.info(f"[Medication] 获取今日状态: user={user_id}")
        today = date.today()

        # 获取活跃药品
        meds = self.list_medications(db, user_id, active_only=True)

        result = []
        for med in meds:
            # 获取今日记录（按 taken_time 排序方便取 last）
            logs = db.query(MedicationLog).filter(
                MedicationLog.medication_id == med.id,
                MedicationLog.user_id == user_id,
                MedicationLog.taken_date == today,
            ).order_by(MedicationLog.taken_time.asc()).all()

            taken_count = sum(1 for l in logs if l.status == "taken")
            skipped_count = sum(1 for l in logs if l.status == "skipped")

            # 今日最后一次 taken
            last_today = None
            for l in reversed(logs):
                if l.status == "taken":
                    last_today = l.taken_time
                    break

            # 若今日无记录，查最近一次 taken（可能昨天或更早）
            last_overall = None
            last_overall_date = None
            if last_today is None:
                last_log = db.query(MedicationLog).filter(
                    MedicationLog.medication_id == med.id,
                    MedicationLog.user_id == user_id,
                    MedicationLog.status == "taken",
                ).order_by(
                    MedicationLog.taken_date.desc(),
                    MedicationLog.taken_time.desc(),
                ).first()
                if last_log:
                    last_overall = last_log.taken_time
                    last_overall_date = str(last_log.taken_date)

            result.append({
                "medication_id": med.id,
                "name": med.name,
                "dosage": med.dosage,
                "category": med.category,
                "total_count": med.times_per_day,
                "taken_count": taken_count,
                "skipped_count": skipped_count,
                "last_taken_time": last_today,  # HH:MM today or None
                "last_taken_time_overall": last_overall,  # 若今日未记录，最近一次时间
                "last_taken_date_overall": last_overall_date,  # 最近一次日期
                "reminder_times": med.reminder_times or [],
                "logs": [
                    {"time": l.taken_time, "status": l.status, "id": l.id}
                    for l in logs
                ],
            })

        return result

    def get_adherence_stats(
        self,
        db: Session,
        user_id: int,
        days: int = 7,
    ) -> Dict[str, Any]:
        """获取服药依从性统计"""
        logger.info(f"[Medication] 获取依从性: user={user_id}, days={days}")
        start_date = date.today() - timedelta(days=days - 1)

        # 获取时段内的服药记录
        logs = db.query(MedicationLog).filter(
            MedicationLog.user_id == user_id,
            MedicationLog.taken_date >= start_date,
        ).all()

        total_taken = sum(1 for l in logs if l.status == "taken")
        total_skipped = sum(1 for l in logs if l.status == "skipped")
        total_logs = len(logs)

        # 获取活跃药品的预期总次数
        meds = self.list_medications(db, user_id, active_only=True)
        expected_total = sum(m.times_per_day for m in meds) * days

        adherence_rate = round(total_taken / expected_total * 100, 1) if expected_total > 0 else 0

        # 按药品统计
        med_stats = {}
        for log in logs:
            mid = log.medication_id
            if mid not in med_stats:
                med_stats[mid] = {"taken": 0, "skipped": 0, "total": 0}
            med_stats[mid]["total"] += 1
            if log.status == "taken":
                med_stats[mid]["taken"] += 1
            elif log.status == "skipped":
                med_stats[mid]["skipped"] += 1

        return {
            "adherence_rate": adherence_rate,
            "total_taken": total_taken,
            "total_skipped": total_skipped,
            "total_expected": expected_total,
            "days": days,
            "medication_stats": med_stats,
        }


medication_service = MedicationService()
