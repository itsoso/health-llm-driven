"""Doctor Weekly Report — 辅助 helper.

从 app/tasks/notifications.py 拆出来 (弱点 F: 大文件拆分).
@celery_app.task 函数保留在原处 (保持 Celery beat schedule 路径不变),
只把 private helper 搬到这里.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from sqlalchemy import func


def build_medication_adherence_block(db, user_id: int, since_date: date) -> str:
    """医生周报: 过去 7 天用药依从率 (daily frequency 的 medicine 模板).

    依从率 < 70% 标 ⚠️ 提示. 返回空串若用户无 medicine 模板.
    """
    from app.models.checkin import CheckinTemplate, CheckinRecord

    templates = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == user_id,
        CheckinTemplate.is_active == True,  # noqa: E712
        CheckinTemplate.is_archived == False,  # noqa: E712
        CheckinTemplate.category == "medicine",
        CheckinTemplate.frequency == "daily",
    ).all()

    if not templates:
        return ""

    tmpl_ids = [t.id for t in templates]
    counts = dict(
        db.query(
            CheckinRecord.template_id,
            func.count(CheckinRecord.id),
        ).filter(
            CheckinRecord.template_id.in_(tmpl_ids),
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date >= since_date,
        ).group_by(CheckinRecord.template_id).all()
    )

    lines = ["\n💊 *用药依从率 (7 天)*"]
    for t in templates:
        actual = counts.get(t.id, 0)
        rate = round(100 * actual / 7)
        mark = " ⚠️" if rate < 70 else ""
        lines.append(f"  • {t.name}: {actual}/7 ({rate}%){mark}")
    return "\n".join(lines)


def build_journal_summary_block(db, user_id: int, since_date: date) -> str:
    """医生周报: 过去 7 天 Clinical Journal SOAP 条目分主题计数 + 最重一条.

    返回空串若无 entries. 最重标准: assessment 包含 ⚠️ 或 related_action_card_ids 非空.
    """
    from app.models.clinical_journal import ClinicalJournalEntry, CaseThread

    since_dt = datetime.combine(since_date, datetime.min.time()).replace(tzinfo=UTC)

    theme_counts = dict(
        db.query(
            CaseThread.theme,
            func.count(ClinicalJournalEntry.id),
        ).join(
            ClinicalJournalEntry, ClinicalJournalEntry.case_thread_id == CaseThread.id,
        ).filter(
            ClinicalJournalEntry.user_id == user_id,
            ClinicalJournalEntry.generated_at >= since_dt,
        ).group_by(CaseThread.theme).all()
    )

    if not theme_counts:
        return ""

    total = sum(theme_counts.values())
    theme_zh = {
        "rhinitis": "鼻炎", "sleep_osahs": "睡眠呼吸", "sleep_quality": "睡眠",
        "liver": "肝功能", "lipid": "血脂", "metabolic": "代谢",
        "weight_loss": "体重", "hypertension": "血压", "recovery": "恢复",
        "daily_briefing": "日报", "general": "综合",
    }
    parts = [f"{theme_zh.get(k, k)}×{v}" for k, v in sorted(
        theme_counts.items(), key=lambda x: -x[1])]
    lines = [f"\n📓 *AI 记录 {total} 条*: " + " / ".join(parts)]

    # 取最重一条: assessment 含 ⚠️ 优先
    priority_entry = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.user_id == user_id,
        ClinicalJournalEntry.generated_at >= since_dt,
        ClinicalJournalEntry.assessment.like("%⚠️%"),
    ).order_by(ClinicalJournalEntry.generated_at.desc()).first()
    if priority_entry and priority_entry.assessment:
        first_line = priority_entry.assessment.split("\n")[0][:120]
        lines.append(f"  最需关注: {first_line}")
    return "\n".join(lines)
