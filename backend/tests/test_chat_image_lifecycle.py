import base64
import json
import threading
from contextlib import contextmanager
import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService


def _image_payload(data: bytes = b"complete-image-bytes") -> str:
    return base64.b64encode(data).decode()


def test_chat_image_publish_failure_never_exposes_a_partial_target(tmp_path, monkeypatch):
    from app.services import chat_utils

    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        chat_utils.os,
        "link",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("publish failed")),
    )

    with pytest.raises(OSError, match="publish failed"):
        chat_utils.upload_chat_image(
            _image_payload(),
            user_id=7,
            image_type="jpeg",
            object_key="turn-atomic-1",
        )

    owner_dir = tmp_path / "7"
    assert list(owner_dir.iterdir()) == []


def test_delete_conversation_removes_owner_scoped_and_legacy_chat_images(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    owner_file = owner_dir / "owner.jpg"
    owner_file.write_bytes(b"owner")
    legacy_file = tmp_path / "legacy.jpg"
    legacy_file.write_bytes(b"legacy")

    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="图片会话")
    service.save_message(
        conversation.id,
        "user",
        "两张图片",
        image_url=json.dumps([
            f"/api/v1/upload/files/chat/{user.id}/owner.jpg",
            "/api/v1/upload/files/chat/legacy.jpg",
        ]),
    )

    assert service.delete_conversation(user.id, conversation.id) is True
    assert db.query(AgentMessage).count() == 0
    assert owner_file.exists() is False
    assert legacy_file.exists() is False


def test_delete_conversation_keeps_image_referenced_by_another_conversation(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    shared_file = owner_dir / "shared.jpg"
    shared_file.write_bytes(b"shared-private")
    image_url = f"/api/v1/upload/files/chat/{user.id}/shared.jpg"

    service = AgentConversationService(db)
    first = service.get_or_create_conversation(user.id, None, title="第一处引用")
    second = service.get_or_create_conversation(user.id, None, title="第二处引用")
    service.save_message(first.id, "user", "图片", image_url=image_url)
    service.save_message(second.id, "user", "图片", image_url=image_url)

    assert service.delete_conversation(user.id, first.id) is True
    assert shared_file.read_bytes() == b"shared-private"
    assert service.get_conversation_detail(user.id, second.id) is not None

    assert service.delete_conversation(user.id, second.id) is True
    assert shared_file.exists() is False


def test_delete_conversation_keeps_legacy_image_referenced_by_another_user(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.models.user import User
    from app.services import chat_utils

    user_a, _ = auth_user_and_headers
    user_b = User(
        username="shared_legacy_owner_b",
        email="shared_legacy_owner_b@example.com",
        name="Shared Legacy Owner B",
        hashed_password="x",
        is_active=True,
        is_approved=True,
    )
    db.add(user_b)
    db.commit()
    db.refresh(user_b)
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    shared_file = tmp_path / "shared-legacy.jpg"
    shared_file.write_bytes(b"shared-legacy-private")
    image_url = "/api/v1/upload/files/chat/shared-legacy.jpg"

    service = AgentConversationService(db)
    first = service.get_or_create_conversation(user_a.id, None, title="A 的引用")
    second = service.get_or_create_conversation(user_b.id, None, title="B 的引用")
    service.save_message(first.id, "user", "图片", image_url=image_url)
    service.save_message(second.id, "user", "图片", image_url=image_url)

    assert service.delete_conversation(user_a.id, first.id) is True
    assert shared_file.read_bytes() == b"shared-legacy-private"
    assert service.get_conversation_detail(user_b.id, second.id) is not None

    assert service.delete_conversation(user_b.id, second.id) is True
    assert shared_file.exists() is False


def test_updating_existing_message_image_reference_uses_lifecycle_lock(
    db, auth_user_and_headers, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="补图片引用",
    )
    message = service.save_message(conversation.id, "user", "原始内容")
    active = False
    entered = 0

    @contextmanager
    def observed_lifecycle_lock():
        nonlocal active, entered
        entered += 1
        active = True
        try:
            yield
        finally:
            active = False

    monkeypatch.setattr(
        chat_utils,
        "chat_image_lifecycle_lock",
        observed_lifecycle_lock,
    )
    original_commit = db.commit
    commit_lock_states: list[bool] = []

    def observed_commit():
        commit_lock_states.append(active)
        original_commit()

    monkeypatch.setattr(db, "commit", observed_commit)

    updated = service.update_user_message_after_image_upload(
        user.id,
        message.id,
        content="带图片内容",
        image_url=f"/api/v1/upload/files/chat/{user.id}/attached.jpg",
        meta={"client_turn_id": "turn-image-attach"},
    )

    assert entered == 1
    assert commit_lock_states == [True]
    assert updated is not None
    assert updated.image_url.endswith("attached.jpg")


def test_delete_conversation_keeps_database_row_when_file_staging_fails(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    owner_file = owner_dir / "owner.jpg"
    owner_file.write_bytes(b"owner")

    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="不可删除图片")
    service.save_message(
        conversation.id,
        "user",
        "图片",
        image_url=f"/api/v1/upload/files/chat/{user.id}/owner.jpg",
    )
    monkeypatch.setattr(
        chat_utils.os,
        "replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("stage failed")),
    )

    with pytest.raises(RuntimeError, match="chat_image_deletion_staging_failed"):
        service.delete_conversation(user.id, conversation.id)

    assert service.get_conversation_detail(user.id, conversation.id) is not None
    assert owner_file.exists() is True


def test_failed_finalization_is_retried_from_durable_tombstone(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    owner_file = owner_dir / "owner.jpg"
    owner_file.write_bytes(b"private")

    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="待清理图片")
    service.save_message(
        conversation.id,
        "user",
        "图片",
        image_url=f"/api/v1/upload/files/chat/{user.id}/owner.jpg",
    )

    original_remove = chat_utils.os.remove
    failed_once = False

    def flaky_remove(path):
        nonlocal failed_once
        if ".delete-" in str(path) and not failed_once:
            failed_once = True
            raise OSError("transient unlink failure")
        return original_remove(path)

    monkeypatch.setattr(
        chat_utils.os,
        "remove",
        flaky_remove,
    )
    assert service.delete_conversation(user.id, conversation.id) is True
    assert owner_file.exists() is False
    assert len(list(owner_dir.glob("*.delete-*"))) == 1

    legacy_tombstone = tmp_path / "legacy.jpg.delete-stale"
    legacy_tombstone.write_bytes(b"legacy-private")
    monkeypatch.setattr(chat_utils.os, "remove", original_remove)
    assert service.retry_staged_chat_image_deletions(user.id) == 1
    assert list(owner_dir.glob("*.delete-*")) == []
    assert legacy_tombstone.exists() is True
    assert service.retry_staged_chat_image_deletions() == 1
    assert legacy_tombstone.exists() is False


def test_cleanup_skips_a_tombstone_locked_by_an_active_delete_transaction(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    owner_file = owner_dir / "active.jpg"
    owner_file.write_bytes(b"active-private")

    staged = chat_utils.stage_chat_image_deletion(
        f"/api/v1/upload/files/chat/{user.id}/active.jpg",
        user.id,
    )
    assert staged is not None
    service = AgentConversationService(db)
    assert service.retry_staged_chat_image_deletions(user.id) == 0
    assert owner_file.exists() is False
    assert len(list(owner_dir.glob("*.delete-*"))) == 1

    chat_utils.restore_staged_chat_image(staged)
    assert owner_file.read_bytes() == b"active-private"
    assert list(owner_dir.glob("*.delete-*")) == []


def test_unlocked_tombstone_is_restored_when_database_still_references_the_image(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    owner_file = owner_dir / "referenced.jpg"
    owner_file.write_bytes(b"referenced-private")

    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="仍被引用")
    image_url = f"/api/v1/upload/files/chat/{user.id}/referenced.jpg"
    service.save_message(conversation.id, "user", "图片", image_url=image_url)
    staged = chat_utils.stage_chat_image_deletion(image_url, user.id)
    assert staged is not None

    chat_utils._release_staged_chat_image_lock(staged)
    assert service.retry_staged_chat_image_deletions(user.id) == 1
    assert owner_file.read_bytes() == b"referenced-private"
    assert list(owner_dir.glob("*.delete-*")) == []


def test_cleanup_rechecks_database_reference_after_tombstone_lock(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, _ = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / str(user.id)
    owner_dir.mkdir(parents=True)
    owner_file = owner_dir / "late-reference.jpg"
    owner_file.write_bytes(b"late-reference-private")
    image_url = (
        f"/api/v1/upload/files/chat/{user.id}/late-reference.jpg"
    )
    staged = chat_utils.stage_chat_image_deletion(image_url, user.id)
    assert staged is not None
    chat_utils._release_staged_chat_image_lock(staged)

    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="清理期间新增引用",
    )
    original_retry = chat_utils.retry_staged_chat_image_deletions
    reference_added = False

    def add_reference_before_tombstone_check(user_id, *, is_referenced):
        nonlocal reference_added
        if not reference_added:
            reference_added = True
            service.save_message(
                conversation.id,
                "user",
                "图片",
                image_url=image_url,
            )
        return original_retry(user_id, is_referenced=is_referenced)

    monkeypatch.setattr(
        chat_utils,
        "retry_staged_chat_image_deletions",
        add_reference_before_tombstone_check,
    )

    assert service.retry_staged_chat_image_deletions(user.id) == 1
    assert owner_file.read_bytes() == b"late-reference-private"
    assert list(owner_dir.glob("*.delete-*")) == []


def test_user_scoped_cleanup_never_touches_another_users_legacy_tombstone(
    db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.models.user import User
    from app.services import chat_utils

    user_a, _ = auth_user_and_headers
    user_b = User(
        username="legacy_owner_b",
        email="legacy_owner_b@example.com",
        name="Legacy Owner B",
        hashed_password="x",
        is_active=True,
        is_approved=True,
    )
    db.add(user_b)
    db.commit()
    db.refresh(user_b)
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    legacy_file = tmp_path / "legacy-b.jpg"
    legacy_file.write_bytes(b"owner-b-private")
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user_b.id, None, title="B 的图片")
    legacy_url = "/api/v1/upload/files/chat/legacy-b.jpg"
    service.save_message(conversation.id, "user", "图片", image_url=legacy_url)
    staged = chat_utils.stage_chat_image_deletion(legacy_url, user_b.id)
    assert staged is not None
    chat_utils._release_staged_chat_image_lock(staged)

    assert service.retry_staged_chat_image_deletions(user_a.id) == 0
    assert len(list(tmp_path.glob("legacy-b.jpg.delete-*"))) == 1
    assert service.retry_staged_chat_image_deletions() == 1
    assert legacy_file.read_bytes() == b"owner-b-private"


def test_chat_image_lifecycle_lock_serializes_cleanup_workers(tmp_path, monkeypatch):
    from app.services import chat_utils

    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    entered = threading.Event()

    def contender():
        with chat_utils.chat_image_lifecycle_lock():
            entered.set()

    with chat_utils.chat_image_lifecycle_lock():
        thread = threading.Thread(target=contender)
        thread.start()
        assert entered.wait(0.1) is False
    thread.join(timeout=1)
    assert entered.is_set() is True


def test_chat_image_lifecycle_lock_times_out_instead_of_waiting_forever(
    tmp_path, monkeypatch
):
    from app.services import chat_utils

    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        chat_utils,
        "CHAT_IMAGE_LIFECYCLE_LOCK_TIMEOUT_SECONDS",
        0.05,
    )
    entered = threading.Event()
    release = threading.Event()

    def holder():
        with chat_utils.chat_image_lifecycle_lock():
            entered.set()
            release.wait(timeout=1)

    thread = threading.Thread(target=holder)
    thread.start()
    assert entered.wait(timeout=1) is True

    with pytest.raises(TimeoutError, match="chat_image_lifecycle_lock_timeout"):
        with chat_utils.chat_image_lifecycle_lock():
            pass

    release.set()
    thread.join(timeout=1)
    assert thread.is_alive() is False
