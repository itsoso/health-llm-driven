"""Authorization and rollback contracts for destructive user merges."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api import admin as admin_api
from app.api import user_merge as user_merge_api
from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.monthly_report import MonthlyReport
from app.models.user import User
from app.services.auth import auth_service
from app.services.user_merge import UserMergeService
from main import app


def _user(db, suffix: str, **overrides) -> User:
    values = {
        "username": f"merge_{suffix}",
        "email": f"merge-{suffix}@example.com",
        "name": f"Merge {suffix}",
        "is_active": True,
        "is_approved": True,
    }
    values.update(overrides)
    user = User(**values)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def test_legacy_self_service_merge_openapi_declares_disabled_410_contract():
    app.openapi_schema = None
    operation = app.openapi()["paths"]["/api/v1/user-merge/merge"]["post"]

    assert operation["summary"] == "旧版账号合并已禁用（需要双方重新验证）"
    assert "ID-only" in operation["description"]
    assert "ACCOUNT_MERGE_REAUTH_REQUIRED" in operation["description"]
    assert "200" not in operation["responses"]
    gone = operation["responses"]["410"]
    assert gone["description"] == "旧版自助合并已禁用，需要双方重新验证"
    assert gone["content"]["application/json"]["example"] == {
        "detail": {
            "code": "ACCOUNT_MERGE_REAUTH_REQUIRED",
            "message": "账号合并需要双方重新验证，请联系管理员处理",
        }
    }


@pytest.mark.parametrize("attacker_position", ["source", "target"])
def test_self_service_merge_is_disabled_before_victim_lookup_or_service(
    client, db, monkeypatch, attacker_position
):
    attacker = _user(db, f"attacker-{attacker_position}")
    victim = _user(
        db,
        f"victim-{attacker_position}",
        hashed_password="victim-password-hash-private-marker",
        wechat_openid=f"victim-openid-private-marker-{attacker_position}",
    )
    source, target = (
        (attacker, victim) if attacker_position == "source" else (victim, attacker)
    )

    def forbidden_merge(*args, **kwargs):
        raise AssertionError("self-service merge must remain unreachable")

    monkeypatch.setattr(UserMergeService, "merge_users", forbidden_merge)
    response = client.post(
        "/api/v1/user-merge/merge",
        headers=_headers(attacker),
        json={
            "source_user_id": source.id,
            "target_user_id": target.id,
            "confirm": True,
        },
    )

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "ACCOUNT_MERGE_REAUTH_REQUIRED"
    assert db.query(User).count() == 2
    db.refresh(victim)
    assert victim.hashed_password == "victim-password-hash-private-marker"
    assert victim.wechat_openid == f"victim-openid-private-marker-{attacker_position}"


@pytest.mark.asyncio
async def test_concurrent_self_service_merge_attempts_never_reach_service(db, monkeypatch):
    attacker = _user(db, "concurrent-attacker")
    calls = 0

    def forbidden_merge(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("disabled merge service was called")

    monkeypatch.setattr(UserMergeService, "merge_users", forbidden_merge)
    request = user_merge_api.MergeUsersRequest(
        source_user_id=attacker.id,
        target_user_id=999999,
        confirm=True,
    )
    results = await asyncio.gather(
        user_merge_api.merge_users(request, current_user=attacker, db=db),
        user_merge_api.merge_users(request, current_user=attacker, db=db),
        return_exceptions=True,
    )

    assert calls == 0
    assert all(getattr(item, "status_code", None) == 410 for item in results)
    assert db.get(User, attacker.id) is not None


@pytest.mark.parametrize(
    ("blocked_side", "status_field"),
    [
        ("source", "is_approved"),
        ("target", "is_approved"),
        ("source", "is_active"),
        ("target", "is_active"),
    ],
)
def test_enforced_admin_merge_blocks_pending_or_inactive_accounts_without_propagation(
    client, db, monkeypatch, blocked_side, status_field
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, f"admin-{blocked_side}-{status_field}", is_admin=True)
    source = _user(
        db,
        f"source-{blocked_side}-{status_field}",
        hashed_password="source-password-hash-private-marker",
        wechat_openid="source-openid-private-marker",
    )
    target = _user(
        db,
        f"target-{blocked_side}-{status_field}",
        hashed_password=None,
        wechat_openid=None,
    )
    setattr(source if blocked_side == "source" else target, status_field, False)
    db.commit()

    def forbidden_merge(*args, **kwargs):
        raise AssertionError("ineligible admin merge must remain unreachable")

    monkeypatch.setattr(UserMergeService, "merge_users", forbidden_merge)
    response = client.post(
        "/api/v1/admin/users/merge",
        headers=_headers(admin),
        json={"source_user_id": source.id, "target_user_id": target.id},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACCOUNT_MERGE_INELIGIBLE"
    db.refresh(source)
    db.refresh(target)
    assert source.hashed_password == "source-password-hash-private-marker"
    assert source.wechat_openid == "source-openid-private-marker"
    assert target.hashed_password is None
    assert target.wechat_openid is None
    actions = [
        item.action
        for item in db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == admin.id)
        .order_by(AgentAuditLog.id)
    ]
    assert actions == ["privileged_request_authorized", "admin_user_merge_blocked"]


def test_enforced_admin_merge_allows_two_active_approved_existing_accounts(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, "admin-valid", is_admin=True)
    source = _user(db, "source-valid")
    target = _user(db, "target-valid")
    calls = []

    def safe_merge(
        *, db, source_user_id, target_user_id, require_active_approved=False
    ):
        calls.append((source_user_id, target_user_id))
        assert require_active_approved is True
        return {
            "success": True,
            "source_user_id": source_user_id,
            "target_user_id": target_user_id,
            "stats": {},
        }

    monkeypatch.setattr(UserMergeService, "merge_users", safe_merge)
    response = client.post(
        "/api/v1/admin/users/merge",
        headers=_headers(admin),
        json={"source_user_id": source.id, "target_user_id": target.id},
    )

    assert response.status_code == 200
    assert calls == [(source.id, target.id)]
    actions = [
        item.action
        for item in db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == admin.id)
        .order_by(AgentAuditLog.id)
    ]
    assert actions == [
        "privileged_request_authorized",
        "admin_user_merge_authorized",
        "admin_user_merge_completed",
    ]


def test_admin_merge_real_service_returns_success_after_committed_source_delete(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, "admin-real-service", is_admin=True)
    source = _user(db, "source-real-service")
    target = _user(db, "target-real-service")
    source_id = source.id
    target_id = target.id

    response = client.post(
        "/api/v1/admin/users/merge",
        headers=_headers(admin),
        json={"source_user_id": source_id, "target_user_id": target_id},
    )

    assert response.status_code == 200
    assert response.json()["source_user_id"] == source_id
    assert response.json()["target_user_id"] == target_id
    assert db.get(User, source_id) is None
    assert db.get(User, target_id) is not None
    actions = [
        item.action
        for item in db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == admin.id)
        .order_by(AgentAuditLog.id)
    ]
    assert actions == [
        "privileged_request_authorized",
        "admin_user_merge_authorized",
        "admin_user_merge_completed",
    ]


def test_post_commit_merge_logger_failure_cannot_turn_success_into_503(
    client, db, monkeypatch
):
    from app.services import user_merge as merge_module

    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, "admin-log-failure", is_admin=True)
    source = _user(db, "log-failure-source")
    target = _user(db, "log-failure-target")
    source_id = source.id
    target_id = target.id
    real_info = merge_module.logger.info

    def fail_only_committed_message(message, *args, **kwargs):
        if str(message).startswith("成功合并用户"):
            raise RuntimeError("post-commit-observability-private-marker")
        return real_info(message, *args, **kwargs)

    monkeypatch.setattr(merge_module.logger, "info", fail_only_committed_message)
    response = client.post(
        "/api/v1/admin/users/merge",
        headers=_headers(admin),
        json={"source_user_id": source_id, "target_user_id": target_id},
    )

    assert response.status_code == 200
    assert response.json()["source_user_id"] == source_id
    assert response.json()["target_user_id"] == target_id
    assert db.get(User, source_id) is None
    assert db.get(User, target_id) is not None
    actions = [
        item.action
        for item in db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == admin.id)
        .order_by(AgentAuditLog.id)
    ]
    assert actions == [
        "privileged_request_authorized",
        "admin_user_merge_authorized",
        "admin_user_merge_completed",
    ]


def test_non_admin_cannot_reach_admin_merge_service(client, db, monkeypatch):
    ordinary = _user(db, "ordinary-caller", is_admin=False)
    source = _user(db, "nonadmin-source")
    target = _user(db, "nonadmin-target")

    def forbidden_merge(*args, **kwargs):
        raise AssertionError("non-admin reached merge service")

    monkeypatch.setattr(UserMergeService, "merge_users", forbidden_merge)
    response = client.post(
        "/api/v1/admin/users/merge",
        headers=_headers(ordinary),
        json={"source_user_id": source.id, "target_user_id": target.id},
    )

    assert response.status_code == 403
    assert db.get(User, source.id) is not None
    assert db.get(User, target.id) is not None


def test_non_enforced_admin_merge_preserves_legacy_status_compatibility(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    admin = _user(db, "admin-compat", is_admin=True)
    source = _user(db, "compat-pending-source", is_approved=False)
    target = _user(db, "compat-target")
    calls = []

    def safe_merge(
        *, db, source_user_id, target_user_id, require_active_approved=False
    ):
        calls.append((source_user_id, target_user_id, require_active_approved))
        return {
            "success": True,
            "source_user_id": source_user_id,
            "target_user_id": target_user_id,
            "stats": {},
        }

    monkeypatch.setattr(UserMergeService, "merge_users", safe_merge)
    response = client.post(
        "/api/v1/admin/users/merge",
        headers=_headers(admin),
        json={"source_user_id": source.id, "target_user_id": target.id},
    )

    assert response.status_code == 200
    assert calls == [(source.id, target.id, False)]


def test_merge_service_revalidates_status_under_lock_before_any_migration(
    db, monkeypatch
):
    source = _user(db, "locked-pending-source", is_approved=False)
    target = _user(db, "locked-target")
    discovery_calls = 0

    def forbidden_discovery(_db):
        nonlocal discovery_calls
        discovery_calls += 1
        raise AssertionError("migration discovery ran for ineligible accounts")

    monkeypatch.setattr(
        UserMergeService,
        "_get_all_user_tables",
        staticmethod(forbidden_discovery),
    )

    with pytest.raises(ValueError, match="仅可合并已启用且已审核的既有账号"):
        UserMergeService.merge_users(
            db,
            source.id,
            target.id,
            require_active_approved=True,
        )

    assert discovery_calls == 0
    assert db.get(User, source.id) is not None
    assert db.get(User, target.id) is not None


def test_admin_merge_failure_is_bounded_and_preserves_authorization_audit(
    client, db, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, "admin-failure", is_admin=True)
    source = _user(db, "failure-source")
    target = _user(db, "failure-target")
    sensitive = "provider-database-private-error-marker"

    def failed_merge(*args, **kwargs):
        raise RuntimeError(sensitive)

    monkeypatch.setattr(UserMergeService, "merge_users", failed_merge)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/admin/users/merge",
            headers=_headers(admin),
            json={"source_user_id": source.id, "target_user_id": target.id},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ACCOUNT_MERGE_FAILED"
    assert sensitive not in response.text
    assert sensitive not in caplog.text
    assert db.get(User, source.id) is not None
    assert db.get(User, target.id) is not None
    actions = [
        item.action
        for item in db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == admin.id)
        .order_by(AgentAuditLog.id)
    ]
    assert actions == [
        "privileged_request_authorized",
        "admin_user_merge_authorized",
        "admin_user_merge_failed",
    ]
    terminal = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "admin_user_merge_failed")
        .one()
    )
    assert sensitive not in terminal.result_summary
    assert sensitive not in repr(terminal.result_detail)
    assert set(terminal.result_detail) == {
        "source_user_id",
        "target_user_id",
        "source_active",
        "source_approved",
        "target_active",
        "target_approved",
    }


def test_admin_merge_failure_audit_error_does_not_mask_primary_api_error(
    client, db, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, "admin-failed-audit", is_admin=True)
    source = _user(db, "failed-audit-source")
    target = _user(db, "failed-audit-target")
    merge_sensitive = "merge-provider-private-marker"
    audit_sensitive = "audit-provider-private-marker"
    real_commit = db.commit

    def failed_merge(*args, **kwargs):
        raise RuntimeError(merge_sensitive)

    def fail_only_terminal_audit_commit():
        if any(
            isinstance(item, AgentAuditLog)
            and item.action == "admin_user_merge_failed"
            for item in db.new
        ):
            raise RuntimeError(audit_sensitive)
        return real_commit()

    monkeypatch.setattr(UserMergeService, "merge_users", failed_merge)
    monkeypatch.setattr(db, "commit", fail_only_terminal_audit_commit)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/admin/users/merge",
            headers=_headers(admin),
            json={"source_user_id": source.id, "target_user_id": target.id},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ACCOUNT_MERGE_FAILED"
    assert merge_sensitive not in response.text
    assert audit_sensitive not in response.text
    assert merge_sensitive not in caplog.text
    assert audit_sensitive not in caplog.text
    assert "管理员合并失败审计写入失败" in caplog.text
    actions = [
        item.action
        for item in db.query(AgentAuditLog)
        .filter(AgentAuditLog.user_id == admin.id)
        .order_by(AgentAuditLog.id)
    ]
    assert actions == [
        "privileged_request_authorized",
        "admin_user_merge_authorized",
    ]


def test_admin_merge_compound_cleanup_failures_still_return_bounded_503(
    client, db, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _user(db, "admin-compound-failure", is_admin=True)
    source = _user(db, "compound-failure-source")
    target = _user(db, "compound-failure-target")
    service_sensitive = "service-primary-private-marker"
    audit_sensitive = "audit-commit-private-marker"
    rollback_sensitive = "rollback-private-marker"
    logger_sensitive = "logger-private-marker"
    real_commit = db.commit

    def failed_merge(*args, **kwargs):
        raise RuntimeError(service_sensitive)

    def fail_only_terminal_audit_commit():
        if any(
            isinstance(item, AgentAuditLog)
            and item.action == "admin_user_merge_failed"
            for item in db.new
        ):
            raise RuntimeError(audit_sensitive)
        return real_commit()

    def failed_rollback():
        raise RuntimeError(rollback_sensitive)

    def failed_logger(*args, **kwargs):
        raise RuntimeError(logger_sensitive)

    monkeypatch.setattr(UserMergeService, "merge_users", failed_merge)
    monkeypatch.setattr(db, "commit", fail_only_terminal_audit_commit)
    monkeypatch.setattr(db, "rollback", failed_rollback)
    monkeypatch.setattr(admin_api.logger, "error", failed_logger)

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/admin/users/merge",
            headers=_headers(admin),
            json={"source_user_id": source.id, "target_user_id": target.id},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ACCOUNT_MERGE_FAILED",
        "message": "账号合并失败，请稍后重试",
    }
    for sensitive in (
        service_sensitive,
        audit_sensitive,
        rollback_sensitive,
        logger_sensitive,
    ):
        assert sensitive not in response.text
        assert sensitive not in caplog.text


def test_postgres_concurrent_same_source_merge_has_one_winner_and_no_data_loss(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row-lock semantics")

    source = _user(db, "pg-concurrent-source")
    target = _user(db, "pg-concurrent-target")
    report = MonthlyReport(
        user_id=source.id,
        year=2026,
        month=9,
        report_data={"owner": "source-private-marker"},
    )
    db.add(report)
    db.commit()
    source_id = source.id
    target_id = target.id
    report_id = report.id
    barrier = threading.Barrier(2)
    SessionLocal = sessionmaker(bind=db.bind)

    def compete():
        session = SessionLocal()
        try:
            barrier.wait(timeout=10)
            return (
                "success",
                UserMergeService.merge_users(
                    session,
                    source_id,
                    target_id,
                    require_active_approved=True,
                ),
            )
        except Exception as exc:  # result is asserted below; never logged
            session.rollback()
            return ("failed", type(exc).__name__, str(exc))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(compete) for _ in range(2)]
        outcomes = [future.result(timeout=30) for future in futures]

    assert [item[0] for item in outcomes].count("success") == 1
    assert [item[0] for item in outcomes].count("failed") == 1
    failure = next(item for item in outcomes if item[0] == "failed")
    assert failure[1:] == ("ValueError", "用户不存在")
    db.expire_all()
    assert db.get(User, source_id) is None
    assert db.get(User, target_id) is not None
    persisted = db.get(MonthlyReport, report_id)
    assert persisted is not None
    assert persisted.user_id == target_id
    assert db.query(MonthlyReport).filter(MonthlyReport.id == report_id).count() == 1


def test_user_merge_service_rolls_back_partial_migration_and_preserves_accounts(
    db, monkeypatch
):
    source = _user(
        db,
        "rollback-source",
        hashed_password="rollback-source-password-private-marker",
        wechat_openid="rollback-source-openid-private-marker",
    )
    target = _user(db, "rollback-target", hashed_password=None, wechat_openid=None)
    report = MonthlyReport(
        user_id=source.id,
        year=2026,
        month=8,
        report_data={"owner": "source"},
    )
    db.add(report)
    db.commit()
    report_id = report.id

    monkeypatch.setattr(
        UserMergeService,
        "_get_all_user_tables",
        staticmethod(lambda _db: ["monthly_reports"]),
    )

    def mutate_then_fail(db, table_name, unique_cols, source_id, target_id):
        db.execute(
            text("UPDATE monthly_reports SET user_id = :target WHERE id = :report"),
            {"target": target_id, "report": report_id},
        )
        raise RuntimeError("bounded forced migration failure")

    monkeypatch.setattr(
        UserMergeService,
        "_migrate_composite_unique_table",
        staticmethod(mutate_then_fail),
    )

    with pytest.raises(RuntimeError, match="bounded forced migration failure"):
        UserMergeService.merge_users(db, source.id, target.id)

    db.expire_all()
    assert db.get(MonthlyReport, report_id).user_id == source.id
    persisted_source = db.get(User, source.id)
    persisted_target = db.get(User, target.id)
    assert persisted_source is not None
    assert persisted_target is not None
    assert persisted_source.hashed_password == "rollback-source-password-private-marker"
    assert persisted_target.hashed_password is None
    assert persisted_target.wechat_openid is None
