import pytest
from fastapi import HTTPException

from app.api.data_collection import sync_my_garmin_data
from app.models.user import User
from app.services.auth import garmin_credential_service
from app.services.data_collection.garmin_native_auth import encode_native_token_store


def _create_user_and_credential(db, suffix: str):
    user = User(
        username=f"garmin-manual-{suffix}",
        email=f"app-manual-{suffix}@example.com",
        hashed_password="unused",
        name=f"Garmin Manual {suffix}",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    credential = garmin_credential_service.save_credentials(
        db,
        user.id,
        f"garmin-manual-{suffix}@example.com",
        "fake-password",
    )
    return user, credential


@pytest.mark.asyncio
async def test_manual_sync_allows_native_token_despite_stale_flags(db, monkeypatch) -> None:
    from app import scheduler

    user, credential = _create_user_and_credential(db, "native")
    credential.garth_session = encode_native_token_store(
        '{"di_token":"manual-token","di_refresh_token":"manual-refresh"}'
    )
    credential.credentials_valid = False
    credential.requires_mfa = True
    db.commit()
    calls = []

    async def fake_sync(passed_db, user_id, email, password, **kwargs):
        calls.append((passed_db, user_id, email, password, kwargs))
        return {
            "success": True,
            "success_count": 1,
            "error_count": 0,
            "activities_count": 2,
            "message": "同步完成",
        }

    monkeypatch.setattr(scheduler, "sync_user_garmin_data", fake_sync)

    result = await sync_my_garmin_data(days=1, current_user=user, db=db)

    assert result["status"] == "success"
    assert result["success_count"] == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_manual_sync_requires_mfa_when_no_native_token(db) -> None:
    user, credential = _create_user_and_credential(db, "mfa")
    credential.requires_mfa = True
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await sync_my_garmin_data(days=1, current_user=user, db=db)

    assert exc_info.value.status_code == 409
    assert "两步验证" in exc_info.value.detail


@pytest.mark.asyncio
async def test_manual_sync_requires_reconnect_for_invalid_credentials_without_token(db) -> None:
    user, credential = _create_user_and_credential(db, "invalid")
    credential.credentials_valid = False
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await sync_my_garmin_data(days=1, current_user=user, db=db)

    assert exc_info.value.status_code == 409
    assert "重新连接" in exc_info.value.detail


@pytest.mark.asyncio
async def test_manual_sync_does_not_echo_upstream_secret(db, monkeypatch) -> None:
    from app import scheduler

    user, _credential = _create_user_and_credential(db, "safe-error")

    async def fake_sync(*_args, **_kwargs):
        raise RuntimeError("upstream-secret-token")

    monkeypatch.setattr(scheduler, "sync_user_garmin_data", fake_sync)

    with pytest.raises(HTTPException) as exc_info:
        await sync_my_garmin_data(days=1, current_user=user, db=db)

    assert exc_info.value.status_code == 502
    assert "upstream-secret-token" not in str(exc_info.value.detail)
    assert "暂时不可用" in exc_info.value.detail


@pytest.mark.asyncio
async def test_manual_sync_rejects_false_green_scheduler_result(db, monkeypatch) -> None:
    from app import scheduler

    user, _credential = _create_user_and_credential(db, "false-green")

    async def fake_sync(*_args, **_kwargs):
        return {
            "success": False,
            "success_count": 0,
            "error_count": 1,
            "message": "upstream failed",
            "is_auth_error": False,
            "requires_mfa": False,
            "skipped": False,
        }

    monkeypatch.setattr(scheduler, "sync_user_garmin_data", fake_sync)

    with pytest.raises(HTTPException) as exc_info:
        await sync_my_garmin_data(days=1, current_user=user, db=db)

    assert exc_info.value.status_code == 502
    assert "暂时不可用" in exc_info.value.detail
