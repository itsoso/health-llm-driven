"""Bounded, read-only evidence for the medication page's review action."""

from app.services.agent_query_window import parse_query_window


def read_medication_reminder_slot(db, user_id, window, time):
    """Current saved plan matches and actual logs for one slot; never intake inference."""
    import re
    from sqlalchemy import or_
    from app.models.medication import Medication, MedicationLog

    if type(user_id) is not int or user_id <= 0:
        raise ValueError('medication_reminder_owner_required')
    window = parse_query_window(window.as_dict())
    if (window.start_date != window.end_date or window.period is not None
            or not isinstance(time, str) or re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time) is None):
        raise ValueError('medication_reminder_slot_invalid')
    candidates = (db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active.is_(True),
                or_(Medication.start_date.is_(None), Medication.start_date <= window.start_date),
                or_(Medication.end_date.is_(None), Medication.end_date >= window.start_date))
        .order_by(Medication.id).limit(201).all())
    # Check both owners even for inconsistent imported foreign keys.
    logs = (db.query(MedicationLog, Medication.name)
        .join(Medication, Medication.id == MedicationLog.medication_id)
        .filter(MedicationLog.user_id == user_id, Medication.user_id == user_id,
                MedicationLog.taken_date == window.start_date, MedicationLog.taken_time == time)
        .order_by(MedicationLog.id).limit(501).all())
    if len(candidates) > 200 or len(logs) > 500:
        raise ValueError('medication_reminder_result_limit_exceeded')
    if any(m.reminder_times is not None and (
            not isinstance(m.reminder_times, list) or any(not isinstance(t, str) for t in m.reminder_times))
           for m in candidates):
        raise ValueError('medication_reminder_schedule_invalid')
    medications = [m for m in candidates if time in (m.reminder_times or [])]
    return {
        'dimension': 'medication', 'window': window.as_dict(),
        'source_scope': 'owned_medication_reminder_slot', 'reminder_time': time,
        'availability': 'available' if logs else 'no_data',
        'active_medications': [
            {**{key: getattr(m, key) for key in ('id', 'name', 'dosage', 'frequency')},
             'reminder_times': [time]}
            for m in medications],
        'records': [
            {'record_date': row.taken_date.isoformat(), 'medication_name': name,
             **{key: getattr(row, key) for key in ('id', 'medication_id', 'taken_time', 'status', 'actual_dosage')}}
            for row, name in logs],
        'limitations': [
            '仅核对本人指定日期、时区和时段；没有记录服药或修改计划。',
            '计划来自当前保存的在用列表，不能证明通知发送时的历史计划；未匹配不代表当时没有提醒。',
            '保存的药名和剂量不是已核验处方，不建议自行停药、换药或改剂量。',
            '无打卡不等于未服用，跳过或延迟记录不等于已服用。',
        ],
    }


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


def read_medication_history(db, user_id, window):
    """Actual owned logs in an explicit local-date window, never active plans."""
    from app.models.medication import Medication, MedicationLog

    if type(user_id) is not int or user_id <= 0:
        raise ValueError("medication_history_owner_required")
    window = parse_query_window(window.as_dict())
    if window.period is not None or not 1 <= (window.end_date - window.start_date).days + 1 <= 31:
        raise ValueError("medication_history_window_invalid")
    rows = (db.query(MedicationLog, Medication.name)
        .join(Medication, Medication.id == MedicationLog.medication_id)
        .filter(MedicationLog.user_id == user_id, Medication.user_id == user_id,
                MedicationLog.taken_date >= window.start_date,
                MedicationLog.taken_date <= window.end_date)
        .order_by(MedicationLog.taken_date, MedicationLog.id).limit(501).all())
    if len(rows) > 500:
        raise ValueError("medication_history_result_limit_exceeded")
    return {
        'dimension': 'medication', 'window': window.as_dict(),
        'availability': 'available' if rows else 'no_data',
        'source_scope': 'owned_medication_intake_logs',
        'active_medications': [],
        'records': [
            {'record_date': row.taken_date.isoformat(), 'record_kind': 'medication_log',
             'medication_name': name,
             **{key: getattr(row, key) for key in
                ('id', 'medication_id', 'taken_time', 'status', 'actual_dosage', 'skip_reason')}}
            for row, name in rows
        ],
        'limitations': [
            '仅查询本人实际保存的服药日志；在用列表未查询，日志不是处方核验。',
            '状态为跳过或延迟的日志不算已服用；无打卡不等于未服用。',
            '记录不能确定病因，不建议自行停药、换药或改剂量。',
        ],
    }
