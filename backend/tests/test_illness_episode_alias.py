"""病程 episode 录入对弱模型 tool-calling 的容错。

回归:deepseek/qwen 经 health_record skill 把字段写成 illness_name、漏 start_date,
导致 422 (name Field required)。Schema 接受 illness_name 别名 + start_date 默认今天。
"""
import pytest
from app.models.user import User


@pytest.fixture
def auth_headers(client, db):
    user = User(
        username="illnessuser", email="illness@example.com",
        hashed_password="x", name="病程测试", is_active=True, is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service
    return {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def test_episode_accepts_illness_name_alias_and_defaults_start_date(client, auth_headers):
    # 弱模型实测 payload:illness_name 而非 name,且这次漏 start_date
    r = client.post("/api/v1/illness/episodes", headers=auth_headers,
                    json={"illness_name": "鼻炎发作", "severity": 3, "notes": "喷嚏 1 次"})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["name"] == "鼻炎发作"
    assert body["start_date"]  # 默认今天,非 422


def test_episode_still_accepts_canonical_name(client, auth_headers):
    r = client.post("/api/v1/illness/episodes", headers=auth_headers,
                    json={"name": "感冒", "start_date": "2026-06-10", "severity": 5})
    assert r.status_code in (200, 201), r.text
    assert r.json()["name"] == "感冒"


def test_episode_without_severity_persists_unknown_instead_of_midpoint(
    client, auth_headers
):
    r = client.post(
        "/api/v1/illness/episodes",
        headers=auth_headers,
        json={"name": "口腔溃疡", "start_date": "2026-07-17"},
    )

    assert r.status_code in (200, 201), r.text
    assert r.json()["severity"] is None


def test_episode_patch_can_explicitly_clear_severity(client, auth_headers):
    created = client.post(
        "/api/v1/illness/episodes",
        headers=auth_headers,
        json={"name": "感冒", "start_date": "2026-08-08", "severity": 7},
    )
    assert created.status_code in (200, 201), created.text

    patched = client.patch(
        f"/api/v1/illness/episodes/{created.json()['id']}",
        headers=auth_headers,
        json={"severity": None},
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["severity"] is None


def test_episode_patch_rejects_null_status_without_mutating_record(
    client, auth_headers
):
    created = client.post(
        "/api/v1/illness/episodes",
        headers=auth_headers,
        json={"name": "感冒", "start_date": "2026-08-08"},
    )
    assert created.status_code in (200, 201), created.text

    rejected = client.patch(
        f"/api/v1/illness/episodes/{created.json()['id']}",
        headers=auth_headers,
        json={"status": None},
    )

    assert rejected.status_code == 422, rejected.text
    fetched = client.get(
        f"/api/v1/illness/episodes/{created.json()['id']}",
        headers=auth_headers,
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == "active"
