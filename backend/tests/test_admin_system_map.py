from __future__ import annotations

import importlib
from pathlib import Path

import pytest


ENDPOINT = "/api/v1/admin/system-map"


def _admin_headers(db, auth_user_and_headers) -> dict[str, str]:
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add(user)
    db.commit()
    return headers


def _api_module():
    try:
        return importlib.import_module("app.api.admin_system_map")
    except ModuleNotFoundError:
        pytest.fail("app.api.admin_system_map must provide the protected endpoint")


def test_system_map_rejects_unauthenticated(client) -> None:
    assert client.get(ENDPOINT).status_code == 401


def test_system_map_rejects_non_admin(client, auth_user_and_headers) -> None:
    _, headers = auth_user_and_headers

    assert client.get(ENDPOINT, headers=headers).status_code == 403


def test_system_map_returns_valid_graph_to_admin(client, db, auth_user_and_headers) -> None:
    headers = _admin_headers(db, auth_user_and_headers)

    response = client.get(ENDPOINT, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "2.0"
    assert payload["entities"]
    assert payload["relations"]


@pytest.mark.parametrize(
    "content",
    [
        None,
        "{not-json",
        '{"schema_version": "2.0"}',
    ],
    ids=["missing", "corrupt", "invalid-contract"],
)
def test_system_map_unavailable_artifact_is_explicit_503(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
    tmp_path: Path,
    content: str | None,
) -> None:
    module = _api_module()
    artifact = tmp_path / "system-map.json"
    if content is not None:
        artifact.write_text(content, encoding="utf-8")
    monkeypatch.setattr(module, "SYSTEM_MAP_PATH", artifact)
    headers = _admin_headers(db, auth_user_and_headers)

    response = client.get(ENDPOINT, headers=headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "系统地图暂不可用"}
