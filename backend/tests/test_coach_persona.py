"""test_coach_persona —— P3-1: User.coach_persona 字段 + endpoint + Orchestrator prompt 切换."""

import uuid
from unittest.mock import patch

import pytest

from app.models.user import User
from app.orchestrator.orchestrator import (
    PERSONA_ADDENDUM,
    _build_persona_addendum,
)
from app.services.auth import auth_service


def _make_user(db, persona=None):
    u = User(
        username=f"persona_{uuid.uuid4().hex[:8]}",
        email=f"persona_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="persona",
        is_active=True,
        is_approved=True,
    )
    if persona:
        u.coach_persona = persona
    db.add(u)
    db.commit()
    db.refresh(u)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, {"Authorization": f"Bearer {token}"}


# ── Endpoint ────────────────────────────────────────────────────────────────


def test_get_default_persona_is_gentle(client, db):
    user, headers = _make_user(db)
    resp = client.get("/api/v1/users/me/coach-persona", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["coach_persona"] == "gentle_advisor"


@pytest.mark.parametrize("persona", ["strict_coach", "gentle_advisor", "data_driven"])
def test_set_persona_persists(client, db, persona):
    user, headers = _make_user(db)
    resp = client.patch(
        "/api/v1/users/me/coach-persona",
        headers=headers,
        json={"coach_persona": persona},
    )
    assert resp.status_code == 200
    assert resp.json()["coach_persona"] == persona

    # 二次 GET 验持久化
    r2 = client.get("/api/v1/users/me/coach-persona", headers=headers)
    assert r2.json()["coach_persona"] == persona


def test_set_invalid_persona_rejected(client, db):
    user, headers = _make_user(db)
    resp = client.patch(
        "/api/v1/users/me/coach-persona",
        headers=headers,
        json={"coach_persona": "drill_sergeant"},
    )
    assert resp.status_code == 400


# ── Prompt Addendum ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona,marker",
    [
        ("strict_coach", "严厉教练"),
        ("gentle_advisor", "温和顾问"),
        ("data_driven", "数据派"),
    ],
)
def test_build_persona_addendum_returns_correct_template(db, persona, marker):
    user, _ = _make_user(db, persona=persona)
    addendum = _build_persona_addendum(db, user.id)
    assert marker in addendum
    assert addendum == PERSONA_ADDENDUM[persona]


def test_build_persona_addendum_unknown_persona_returns_empty(db):
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="x",
        coach_persona="bogus",
    )
    db.add(user)
    db.commit()
    addendum = _build_persona_addendum(db, user.id)
    assert addendum == ""


def test_build_persona_addendum_missing_user_returns_empty(db):
    assert _build_persona_addendum(db, 999999) == ""


def test_persona_template_features_distinct(db):
    """三档语气不能描述相同 — 每档有自己的特征指令."""
    s = PERSONA_ADDENDUM["strict_coach"]
    g = PERSONA_ADDENDUM["gentle_advisor"]
    d = PERSONA_ADDENDUM["data_driven"]
    assert "立刻" in s or "必须" in s
    assert "共情" in g or "或许" in g or "可以考虑" in g
    assert "数字" in d or "阈值" in d
