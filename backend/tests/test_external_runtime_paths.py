from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.utils import runtime_data


def test_upload_dir_uses_external_production_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HEALTH_UPLOAD_DIR", raising=False)

    assert runtime_data.upload_dir() == Path("/var/lib/health-app/uploads")


def test_upload_dir_preserves_legacy_development_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("HEALTH_UPLOAD_DIR", raising=False)

    assert runtime_data.upload_dir() == (
        Path(__file__).resolve().parents[1] / "uploads"
    )


def test_skills_cache_uses_external_production_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HEALTH_SKILLS_CACHE_DIR", raising=False)

    assert runtime_data.skills_hub_cache_dir() == Path(
        "/var/cache/health-app/skills-hub"
    )


def test_skills_cache_preserves_legacy_development_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("HEALTH_SKILLS_CACHE_DIR", raising=False)

    assert runtime_data.skills_hub_cache_dir() == (
        Path.home() / ".health-skills-cache"
    )


@pytest.mark.parametrize(
    ("environment_name", "resolver_name"),
    (
        ("HEALTH_UPLOAD_DIR", "upload_dir"),
        ("HEALTH_SKILLS_CACHE_DIR", "skills_hub_cache_dir"),
    ),
)
def test_mutable_path_overrides_must_be_absolute(
    monkeypatch,
    environment_name,
    resolver_name,
):
    monkeypatch.setenv(environment_name, "relative/path")

    with pytest.raises(ValueError, match="absolute"):
        getattr(runtime_data, resolver_name)()


@pytest.mark.parametrize(
    ("environment_name", "resolver_name"),
    (
        ("HEALTH_UPLOAD_DIR", "upload_dir"),
        ("HEALTH_SKILLS_CACHE_DIR", "skills_hub_cache_dir"),
    ),
)
def test_production_mutable_path_overrides_must_be_outside_checkout(
    monkeypatch,
    environment_name,
    resolver_name,
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(environment_name, str(runtime_data._CHECKOUT_ROOT))

    with pytest.raises(ValueError, match="outside the Git checkout"):
        getattr(runtime_data, resolver_name)()


def test_skills_hub_client_uses_shared_cache_resolver(monkeypatch, tmp_path):
    from app.services.skills_hub_client import SkillsHubClient

    cache_dir = tmp_path / "hub-cache"
    monkeypatch.setenv("HEALTH_SKILLS_CACHE_DIR", str(cache_dir))

    client = SkillsHubClient()

    assert client.CACHE_DIR == cache_dir
    assert not cache_dir.exists()

    monkeypatch.setattr(
        client,
        "_fetch_url",
        lambda _url: '{"domains": []}',
    )
    assert client.get_taxonomy() == {"domains": []}
    assert cache_dir.is_dir()


class _PathAccessForbidden:
    def __truediv__(self, _child):
        pytest.fail("production mutation inspected the Skills path")


def test_production_skill_install_is_disabled_before_fetch_or_path_access(
    monkeypatch,
    tmp_path,
):
    from app.services import skills_hub_client as hub_module

    cache_dir = tmp_path / "hub-cache"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "HEALTH_SKILLS_CACHE_DIR",
        str(cache_dir),
    )
    client = hub_module.SkillsHubClient()
    assert not cache_dir.exists()
    monkeypatch.setattr(hub_module, "SKILLS_DIR", _PathAccessForbidden())

    def unexpected_fetch(*_args, **_kwargs):
        pytest.fail("production mutation fetched remote Skill content")

    monkeypatch.setattr(client, "fetch_skill", unexpected_fetch)

    assert client.install_skill("nutrition", "example") == {
        "success": False,
        "error": "hub_skill_mutation_disabled",
    }


def test_production_skill_uninstall_is_disabled_before_path_access(
    monkeypatch,
    tmp_path,
):
    from app.services import skills_hub_client as hub_module

    cache_dir = tmp_path / "hub-cache"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "HEALTH_SKILLS_CACHE_DIR",
        str(cache_dir),
    )
    client = hub_module.SkillsHubClient()
    assert not cache_dir.exists()
    monkeypatch.setattr(hub_module, "SKILLS_DIR", _PathAccessForbidden())

    assert client.uninstall_skill("example") == {
        "success": False,
        "error": "hub_skill_mutation_disabled",
    }


@pytest.mark.parametrize(
    ("operation_name", "arguments"),
    (
        ("install_hub_skill", ("nutrition", "example")),
        ("uninstall_hub_skill", ("example",)),
    ),
)
def test_production_skills_api_surfaces_mutation_disabled_as_400(
    monkeypatch,
    operation_name,
    arguments,
):
    from app.api import skills as skills_api

    monkeypatch.setenv("APP_ENV", "production")
    admin = type("Admin", (), {"is_admin": True})()

    with pytest.raises(HTTPException) as captured:
        getattr(skills_api, operation_name)(
            *arguments,
            current_user=admin,
        )

    assert captured.value.status_code == 400
    assert captured.value.detail == "hub_skill_mutation_disabled"


def test_upload_consumers_share_resolved_override(tmp_path):
    upload_root = tmp_path / "external-uploads"
    environment = {
        **os.environ,
        "APP_ENV": "production",
        "DATABASE_URL": "sqlite:///:memory:",
        "HEALTH_UPLOAD_DIR": str(upload_root),
    }
    script = """
import base64
import json
from app.api import upload, users
from app.services import account_deletion, aigc_media_job_service, chat_utils
from app.services.diet_media_storage import store_diet_image

diet_photo = store_diet_image(
    base64.b64encode(b"\\x89PNG\\r\\n\\x1a\\npayload").decode(),
    "png",
    owner_id=7,
)

print("UPLOAD_PATHS=" + json.dumps([
    upload.UPLOAD_DIR,
    users.UPLOAD_DIR,
    chat_utils._UPLOAD_DIR,
    str(aigc_media_job_service._AIGC_UPLOAD_ROOT),
    str(account_deletion._UPLOAD_ROOT),
    diet_photo.file_path,
]))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    payload = next(
        line.removeprefix("UPLOAD_PATHS=")
        for line in completed.stdout.splitlines()
        if line.startswith("UPLOAD_PATHS=")
    )

    paths = json.loads(payload)
    assert paths[:5] == [
        str(upload_root),
        str(upload_root),
        str(upload_root / "chat"),
        str(upload_root / "aigc"),
        str(upload_root),
    ]
    diet_path = Path(paths[5])
    assert diet_path.parent == upload_root / "diet" / "7"
    assert diet_path.read_bytes() == b"\x89PNG\r\n\x1a\npayload"
