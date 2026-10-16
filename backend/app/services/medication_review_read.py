"""Bounded, read-only evidence for the medication page's review action."""

from app.services.agent_query_window import parse_query_window


def read_medication_review(db, user_id, window):
    from app.models.medication import Medication, MedicationLog

    if type(user_id) is not int or user_id <= 0:
        raise ValueError("medication_review_owner_required")
    window = parse_query_window(window.as_dict())
    if window.start_date != window.end_date or window.period is not None:
        raise ValueError("medication_review_requires_one_day")
    medications = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active.is_(True))
        .order_by(Medication.id)
        .limit(201)
        .all()
    )
    # Join and check BOTH owners, including imported/inconsistent foreign keys.
    logs = (
        db.query(MedicationLog)
        .join(Medication, Medication.id == MedicationLog.medication_id)
        .filter(
            MedicationLog.user_id == user_id,
            Medication.user_id == user_id,
            MedicationLog.taken_date == window.start_date,
        )
        .order_by(MedicationLog.id)
        .limit(501)
        .all()
    )
    if len(medications) > 200 or len(logs) > 500:
        raise ValueError("medication_review_result_limit_exceeded")
    return {
        "dimension": "medication",
        "window": window.as_dict(),
        "availability": "available" if logs else "no_data",
        "active_medications": [
            {
                key: getattr(m, key)
                for key in (
                    "id",
                    "name",
                    "dosage",
                    "frequency",
                    "reminder_times",
                    "category",
                    "purpose",
                )
            }
            for m in medications
        ],
        "records": [
            {
                "record_date": row.taken_date.isoformat(),
                **{
                    key: getattr(row, key)
                    for key in (
                        "id",
                        "medication_id",
                        "taken_time",
                        "status",
                        "actual_dosage",
                        "skip_reason",
                    )
                },
            }
            for row in logs
        ],
        "limitations": [
            "在用列表和服药记录是用户保存的信息，不代表处方已经核验。",
            "无打卡不等于未服用，不推断漏服或依从率。",
            "未查询近期症状；描述不适需用户补充发生时间、表现和变化。",
            "仅整理向医生确认的问题，不建议自行停药、换药或改剂量。",
        ],
    }
