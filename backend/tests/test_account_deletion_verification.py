from datetime import date

from app.models.basic_health import BasicHealthData
from app.models.user import User
from app.services import account_deletion


class _EmptyRedis:
    def scan_iter(self, match):
        return iter(())


def test_deletion_report_fails_closed_when_user_data_remains(db, auth_user_and_headers, monkeypatch, tmp_path):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path / "uploads")
    db.add(BasicHealthData(user_id=user.id, record_date=date.today(), weight=70))
    db.commit()
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: _EmptyRedis())

    report = account_deletion.build_deletion_verification_report(db, user.id)

    assert report["user_exists"] is True
    assert report["blocking_rows"] >= 1
    assert report["cache"]["status"] == "checked"
    assert report["cache"]["keys"] == 0
    assert report["can_finalize"] is False
    assert len(report["scope_digest"]) == 64


def test_deletion_report_can_pass_only_after_user_and_rows_are_gone(
    db, auth_user_and_headers, monkeypatch, tmp_path
):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path / "uploads")
    db.add(BasicHealthData(user_id=user.id, record_date=date.today(), weight=70))
    db.commit()
    db.query(BasicHealthData).filter(BasicHealthData.user_id == user.id).delete()
    db.delete(db.query(User).filter(User.id == user.id).one())
    db.commit()
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: _EmptyRedis())

    report = account_deletion.build_deletion_verification_report(db, user.id)

    assert report["user_exists"] is False
    assert report["blocking_rows"] == 0
    assert report["can_finalize"] is True
