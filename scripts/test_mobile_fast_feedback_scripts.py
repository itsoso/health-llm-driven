import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
FAST_TEST = ROOT / "scripts" / "mobile-fast-test.sh"
FAST_DEVICE = ROOT / "scripts" / "mobile-fast-device.sh"
LOCAL_DEVICE = ROOT / "scripts" / "mobile-local-device.sh"
MAC_PACKAGE = ROOT / "apps" / "mac" / "scripts" / "package-app.sh"
ANDROID_WRITER = ROOT / "scripts" / "mobile-android-frozen.sh"
OTA_WRITER = ROOT / "scripts" / "mobile-ota.sh"
OTA_ROLLBACK_WRITER = ROOT / "scripts" / "mobile-ota-rollback.sh"
EAS_PREFLIGHT = ROOT / "scripts" / "preflight-eas.sh"
RELEASE_SCRIPT = ROOT / "scripts" / "release.py"
OTA_SOURCE_GUARD = ROOT / "scripts" / "ota_source_guard.py"


def test_mobile_dependency_overrides_preserve_brace_expansion_major_compatibility() -> None:
    package_json = json.loads((ROOT / "mobile" / "package.json").read_text())
    overrides = package_json["overrides"]

    assert "brace-expansion" not in overrides
    assert overrides["brace-expansion@<2.0.0"] == "1.1.18"
    assert overrides["brace-expansion@>=2.0.0 <3.0.0"] == "2.1.4"
    assert overrides["brace-expansion@>=5.0.0"] == "5.0.9"
    assert overrides["js-yaml@>=3.0.0 <4.0.0"] == "3.15.1"
    assert overrides["js-yaml@>=4.0.0 <5.0.0"] == "4.3.1"
    assert overrides["nanoid"] == "3.3.18"
    assert overrides["postcss"] == "8.5.26"


def test_frontend_dependency_overrides_close_nanoid_and_postcss_advisories() -> None:
    package_json = json.loads((ROOT / "frontend" / "package.json").read_text())

    assert package_json["devDependencies"]["postcss"] == "8.5.26"
    assert package_json["overrides"]["postcss"] == "8.5.26"
    assert package_json["overrides"]["nanoid"] == "3.3.18"


def test_committed_npm_lockfiles_only_use_the_public_registry() -> None:
    allowed_hosts = {"registry.npmjs.org", "registry.npmmirror.com"}

    for app_dir in ("frontend", "mobile"):
        lockfile = json.loads((ROOT / app_dir / "package-lock.json").read_text())

        for package in lockfile["packages"].values():
            if resolved := package.get("resolved"):
                source = urlparse(resolved)
                assert source.scheme == "https"
                assert source.hostname in allowed_hosts


def run_fast_test(*args: str, changed_files: str = "") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MOBILE_FAST_TEST_DRY_RUN"] = "1"
    env["MOBILE_FAST_TEST_CHANGED_FILES"] = changed_files
    return subprocess.run(
        [str(FAST_TEST), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_fast_test_selects_related_jest_lint_and_incremental_typecheck() -> None:
    result = run_fast_test(
        changed_files="mobile/services/appUpdate.ts\nmobile/hooks/useAppUpdate.tsx\n"
    )

    assert result.returncode == 0, result.stderr
    assert "jest --findRelatedTests services/appUpdate.ts hooks/useAppUpdate.tsx" in result.stdout
    assert "eslint services/appUpdate.ts hooks/useAppUpdate.tsx" in result.stdout
    assert "tsc --noEmit --incremental" in result.stdout
    assert "git -C" in result.stdout and "diff --check" in result.stdout


def test_fast_test_skips_jest_for_non_code_mobile_changes() -> None:
    result = run_fast_test(changed_files="mobile/assets/icon.png\n")

    assert result.returncode == 0, result.stderr
    assert "jest" not in result.stdout
    assert "eslint" not in result.stdout
    assert "tsc" not in result.stdout
    assert "diff --check" in result.stdout


def test_fast_test_runs_full_gate_on_shared_package_changes() -> None:
    result = run_fast_test(changed_files="packages/shared/src/types.ts\n")

    assert result.returncode == 0, result.stderr
    assert "npm test -- --runInBand" in result.stdout
    assert "npm run lint" in result.stdout
    assert "tsc --noEmit --incremental" in result.stdout


def test_fast_test_all_mode_is_explicit() -> None:
    result = run_fast_test("--all")

    assert result.returncode == 0, result.stderr
    assert "npm test -- --runInBand" in result.stdout
    assert "--forceExit" in result.stdout
    assert "npm run lint" in result.stdout
    assert "tsc --noEmit --incremental" in result.stdout


def _fake_path_tools(tmp_path: Path, names: tuple[str, ...]) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-tool-called"
    for name in names:
        fake = fake_bin / name
        fake.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "{name}" >> "{marker}"\nexit 91\n',
            encoding="utf-8",
        )
        fake.chmod(0o755)
    return fake_bin, marker


def _run_frozen_writer(
    script: Path,
    arguments: tuple[str, ...],
    *,
    fake_bin: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(script), *arguments],
        cwd=ROOT,
        env={
            **os.environ,
            **(extra_env or {}),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_device_and_mac_writer_entrypoints_freeze_before_external_tools(
    tmp_path: Path,
) -> None:
    fake_bin, marker = _fake_path_tools(
        tmp_path,
        (
            "basename",
            "chmod",
            "codesign",
            "cp",
            "dirname",
            "find",
            "git",
            "mkdir",
            "mktemp",
            "npx",
            "open",
            "osascript",
            "pgrep",
            "pkill",
            "plutil",
            "pod",
            "python3",
            "rm",
            "seq",
            "sleep",
            "swift",
            "xcodebuild",
            "xcrun",
        ),
    )
    cases = (
        (FAST_DEVICE, ()),
        (FAST_DEVICE, ("release",)),
        (FAST_DEVICE, ("metro", "--tunnel")),
        (LOCAL_DEVICE, ()),
        (LOCAL_DEVICE, ("--help",)),
        (MAC_PACKAGE, ()),
        (MAC_PACKAGE, ("--no-sign",)),
        (MAC_PACKAGE, ("--install", "--open")),
        (MAC_PACKAGE, ("--help",)),
        (ANDROID_WRITER, ()),
        (ANDROID_WRITER, ("--device", "physical-device")),
    )

    for script, arguments in cases:
        completed = _run_frozen_writer(
            script,
            arguments,
            fake_bin=fake_bin,
            extra_env={
                "MOBILE_FAST_DEVICE_DRY_RUN": "1",
                "MOBILE_FAST_DEVICE_WORKSPACE": "attacker-workspace",
                "HEALTH_MAC_SIGN_IDENTITY": "attacker-identity",
                "MAC_APP_VERSION": "attacker-version",
            },
        )
        assert completed.returncode == 78, (script, arguments, completed.stderr)
        assert "frozen" in completed.stderr.lower()
        assert not marker.exists(), (script, arguments, marker.read_text())


def test_mobile_android_npm_entrypoint_is_frozen_before_native_tools(
    tmp_path: Path,
) -> None:
    package = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["android"] == "../scripts/mobile-android-frozen.sh"

    fake_bin, marker = _fake_path_tools(
        tmp_path,
        ("adb", "expo", "gradle", "java", "npx"),
    )
    result = _run_frozen_writer(
        ANDROID_WRITER,
        ("--device", "physical-device"),
        fake_bin=fake_bin,
    )
    assert result.returncode == 78
    assert "frozen" in result.stderr.lower()
    assert not marker.exists()


def test_device_and_mac_writer_freeze_precedes_path_env_and_tool_resolution() -> None:
    expectations = {
        FAST_DEVICE: ('REPO_ROOT="', 'MODE="', "xcodebuild"),
        LOCAL_DEVICE: ('REPO_ROOT="', "command -v xcodebuild", "npx expo prebuild"),
        MAC_PACKAGE: ('APP_NAME="', 'SIGN_IDENTITY="', "swift build"),
    }

    for script, later_tokens in expectations.items():
        source = script.read_text(encoding="utf-8")
        freeze = source.index("writer entrypoint is frozen")
        for token in later_tokens:
            assert freeze < source.index(token), (script, token)


def test_ota_writer_entrypoints_freeze_without_runner_or_state_side_effects(
    tmp_path: Path,
) -> None:
    fake_bin, marker = _fake_path_tools(
        tmp_path,
        ("date", "dirname", "eas", "git", "mkdir", "mktemp", "node", "npx", "python3", "sleep"),
    )
    state_paths = (
        tmp_path / "anchor",
        tmp_path / "audit.jsonl",
        tmp_path / "manifest.json",
        tmp_path / "release-lock",
    )
    extra_env = {
        "OTA_EAS_RUNNER": str(fake_bin / "eas"),
        "OTA_EXPO_RUNNER": str(fake_bin / "npx"),
        "OTA_ANCHOR_FILE": str(state_paths[0]),
        "OTA_AUDIT_LOG": str(state_paths[1]),
        "OTA_MANIFEST_FILE": str(state_paths[2]),
        "REVA_RELEASE_LOCK_DIR": str(state_paths[3]),
    }
    cases = (
        (OTA_WRITER, ()),
        (OTA_WRITER, ("production", "message")),
        (OTA_WRITER, ("preview", "message")),
        (OTA_WRITER, ("development", "message")),
        (OTA_ROLLBACK_WRITER, ()),
        (OTA_ROLLBACK_WRITER, ("production",)),
        (OTA_ROLLBACK_WRITER, ("production", "--confirm")),
    )

    for script, arguments in cases:
        completed = _run_frozen_writer(
            script,
            arguments,
            fake_bin=fake_bin,
            extra_env=extra_env,
        )
        assert completed.returncode == 78, (script, arguments, completed.stderr)
        assert "冻结" in completed.stderr
        assert not marker.exists(), (script, arguments, marker.read_text())
        assert all(not path.exists() for path in state_paths)


def test_local_device_guidance_does_not_advertise_frozen_publishers() -> None:
    local_device_source = LOCAL_DEVICE.read_text(encoding="utf-8")
    release_source = RELEASE_SCRIPT.read_text(encoding="utf-8")

    assert "./scripts/mobile-ota.sh " + "preview" not in local_device_source
    assert "./scripts/_run-mobile-tf.sh " + "remote" not in local_device_source
    assert "preview/dev OTA remains " + "available" not in release_source
    assert "所有 EAS OTA 与 production 原生候选发布入口当前冻结" in local_device_source
    assert "no direct preview, development," in release_source


def test_eas_preflight_only_claims_simulator_and_static_validation() -> None:
    source = EAS_PREFLIGHT.read_text(encoding="utf-8")

    assert "可以放心触发 EAS / 本地 build" not in source
    assert "先跑 ./scripts/mobile-local-device.sh" not in source
    assert "不授权 EAS、真机签名、设备安装或商店发布" in source


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def _source_guard(
    repo: Path,
    source: str,
    main: str,
    *,
    allow_divergence: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        "python3",
        str(OTA_SOURCE_GUARD),
        "--repo",
        str(repo),
        "--source",
        source,
        "--main",
        main,
        "--format",
        "json",
    ]
    if allow_divergence:
        command.append("--allow-divergence")
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _make_source_guard_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "mobile").mkdir(parents=True)
    (repo / "packages/shared").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "mobile/app.ts").write_text("export const version = 1;\n")
    (repo / "packages/shared/types.ts").write_text("export type Id = string;\n")
    (repo / "docs/readme.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"], cwd=repo, check=True
    )
    return repo, _commit(repo, "base")


def test_ota_source_guard_allows_docs_only_main_advancement(tmp_path: Path) -> None:
    repo, source = _make_source_guard_repo(tmp_path)
    (repo / "docs/readme.md").write_text("advanced docs\n")
    main = _commit(repo, "docs only")

    result = _source_guard(repo, source, main)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["source_commit_sha"] == source
    assert payload["main_commit_sha"] == main
    assert payload["release_commit_sha"] == main
    assert payload["main_advanced"] is True
    assert len(payload["mobile_tree_digest"]) == 64


def test_ota_source_guard_rejects_mobile_divergence_and_dirty_paths(
    tmp_path: Path,
) -> None:
    repo, source = _make_source_guard_repo(tmp_path)
    (repo / "mobile/app.ts").write_text("export const version = 2;\n")
    main = _commit(repo, "mobile change")

    diverged = _source_guard(repo, source, main)
    assert diverged.returncode != 0
    assert "mobile/shared" in diverged.stderr.lower()

    clean = _source_guard(repo, main, main)
    assert clean.returncode == 0, clean.stderr
    (repo / "packages/shared/types.ts").write_text("export type Id = number;\n")
    dirty = _source_guard(repo, main, main)
    assert dirty.returncode != 0
    assert "uncommitted" in dirty.stderr.lower()
