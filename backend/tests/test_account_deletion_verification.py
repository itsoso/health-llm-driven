from datetime import date
from pathlib import Path

import pytest
from app.models.basic_health import BasicHealthData
from app.models.user import User
from app.services import account_deletion


class _EmptyRedis:
    def scan_iter(self, match):
        return iter(())


def test_deletion_report_fails_closed_when_user_data_remains(db, auth_user_and_headers, monkeypatch, tmp_path):
    user, _ = auth_user_and_headers
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path / "uploads")
    db.add(BasicHealthData(user_id=user.id, record_date=date(2026, 9, 7), weight=70))
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
    db.add(BasicHealthData(user_id=user.id, record_date=date(2026, 9, 7), weight=70))
    db.commit()
    db.query(BasicHealthData).filter(BasicHealthData.user_id == user.id).delete()
    db.delete(db.query(User).filter(User.id == user.id).one())
    db.commit()
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: _EmptyRedis())

    report = account_deletion.build_deletion_verification_report(db, user.id)

    assert report["user_exists"] is False
    assert report["blocking_rows"] == 0
    assert report["can_finalize"] is True


@pytest.mark.parametrize("category", ["aigc", "chat", "diet", "medical", "other"])
def test_upload_report_counts_every_owner_scoped_category(monkeypatch, tmp_path, category):
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path)
    owner_dir = tmp_path / category / "17"
    owner_dir.mkdir(parents=True)
    (owner_dir / "synthetic.png").write_bytes(b"synthetic")

    assert account_deletion._upload_report(17)["files"] == 1
    assert account_deletion._upload_report(18)["files"] == 0


@pytest.mark.parametrize("category", ["avatar", "diet", "medical", "other", "chat", "future-media"])
def test_unattributed_uploads_block_completion(db, monkeypatch, tmp_path, category):
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: _EmptyRedis())
    category_dir = tmp_path / category
    category_dir.mkdir()
    (category_dir / "synthetic.png").write_bytes(b"synthetic")

    report = account_deletion.build_deletion_verification_report(db, 987654)

    assert report["uploads"]["unresolved_files"] == 1
    assert report["can_finalize"] is False
    assert (category_dir / "synthetic.png").read_bytes() == b"synthetic"


def test_user_controlled_avatar_reference_cannot_prove_another_users_file_is_clear(
    client, db, auth_user_and_headers, monkeypatch, tmp_path
):
    user, headers = auth_user_and_headers
    # This is an actual supported write path, not a trusted owner ledger.
    response = client.put(
        "/api/v1/wechat/user/info",
        headers=headers,
        json={"avatar_url": "/api/v1/upload/files/avatar/synthetic.png"},
    )
    assert response.status_code == 200
    db.refresh(user)
    assert user.avatar_url == "/api/v1/upload/files/avatar/synthetic.png"
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: _EmptyRedis())
    avatar_dir = tmp_path / "avatar"
    avatar_dir.mkdir()
    (avatar_dir / "synthetic.png").write_bytes(b"synthetic")

    report = account_deletion.build_deletion_verification_report(db, user.id + 100)

    assert report["uploads"]["unresolved_files"] == 1
    assert report["can_finalize"] is False
    assert (avatar_dir / "synthetic.png").read_bytes() == b"synthetic"


def test_upload_symlink_is_unresolved_and_never_followed(db, monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (upload_root / "aigc").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: _EmptyRedis())

    report = account_deletion.build_deletion_verification_report(db, 987654)

    assert report["uploads"]["unresolved_files"] == 1
    assert report["can_finalize"] is False


def test_other_owner_directory_is_not_traversed(monkeypatch, tmp_path):
    other_dir = tmp_path / "aigc" / "18"
    other_dir.mkdir(parents=True)
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path)
    original_iterdir = Path.iterdir

    def guarded_iterdir(path):
        if path == other_dir:
            raise AssertionError("must not inspect another owner's private files")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    report = account_deletion._upload_report(17)
    assert report["files"] == 0
    assert report["unresolved_files"] == 0


def test_upload_scan_error_cannot_be_reported_as_clear(monkeypatch, tmp_path):
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path)

    def unreadable(_path):
        raise PermissionError("synthetic unreadable upload root")

    monkeypatch.setattr(Path, "iterdir", unreadable)
    with pytest.raises(PermissionError):
        account_deletion._upload_report(17)
