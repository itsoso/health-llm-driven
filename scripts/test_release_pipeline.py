import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = ROOT / "scripts/release.py"


def _release_module():
    assert RELEASE_SCRIPT.exists(), "scripts/release.py has not been implemented"
    spec = importlib.util.spec_from_file_location("reva_release", RELEASE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _change(release, status: str, *paths: str):
    return release.Change(status=status, paths=paths)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repository_with_origin(tmp_path: Path) -> tuple[Path, Path]:
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
    return repo, origin


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


def test_mobile_runtime_change_plans_ota_only():
    release = _release_module()

    plan = release.build_plan(
        (_change(release, "M", "mobile/app/settings.tsx"),),
        base_sha="a" * 40,
        target_sha="b" * 40,
    )

    assert plan.surfaces == ("mobile_ota",)
    assert plan.actions == ("validate", "mobile_ota")
    assert plan.publishable is True


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

    assert plan.actions == ("validate", "deploy_backend", "mobile_ota")


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

    assert plan.actions == ("validate", "deploy_all", "mobile_ota")


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
    repo, _origin = repository_with_origin
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
    repo, _origin = repository_with_origin
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
    assert ota_plan.surfaces == ("mobile_ota",)
    assert ota_plan.actions == ("validate", "mobile_ota")


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
        "mobile_ota",
    )
    assert delete_plan.actions == ("validate", "native_build")


def test_completed_surface_is_not_repeated_after_partial_publish():
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

    assert plan.completed_actions == ("deploy_backend",)
    assert plan.actions == ("validate", "mobile_ota")


def test_validation_credential_hit_skips_full_suite(
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
    verified: dict[str, object] = {}

    def verify(**kwargs):
        verified.update(kwargs)
        return release.validation_credential.CredentialVerdict(
            True, "reusable", {"result": "pass"}
        )

    monkeypatch.setattr(release.validation_credential, "verify_credential", verify)
    monkeypatch.setattr(
        release.validation_credential,
        "collect_toolchain",
        lambda _repo: {"python": "test"},
    )

    def runner(*_args, **_kwargs):
        raise AssertionError("credential hit must not rerun validation")

    release.run_validation(plan, repo, runner=runner)

    assert verified["repo"] == repo
    assert verified["profile_name"] == "all"
    assert verified["profile_version"] == release.validation_credential.PROFILE_VERSION
    assert verified["commands"] == [
        {
            "name": "validation:all",
            "argv": ["bash", "scripts/run-all-tests.sh"],
            "cwd": ".",
            "blocking": True,
        }
    ]
    assert verified["toolchain"] == {"python": "test"}
    assert "validation credential hit" in capsys.readouterr().out


@pytest.mark.parametrize(
    "reason", ["credential missing", "credential is invalid JSON", "credential expired"]
)
def test_validation_credential_miss_runs_suite_then_atomically_issues(
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
    built: dict[str, object] = {}
    written: list[tuple[Path, dict[str, str]]] = []

    monkeypatch.setattr(
        release.validation_credential,
        "verify_credential",
        lambda **_kwargs: release.validation_credential.CredentialVerdict(
            False, reason
        ),
    )
    monkeypatch.setattr(
        release.validation_credential,
        "collect_toolchain",
        lambda _repo: {"python": "test"},
    )

    def build(**kwargs):
        built.update(kwargs)
        return {"result": "pass"}

    monkeypatch.setattr(release.validation_credential, "build_credential", build)
    monkeypatch.setattr(
        release.validation_credential,
        "write_credential_atomic",
        lambda path, payload: written.append((Path(path), payload)),
    )

    def runner(command, **kwargs):
        calls.append(tuple(command))
        kwargs["stdout"].write("all checks passed\n")
        return subprocess.CompletedProcess(command, 0)

    release.run_validation(plan, repo, runner=runner)

    assert calls == [("bash", "scripts/run-all-tests.sh")]
    assert built["repo"] == repo
    assert built["profile_name"] == "all"
    assert built["commands"] == [
        {
            "name": "validation:all",
            "argv": ["bash", "scripts/run-all-tests.sh"],
            "cwd": ".",
            "blocking": True,
        }
    ]
    log_path = Path(built["logs"]["validation:all"])
    assert log_path.read_text(encoding="utf-8") == "all checks passed\n"
    assert written == [
        (release.validation_credential.credential_path(repo, "all"), {"result": "pass"})
    ]
    output = capsys.readouterr().out
    assert f"validation credential miss: profile=all reason={reason}" in output
    assert "validation credential issued" in output


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
        "collect_toolchain",
        lambda _repo: {"python": "test"},
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
    assert "CI requires commit-specific validation" in capsys.readouterr().out


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
        (_change(release, "M", "mobile/app/index.tsx"),),
        base_sha="a" * 40,
        target_sha=head,
    )
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
    ):
        monkeypatch.setenv(name, "/tmp/shell-injection")
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
    ):
        assert name not in observed[0]


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


def test_release_worktree_is_detached_and_exactly_tracks_remote_main(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    release_path = tmp_path / "permanent.release"

    prepared = release.ensure_release_worktree(repo, release_path=release_path)

    assert prepared == release_path.resolve()
    assert (
        subprocess.run(
            ["git", "-C", str(prepared), "symbolic-ref", "-q", "HEAD"],
            check=False,
        ).returncode
        != 0
    )
    assert _git(prepared, "rev-parse", "HEAD") == _git(repo, "rev-parse", "origin/main")
    release.assert_release_source(prepared)


def test_dirty_release_worktree_is_refused_without_cleanup(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    release_path = tmp_path / "permanent.release"
    release.ensure_release_worktree(repo, release_path=release_path)
    old_head = _git(release_path, "rev-parse", "HEAD")
    dirty_file = release_path / "operator-notes.txt"
    dirty_file.write_text("do not delete\n", encoding="utf-8")
    (repo / "README.md").write_text("advanced\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "advance main")
    _git(repo, "push", "-q", "origin", "main")

    with pytest.raises(release.ReleaseError, match="dirty"):
        release.ensure_release_worktree(repo, release_path=release_path)

    assert dirty_file.read_text(encoding="utf-8") == "do not delete\n"
    assert _git(release_path, "rev-parse", "HEAD") == old_head


def test_named_feature_branch_release_worktree_is_refused(
    repository_with_origin: tuple[Path, Path], tmp_path: Path
):
    release = _release_module()
    repo, _origin = repository_with_origin
    release_path = tmp_path / "permanent.release"
    release.ensure_release_worktree(repo, release_path=release_path)
    _git(release_path, "checkout", "-qb", "feature/not-production")

    with pytest.raises(release.ReleaseError, match="feature/not-production"):
        release.ensure_release_worktree(repo, release_path=release_path)

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


def test_plan_command_does_not_create_shared_operational_state(
    repository_with_origin: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
):
    release = _release_module()
    repo, _origin = repository_with_origin
    common_dir = Path(_git(repo, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    state_dir = common_dir.resolve() / "reva-release-state"

    exit_code = release.main(
        [
            "plan",
            "--repo",
            str(repo),
            "--base",
            "HEAD",
            "--target",
            "HEAD",
        ]
    )

    assert exit_code == 0, capsys.readouterr().err
    assert not state_dir.exists()


def test_validate_runs_for_manual_native_plan_without_publishing(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    exit_code = release.main(
        [
            "validate",
            "--repo",
            str(repo),
            "--base",
            baseline,
            "--release-worktree",
            str(tmp_path / "release"),
        ]
    )

    assert exit_code == 0, capsys.readouterr().err
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
    plan = release.build_plan(changes, base_sha="a" * 40, target_sha=head)
    monkeypatch.setenv("OTA_TRANSACTION_ID", "forged-parent-value")
    monkeypatch.setattr(release, "run_validation", lambda *_args, **_kwargs: None)
    observed_transaction_ids: list[str] = []
    commands: list[str] = []

    def first_runner(command, **kwargs):
        commands.append(Path(command[0]).name)
        observed_transaction_ids.append(kwargs["env"]["OTA_TRANSACTION_ID"])
        if Path(command[0]).name == "mobile-ota.sh":
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
    assert observed_transaction_ids == [transaction_id, transaction_id]
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

    retry_plan = release.build_plan(
        changes,
        base_sha="a" * 40,
        target_sha=head,
        completed_actions=release._state_completed_actions(repo, "a" * 40, head),
    )
    retry_commands: list[str] = []

    def retry_runner(command, **kwargs):
        retry_commands.append(Path(command[0]).name)
        assert kwargs["env"]["OTA_TRANSACTION_ID"] == transaction_id
        return subprocess.CompletedProcess(command, 0)

    release.publish_plan(
        retry_plan,
        repo,
        owner_repo=repo,
        message="different message must not affect identity",
        runner=retry_runner,
    )

    succeeded_state = release.read_release_state(repo)
    assert retry_commands == ["mobile-ota.sh"]
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
        ("mobile_ota", "succeeded", 2),
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
        release._state_completed_actions(repo, head, head)


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
        release._state_completed_actions(repo, "a" * 40, head)


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


def test_republishing_succeeded_range_keeps_original_transaction_stage_proof(
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
    assert second_commands == []
    assert second_state["transaction_id"] == first_state["transaction_id"]
    assert second_state["attempt"] == 2
    assert release._state_completed_actions(repo, "a" * 40, head) == ("deploy_backend",)


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


def test_publish_cli_acquires_coordinator_lock_before_preparing_worktree(
    repository_with_origin: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    release = _release_module()
    repo, _origin = repository_with_origin
    head = _git(repo, "rev-parse", "HEAD")
    lock_observed: list[bool] = []
    publish_lock_flags: list[bool] = []

    def ensure_while_locked(source, *, release_path=None):
        del release_path
        with pytest.raises(release.ReleaseError, match="already active"):
            with release.release_publish_lock(source):
                raise AssertionError("coordinator lock was not held")
        lock_observed.append(True)
        return repo

    def publish_while_locked(_plan, _repo, **kwargs):
        publish_lock_flags.append(kwargs["_lock_held"])
        assert kwargs["owner_repo"] == repo

    monkeypatch.setattr(release, "ensure_release_worktree", ensure_while_locked)
    monkeypatch.setattr(release, "assert_release_source", lambda _repo: head)
    monkeypatch.setattr(
        release,
        "_plan_for_refs",
        lambda *_args, **_kwargs: release.build_plan(
            (), base_sha=head, target_sha=head
        ),
    )
    monkeypatch.setattr(release, "_print_plan", lambda _plan: None)
    monkeypatch.setattr(release, "publish_plan", publish_while_locked)

    result = release.main(
        [
            "publish",
            "--repo",
            str(repo),
            "--base",
            head,
            "--target",
            head,
            "--release-worktree",
            str(tmp_path / "release"),
        ]
    )

    assert result == 0
    assert lock_observed == [True]
    assert publish_lock_flags == [True]
