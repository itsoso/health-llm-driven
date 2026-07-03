from app.models.monthly_report import MonthlyReport
from app.models.user import User
from app.services.user_merge import UserMergeService


def test_merge_users_handles_monthly_report_unique_conflicts(db):
    target = User(username="target", email="target@example.com", name="Target", is_active=True)
    source = User(username="source", email="source@example.com", name="Source", is_active=True)
    db.add_all([target, source])
    db.commit()
    db.refresh(target)
    db.refresh(source)
    target_id = target.id
    source_id = source.id

    db.add_all(
        [
            MonthlyReport(user_id=target_id, year=2026, month=5, report_data={"owner": "target"}),
            MonthlyReport(user_id=source_id, year=2026, month=5, report_data={"owner": "source-conflict"}),
            MonthlyReport(user_id=source_id, year=2026, month=6, report_data={"owner": "source-kept"}),
        ]
    )
    db.commit()

    result = UserMergeService.merge_users(db, source_user_id=source_id, target_user_id=target_id)

    assert result["success"] is True
    assert db.query(User).filter(User.id == source_id).first() is None

    reports = (
        db.query(MonthlyReport)
        .filter(MonthlyReport.user_id == target_id)
        .order_by(MonthlyReport.year, MonthlyReport.month)
        .all()
    )
    assert [(report.year, report.month, report.report_data["owner"]) for report in reports] == [
        (2026, 5, "target"),
        (2026, 6, "source-kept"),
    ]
