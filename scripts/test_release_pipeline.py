import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = ROOT / "scripts/release.py"
_TEST_AUTHORITY_URL: str | None = None


def _release_module():
    assert RELEASE_SCRIPT.exists(), "scripts/release.py has not been implemented"
    spec = importlib.util.spec_from_file_location("reva_release", RELEASE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if _TEST_AUTHORITY_URL is not None:
        module.CANONICAL_RELEASE_ORIGIN_URL = _TEST_AUTHORITY_URL
    return module


def _change(release, status: str, *paths: str):
    return release.Change(status=status, paths=paths)


def _isolated_historical_ota_protocol_plan(
    release,
    changes,
    *,
    base_sha: str,
    target_sha: str,
    completed_actions=(),
):
    """Test-module-only protocol fixture; production planning remains frozen."""

    plan = release.build_plan(
        changes,
        base_sha=base_sha,
        target_sha=target_sha,
        completed_actions=completed_actions,
    )
    assert "mobile_ota" in plan.surfaces
    assert "mobile_native" in plan.surfaces
    assert "native_build" in plan.actions
    assert plan.publishable is False
    assert not plan.blocked_paths

    actions = ["validate"]
    if "frontend" in plan.surfaces:
        actions.append("deploy_all")
    elif "backend" in plan.surfaces:
        actions.append("deploy_backend")
    actions.append("mobile_ota")
    return replace(
        plan,
        surfaces=tuple(
            surface for surface in plan.surfaces if surface != "mobile_native"
        ),
        actions=tuple(actions),
        publishable=True,
    )


def _production_surfaces(
    *,
    backend_sha: str,
    mobile_ota_sha: str,
    backend_proof_id: str = "backend-proof-old",
    frontend_sha: str | None = None,
    frontend_proof_id: str | None = None,
    mobile_group_id: str = "mobile-group-old",
    mobile_update_id: str = "mobile-update-old",
    mobile_runtime: str = "1.3.3",
    mobile_channel_id: str = "channel-old",
    mobile_channel_updated_at: str = "2026-08-12T00:00:00Z",
    mobile_branch_mapping: str = '{"data":[{"branchId":"branch-old"}],"version":0}',
    mobile_branch_id: str = "branch-old",
    mobile_identity_digest: str = "1" * 64,
    mobile_runtime_vector_digest: str = "3" * 64,
    mac_sha: str | None = None,
    mac_artifact_sha256: str | None = None,
    mac_receipt_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        backend_sha=backend_sha,
        backend_proof_id=backend_proof_id,
        frontend_sha=frontend_sha,
        frontend_proof_id=frontend_proof_id,
        # Compatibility with the first production-probe schema.
        server_sha=backend_sha,
        mobile_ota_sha=mobile_ota_sha,
        mobile_group_id=mobile_group_id,
        mobile_update_id=mobile_update_id,
        mobile_runtime=mobile_runtime,
        mobile_channel_id=mobile_channel_id,
        mobile_channel_updated_at=mobile_channel_updated_at,
        mobile_branch_mapping=mobile_branch_mapping,
        mobile_branch_id=mobile_branch_id,
        mobile_identity_digest=mobile_identity_digest,
        mobile_runtime_vector_digest=mobile_runtime_vector_digest,
        mac_sha=mac_sha,
        mac_artifact_sha256=mac_artifact_sha256,
        mac_receipt_id=mac_receipt_id,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repository_with_origin(tmp_path: Path):
    origin = tmp_path / "origin.git"
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "release@example.test")
    _git(repo, "config", "user.name", "Release Test")
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "initial")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-qu", "origin", "main")
    global _TEST_AUTHORITY_URL
    previous = _TEST_AUTHORITY_URL
    _TEST_AUTHORITY_URL = str(origin)
    try:
        yield repo, origin
    finally:
        _TEST_AUTHORITY_URL = previous


def test_parses_git_name_status_with_rename_and_delete():
    release = _release_module()

    changes = release.parse_name_status(
        b"R100\0backend/app/old.py\0mobile/app/new.tsx\0D\0mobile/app.json\0"
    )

    assert changes == (
        _change(
            release,
            "R100",
            "backend/app/old.py",
            "mobile/app/new.tsx",
        ),
        _change(release, "D", "mobile/app.json"),
    )


@pytest.mark.parametrize("command", ("plan", "validate", "publish"))
def test_release_cli_is_frozen_before_local_imports_git_tokens_or_locks(
    tmp_path: Path,
    command: str,
) -> None:
    isolated = tmp_path / "scripts"
    isolated.mkdir()
    script = isolated / "release.py"
    shutil.copyfile(RELEASE_SCRIPT, script)
    marker = tmp_path / "local-import-ran"
    (isolated / "json.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('called')\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git_marker = tmp_path / "fake-git-ran"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        f"#!/bin/sh\nprintf called > {fake_git_marker!s}\nexit 91\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    result = subprocess.run(
        [sys.executable, str(script), command, "--base", "HEAD"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin), "EXPO_TOKEN": "must-not-leak"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78, result.stdout + result.stderr
    assert "manual Gate" in result.stderr
    assert "must-not-leak" not in result.stdout + result.stderr
    assert not marker.exists()
    assert not fake_git_marker.exists()


def test_release_executable_ignores_hostile_path_before_freeze(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    marker = tmp_path / "fake-python-called"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        f"#!/bin/sh\nprintf called > {marker!s}\nexit 91\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    result = subprocess.run(
        [str(RELEASE_SCRIPT), "publish", "--base", "HEAD"],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "manual Gate" in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("command", ("plan", "validate", "publish"))
def test_release_wrapper_freezes_all_commands_before_path_tools(
    tmp_path: Path,
    command: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "ambient-command-ran"
    for name in ("dirname", "python3"):
        executable = fake_bin / name
        executable.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)

    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/release.sh"), command],
        cwd=tmp_path,
        env={"PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78, result.stdout + result.stderr
    assert "manual Gate" in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("command", ("plan", "validate", "publish"))
def test_programmatic_main_freezes_production_commands_before_parser(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    release = _release_module()

    def unexpected_parser():
        raise AssertionError("parser must not run for publish")

    monkeypatch.setattr(release, "_build_parser", unexpected_parser)

    assert release.main([command]) == 78


def test_mobile_runtime_change_requires_manual_native_build_while_production_ota_is_frozen():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", "mobile/app/settings.tsx"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native", "mobile_ota")
    assert plan.actions == ("validate", "native_build")
    assert plan.publishable is False


def test_native_mobile_change_suppresses_ota():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "mobile/app/settings.tsx"),
            _change(release, "M", "mobile/app.json"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native", "mobile_ota")
    assert plan.actions == ("validate", "native_build")
    assert "mobile_ota" not in plan.actions
    assert plan.publishable is False


def test_backend_and_mobile_ota_are_ordered_server_first():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "mobile/services/api.ts"),
            _change(release, "M", "backend/app/api/profile.py"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.actions == ("validate", "deploy_backend", "native_build")
    assert plan.publishable is False


def test_frontend_change_uses_full_deploy_for_new_repository_sha():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", "frontend/app/page.tsx"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.actions == ("validate", "deploy_all")
    assert "deploy_frontend" not in plan.actions


def test_frontend_backend_and_ota_use_one_full_deploy_then_ota():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "frontend/app/page.tsx"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.actions == ("validate", "deploy_all", "native_build")
    assert plan.publishable is False


def test_docs_and_tests_are_validation_only():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "docs/governance/deploy.md"),
            _change(release, "A", "backend/tests/test_profile.py"),
            _change(release, "A", "mobile/app/__tests__/settings.test.tsx"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("validation_only",)
    assert plan.actions == ("validate",)
    assert plan.publishable is True


@pytest.mark.parametrize(
    "path",
    (
        "apps/mac/README.md",
        "apps/watch/README.md",
        "apps/rokid-pushup-glasses/README.md",
        "mobile/PRODUCT_MAP.md",
        "mobile/SENTRY_SETUP.md",
    ),
)
def test_colocated_client_documents_are_validation_only(path: str):
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", path),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("validation_only",)
    assert plan.actions == ("validate",)


@pytest.mark.parametrize(
    ("old_path", "new_path", "expected"),
    (
        ("apps/mac/README.md", "apps/mac/NOTES.md", "mac"),
        ("apps/watch/README.md", "apps/watch/Notes.swift", "mobile_native"),
        ("mobile/PRODUCT_MAP.md", "mobile/app/product.ts", "mobile_ota"),
    ),
)
def test_rename_between_colocated_docs_and_runtime_classifies_both_directions(
    old_path: str, new_path: str, expected: str
):
    release = _release_module()
    forward = release.build_plan(
        (_change(release, "R100", old_path, new_path),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )
    backward = release.build_plan(
        (_change(release, "R100", new_path, old_path),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    expected_surfaces = (
        ("mobile_native", "mobile_ota")
        if expected == "mobile_ota"
        else (expected,)
    )
    assert forward.surfaces == expected_surfaces
    assert backward.surfaces == expected_surfaces
    assert forward.actions == backward.actions


@pytest.mark.parametrize(
    "path",
    [
        "deploy.sh",
        "backend/scripts/verify_locked_requirements.py",
        "backend/scripts/import_system_kb_v2_artifacts.py",
    ],
)
def test_server_release_inputs_require_backend_deploy(path: str):
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", path),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("backend",)
    assert plan.actions == ("validate", "deploy_backend")


def test_unknown_path_blocks_release_fail_closed():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "A", "new-product-surface/config.toml"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.blocked_paths == ("new-product-surface/config.toml",)
    assert plan.publishable is False


def test_root_eas_build_input_requires_native_release():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", ".easignore"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native",)
    assert plan.blocked_paths == ()
    assert plan.publishable is False


def _commit_mobile_config_fixture(
    repo: Path,
    *,
    app_json: dict | None = None,
    app_config: str | None = None,
) -> str:
    mobile = repo / "mobile"
    (mobile / "assets/images").mkdir(parents=True, exist_ok=True)
    (mobile / "assets/social").mkdir(parents=True, exist_ok=True)
    (mobile / "assets/rokid").mkdir(parents=True, exist_ok=True)
    (mobile / "assets/images/icon.png").write_bytes(b"icon-v1")
    (mobile / "assets/images/splash.png").write_bytes(b"splash-v1")
    (mobile / "assets/images/adaptive.png").write_bytes(b"adaptive-v1")
    (mobile / "assets/images/adaptive-background.png").write_bytes(b"background-v1")
    (mobile / "assets/images/adaptive-monochrome.png").write_bytes(b"monochrome-v1")
    (mobile / "assets/images/notification.png").write_bytes(b"notification-v1")
    (mobile / "assets/images/favicon.png").write_bytes(b"favicon-v1")
    (mobile / "assets/social/share.jpg").write_bytes(b"share-v1")
    (mobile / "assets/rokid/rokid-pushup-glasses.apk").write_bytes(b"apk-v1")
    if app_json is not None:
        (mobile / "app.json").write_text(json.dumps(app_json), encoding="utf-8")
    if app_config is not None:
        (mobile / "app.config.ts").write_text(app_config, encoding="utf-8")
    _git(repo, "add", "mobile")
    _git(repo, "commit", "-qm", "mobile config fixture")
    return _git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    ("expo_config", "expected_asset"),
    [
        ({"icon": "./native.bin"}, "mobile/native.bin"),
        ({"splash": {"image": "./native.bin"}}, "mobile/native.bin"),
        ({"ios": {"icon": "./native.bin"}}, "mobile/native.bin"),
        ({"ios": {"icon": {"light": "./native.bin"}}}, "mobile/native.bin"),
        ({"ios": {"icon": {"dark": "./native.bin"}}}, "mobile/native.bin"),
        ({"ios": {"icon": {"tinted": "./native.bin"}}}, "mobile/native.bin"),
        ({"ios": {"googleServicesFile": "./native.bin"}}, "mobile/native.bin"),
        ({"ios": {"splash": {"image": "./native.bin"}}}, "mobile/native.bin"),
        (
            {"ios": {"splash": {"tabletImage": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"ios": {"splash": {"dark": {"image": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"ios": {"splash": {"dark": {"tabletImage": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        ({"android": {"icon": "./native.bin"}}, "mobile/native.bin"),
        (
            {"android": {"googleServicesFile": "./native.bin"}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"image": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"mdpi": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"hdpi": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"xhdpi": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"xxhdpi": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"xxxhdpi": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"dark": {"image": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"dark": {"mdpi": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"dark": {"hdpi": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"dark": {"xhdpi": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"dark": {"xxhdpi": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"splash": {"dark": {"xxxhdpi": "./native.bin"}}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"adaptiveIcon": {"foregroundImage": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"adaptiveIcon": {"backgroundImage": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"android": {"adaptiveIcon": {"monochromeImage": "./native.bin"}}},
            "mobile/native.bin",
        ),
        ({"notification": {"icon": "./native.bin"}}, "mobile/native.bin"),
        ({"web": {"favicon": "./native.bin"}}, "mobile/native.bin"),
        (
            {"web": {"splash": {"image": "./native.bin"}}},
            "mobile/native.bin",
        ),
        (
            {"updates": {"codeSigningCertificate": "./native.bin"}},
            "mobile/native.bin",
        ),
        ({"locales": {"zh": "./native.bin"}}, "mobile/native.bin"),
        ({"plugins": ["./native.bin"]}, "mobile/native.bin"),
        ({"plugins": [["./native.bin", {}]]}, "mobile/native.bin"),
        (
            {"plugins": [["expo-notifications", {"icon": "./native.bin"}]]},
            "mobile/native.bin",
        ),
        (
            {"plugins": [["expo-notifications", {"sounds": ["./native.bin"]}]]},
            "mobile/native.bin",
        ),
        (
            {"plugins": [["expo-splash-screen", {"image": "./native.bin"}]]},
            "mobile/native.bin",
        ),
        (
            {"plugins": [["expo-splash-screen", {"dark": {"image": "./native.bin"}}]]},
            "mobile/native.bin",
        ),
        (
            {"plugins": [["expo-splash-screen", {"ios": {"image": "./native.bin"}}]]},
            "mobile/native.bin",
        ),
        (
            {
                "plugins": [
                    [
                        "expo-splash-screen",
                        {"android": {"image": "./native.bin"}},
                    ]
                ]
            },
            "mobile/native.bin",
        ),
    ],
)
def test_each_app_json_native_reference_is_classified_independently(
    expo_config: dict, expected_asset: str
):
    release = _release_module()

    assets = frozenset(
        release._app_json_native_assets(
            json.dumps({"expo": expo_config}), source="mobile/app.json@test"
        )
    )
    plan = release.build_plan(
        (_change(release, "M", expected_asset),),
        base_sha="a" * 40,
        target_sha="b" * 40,
        native_mobile_assets=assets,
    )

    assert assets == {expected_asset}
    assert plan.surfaces == ("mobile_native",)


@pytest.mark.parametrize(
    ("options", "expected_assets"),
    [
        ("./asset-a.bin", {"mobile/asset-a.bin"}),
        (
            ["./asset-a.bin", "./asset-b.bin"],
            {"mobile/asset-a.bin", "mobile/asset-b.bin"},
        ),
    ],
)
def test_app_json_plugin_scalar_and_list_options_are_native(
    options: object, expected_assets: set[str]
):
    release = _release_module()

    assets = release._app_json_native_assets(
        json.dumps({"expo": {"plugins": [["custom-plugin", options]]}}),
        source="mobile/app.json@test",
    )

    assert assets == expected_assets


@pytest.mark.parametrize(
    ("plugin_entry", "expected_paths"),
    [
        (
            "./config/withFoo",
            {
                "mobile/config/withFoo",
                "mobile/config/withFoo.js",
                "mobile/config/withFoo/index.js",
            },
        ),
        (["./config/withFoo.js"], {"mobile/config/withFoo.js"}),
    ],
)
def test_app_json_local_plugin_resolution_candidates_are_native(
    plugin_entry: object, expected_paths: set[str]
):
    release = _release_module()

    assets = release._app_json_native_assets(
        json.dumps({"expo": {"plugins": [plugin_entry]}}),
        source="mobile/app.json@test",
    )

    assert expected_paths.issubset(assets)


def test_repository_dynamic_config_is_audited_and_plannable():
    release = _release_module()

    assets = release._native_mobile_assets_for_refs(ROOT, ("HEAD",))

    assert "mobile/assets/images/icon.png" in assets
    assert "mobile/assets/images/splash-icon.png" in assets


def test_native_asset_references_are_unioned_across_base_and_target(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_json={"expo": {"icon": "./assets/images/icon.png"}},
    )
    (repo / "mobile/assets/images/new-icon.png").write_bytes(b"new-icon")
    (repo / "mobile/app.json").write_text(
        json.dumps({"expo": {"icon": "./assets/images/new-icon.png"}}),
        encoding="utf-8",
    )
    _git(repo, "rm", "mobile/assets/images/icon.png")
    _git(repo, "add", "mobile/app.json", "mobile/assets/images/new-icon.png")
    _git(repo, "commit", "-qm", "replace native icon")

    plan = release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)

    assert plan.surfaces == ("mobile_native",)


def test_app_json_packaged_images_are_native_but_unreferenced_assets_remain_ota(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_json={
            "expo": {
                "icon": "./assets/images/icon.png",
                "splash": {"image": "./assets/images/splash.png"},
                "android": {
                    "adaptiveIcon": {
                        "foregroundImage": "./assets/images/adaptive.png",
                        "backgroundImage": "./assets/images/adaptive-background.png",
                        "monochromeImage": "./assets/images/adaptive-monochrome.png",
                    }
                },
                "notification": {"icon": "./assets/images/notification.png"},
                "web": {"favicon": "./assets/images/favicon.png"},
            }
        },
    )

    for relative in (
        "assets/images/icon.png",
        "assets/images/splash.png",
        "assets/images/adaptive.png",
        "assets/images/adaptive-background.png",
        "assets/images/adaptive-monochrome.png",
        "assets/images/notification.png",
        "assets/images/favicon.png",
    ):
        path = repo / "mobile" / relative
        path.write_bytes(path.read_bytes() + b"-v2")
    _git(repo, "add", "mobile/assets/images")
    _git(repo, "commit", "-qm", "change packaged images")
    native_plan = release._plan_for_refs(
        repo, base, "HEAD", include_partial_state=False
    )

    native_head = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change ota image")
    ota_plan = release._plan_for_refs(
        repo, native_head, "HEAD", include_partial_state=False
    )

    assert native_plan.surfaces == ("mobile_native",)
    assert native_plan.actions == ("validate", "native_build")
    assert native_plan.publishable is False
    assert ota_plan.surfaces == ("mobile_native", "mobile_ota")
    assert ota_plan.actions == ("validate", "native_build")
    assert ota_plan.publishable is False


def test_dynamic_app_config_literal_packaged_image_is_native(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_config="export default { icon: './assets/images/icon.png' };\n",
    )
    (repo / "mobile/assets/images/icon.png").write_bytes(b"icon-v2")
    _git(repo, "add", "mobile/assets/images/icon.png")
    _git(repo, "commit", "-qm", "change dynamic config icon")

    plan = release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)

    assert plan.surfaces == ("mobile_native",)
    assert plan.actions == ("validate", "native_build")


def test_unknown_dynamic_packaged_image_reference_fails_closed(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_config=(
            "const configuredIcon = process.env.REVA_ICON;\n"
            "export default { icon: configuredIcon };\n"
        ),
    )
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change asset with unresolved native config")

    with pytest.raises(
        release.ReleaseError, match="cannot prove native asset references"
    ):
        release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)


def test_mismatched_dynamic_config_passthrough_fails_closed(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_json={"expo": {"brandIcon": "./assets/images/icon.png"}},
        app_config="export default { icon: config.brandIcon };\n",
    )
    (repo / "mobile/assets/images/icon.png").write_bytes(b"icon-v2")
    _git(repo, "add", "mobile/assets/images/icon.png")
    _git(repo, "commit", "-qm", "change mismatched passthrough icon")

    with pytest.raises(
        release.ReleaseError, match="cannot prove native asset references"
    ):
        release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)


@pytest.mark.parametrize(
    "app_config",
    [
        "const icon = './assets/images/icon.png'; export default { icon };\n",
        "const key = 'icon'; export default { [key]: './assets/images/icon.png' };\n",
    ],
)
def test_unresolved_dynamic_config_shape_fails_closed(
    app_config: str,
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(repo, app_config=app_config)
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change asset with unsupported dynamic config")

    with pytest.raises(
        release.ReleaseError, match="cannot prove native asset references"
    ):
        release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)


def test_quoted_dynamic_config_asset_key_is_classified_native(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_config="export default { 'icon': './assets/images/icon.png' };\n",
    )
    (repo / "mobile/assets/images/icon.png").write_bytes(b"icon-v2")
    _git(repo, "add", "mobile/assets/images/icon.png")
    _git(repo, "commit", "-qm", "change quoted dynamic config icon")

    plan = release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)

    assert plan.surfaces == ("mobile_native",)


@pytest.mark.parametrize(
    "app_config",
    [
        "import nativeConfig from './native-config'; export default {...nativeConfig};\n",
        "export default makeConfig();\n",
        (
            "const notificationOptions = getOptions(); "
            "export default { plugins: [['expo-notifications', notificationOptions]] };\n"
        ),
        "const defaults = { name: 'x' }; export default makeConfig();\n",
        "const defaults = { name: 'x' }; export default cfg;\n",
        "const defaults = { name: 'x' }; export default () => makeConfig();\n",
    ],
)
def test_unproved_dynamic_config_export_fails_closed(
    app_config: str,
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(repo, app_config=app_config)
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change asset with unproved config export")

    with pytest.raises(
        release.ReleaseError, match="cannot prove native asset references"
    ):
        release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)


@pytest.mark.parametrize(
    "app_config",
    [
        "export default { name: 'x', ios: getIos() };\n",
        "export default { name: 'x', android: getAndroid() };\n",
        "export default { name: 'x', splash: getSplash() };\n",
        "export default { name: 'x', plugins: getPlugins() };\n",
        (
            "const pluginName = 'expo-notifications'; "
            "export default { name: 'x', plugins: [[pluginName, "
            "{ icon: './assets/images/notification.png' }]] };\n"
        ),
        (
            "export default { name: 'x', get icon() { "
            "return './assets/images/icon.png' } };\n"
        ),
        (
            "export default { name: 'x', plugins: [["
            "'custom-native-plugin', { resource: getResource() }]] };\n"
        ),
        (
            "export default { name: 'x', plugins: [["
            "'expo-notifications', { sounds: getSounds() }]] };\n"
        ),
        (
            "export default { name: 'x', plugins: [["
            "'custom-native-plugin', { ...getOptions() }]] };\n"
        ),
        "const ios = getIos(); export default { name: 'x', ios };\n",
        (
            "const resource = getResource(); export default { name: 'x', "
            "plugins: [['custom-native-plugin', { resource }]] };\n"
        ),
        (
            "const sounds = getSounds(); export default { name: 'x', "
            "plugins: [['expo-notifications', { sounds }]] };\n"
        ),
        (
            "export default { name: 'x', plugins: [["
            "'custom-native-plugin', { resource() { return './x' } }]] };\n"
        ),
    ],
)
def test_dynamic_native_container_expression_fails_closed(
    app_config: str,
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(repo, app_config=app_config)
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change asset with dynamic native container")

    with pytest.raises(release.ReleaseError, match="cannot prove"):
        release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)


@pytest.mark.parametrize(
    "escaped_path",
    [
        r"./assets/images/ic\x6fn.png",
        r"./assets/images/ic\u006fn.png",
    ],
)
def test_escaped_dynamic_asset_path_fails_closed(escaped_path: str):
    release = _release_module()

    with pytest.raises(release.ReleaseError, match="escaped"):
        release._app_config_native_assets(
            f"export default {{ icon: '{escaped_path}' }};\n",
            source="mobile/app.config.ts@test",
        )


def test_unknown_plugin_static_local_option_is_native(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_config=(
            "export default { plugins: [['custom-native-plugin', "
            "{ resource: './assets/social/share.jpg' }]] };\n"
        ),
    )
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change custom plugin resource")

    plan = release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)

    assert plan.surfaces == ("mobile_native",)


def test_non_audited_dynamic_arrow_config_fails_closed(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_config=(
            "export default ({ config }) => ({ ...config, "
            "icon: config.icon, extra: { image: './assets/social/share.jpg' } });\n"
        ),
    )
    (repo / "mobile/assets/social/share.jpg").write_bytes(b"share-v2")
    _git(repo, "add", "mobile/assets/social/share.jpg")
    _git(repo, "commit", "-qm", "change extra image")

    with pytest.raises(release.ReleaseError, match="cannot prove"):
        release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)


def test_app_json_plugin_and_ios_assets_require_native_build(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    base = _commit_mobile_config_fixture(
        repo,
        app_json={
            "expo": {
                "ios": {"icon": "./assets/images/icon.png"},
                "plugins": [
                    [
                        "expo-notifications",
                        {"icon": "./assets/images/notification.png"},
                    ],
                    [
                        "expo-splash-screen",
                        {
                            "image": "./assets/images/splash.png",
                            "dark": {"image": "./assets/images/adaptive.png"},
                        },
                    ],
                ],
            }
        },
    )
    for relative in (
        "assets/images/icon.png",
        "assets/images/notification.png",
        "assets/images/splash.png",
        "assets/images/adaptive.png",
    ):
        path = repo / "mobile" / relative
        path.write_bytes(path.read_bytes() + b"-v2")
    _git(repo, "add", "mobile/assets/images")
    _git(repo, "commit", "-qm", "change plugin native assets")

    plan = release._plan_for_refs(repo, base, "HEAD", include_partial_state=False)

    assert plan.surfaces == ("mobile_native",)


@pytest.mark.parametrize(
    "path",
    [
        "mobile/plugins/withNativeCapability.js",
        "mobile/.easignore",
        "mobile/react-native.config.js",
        "mobile/assets/rokid/rokid-pushup-glasses.apk",
        "mobile/vendor/HealthSDK.xcframework/Info.plist",
        "mobile/assets/native/AppIcon.xcassets/Contents.json",
        "mobile/assets/native/Models.mlmodel/Data.bin",
        "mobile/assets/native/PrivacyInfo.xcprivacy",
        "mobile/assets/native/Resources.bundle/file.png",
    ],
)
def test_native_plugins_and_bundled_native_resources_require_native_build(path: str):
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", path),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native",)
    assert plan.actions == ("validate", "native_build")
    assert plan.publishable is False


@pytest.mark.parametrize(
    "path",
    [
        "mobile/plugins/test_native.js",
        "mobile/assets/rokid/test_pushup.apk",
        "mobile/vendor/tests/SDK.xcframework/Info.plist",
    ],
)
def test_test_named_native_resources_cannot_be_downgraded_to_validation(path: str):
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", path),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_native",)


def test_native_binary_suffix_does_not_reclassify_non_mobile_surface():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "A", "frontend/public/downloads/companion.apk"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("frontend",)
    assert plan.actions == ("validate", "deploy_all")


def test_rename_classifies_both_old_and_new_paths_and_delete_keeps_old_surface():
    release = _release_module()

    rename_plan = release.build_plan(
        (
            _change(
                release,
                "R096",
                "backend/app/old.py",
                "mobile/app/new.tsx",
            ),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )
    delete_plan = release.build_plan(
        (_change(release, "D", "apps/watch/Sources/App.swift"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert rename_plan.actions == (
        "validate",
        "deploy_backend",
        "native_build",
    )
    assert rename_plan.publishable is False
    assert delete_plan.actions == ("validate", "native_build")


def test_untrusted_completed_surface_hint_never_suppresses_release_action():
    release = _release_module()

    plan = release.build_plan(
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha="b" * 40,
        completed_actions=("deploy_backend",),
    )

    assert plan.completed_actions == ()
    assert plan.actions == ("validate", "deploy_backend", "native_build")
    assert plan.publishable is False


def test_unsigned_local_validation_credential_never_skips_full_suite(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("release must not trust unsigned local credentials")
        ),
    )
    calls: list[tuple[str, ...]] = []

    def runner(command, **kwargs):
        calls.append(tuple(command))
        kwargs["stdout"].write("full suite passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert calls == [("bash", "scripts/run-all-tests.sh")]
    assert "unsigned local credentials cannot replace the full suite" in capsys.readouterr().out


@pytest.mark.parametrize(
    "reason", ["credential missing", "credential is invalid JSON", "credential expired"]
)
def test_validation_always_runs_suite_and_never_issues_local_skip(
    reason: str,
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "mobile/app/index.tsx"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    calls: list[tuple[str, ...]] = []
    written: list[object] = []

    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: release.validation_credential.CredentialVerdict(
            False, reason
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda *_args: written.append(object()),
    )

    def runner(command, **kwargs):
        calls.append(tuple(command))
        kwargs["stdout"].write("all checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert calls == [("bash", "scripts/run-all-tests.sh")]
    assert written == []
    output = capsys.readouterr().out
    assert "no local skip issued" in output


def test_validation_runs_in_bound_repo_and_scrubs_root_overrides(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://attacker.invalid/prod")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://attacker.invalid/test")
    monkeypatch.setenv("TZ", "UTC")
    for name in (
        "REVA_VALIDATION_ROOT",
        "REVA_VALIDATION_ALLOW_ROOT_OVERRIDE_FOR_TESTS",
        "REVA_VALIDATION_LOG_DIR",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "BASH_ENV",
        "ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTEST_PLUGINS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_USERCONFIG",
        "npm_config_script_shell",
        "npm_config_node_options",
        "npm_config_userconfig",
        "Npm_Config_Script_Shell",
        "npm_config_script-shell",
        "BASH_FUNC_injected%%",
    ):
        monkeypatch.setenv(name, "/tmp/untrusted-validation-root")
    observed: dict[str, object] = {}

    def runner(command, **kwargs):
        observed.update(kwargs)
        kwargs["stdout"].write("bound checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert observed["cwd"] == repo
    environment = observed["env"]
    assert environment["REVA_VALIDATION_EXPECTED_ROOT"] == str(repo)
    assert environment["APP_ENV"] == "test"
    assert environment["DATABASE_URL"] == "sqlite:///:memory:"
    assert "TEST_DATABASE_URL" not in environment
    assert environment["TZ"] == "Asia/Shanghai"
    for name in (
        "REVA_VALIDATION_ROOT",
        "REVA_VALIDATION_ALLOW_ROOT_OVERRIDE_FOR_TESTS",
        "REVA_VALIDATION_LOG_DIR",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "BASH_ENV",
        "ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTEST_PLUGINS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_USERCONFIG",
        "npm_config_script_shell",
        "npm_config_node_options",
        "npm_config_userconfig",
        "Npm_Config_Script_Shell",
        "npm_config_script-shell",
        "BASH_FUNC_injected%%",
    ):
        assert name not in environment


def test_failed_validation_never_writes_a_credential(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    writes: list[object] = []
    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: release.validation_credential.CredentialVerdict(
            False, "credential expired"
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda *_args: writes.append(object()),
    )

    def runner(command, **_kwargs):
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        release.run_validation(plan, repo, runner=runner)

    assert writes == []


def test_ci_never_reuses_or_issues_tree_credential(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=_git(repo, "rev-parse", "HEAD"),
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("CI must not load a tree credential")
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("CI must not issue a tree credential")
        ),
    )

    def runner(command, **kwargs):
        calls.append(tuple(command))
        kwargs["stdout"].write("commit-specific checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert calls == [("bash", "scripts/run-all-tests.sh")]
    assert "unsigned local credentials cannot replace the full suite" in capsys.readouterr().out


def test_validation_invokes_no_mutating_release_script(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    commands: list[tuple[str, ...]] = []

    monkeypatch.setenv("CI", "true")

    def runner(command, **kwargs):
        commands.append(tuple(str(part) for part in command))
        kwargs["stdout"].write("checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )
    release.run_validation(plan, repo, runner=runner)

    assert commands == [("bash", "scripts/run-all-tests.sh")]
    assert all("deploy.sh" not in part for command in commands for part in command)
    assert all("mobile-ota.sh" not in part for command in commands for part in command)


def test_publish_rechecks_release_source_after_validation_before_mutation(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    commands: list[str] = []

    def dirty_after_validation(_plan, _repo, **_kwargs):
        (repo / "validation-generated.txt").write_text("unexpected\n", encoding="utf-8")

    monkeypatch.setattr(release, "run_validation", dirty_after_validation)

    def runner(command, **_kwargs):
        commands.append(str(command[0]))
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(release.ReleaseError, match="dirty"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="test",
            runner=runner,
        )

    assert commands == []


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "OTA_EAS_RUNNER",
        "OTA_EXPO_RUNNER",
        "OTA_TEST_AFTER_ARTIFACT_VERIFIED",
        "OTA_TEST_AFTER_RECEIPTS_WRITTEN",
        "OTA_ALLOW_DIRTY",
    ],
)
def test_publish_rejects_ota_test_hooks_before_any_mutation(
    unsafe_name: str,
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        # Mobile changes are intentionally non-publishable while every OTA and
        # native writer is frozen, so use the remaining publishable server
        # fixture to exercise the global environment-override guard itself.
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    assert plan.publishable is True
    monkeypatch.setenv(unsafe_name, "/tmp/fake-release-runner")
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    calls: list[object] = []

    with pytest.raises(release.ReleaseError, match="test/debug override"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="test",
            runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []
    assert release.read_release_state(repo) == {}


def test_publish_scrubs_shell_startup_injection_from_mutating_commands(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    for name in (
        "BASH_ENV",
        "ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_USERCONFIG",
        "npm_config_script_shell",
        "npm_config_node_options",
        "npm_config_userconfig",
        "Npm_Config_Script_Shell",
        "npm_config_script-shell",
        "BASH_FUNC_injected%%",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
        "GIT_CONFIG_PARAMETERS",
        "MOBILE_RUNTIME_VERSION",
        "OTA_MANIFEST_FILE",
        "OTA_ANCHOR_FILE",
        "OTA_AUDIT_LOG",
        "OTA_LOOKUP_ATTEMPTS",
        "OTA_LOOKUP_DELAY_SECONDS",
        "OTA_LOOKUP_MAX_PAGES",
        "OTA_RETRY_DELAY_SECONDS",
        "OTA_EAS_CLI_VERSION",
        "OTA_FORCE_NO_BYTECODE",
        "RELEASE_STEP_PROOF_MODE",
        "REMOTE_RELEASE_PROOF_ROOT",
        "ALLOW_MISSING_LANGBRIDGE_ENV",
        "DEPLOY_ENV_FORCE",
        "DEPLOY_EXPECTED_SHA",
        "DEPLOY_MODE",
        "DEPLOY_SCORE_THRESHOLD",
        "REVA_RELEASE_LOCK_ADOPT",
        "REVA_RELEASE_LOCK_FD",
        "REVA_RELEASE_LOCK_TOKEN",
        "REVA_REMOTE_RELEASE_LOCK_ADOPT",
        "REVA_REMOTE_RELEASE_LOCK_TOKEN",
        "REVA_EXPECTED_SERVER_SURFACES",
        "REMOTE_RELEASE_LOCK_DIR",
        "REMOTE_RELEASE_STATE_DIR",
        "REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT",
        "REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR",
        "REMOTE_HEALTH_EVIDENCE_PROC_ROOT",
        "REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR",
        "REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR",
        "SYSTEM_KB_IMPORT_PROOF_MODE",
    ):
        monkeypatch.setenv(name, "/tmp/shell-injection")
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    observed: list[dict[str, str]] = []
    observed_pass_fds: list[tuple[int, ...]] = []

    def runner(_command, **kwargs):
        observed.append(kwargs["env"])
        observed_pass_fds.append(kwargs["pass_fds"])
        return subprocess.CompletedProcess(_command, 0)

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="test",
        runner=runner,
    )

    assert len(observed) == 1
    for name in (
        "BASH_ENV",
        "ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_USERCONFIG",
        "npm_config_script_shell",
        "npm_config_node_options",
        "npm_config_userconfig",
        "Npm_Config_Script_Shell",
        "npm_config_script-shell",
        "BASH_FUNC_injected%%",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
        "GIT_CONFIG_PARAMETERS",
        "MOBILE_RUNTIME_VERSION",
        "OTA_MANIFEST_FILE",
        "OTA_ANCHOR_FILE",
        "OTA_AUDIT_LOG",
        "OTA_LOOKUP_ATTEMPTS",
        "OTA_LOOKUP_DELAY_SECONDS",
        "OTA_LOOKUP_MAX_PAGES",
        "OTA_RETRY_DELAY_SECONDS",
        "OTA_EAS_CLI_VERSION",
        "OTA_FORCE_NO_BYTECODE",
        "RELEASE_STEP_PROOF_MODE",
        "REMOTE_RELEASE_PROOF_ROOT",
        "ALLOW_MISSING_LANGBRIDGE_ENV",
        "DEPLOY_ENV_FORCE",
        "DEPLOY_EXPECTED_SHA",
        "DEPLOY_MODE",
        "DEPLOY_SCORE_THRESHOLD",
        "REVA_RELEASE_LOCK_ADOPT",
        "REVA_RELEASE_LOCK_FD",
        "REVA_RELEASE_LOCK_TOKEN",
        "REVA_REMOTE_RELEASE_LOCK_ADOPT",
        "REVA_REMOTE_RELEASE_LOCK_TOKEN",
        "REVA_EXPECTED_SERVER_SURFACES",
        "REMOTE_RELEASE_LOCK_DIR",
        "REMOTE_RELEASE_STATE_DIR",
        "REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT",
        "REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR",
        "REMOTE_HEALTH_EVIDENCE_PROC_ROOT",
        "REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR",
        "REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR",
        "SYSTEM_KB_IMPORT_PROOF_MODE",
    ):
        if name in {"REVA_RELEASE_LOCK_ADOPT", "REVA_RELEASE_LOCK_FD"}:
            continue
        assert name not in observed[0]
    assert observed[0]["REVA_RELEASE_LOCK_ADOPT"] == "1"
    inherited_fd = int(observed[0]["REVA_RELEASE_LOCK_FD"])
    assert inherited_fd >= 3
    assert observed_pass_fds == [(inherited_fd,)]
    assert "REVA_RELEASE_LOCK_TOKEN" not in observed[0]


def test_publish_passes_only_explicit_remote_release_handoff_token(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    monkeypatch.setenv("REVA_REMOTE_RELEASE_LOCK_ADOPT", "0")
    monkeypatch.setenv("REVA_REMOTE_RELEASE_LOCK_TOKEN", "ambient-attacker")
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    observed: list[dict[str, str]] = []

    def runner(_command, **kwargs):
        observed.append(kwargs["env"])
        return subprocess.CompletedProcess(_command, 0)

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="test",
        runner=runner,
        remote_release_token="durable-owner-token",
    )

    assert len(observed) == 1
    assert observed[0]["REVA_REMOTE_RELEASE_LOCK_ADOPT"] == "1"
    assert observed[0]["REVA_REMOTE_RELEASE_LOCK_TOKEN"] == "durable-owner-token"


def test_publish_passes_full_expected_server_identity_to_deploy_cas(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        backend_proof_id="b" * 64,
        frontend_sha="c" * 40,
        frontend_proof_id="d" * 64,
        mobile_ota_sha=target,
        mac_sha="e" * 40,
        mac_artifact_sha256="f" * 64,
        mac_receipt_id="1" * 64,
    )
    after = _production_surfaces(
        backend_sha=target,
        backend_proof_id="2" * 64,
        frontend_sha="c" * 40,
        frontend_proof_id="d" * 64,
        mobile_ota_sha=target,
        mac_sha="e" * 40,
        mac_artifact_sha256="f" * 64,
        mac_receipt_id="1" * 64,
    )
    probes = iter((baseline, baseline, baseline, after))
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: next(probes),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    observed: list[dict[str, str]] = []

    def runner(command, **kwargs):
        observed.append(kwargs["env"])
        return subprocess.CompletedProcess(command, 0)

    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=target,
    )
    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="test",
        expected_production_surfaces=baseline,
        runner=runner,
    )

    assert json.loads(observed[0]["REVA_EXPECTED_SERVER_SURFACES"]) == [
        "a" * 40,
        "b" * 64,
        "c" * 40,
        "d" * 64,
        "e" * 40,
        "f" * 64,
        "1" * 64,
    ]


def test_publish_rejects_invalid_explicit_remote_release_handoff_token_before_mutation(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    calls: list[object] = []

    with pytest.raises(release.ReleaseError, match="remote release handoff token"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="test",
            runner=lambda *args, **kwargs: calls.append((args, kwargs)),
            remote_release_token="bad token; rm",
        )

    assert calls == []


def test_publish_cli_accepts_explicit_remote_release_handoff_token():
    release = _release_module()

    args = release._build_parser().parse_args(
        [
            "publish",
            "--base",
            "HEAD^",
            "--remote-release-token",
            "durable-owner-token",
        ]
    )

    assert args.remote_release_token == "durable-owner-token"


def test_release_probe_uses_token_aware_server_probe_for_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    sentinel = object()
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("quiescent probe must not run while retained lock exists")
        ),
    )

    def under_lock(_repo, *, mobile_dir, expected_lock_token):
        calls.append((str(mobile_dir), expected_lock_token))
        return sentinel

    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces_under_release_lock",
        under_lock,
        raising=False,
    )

    observed = release._probe_production_surfaces(
        tmp_path,
        remote_release_token="durable-owner-token",
    )

    assert observed is sentinel
    assert calls == [(str(tmp_path / "mobile"), "durable-owner-token")]


def test_production_planner_uses_handoff_token_for_initial_live_probe(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("backend = 1\n", encoding="utf-8")
    _git(repo, "add", "backend/main.py")
    _git(repo, "commit", "-qm", "backend")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=baseline,
        mobile_ota_sha=baseline,
    )
    calls: list[str | None] = []

    def probe(_repo, *, remote_release_token=None):
        calls.append(remote_release_token)
        return production

    monkeypatch.setattr(release, "_probe_production_surfaces", probe)

    plan, observed = release._plan_for_production_surfaces(
        repo,
        requested_base=baseline,
        target=target,
        remote_release_token="durable-owner-token",
    )

    assert observed is production
    assert plan.actions == ("validate", "deploy_all")
    assert calls == ["durable-owner-token"]


def test_publish_handoff_probes_under_token_until_server_deploy_releases_lock(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        backend_proof_id="b" * 64,
        frontend_sha=None,
        frontend_proof_id=None,
        mobile_ota_sha=target,
    )
    after = _production_surfaces(
        backend_sha=target,
        backend_proof_id="c" * 64,
        frontend_sha=None,
        frontend_proof_id=None,
        mobile_ota_sha=target,
    )
    samples = iter((baseline, baseline, baseline, after))
    probe_tokens: list[str | None] = []

    def probe(_repo, *, remote_release_token=None):
        probe_tokens.append(remote_release_token)
        return next(samples)

    monkeypatch.setattr(release, "_probe_production_surfaces", probe)
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=target,
    )

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="test",
        expected_production_surfaces=baseline,
        remote_release_token="durable-owner-token",
        runner=lambda command, **_kwargs: subprocess.CompletedProcess(command, 0),
    )

    assert probe_tokens == [
        "durable-owner-token",
        "durable-owner-token",
        "durable-owner-token",
        None,
    ]


def test_publish_handoff_token_without_server_recovery_action_fails_closed(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "mobile/app/index.tsx"),),
        base_sha="a" * 40,
        target_sha=target,
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    calls: list[object] = []

    with pytest.raises(release.ReleaseError, match="server recovery action"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="test",
            remote_release_token="durable-owner-token",
            runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_publish_handoff_switches_to_normal_probe_for_following_mobile_ota(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        backend_proof_id="b" * 64,
        frontend_sha="a" * 40,
        frontend_proof_id="c" * 64,
        mobile_ota_sha="a" * 40,
    )
    server_after = _production_surfaces(
        backend_sha=target,
        backend_proof_id="d" * 64,
        frontend_sha="a" * 40,
        frontend_proof_id="c" * 64,
        mobile_ota_sha="a" * 40,
    )
    ota_after = _production_surfaces(
        backend_sha=target,
        backend_proof_id="d" * 64,
        frontend_sha="a" * 40,
        frontend_proof_id="c" * 64,
        mobile_ota_sha=target,
        mobile_group_id="new-group",
        mobile_update_id="new-update",
        mobile_channel_updated_at="2026-08-12T00:01:00Z",
        mobile_identity_digest="2" * 64,
        mobile_runtime_vector_digest="4" * 64,
    )
    samples = iter(
        (baseline, baseline, baseline, server_after, server_after, ota_after)
    )
    probe_tokens: list[str | None] = []

    def probe(_repo, *, remote_release_token=None):
        probe_tokens.append(remote_release_token)
        return next(samples)

    monkeypatch.setattr(release, "_probe_production_surfaces", probe)
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    plan = _isolated_historical_ota_protocol_plan(
        release,
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha=target,
    )

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="test",
        expected_production_surfaces=baseline,
        remote_release_token="durable-owner-token",
        runner=lambda command, **_kwargs: subprocess.CompletedProcess(command, 0),
    )

    assert probe_tokens == [
        "durable-owner-token",
        "durable-owner-token",
        "durable-owner-token",
        None,
        None,
        None,
    ]


def test_publish_scrubs_ambient_ota_release_overrides(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = _isolated_historical_ota_protocol_plan(
        release,
        (_change(release, "M", "mobile/app/index.tsx"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    unsafe = {
        "MOBILE_RUNTIME_VERSION": "attacker-runtime",
        "OTA_MANIFEST_FILE": "/tmp/attacker-manifest",
        "OTA_ANCHOR_FILE": "/tmp/attacker-anchor",
        "OTA_AUDIT_LOG": "/tmp/attacker-audit",
        "OTA_LOOKUP_ATTEMPTS": "1",
        "OTA_LOOKUP_DELAY_SECONDS": "99",
        "OTA_LOOKUP_MAX_PAGES": "1",
        "OTA_RETRY_DELAY_SECONDS": "99",
        "OTA_EAS_CLI_VERSION": "0.0.1",
        "OTA_FORCE_NO_BYTECODE": "1",
        "RELEASE_STEP_PROOF_MODE": "off",
        "REMOTE_RELEASE_PROOF_ROOT": "/tmp/attacker-proofs",
        "ALLOW_MISSING_LANGBRIDGE_ENV": "1",
        "DEPLOY_ENV_FORCE": "1",
        "DEPLOY_EXPECTED_SHA": "a" * 40,
        "DEPLOY_MODE": "all",
        "DEPLOY_SCORE_THRESHOLD": "0",
        "REVA_RELEASE_LOCK_ADOPT": "1",
        "REVA_RELEASE_LOCK_FD": "999",
        "REVA_RELEASE_LOCK_TOKEN": "attacker-token",
        "REVA_REMOTE_RELEASE_LOCK_ADOPT": "1",
        "REVA_REMOTE_RELEASE_LOCK_TOKEN": "attacker-remote-token",
        "REVA_EXPECTED_SERVER_SURFACES": "attacker-server-state",
        "REMOTE_RELEASE_LOCK_DIR": "/tmp/attacker-lock",
        "REMOTE_RELEASE_STATE_DIR": "/tmp/attacker-state",
        "REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT": "/tmp/attacker-cgroup",
        "REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR": "/tmp/attacker-durable",
        "REMOTE_HEALTH_EVIDENCE_PROC_ROOT": "/tmp/attacker-proc",
        "REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR": "/tmp/attacker-runtime",
        "REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR": "/tmp/attacker-systemd",
        "SYSTEM_KB_IMPORT_PROOF_MODE": "off",
    }
    for name, value in unsafe.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    observed: list[dict[str, str]] = []
    observed_pass_fds: list[tuple[int, ...]] = []

    def runner(command, **kwargs):
        observed.append(kwargs["env"])
        observed_pass_fds.append(kwargs["pass_fds"])
        return subprocess.CompletedProcess(command, 0)

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="test",
        runner=runner,
    )

    assert len(observed) == 1
    for name in unsafe:
        if name in {"REVA_RELEASE_LOCK_ADOPT", "REVA_RELEASE_LOCK_FD"}:
            continue
        assert name not in observed[0]
    assert observed[0]["REVA_RELEASE_LOCK_ADOPT"] == "1"
    inherited_fd = int(observed[0]["REVA_RELEASE_LOCK_FD"])
    assert inherited_fd >= 3
    assert inherited_fd != 999
    assert observed_pass_fds == [(inherited_fd,)]
    assert "REVA_RELEASE_LOCK_TOKEN" not in observed[0]


def test_planning_uses_each_live_production_surface_baseline(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "backend/app").mkdir(parents=True)
    (repo / "backend/app/main.py").write_text("backend = 1\n", encoding="utf-8")
    _git(repo, "add", "backend/app/main.py")
    _git(repo, "commit", "-qm", "server")
    server_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile/app").mkdir(parents=True)
    (repo / "mobile/app/index.tsx").write_text("export {};\n", encoding="utf-8")
    _git(repo, "add", "mobile/app/index.tsx")
    _git(repo, "commit", "-qm", "mobile")
    target = _git(repo, "rev-parse", "HEAD")
    production = type(
        "Surfaces", (), {"server_sha": server_sha, "mobile_ota_sha": first}
    )()
    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: production,
    )

    plan, observed = release._plan_for_production_surfaces(
        repo, requested_base=first, target=target
    )

    assert observed is production
    assert plan.base_sha == first
    assert plan.target_sha == target
    assert plan.surfaces == ("mobile_native", "mobile_ota")
    assert plan.actions == ("validate", "native_build")
    assert plan.publishable is False


def test_production_planner_uses_independent_frontend_runtime_baseline(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "frontend").mkdir()
    (repo / "frontend/app.tsx").write_text("export const version = 1;\n", encoding="utf-8")
    _git(repo, "add", "frontend/app.tsx")
    _git(repo, "commit", "-qm", "frontend")
    frontend_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("backend = 1\n", encoding="utf-8")
    _git(repo, "add", "backend/main.py")
    _git(repo, "commit", "-qm", "backend")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=target,
        frontend_sha=first,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, observed = release._plan_for_production_surfaces(
        repo, requested_base=first, target=target
    )

    assert observed is production
    assert plan.surfaces == ("frontend",)
    assert plan.actions == ("validate", "deploy_all")


def test_production_planner_bootstraps_missing_frontend_receipt_with_server_release(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("backend = 1\n", encoding="utf-8")
    _git(repo, "add", "backend/main.py")
    _git(repo, "commit", "-qm", "backend")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=baseline,
        frontend_sha=None,
        frontend_proof_id=None,
        mobile_ota_sha=baseline,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo, requested_base=baseline, target=target
    )

    assert plan.surfaces == ("backend", "frontend")
    assert plan.actions == ("validate", "deploy_all")


def test_production_planner_uses_independent_mac_runtime_baseline(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "apps/mac").mkdir(parents=True)
    (repo / "apps/mac/App.swift").write_text("let version = 1\n", encoding="utf-8")
    _git(repo, "add", "apps/mac/App.swift")
    _git(repo, "commit", "-qm", "mac")
    mac_change = _git(repo, "rev-parse", "HEAD")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("backend = 1\n", encoding="utf-8")
    _git(repo, "add", "backend/main.py")
    _git(repo, "commit", "-qm", "backend advanced")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=target,
        frontend_sha=target,
        frontend_proof_id="frontend-proof-current",
        mobile_ota_sha=target,
        mac_sha=baseline,
        mac_artifact_sha256="1" * 64,
        mac_receipt_id="2" * 64,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, observed = release._plan_for_production_surfaces(
        repo, requested_base=baseline, target=target
    )

    assert observed is production
    assert mac_change != target
    assert plan.surfaces == ("mac",)
    assert plan.actions == ("validate", "mac_build")
    assert plan.publishable is False
    assert plan.deferred_surfaces == ()


def test_production_planner_marks_existing_mac_tree_pending_without_receipt(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    (repo / "apps/mac").mkdir(parents=True)
    (repo / "apps/mac/App.swift").write_text("let version = 1\n", encoding="utf-8")
    _git(repo, "add", "apps/mac/App.swift")
    _git(repo, "commit", "-qm", "mac exists")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=target,
        frontend_sha=target,
        frontend_proof_id="frontend-proof-current",
        mobile_ota_sha=target,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo, requested_base=target, target=target
    )

    assert plan.surfaces == ("mac",)
    assert plan.actions == ("validate", "mac_build")
    assert plan.publishable is False


def test_explicit_surface_scope_allows_partial_server_release_and_reports_mac_deferred(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "apps/mac").mkdir(parents=True)
    (repo / "apps/mac/App.swift").write_text("let version = 1\n", encoding="utf-8")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("backend = 1\n", encoding="utf-8")
    _git(repo, "add", "apps/mac/App.swift", "backend/main.py")
    _git(repo, "commit", "-qm", "mac and backend")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=baseline,
        frontend_sha=target,
        frontend_proof_id="frontend-proof-current",
        mobile_ota_sha=target,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo,
        requested_base=baseline,
        target=target,
        surface_scope=frozenset({"backend"}),
    )

    assert plan.surfaces == ("backend",)
    assert plan.actions == ("validate", "deploy_backend")
    assert plan.publishable is True
    assert plan.surface_scope == ("backend",)
    assert plan.deferred_surfaces == ("mac",)


def test_explicit_mobile_ota_scope_cannot_defer_native_changes(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile/app").mkdir(parents=True)
    (repo / "mobile/app.json").write_text('{"expo": {}}\n', encoding="utf-8")
    (repo / "mobile/app/index.tsx").write_text("export {};\n", encoding="utf-8")
    _git(repo, "add", "mobile/app.json", "mobile/app/index.tsx")
    _git(repo, "commit", "-qm", "native and ota")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=target,
        frontend_sha=target,
        frontend_proof_id="frontend-proof-current",
        mobile_ota_sha=baseline,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo,
        requested_base=baseline,
        target=target,
        surface_scope=frozenset({"mobile_ota"}),
    )

    assert plan.surfaces == ("mobile_native", "mobile_ota")
    assert plan.surface_scope == ("mobile_native", "mobile_ota")
    assert plan.publishable is False
    assert "mobile_native" not in plan.deferred_surfaces


def test_live_runtime_a_can_plan_native_target_runtime_b(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    repo, _origin = repository_with_origin
    (repo / "mobile").mkdir()
    (repo / "mobile/app.json").write_text(
        '{"expo":{"version":"1.0.0","runtimeVersion":"1.0.0"}}\n',
        encoding="utf-8",
    )
    _git(repo, "add", "mobile/app.json")
    _git(repo, "commit", "-qm", "runtime A")
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile/app.json").write_text(
        '{"expo":{"version":"2.0.0","runtimeVersion":"2.0.0"}}\n',
        encoding="utf-8",
    )
    _git(repo, "add", "mobile/app.json")
    _git(repo, "commit", "-qm", "runtime B")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=target,
        frontend_sha=target,
        frontend_proof_id="frontend-proof-current",
        mobile_ota_sha=baseline,
        mobile_runtime="1.0.0",
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, observed = release._plan_for_production_surfaces(
        repo,
        requested_base=baseline,
        target=target,
    )

    assert observed.mobile_runtime == "1.0.0"
    assert plan.surfaces == ("mobile_native",)
    assert plan.publishable is False


def test_explicit_frontend_scope_includes_pending_backend_deployed_by_deploy_all(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("backend = 1\n", encoding="utf-8")
    (repo / "frontend").mkdir()
    (repo / "frontend/app.tsx").write_text("export {};\n", encoding="utf-8")
    _git(repo, "add", "backend/main.py", "frontend/app.tsx")
    _git(repo, "commit", "-qm", "server surfaces")
    target = _git(repo, "rev-parse", "HEAD")
    production = _production_surfaces(
        backend_sha=baseline,
        frontend_sha=baseline,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo,
        requested_base=baseline,
        target=target,
        surface_scope=frozenset({"frontend"}),
    )

    assert plan.surfaces == ("backend", "frontend")
    assert plan.surface_scope == ("backend", "frontend")
    assert plan.actions == ("validate", "deploy_all")
    assert plan.deferred_surfaces == ()


def test_mac_transition_requires_new_trusted_receipt_bound_to_target():
    release = _release_module()
    before = _production_surfaces(
        backend_sha="a" * 40,
        mobile_ota_sha="b" * 40,
        mac_sha="c" * 40,
        mac_artifact_sha256="1" * 64,
        mac_receipt_id="2" * 64,
    )
    after = _production_surfaces(
        backend_sha="a" * 40,
        mobile_ota_sha="b" * 40,
        mac_sha="d" * 40,
        # A source-only metadata change may legitimately reproduce identical bytes.
        mac_artifact_sha256="1" * 64,
        mac_receipt_id="4" * 64,
    )

    release._assert_production_transition(
        "mac_build", before=before, after=after, target_sha="d" * 40
    )

    with pytest.raises(release.ReleaseError, match="could not be proven"):
        release._assert_production_transition(
            "mac_build", before=before, after=before, target_sha="d" * 40
        )


def test_mac_identity_drift_blocks_server_publish_before_mutation(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
        mac_sha="b" * 40,
        mac_artifact_sha256="1" * 64,
        mac_receipt_id="2" * 64,
    )
    drifted = _production_surfaces(
        backend_sha="a" * 40,
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
        mac_sha="c" * 40,
        mac_artifact_sha256="3" * 64,
        mac_receipt_id="4" * 64,
    )
    probes = iter((baseline, drifted))
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: next(probes),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    mutations: list[str] = []
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=target,
    )

    with pytest.raises(
        release.ReleaseError, match="production_surface_changed_during_validation"
    ):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="blocked",
            expected_production_surfaces=baseline,
            runner=lambda command, **_kwargs: mutations.append(Path(command[0]).name),
        )

    assert mutations == []


def test_scoped_publish_persists_deferred_surfaces_in_state_and_events(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=target,
        surface_scope=("backend",),
        deferred_surfaces=("mac",),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="scoped",
        runner=lambda command, **_kwargs: subprocess.CompletedProcess(command, 0),
    )

    state = release.read_release_state(repo)
    assert state["status"] == "succeeded"
    assert state["surface_scope"] == ["backend"]
    assert state["deferred_surfaces"] == ["mac"]
    events = [
        json.loads(line)
        for line in release._transaction_log_path(repo).read_text(encoding="utf-8").splitlines()
    ]
    assert events
    assert all(event["surface_scope"] == ["backend"] for event in events)
    assert all(event["deferred_surfaces"] == ["mac"] for event in events)


def test_publish_reprobes_inside_lock_and_blocks_if_surface_moves(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    changed = type(
        "Surfaces", (), {"server_sha": "c" * 40, "mobile_ota_sha": "d" * 40}
    )()
    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: changed,
    )
    monkeypatch.setattr(
        release,
        "run_validation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("drift must block before validation")
        ),
    )

    with pytest.raises(release.ReleaseError, match="production surface changed"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="blocked",
            expected_production_surfaces=type(
                "Surfaces",
                (),
                {"server_sha": "a" * 40, "mobile_ota_sha": "d" * 40},
            )(),
        )


def test_publish_blocks_production_drift_during_validation_before_mutation(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
    )
    drifted = _production_surfaces(
        backend_sha="c" * 40,
        backend_proof_id="backend-proof-external",
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
    )
    probes = iter((baseline, drifted))
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: next(probes),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    mutations: list[str] = []
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=target,
    )

    with pytest.raises(
        release.ReleaseError, match="production_surface_changed_during_validation"
    ):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="blocked",
            expected_production_surfaces=baseline,
            runner=lambda command, **_kwargs: mutations.append(Path(command[0]).name),
        )

    assert mutations == []


def test_publish_blocks_surface_drift_between_backend_and_ota_mutations(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha="b" * 40,
    )
    after_backend = _production_surfaces(
        backend_sha=target,
        backend_proof_id="backend-proof-new",
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha="b" * 40,
    )
    externally_changed = _production_surfaces(
        backend_sha=target,
        backend_proof_id="backend-proof-new",
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha="b" * 40,
        mobile_group_id="mobile-group-external",
        mobile_update_id="mobile-update-external",
    )
    probes = iter(
        (baseline, baseline, baseline, after_backend, externally_changed)
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: next(probes),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    mutations: list[str] = []

    def runner(command, **_kwargs):
        mutations.append(Path(command[0]).name)
        return subprocess.CompletedProcess(command, 0)

    plan = _isolated_historical_ota_protocol_plan(
        release,
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha=target,
    )

    with pytest.raises(
        release.ReleaseError, match="production_surface_changed_before_mobile_ota"
    ):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="blocked",
            expected_production_surfaces=baseline,
            runner=runner,
        )

    assert mutations == ["deploy.sh"]


def test_publish_accepts_only_expected_backend_and_ota_state_transitions(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha="b" * 40,
    )
    after_backend = _production_surfaces(
        backend_sha=target,
        backend_proof_id="backend-proof-new",
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha="b" * 40,
    )
    after_ota = _production_surfaces(
        backend_sha=target,
        backend_proof_id="backend-proof-new",
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha=target,
        mobile_group_id="mobile-group-new",
        mobile_update_id="mobile-update-new",
        mobile_channel_updated_at="2026-08-12T00:01:00Z",
        mobile_identity_digest="2" * 64,
        mobile_runtime_vector_digest="4" * 64,
    )
    probes = iter(
        (
            baseline,
            baseline,
            baseline,
            after_backend,
            after_backend,
            after_ota,
        )
    )
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: next(probes),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    mutations: list[str] = []

    def runner(command, **_kwargs):
        mutations.append(Path(command[0]).name)
        return subprocess.CompletedProcess(command, 0)

    plan = _isolated_historical_ota_protocol_plan(
        release,
        (
            _change(release, "M", "backend/app/main.py"),
            _change(release, "M", "mobile/app/index.tsx"),
        ),
        base_sha="a" * 40,
        target_sha=target,
    )

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="safe transitions",
        expected_production_surfaces=baseline,
        runner=runner,
    )

    assert mutations == ["deploy.sh", "mobile-ota.sh"]


def test_publish_rejects_unexpected_frontend_transition_after_full_deploy(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    baseline = _production_surfaces(
        backend_sha="a" * 40,
        frontend_sha="a" * 40,
        frontend_proof_id="frontend-proof-old",
        mobile_ota_sha="b" * 40,
    )
    wrong_frontend = _production_surfaces(
        backend_sha=target,
        backend_proof_id="backend-proof-new",
        frontend_sha="c" * 40,
        frontend_proof_id="frontend-proof-new",
        mobile_ota_sha="b" * 40,
    )
    probes = iter((baseline, baseline, baseline, wrong_frontend))
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: next(probes),
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    plan = release.build_plan(
        (_change(release, "M", "frontend/app.tsx"),),
        base_sha="a" * 40,
        target_sha=target,
    )

    with pytest.raises(
        release.ReleaseError, match="production_transition_unproven"
    ):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="blocked",
            expected_production_surfaces=baseline,
            runner=lambda command, **_kwargs: subprocess.CompletedProcess(command, 0),
        )


def test_production_plan_blocks_requested_baseline_that_is_not_live_merge_base(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    first = _git(repo, "rev-parse", "HEAD")
    (repo / "backend").mkdir()
    (repo / "backend/main.py").write_text("server = 1\n", encoding="utf-8")
    _git(repo, "add", "backend/main.py")
    _git(repo, "commit", "-qm", "server")
    server_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile").mkdir()
    (repo / "mobile/index.tsx").write_text("export {};\n", encoding="utf-8")
    _git(repo, "add", "mobile/index.tsx")
    _git(repo, "commit", "-qm", "mobile")
    target = _git(repo, "rev-parse", "HEAD")
    production = type(
        "Surfaces", (), {"server_sha": server_sha, "mobile_ota_sha": first}
    )()
    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: production,
    )

    with pytest.raises(release.ReleaseError, match="live production merge-base"):
        release._plan_for_production_surfaces(
            repo, requested_base=server_sha, target=target
        )


def test_production_plan_rejects_live_surface_not_ancestor_of_target(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    target = _git(repo, "rev-parse", "HEAD")
    production = type(
        "Surfaces",
        (),
        {"server_sha": "c" * 40, "mobile_ota_sha": target},
    )()
    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: production,
    )

    with pytest.raises(release.ReleaseError, match="backend production SHA"):
        release._plan_for_production_surfaces(
            repo, requested_base=target, target=target
        )


def test_production_planner_treats_package_scripts_only_change_as_validation_only(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    (repo / "mobile").mkdir()
    package = {
        "name": "fixture",
        "scripts": {"generate-types": "old"},
        "dependencies": {"expo": "1.0.0"},
        "devDependencies": {"typescript": "1.0.0"},
    }
    (repo / "mobile/package.json").write_text(
        json.dumps(package), encoding="utf-8"
    )
    _git(repo, "add", "mobile/package.json")
    _git(repo, "commit", "-qm", "mobile package baseline")
    baseline = _git(repo, "rev-parse", "HEAD")
    package["scripts"]["generate-types"] = "new"
    (repo / "mobile/package.json").write_text(
        json.dumps(package), encoding="utf-8"
    )
    _git(repo, "add", "mobile/package.json")
    _git(repo, "commit", "-qm", "change development script")
    target = _git(repo, "rev-parse", "HEAD")
    production = type(
        "Surfaces", (), {"server_sha": baseline, "mobile_ota_sha": baseline}
    )()
    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo, requested_base=baseline, target=target
    )

    assert plan.surfaces == ("validation_only",)
    assert plan.actions == ("validate",)
    assert plan.publishable is True


def test_production_planner_blocks_package_dependency_change_as_native(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    (repo / "mobile").mkdir()
    package = {"name": "fixture", "dependencies": {"expo": "1.0.0"}}
    (repo / "mobile/package.json").write_text(
        json.dumps(package), encoding="utf-8"
    )
    _git(repo, "add", "mobile/package.json")
    _git(repo, "commit", "-qm", "mobile package baseline")
    baseline = _git(repo, "rev-parse", "HEAD")
    package["dependencies"]["expo"] = "2.0.0"
    (repo / "mobile/package.json").write_text(
        json.dumps(package), encoding="utf-8"
    )
    _git(repo, "add", "mobile/package.json")
    _git(repo, "commit", "-qm", "change native dependency")
    target = _git(repo, "rev-parse", "HEAD")
    production = type(
        "Surfaces", (), {"server_sha": baseline, "mobile_ota_sha": baseline}
    )()
    monkeypatch.setattr(
        release.release_production_state,
        "probe_production_surfaces",
        lambda *_args, **_kwargs: production,
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo, requested_base=baseline, target=target
    )

    assert plan.surfaces == ("mobile_native",)
    assert plan.actions == ("validate", "native_build")
    assert plan.publishable is False


def test_git_branch_checks_ignore_inherited_git_target_overrides(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    feature_worktree = tmp_path / "feature-worktree"
    _git(repo, "branch", "feature/release-check")
    _git(repo, "worktree", "add", str(feature_worktree), "feature/release-check")
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo))

    assert release._branch_name(feature_worktree) == "feature/release-check"


@pytest.mark.parametrize(
    "override",
    [
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.https://attacker.invalid/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
        },
        {
            "GIT_CONFIG_PARAMETERS": (
                "'url.https://attacker.invalid/.insteadOf'='https://github.com/'"
            )
        },
    ],
)
def test_git_commands_ignore_inherited_config_rewrites(
    override: dict[str, str],
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, origin = repository_with_origin
    for name, value in override.items():
        monkeypatch.setenv(name, value)

    assert release._git(repo, "remote", "get-url", "origin") == str(origin)


def test_git_commands_ignore_path_and_home_global_config(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, origin = repository_with_origin
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-git-called"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        f"#!/bin/sh\nprintf called > {marker!s}\nexit 91\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".gitconfig").write_text(
        "[url \"https://attacker.invalid/\"]\n"
        "\tinsteadOf = https://github.com/\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("GIT_EXEC_PATH", str(tmp_path / "attacker-git-exec"))

    assert release._git(repo, "remote", "get-url", "origin") == str(origin)
    assert not marker.exists()
    environment = release._git_environment()
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert "GIT_EXEC_PATH" not in environment


def test_remote_main_uses_literal_canonical_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_module()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"{'a' * 40}\trefs/heads/main\n",
            stderr="",
        )

    monkeypatch.setattr(release.subprocess, "run", run)

    assert release._remote_main_sha(Path("/tmp/release-source")) == "a" * 40
    command, kwargs = calls[-1]
    assert command[0] == "/usr/bin/git"
    assert "origin" not in command
    assert "https://github.com/itsoso/health-llm-driven.git" in command
    assert kwargs["cwd"] == "/"


def test_canonical_origin_rejects_pushurl_and_local_url_rewrite_before_network(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    authority = "https://github.com/itsoso/health-llm-driven.git"
    _git(
        repo,
        "remote",
        "set-url",
        "origin",
        authority,
    )
    _git(repo, "remote", "set-url", "--push", "origin", "https://attacker.invalid/x")

    with pytest.raises(release.ReleaseError, match="pushurl"):
        release._assert_canonical_origin(repo, authority_url=authority)

    _git(repo, "config", "--unset-all", "remote.origin.pushurl")
    _git(
        repo,
        "config",
        "url.https://attacker.invalid/.insteadOf",
        "https://github.com/",
    )
    with pytest.raises(release.ReleaseError, match="rewrite"):
        release._assert_canonical_origin(repo, authority_url=authority)


def test_trusted_git_ignores_and_source_guard_rejects_replace_refs(
    repository_with_origin: tuple[Path, Path],
) -> None:
    release = _release_module()
    repo, origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    canonical_tree = _git(repo, "rev-parse", f"{head}^{{tree}}")
    empty_tree = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "mktree"],
        input="",
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    replacement = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "commit-tree", empty_tree, "-m", "replacement"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    _git(repo, "replace", head, replacement)

    assert _git(repo, "rev-parse", f"{head}^{{tree}}") == empty_tree
    assert release._git(repo, "rev-parse", f"{head}^{{tree}}") == canonical_tree
    with pytest.raises(release.ReleaseError, match="replacement refs"):
        release.assert_release_source(repo, authority_url=str(origin))


def test_release_worktree_is_detached_and_exactly_tracks_remote_main(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, origin = repository_with_origin
    release_path = tmp_path / "permanent.release"

    prepared = release.ensure_release_worktree(
        repo, release_path=release_path, authority_url=str(origin)
    )

    assert prepared == release_path.resolve()
    assert (
        subprocess.run(
            ["git", "-C", str(prepared), "symbolic-ref", "-q", "HEAD"],
            check=False,
        ).returncode
        != 0
    )
    assert _git(prepared, "rev-parse", "HEAD") == _git(repo, "rev-parse", "origin/main")
    release.assert_release_source(prepared, authority_url=str(origin))


def test_dirty_release_worktree_is_refused_without_cleanup(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, origin = repository_with_origin
    release_path = tmp_path / "permanent.release"
    release.ensure_release_worktree(
        repo, release_path=release_path, authority_url=str(origin)
    )
    old_head = _git(release_path, "rev-parse", "HEAD")
    dirty_file = release_path / "operator-notes.txt"
    dirty_file.write_text("do not delete\n", encoding="utf-8")
    (repo / "README.md").write_text("advanced\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "advance main")
    _git(repo, "push", "-q", "origin", "main")

    with pytest.raises(release.ReleaseError, match="dirty"):
        release.ensure_release_worktree(
            repo, release_path=release_path, authority_url=str(origin)
        )

    assert dirty_file.read_text(encoding="utf-8") == "do not delete\n"
    assert _git(release_path, "rev-parse", "HEAD") == old_head


def test_named_feature_branch_release_worktree_is_refused(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, origin = repository_with_origin
    release_path = tmp_path / "permanent.release"
    release.ensure_release_worktree(
        repo, release_path=release_path, authority_url=str(origin)
    )
    _git(release_path, "checkout", "-qb", "feature/not-production")

    with pytest.raises(release.ReleaseError, match="feature/not-production"):
        release.ensure_release_worktree(
            repo, release_path=release_path, authority_url=str(origin)
        )

    assert _git(release_path, "branch", "--show-current") == ("feature/not-production")


def test_shared_release_state_uses_git_common_dir_and_private_permissions(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    other_worktree = tmp_path / "other-worktree"
    _git(repo, "worktree", "add", "--detach", str(other_worktree), "HEAD")

    release.write_release_state(repo, {"schema_version": 1, "ok": True})
    main_state_dir = release.release_state_dir(repo)
    other_state_dir = release.release_state_dir(other_worktree)
    state_file = main_state_dir / "release-state.json"

    assert main_state_dir == other_state_dir
    assert release.read_release_state(other_worktree)["ok"] is True
    assert stat.S_IMODE(main_state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    assert json.loads(state_file.read_text(encoding="utf-8"))["ok"] is True


def test_write_release_state_rejects_existing_hard_link(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_dir = release.release_state_dir(repo)
    state_file = state_dir / release.STATE_FILE_NAME
    state_file.write_text("{}\n", encoding="utf-8")
    state_file.chmod(0o600)
    os.link(state_file, tmp_path / "linked-release-state.json")

    with pytest.raises(release.ReleaseError, match="Unsafe shared release state file"):
        release.write_release_state(repo, {"schema_version": 2})


def test_read_release_state_rejects_symlinked_parent_directory(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    common = release._git_common_dir(repo)
    target = tmp_path / "attacker-state"
    target.mkdir(mode=0o700)
    state_file = target / release.STATE_FILE_NAME
    state_file.write_text('{"schema_version":2,"forged":true}\n', encoding="utf-8")
    state_file.chmod(0o600)
    os.symlink(target, common / release.STATE_DIRECTORY_NAME)

    with pytest.raises(release.ReleaseError, match="Unsafe shared release state"):
        release.read_release_state(repo)


def test_read_release_state_rejects_leaf_symlink_instead_of_missing(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_dir = release.release_state_dir(repo)
    os.symlink(tmp_path / "missing-state-target", state_dir / release.STATE_FILE_NAME)

    with pytest.raises(release.ReleaseError, match="Unsafe shared release state file"):
        release.read_release_state(repo)


@pytest.mark.parametrize("unsafe_kind", ["owner", "mode", "hard_link"])
def test_read_release_state_rejects_unsafe_file_metadata(
    unsafe_kind: str,
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_file = release.write_release_state(repo, {"ok": True})
    state_metadata = state_file.stat()
    if unsafe_kind == "mode":
        state_file.chmod(0o644)
    elif unsafe_kind == "hard_link":
        os.link(state_file, tmp_path / "linked-state.json")
    else:
        real_fstat = release.os.fstat

        def wrong_owner_for_state(descriptor: int):
            metadata = real_fstat(descriptor)
            if (metadata.st_dev, metadata.st_ino) != (
                state_metadata.st_dev,
                state_metadata.st_ino,
            ):
                return metadata
            values = list(metadata)
            values[4] = os.getuid() + 1
            return os.stat_result(values)

        monkeypatch.setattr(release.os, "fstat", wrong_owner_for_state)

    with pytest.raises(release.ReleaseError, match="Unsafe shared release state file"):
        release.read_release_state(repo)


def test_read_release_state_rejects_oversize_before_json_decode(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_file = release.release_state_dir(repo) / release.STATE_FILE_NAME
    state_file.write_bytes(b"x" * (release.MAX_RELEASE_STATE_BYTES + 1))
    state_file.chmod(0o600)
    monkeypatch.setattr(
        release.json,
        "loads",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("oversize state must be rejected before JSON parsing")
        ),
    )

    with pytest.raises(release.ReleaseError, match="too large"):
        release.read_release_state(repo)


def test_write_release_state_rejects_oversize_without_replacing_snapshot(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_file = release.write_release_state(repo, {"value": "original"})
    original = state_file.read_bytes()
    monkeypatch.setattr(release, "MAX_RELEASE_STATE_BYTES", 128)

    with pytest.raises(release.ReleaseError, match="too large"):
        release.write_release_state(repo, {"value": "x" * 512})

    assert state_file.read_bytes() == original
    assert list(state_file.parent.glob(".release-state.*")) == []


def test_write_release_state_uses_anchored_dirfd_during_directory_swap(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_dir = release.release_state_dir(repo)
    original_dir = state_dir.with_name(f"{state_dir.name}.original")
    attacker_dir = tmp_path / "attacker-state"
    attacker_dir.mkdir(mode=0o700)
    real_replace = release.os.replace

    def swap_directory_then_replace(source, destination, *args, **kwargs):
        state_dir.rename(original_dir)
        os.symlink(attacker_dir, state_dir)
        return real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(release.os, "replace", swap_directory_then_replace)

    release.write_release_state(repo, {"value": "anchored"})

    assert not (attacker_dir / release.STATE_FILE_NAME).exists()
    payload = json.loads(
        (original_dir / release.STATE_FILE_NAME).read_text(encoding="utf-8")
    )
    assert payload["value"] == "anchored"


def test_write_release_state_replace_failure_preserves_old_snapshot(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_file = release.write_release_state(repo, {"value": "original"})
    original = state_file.read_bytes()
    monkeypatch.setattr(
        release.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(release.ReleaseError, match="Cannot atomically replace"):
        release.write_release_state(repo, {"value": "new"})

    assert state_file.read_bytes() == original
    assert list(state_file.parent.glob(".release-state.*")) == []


def test_append_transaction_event_rejects_fifo_without_blocking(
    repository_with_origin: tuple[Path, Path]
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_dir = release.release_state_dir(repo)
    os.mkfifo(state_dir / release.TRANSACTION_LOG_FILE_NAME, mode=0o600)
    probe = f"""
import importlib.util
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('release_fifo_probe', {str(RELEASE_SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
try:
    module._append_transaction_event(Path({str(repo)!r}), {{'event': 'probe'}})
except module.ReleaseError:
    raise SystemExit(0)
raise SystemExit(3)
"""

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_append_transaction_event_enforces_total_log_limit_without_writing(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    log_path = release._append_transaction_event(repo, {"event": "first"})
    original = log_path.read_bytes()
    monkeypatch.setattr(release, "MAX_TRANSACTION_LOG_BYTES", len(original))

    with pytest.raises(release.ReleaseError, match="too large"):
        release._append_transaction_event(repo, {"event": "second"})

    assert log_path.read_bytes() == original


def test_different_unfinished_release_range_requires_manual_reconciliation(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    first_plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    first_state = release._begin_release_transaction(
        first_plan,
        repo,
        owner_repo=repo,
        env_file=repo / ".env",
    )
    release._start_release_stage(repo, first_state, "deploy_backend")
    second_plan = release.build_plan(
        (_change(release, "M", "backend/app/other.py"),),
        base_sha="b" * 40,
        target_sha=head,
    )

    with pytest.raises(release.ReleaseError, match="manual reconciliation"):
        release._begin_release_transaction(
            second_plan,
            repo,
            owner_repo=repo,
            env_file=repo / ".env",
        )

    persisted = release.read_release_state(repo)
    assert persisted["transaction_id"] == first_state["transaction_id"]
    assert persisted["base_sha"] == "a" * 40


def test_different_failed_release_range_requires_manual_reconciliation(
    repository_with_origin: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    first_plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)

    with pytest.raises(release.ReleaseError):
        release.publish_plan(
            first_plan,
            repo,
            owner_repo=repo,
            message="first range",
            runner=lambda command, **_kwargs: (_ for _ in ()).throw(
                subprocess.CalledProcessError(7, command)
            ),
        )
    first_state = release.read_release_state(repo)
    second_plan = release.build_plan(
        (_change(release, "M", "backend/app/other.py"),),
        base_sha="b" * 40,
        target_sha=head,
    )

    with pytest.raises(release.ReleaseError, match="manual reconciliation"):
        release._begin_release_transaction(
            second_plan,
            repo,
            owner_repo=repo,
            env_file=repo / ".env",
        )

    assert (
        release.read_release_state(repo)["transaction_id"]
        == first_state["transaction_id"]
    )


def test_internal_planning_does_not_create_shared_operational_state(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    state_dir = common_dir.resolve() / "reva-release-state"
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: type(
            "Surfaces", (), {"server_sha": head, "mobile_ota_sha": head}
        )(),
    )

    plan, _observed = release._plan_for_production_surfaces(
        repo,
        requested_base="HEAD",
        target="HEAD",
    )

    assert plan.publishable is True
    assert not state_dir.exists()


def test_validate_runs_for_manual_native_plan_without_publishing(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    baseline = _git(repo, "rev-parse", "HEAD")
    (repo / "mobile").mkdir()
    (repo / "mobile/app.json").write_text('{"expo": {}}\n', encoding="utf-8")
    _git(repo, "add", "mobile/app.json")
    _git(repo, "commit", "-qm", "native config")
    _git(repo, "push", "-q", "origin", "main")
    validations: list[tuple[str, ...]] = []

    def record_validation(plan, _repo):
        validations.append(plan.surfaces)

    monkeypatch.setattr(release, "run_validation", record_validation)
    monkeypatch.setattr(
        release,
        "_probe_production_surfaces",
        lambda _repo, *, remote_release_token=None: type(
            "Surfaces",
            (),
            {"server_sha": baseline, "mobile_ota_sha": baseline},
        )(),
    )
    plan, _observed = release._plan_for_production_surfaces(
        repo,
        requested_base=baseline,
        target="HEAD",
    )
    release.run_validation(plan, repo)

    assert plan.publishable is False
    assert validations == [("mobile_native",)]


def test_docs_only_publish_writes_private_schema_v2_state_and_transaction_log(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    env_file = tmp_path / "production.env"
    private_message = "PRIVATE_HEALTH_MESSAGE_DO_NOT_PERSIST"
    private_environment = "PRIVATE_ENV_VALUE_DO_NOT_PERSIST"
    monkeypatch.setenv("UNRELATED_PRIVATE_VALUE", private_environment)
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    plan = release.build_plan((), base_sha=head, target_sha=head)

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message=private_message,
        env_file=env_file,
    )

    state = release.read_release_state(repo)
    state_file = release.release_state_dir(repo) / release.STATE_FILE_NAME
    transaction_log = (
        release.release_state_dir(repo) / release.TRANSACTION_LOG_FILE_NAME
    )
    persisted = state_file.read_text(encoding="utf-8") + transaction_log.read_text(
        encoding="utf-8"
    )
    assert release.STATE_SCHEMA_VERSION == 2
    assert state["schema_version"] == 2
    assert state["status"] == "succeeded"
    assert state["attempt"] == 1
    assert state["failed_stage"] is None
    assert state["completed_actions"] == []
    assert state["completed_surfaces"] == ["validation_only"]
    assert state["pending_surfaces"] == []
    assert state["stages"][0]["stage"] == "validate"
    assert state["stages"][0]["status"] == "succeeded"
    assert state["stages"][0]["attempt"] == 1
    assert state["stages"][0]["elapsed_seconds"] >= 0
    assert state["stages"][0]["started_at"]
    assert state["stages"][0]["finished_at"]
    assert state["safe_retry_command"] == [
        sys.executable,
        str(repo.resolve() / "scripts/release.py"),
        "publish",
        "--repo",
        str(repo.resolve()),
        "--base",
        head,
        "--target",
        head,
        "--release-worktree",
        str(repo.resolve()),
        "--env-file",
        str(env_file.resolve()),
    ]
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(transaction_log.stat().st_mode) == 0o600
    assert private_message not in persisted
    assert private_environment not in persisted
    events = [json.loads(line) for line in transaction_log.read_text().splitlines()]
    assert events[0]["event"] == "transaction_started"
    assert events[-1]["event"] == "transaction_succeeded"
    assert {event["transaction_id"] for event in events} == {state["transaction_id"]}


def test_failed_publish_reuses_transaction_and_propagates_exact_id_to_ota_retry(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    changes = (
        _change(release, "M", "backend/app/main.py"),
        _change(release, "M", "mobile/app/index.tsx"),
    )
    plan = _isolated_historical_ota_protocol_plan(
        release, changes, base_sha="a" * 40, target_sha=head
    )
    monkeypatch.setenv("OTA_TRANSACTION_ID", "forged-parent-value")
    monkeypatch.setenv("OTA_TRANSACTION_REUSED", "1")
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    observed_transaction_env: list[tuple[str, str, str]] = []
    commands: list[str] = []

    def first_runner(command, **kwargs):
        command_name = Path(command[0]).name
        commands.append(command_name)
        observed_transaction_env.append(
            (
                command_name,
                kwargs["env"].get("OTA_TRANSACTION_ID", ""),
                kwargs["env"].get("OTA_TRANSACTION_REUSED", ""),
            )
        )
        if command_name == "mobile-ota.sh":
            raise subprocess.CalledProcessError(23, command)
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(release.ReleaseError, match="failed_stage=mobile_ota"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="PRIVATE_RETRY_MESSAGE",
            runner=first_runner,
        )

    failed_state = release.read_release_state(repo)
    transaction_id = failed_state["transaction_id"]
    assert commands == ["deploy.sh", "mobile-ota.sh"]
    assert observed_transaction_env == [
        ("deploy.sh", "", ""),
        ("mobile-ota.sh", transaction_id, "0"),
    ]
    assert failed_state["status"] == "failed"
    assert failed_state["attempt"] == 1
    assert failed_state["failed_stage"] == "mobile_ota"
    assert (
        failed_state["elapsed_seconds"] >= failed_state["stages"][-1]["elapsed_seconds"]
    )
    assert failed_state["completed_actions"] == ["deploy_backend"]
    assert failed_state["completed_surfaces"] == ["backend"]
    assert failed_state["pending_surfaces"] == ["mobile_ota"]
    assert "PRIVATE_RETRY_MESSAGE" not in json.dumps(failed_state)

    retry_plan = _isolated_historical_ota_protocol_plan(
        release,
        changes,
        base_sha="a" * 40,
        target_sha=head,
        completed_actions=release._state_completed_actions(repo, "a" * 40, head),
    )
    retry_commands: list[str] = []

    def retry_runner(command, **kwargs):
        command_name = Path(command[0]).name
        retry_commands.append(command_name)
        if command_name == "mobile-ota.sh":
            assert kwargs["env"]["OTA_TRANSACTION_ID"] == transaction_id
            assert kwargs["env"]["OTA_TRANSACTION_REUSED"] == "1"
        return subprocess.CompletedProcess(command, 0)

    release.publish_plan(
        retry_plan,
        repo,
        owner_repo=repo,
        message="different message must not affect identity",
        runner=retry_runner,
    )

    succeeded_state = release.read_release_state(repo)
    assert retry_commands == ["deploy.sh", "mobile-ota.sh"]
    assert succeeded_state["transaction_id"] == transaction_id
    assert succeeded_state["attempt"] == 2
    assert succeeded_state["status"] == "succeeded"
    assert succeeded_state["failed_stage"] is None
    assert succeeded_state["completed_surfaces"] == ["backend", "mobile_ota"]
    assert succeeded_state["pending_surfaces"] == []
    assert [
        (stage["stage"], stage["status"], stage["attempt"])
        for stage in succeeded_state["stages"]
    ] == [
        ("validate", "succeeded", 1),
        ("deploy_backend", "succeeded", 1),
        ("mobile_ota", "failed", 1),
        ("validate", "succeeded", 2),
        ("deploy_backend", "succeeded", 2),
        ("mobile_ota", "succeeded", 2),
    ]


def test_mobile_ota_first_attempt_after_backend_failure_is_still_fresh(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    changes = (
        _change(release, "M", "backend/app/main.py"),
        _change(release, "M", "mobile/app/index.tsx"),
    )
    plan = _isolated_historical_ota_protocol_plan(
        release, changes, base_sha="a" * 40, target_sha=head
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)

    with pytest.raises(release.ReleaseError, match="failed_stage=deploy_backend"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="first",
            runner=lambda command, **_kwargs: (_ for _ in ()).throw(
                subprocess.CalledProcessError(17, command)
            ),
        )

    failed_state = release.read_release_state(repo)
    transaction_id = failed_state["transaction_id"]
    retry_plan = _isolated_historical_ota_protocol_plan(
        release,
        changes,
        base_sha="a" * 40,
        target_sha=head,
        completed_actions=release._state_completed_actions(repo, "a" * 40, head),
    )
    observed: list[tuple[str, str, str]] = []

    def retry_runner(command, **kwargs):
        observed.append(
            (
                Path(command[0]).name,
                kwargs["env"].get("OTA_TRANSACTION_ID", ""),
                kwargs["env"].get("OTA_TRANSACTION_REUSED", ""),
            )
        )
        return subprocess.CompletedProcess(command, 0)

    release.publish_plan(
        retry_plan,
        repo,
        owner_repo=repo,
        message="retry",
        runner=retry_runner,
    )

    assert observed == [
        ("deploy.sh", "", ""),
        ("mobile-ota.sh", transaction_id, "0"),
    ]


def test_validation_failure_records_private_log_path_without_child_output(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan((), base_sha=head, target_sha=head)
    child_output = "PRIVATE_CHILD_OUTPUT_DO_NOT_COPY"
    monkeypatch.setenv("CI", "true")

    def failing_runner(command, **kwargs):
        kwargs["stdout"].write(child_output + "\n")
        return subprocess.CompletedProcess(command, 7)

    with pytest.raises(release.ReleaseError) as failure:
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="not persisted",
            runner=failing_runner,
        )

    state = release.read_release_state(repo)
    failed_stage = state["stages"][-1]
    validation_log = Path(failed_stage["log_path"])
    transaction_log = (
        release.release_state_dir(repo) / release.TRANSACTION_LOG_FILE_NAME
    )
    release_records = json.dumps(state) + transaction_log.read_text(encoding="utf-8")
    assert state["status"] == "failed"
    assert state["failed_stage"] == "validate"
    assert validation_log.exists()
    assert stat.S_IMODE(validation_log.stat().st_mode) == 0o600
    assert child_output in validation_log.read_text(encoding="utf-8")
    assert child_output not in release_records
    assert str(validation_log) in str(failure.value)
    assert "failed_stage=validate" in str(failure.value)


def test_corrupt_matching_resumable_state_fails_closed(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    release.write_release_state(
        repo,
        {
            "schema_version": 2,
            "base_sha": head,
            "target_sha": head,
            "transaction_id": "not-a-valid-transaction-id",
            "status": "failed",
            "attempt": 1,
            "completed_actions": ["deploy_backend", "malicious_action"],
            "completed_surfaces": ["backend"],
            "pending_surfaces": [],
            "failed_stage": "mobile_ota",
            "stages": "not-a-list",
            "safe_retry_command": [],
        },
    )

    with pytest.raises(release.ReleaseError, match="Corrupt resumable release state"):
        release._resumable_state_for_range(repo, head, head)


@pytest.mark.parametrize(
    "corruption", ["unexpected_field", "unproven_completion", "missing_elapsed"]
)
def test_resumable_state_rejects_privacy_fields_and_unproven_completion(
    corruption: str,
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)

    def failing_runner(command, **_kwargs):
        raise subprocess.CalledProcessError(2, command)

    with pytest.raises(release.ReleaseError):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="not persisted",
            runner=failing_runner,
        )
    state = release.read_release_state(repo)
    if corruption == "unexpected_field":
        state["stages"][-1]["child_output"] = "PRIVATE_CHILD_OUTPUT"
    elif corruption == "unproven_completion":
        state["completed_actions"] = ["deploy_backend"]
        state["completed_surfaces"] = ["backend"]
        state["pending_surfaces"] = []
    else:
        state.pop("elapsed_seconds")
    release.write_release_state(repo, state)

    with pytest.raises(release.ReleaseError, match="Corrupt resumable release state"):
        release._resumable_state_for_range(repo, "a" * 40, head)


def test_legacy_schema_state_is_never_reused_as_completion_proof(
    repository_with_origin: tuple[Path, Path],
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    state_dir = release.release_state_dir(repo)
    legacy_path = state_dir / release.STATE_FILE_NAME
    legacy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "base_sha": head,
                "target_sha": head,
                "completed_actions": ["deploy_backend"],
            }
        ),
        encoding="utf-8",
    )
    legacy_path.chmod(0o600)

    assert release._state_completed_actions(repo, head, head) == ()


def test_forged_self_consistent_state_cannot_skip_server_or_ota_publish(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    changes = (
        _change(release, "M", "backend/app/main.py"),
        _change(release, "M", "mobile/app/index.tsx"),
    )
    release.write_release_state(
        repo,
        {
            "schema_version": 2,
            "transaction_id": "f" * 32,
            "base_sha": "a" * 40,
            "target_sha": head,
            "status": "succeeded",
            "attempt": 1,
            "started_at": "2026-08-12T00:00:00+00:00",
            "finished_at": "2026-08-12T00:00:01+00:00",
            "elapsed_seconds": 1,
            "failed_stage": None,
            "completed_actions": ["deploy_backend", "mobile_ota"],
            "completed_surfaces": ["backend", "mobile_ota"],
            "pending_surfaces": [],
            "surface_scope": [],
            "deferred_surfaces": [],
            "stages": [
                {
                    "stage": action,
                    "status": "succeeded",
                    "attempt": 1,
                    "started_at": "2026-08-12T00:00:00+00:00",
                    "finished_at": "2026-08-12T00:00:01+00:00",
                    "elapsed_seconds": 1,
                }
                for action in ("deploy_backend", "mobile_ota")
            ],
            "safe_retry_command": release._safe_retry_command(
                repo=repo.resolve(),
                owner_repo=repo.resolve(),
                base_sha="a" * 40,
                target_sha=head,
                env_file=(repo / ".env").resolve(),
            ),
        },
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    plan = _isolated_historical_ota_protocol_plan(
        release,
        changes,
        base_sha="a" * 40,
        target_sha=head,
        completed_actions=release._state_completed_actions(repo, "a" * 40, head),
    )
    commands: list[str] = []

    release.publish_plan(
        plan,
        repo,
        owner_repo=repo,
        message="must execute",
        runner=lambda command, **_kwargs: (
            commands.append(Path(command[0]).name)
            or subprocess.CompletedProcess(command, 0)
        ),
    )

    assert plan.actions == ("validate", "deploy_backend", "mobile_ota")
    assert commands == ["deploy.sh", "mobile-ota.sh"]


def test_republishing_succeeded_range_revalidates_and_repeats_mutation_actions(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    changes = (_change(release, "M", "backend/app/main.py"),)
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    first_plan = release.build_plan(changes, base_sha="a" * 40, target_sha=head)
    first_commands: list[str] = []

    release.publish_plan(
        first_plan,
        repo,
        owner_repo=repo,
        message="first",
        runner=lambda command, **_kwargs: (
            first_commands.append(Path(command[0]).name)
            or subprocess.CompletedProcess(command, 0)
        ),
    )
    first_state = release.read_release_state(repo)
    second_plan = release.build_plan(
        changes,
        base_sha="a" * 40,
        target_sha=head,
        completed_actions=release._state_completed_actions(repo, "a" * 40, head),
    )
    second_commands: list[str] = []

    release.publish_plan(
        second_plan,
        repo,
        owner_repo=repo,
        message="second",
        runner=lambda command, **_kwargs: (
            second_commands.append(Path(command[0]).name)
            or subprocess.CompletedProcess(command, 0)
        ),
    )
    second_state = release.read_release_state(repo)

    assert first_commands == ["deploy.sh"]
    assert second_commands == ["deploy.sh"]
    assert second_state["transaction_id"] == first_state["transaction_id"]
    assert second_state["attempt"] == 2
    assert release._state_completed_actions(repo, "a" * 40, head) == ()


def test_interrupted_mutating_stage_requires_manual_reconciliation(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan(
        (_change(release, "M", "backend/app/main.py"),),
        base_sha="a" * 40,
        target_sha=head,
    )
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)

    def failing_runner(command, **_kwargs):
        raise subprocess.CalledProcessError(2, command)

    with pytest.raises(release.ReleaseError):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="not persisted",
            runner=failing_runner,
        )
    state = release.read_release_state(repo)
    interrupted = state["stages"][-1]
    interrupted["status"] = "running"
    interrupted.pop("finished_at")
    interrupted.pop("elapsed_seconds")
    state["status"] = "running"
    state["failed_stage"] = None
    state.pop("finished_at")
    state.pop("elapsed_seconds")
    release.write_release_state(repo, state)

    with pytest.raises(release.ReleaseError, match="manual reconciliation"):
        release.publish_plan(
            plan,
            repo,
            owner_repo=repo,
            message="must not retry uncertain mutation",
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("uncertain mutation must not repeat")
            ),
        )


def test_publish_lock_is_private_nonblocking_and_covers_publish_transaction(
    repository_with_origin: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    plan = release.build_plan((), base_sha=head, target_sha=head)
    monkeypatch.setattr(
        release,
        "run_validation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("busy transaction must reject before validation")
        ),
    )

    with release.release_publish_lock(repo):
        lock_path = release.release_state_dir(repo) / release.LOCK_FILE_NAME
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
        with pytest.raises(release.ReleaseError, match="already active"):
            release.publish_plan(
                plan,
                repo,
                owner_repo=repo,
                message="not reached",
            )

    assert release.read_release_state(repo) == {}


@pytest.mark.parametrize("unsafe_kind", ["permissions", "symlink"])
def test_publish_lock_refuses_unsafe_path_or_mode(
    unsafe_kind: str,
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    state_dir = release.release_state_dir(repo)
    lock_path = state_dir / release.LOCK_FILE_NAME
    if unsafe_kind == "permissions":
        lock_path.write_text("unsafe\n", encoding="utf-8")
        lock_path.chmod(0o644)
    else:
        target = tmp_path / "lock-target"
        target.write_text("unsafe\n", encoding="utf-8")
        os.symlink(target, lock_path)

    with pytest.raises(release.ReleaseError, match="Unsafe release publish lock"):
        with release.release_publish_lock(repo):
            raise AssertionError("unsafe lock must never be acquired")


def test_frozen_publish_cli_never_prepares_worktree_or_acquires_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()

    def unexpected(*_args, **_kwargs):
        raise AssertionError("frozen CLI must stop before release orchestration")

    monkeypatch.setattr(release, "release_publish_lock", unexpected)
    monkeypatch.setattr(release, "ensure_release_worktree", unexpected)
    monkeypatch.setattr(release, "publish_plan", unexpected)

    result = release.main(
        [
            "publish",
            "--repo",
            str(tmp_path),
            "--base",
            "HEAD",
        ]
    )

    assert result == 78
