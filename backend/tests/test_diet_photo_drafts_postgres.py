from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import os
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.api.diet import (
    create_diet_record,
    discard_photo_draft,
    purge_expired_diet_photo_drafts,
)
from app.models.daily_health import DietPhotoDraft, DietRecord
from app.models.user import User
from app.schemas.diet import DietRecordCreate


def test_postgres_photo_draft_terminal_operations_are_serialized(
    db, tmp_path, monkeypatch
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires TEST_DATABASE_URL PostgreSQL")

    from app.api import upload as upload_api

    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
    user = User(
        username="diet-photo-race-user",
        email="diet-photo-race@example.com",
        hashed_password="hashed",
        name="Diet Photo Race",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    owner = SimpleNamespace(id=user.id, is_admin=False)
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)

    def seed_draft(suffix: str) -> tuple[str, str]:
        token = f"postgres-race-{suffix}-1234567890"
        owner_root = upload_root / "diet" / str(user.id)
        owner_root.mkdir(parents=True, exist_ok=True)
        image_path = owner_root / f"{suffix}.png"
        image_path.write_bytes(b"private-image")
        image_url = f"/api/v1/upload/files/diet/{user.id}/{suffix}.png"
        db.add(DietPhotoDraft(
            token=token,
            user_id=user.id,
            image_url=image_url,
            image_type="png",
            recognition_result={"success": True, "foods": [{"name": "鸡胸肉"}]},
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
        return token, str(image_path)

    def run_pair(first, second):
        barrier = Barrier(3)

        def run(operation):
            session = Session()
            try:
                barrier.wait(timeout=5)
                try:
                    return operation(session)
                except HTTPException as exc:
                    return exc.status_code
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(run, first)
            second_future = pool.submit(run, second)
            barrier.wait(timeout=5)
            return first_future.result(timeout=15), second_future.result(timeout=15)

    def confirm(token: str):
        payload = DietRecordCreate(
            record_date=date.today(),
            meal_type="lunch",
            food_items="鸡胸肉 200g",
            calories=330,
            photo_draft_token=token,
            idempotency_key=f"diet-photo:{token}",
        )
        return lambda session: create_diet_record(
            payload,
            current_user=owner,
            db=session,
            idempotency_key=f"diet-photo:{token}",
        )

    def cancel(token: str):
        return lambda session: discard_photo_draft(
            token,
            current_user=owner,
            db=session,
        )

    def purge(_token: str):
        return lambda session: purge_expired_diet_photo_drafts(
            session,
            now=datetime.now(timezone.utc) + timedelta(days=2),
        )

    token, image_path = seed_draft("confirm-confirm")
    first, second = run_pair(confirm(token), confirm(token))
    assert first.id == second.id
    db.expire_all()
    assert db.query(DietRecord).filter(DietRecord.client_action_id == f"diet-photo:{token}").count() == 1
    assert db.query(DietPhotoDraft).filter(DietPhotoDraft.token == token).first() is None
    assert os.path.exists(image_path)

    for suffix, operations in (
        ("confirm-cancel", lambda token: (confirm(token), cancel(token))),
        ("confirm-purge", lambda token: (confirm(token), purge(token))),
    ):
        token, image_path = seed_draft(suffix)
        run_pair(*operations(token))
        db.expire_all()
        record = db.query(DietRecord).filter(
            DietRecord.client_action_id == f"diet-photo:{token}"
        ).first()
        assert os.path.exists(image_path) is (record is not None)
        assert db.query(DietPhotoDraft).filter(DietPhotoDraft.token == token).first() is None

    token, image_path = seed_draft("cancel-purge")
    run_pair(cancel(token), purge(token))
    db.expire_all()
    assert db.query(DietPhotoDraft).filter(DietPhotoDraft.token == token).first() is None
    assert not os.path.exists(image_path)
