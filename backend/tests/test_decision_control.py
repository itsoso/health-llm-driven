"""Admin identity, durable CAS control, and fail-closed routing."""
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.admin_decisions import router
from app.api.auth import get_current_user_required
from app.config import settings
from app.database import get_db
from app.models.agent_audit_log import AgentAuditLog
from app.models.decision_control import DecisionControl
from app.services.decisions import DecisionError, DecisionRequest, SystemOneProvider
from app.services.decisions import control
from app.services.decisions.config import configured_decision


@pytest.fixture
def configured(db, monkeypatch):
    for name, value in {
        "decision_mode": "on", "decision_provider": "laya",
        "decision_admin_control_enabled": True, "decision_base_url": None,
        "decision_model": None, "decision_api_key": None,
    }.items():
        monkeypatch.setattr(settings, name, value)
    db.add(DecisionControl(id=1, enabled=False, revision=0))
    db.commit()
    monkeypatch.setattr(control, "SessionLocal", sessionmaker(bind=db.get_bind()))
    return db


def client_for(db, uid=3, admin=True, active=True):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        id=uid, is_admin=admin, is_active=active,
    )
    return TestClient(app)


@pytest.mark.parametrize("uid,admin,active", [(4, True, True), (3, False, True), (3, True, False)])
def test_only_active_admin_three_can_read_or_write(configured, uid, admin, active):
    with client_for(configured, uid, admin, active) as client:
        assert client.get("/api/v1/admin/decisions").status_code == 403
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 0}).status_code == 403
    assert configured.query(AgentAuditLog).count() == 0
    assert control.runtime_mode() == "off"


def test_control_persists_is_audited_and_rejects_stale_write(configured):
    with client_for(configured) as client:
        first = client.get("/api/v1/admin/decisions")
        assert first.status_code == 200
        assert first.json()["enabled"] is False
        assert "api_key" not in first.text and "base_url" not in first.text
        updated = client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 0})
        assert updated.status_code == 200
        assert updated.json()["effective_mode"] == "on"
        assert updated.json()["revision"] == 1
        assert control.runtime_mode() == "on"  # a separate DB session
        stale = client.put("/api/v1/admin/decisions", json={"enabled": False, "revision": 0})
        assert stale.status_code == 409
        assert control.runtime_mode() == "on"
        disabled = client.put("/api/v1/admin/decisions", json={"enabled": False, "revision": 1})
        assert disabled.status_code == 200
        assert control.runtime_mode() == "off"
    rows = configured.query(AgentAuditLog).filter_by(action="decision_control_changed").all()
    assert len(rows) == 2 and all(row.user_id == 3 for row in rows)
    assert rows[0].result_detail == {"enabled": True, "previous_enabled": False, "revision": 1}


def test_control_body_is_strict_and_master_off_wins(configured, monkeypatch):
    with client_for(configured) as client:
        assert client.put("/api/v1/admin/decisions", json={"enabled": "true", "revision": 0}).status_code == 422
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 0, "user_id": 3}).status_code == 422
        monkeypatch.setattr(settings, "decision_mode", "off")
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 0}).status_code == 409
        assert control.runtime_mode() == "off"


@pytest.mark.asyncio
async def test_disabled_control_prevents_network_even_for_direct_provider(configured):
    provider = SystemOneProvider(configured_decision(), transport=httpx.MockTransport(
        lambda req: pytest.fail("Disabled switch must prevent transport")
    ))
    request = DecisionRequest(state="synthetic", questions={"q": {"type": "noul", "instructions": "Needed?"}})
    with pytest.raises(DecisionError, match="configuration_changed"):
        await provider.evaluate(request, user_id=3)


def test_missing_control_is_explicit_failure(configured):
    configured.query(DecisionControl).delete()
    configured.commit()
    with pytest.raises(DecisionError, match="control_unavailable"):
        control.runtime_mode()
    with client_for(configured) as client:
        assert client.get("/api/v1/admin/decisions").status_code == 503


def test_future_revision_rejected_before_update_and_invalid_config_allows_off(configured, monkeypatch):
    with client_for(configured) as client:
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 1}).status_code == 409
        assert control.read_control(configured).revision == 0
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 0}).status_code == 200
        monkeypatch.setattr(settings, "decision_base_url", "http://untrusted.example/v1")
        state = client.get("/api/v1/admin/decisions")
        assert state.status_code == 200 and state.json()["configured"] is False
        disabled = client.put("/api/v1/admin/decisions", json={"enabled": False, "revision": 1})
        assert disabled.status_code == 200 and disabled.json()["effective_mode"] == "off"
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 2}).status_code == 409


def test_unauthenticated_requests_cannot_access_control(configured):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: configured
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/decisions").status_code == 401
        assert client.put("/api/v1/admin/decisions", json={"enabled": True, "revision": 0}).status_code == 401


def test_postgres_concurrent_admin_updates_have_one_winner(configured):
    if configured.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated PostgreSQL")
    from app.api.admin_decisions import DecisionControlUpdate, update_decision_control
    sessions = sessionmaker(bind=configured.get_bind())
    barrier = Barrier(3)

    def change():
        with sessions() as db:
            barrier.wait(timeout=5)
            try:
                update_decision_control(DecisionControlUpdate(enabled=True, revision=0), SimpleNamespace(id=3), db)
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: change(), range(3)))
    assert sorted(results) == [200, 409, 409]
    assert configured.query(AgentAuditLog).filter_by(action="decision_control_changed").count() == 1
    assert control.read_control(configured).revision == 1


def test_dialect_migration_replays_without_resetting_switch(db):
    from app.services.managed_migrations import _split_sql_statements
    dialect = db.get_bind().dialect.name
    path = Path(__file__).parents[1] / "migrations/managed" / f"20260924_100000_decision_control.{dialect}.sql"
    db.execute(text("DROP TABLE decision_controls"))
    for statement in _split_sql_statements(path.read_text()):
        db.execute(text(statement))
    db.commit()
    assert db.execute(text("SELECT enabled, revision FROM decision_controls")).one() == (False, 0)
    db.execute(text("UPDATE decision_controls SET enabled = TRUE, revision = 1 WHERE id = 1"))
    for statement in _split_sql_statements(path.read_text()):
        db.execute(text(statement))
    db.commit()
    assert db.execute(text("SELECT enabled, revision FROM decision_controls")).one() == (True, 1)
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO decision_controls (id) VALUES (2)"))
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE decision_controls SET updated_by = 4 WHERE id = 1"))
        db.commit()
    db.rollback()


@pytest.mark.asyncio
async def test_disable_while_inference_runs_discards_advice(configured, monkeypatch):
    from app.services.decisions.routing import decide_route
    from app.services.decisions.systemone import DecisionResult

    configured.query(DecisionControl).update({"enabled": True})
    configured.commit()

    class Provider:
        async def evaluate(self, request, *, user_id):
            configured.query(DecisionControl).update({"enabled": False})
            configured.commit()
            return DecisionResult("synthetic", {}, 1, 0)

    monkeypatch.setattr("app.services.decisions.routing.provider_from_settings", lambda: Provider())
    result = await decide_route("synthetic", user_id=3, baseline_tier="balanced")
    assert result.status == "fallback" and result.reason == "configuration_changed"
    assert result.effective_tier == "balanced" and result.prompt_hint() == ""
