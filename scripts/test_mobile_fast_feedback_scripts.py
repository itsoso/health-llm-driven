import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
FAST_TEST = ROOT / "scripts" / "mobile-fast-test.sh"
FAST_DEVICE = ROOT / "scripts" / "mobile-fast-device.sh"
OTA_SOURCE_GUARD = ROOT / "scripts" / "ota_source_guard.py"
EAS_OTA_PREVIEW_WORKFLOW = (
    ROOT / "mobile" / ".eas" / "workflows" / "ota-preview-manual.yml"
)


def test_eas_ota_fallback_is_manual_ios_preview_only() -> None:
    workflow = EAS_OTA_PREVIEW_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch: {}" in workflow
    assert "\n  push:" not in workflow
    assert "\n  pull_request:" not in workflow
    assert "type: update" in workflow
    assert "environment: preview" in workflow
    assert "platform: ios" in workflow
    assert "channel: preview" in workflow
    assert "channel: production" not in workflow


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


def run_fast_device(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "MOBILE_FAST_DEVICE_DRY_RUN": "1",
            "MOBILE_FAST_DEVICE_DEVICE_ID": "01177F59-4E5B-50D4-A900-2AC9A4D5F372",
            "MOBILE_FAST_DEVICE_XCODE_UDID": "00008150-00112D220E32401C",
            "MOBILE_FAST_DEVICE_DDI_AVAILABLE": "true",
            "MOBILE_FAST_DEVICE_WORKSPACE": "ios/app.xcworkspace",
            "MOBILE_FAST_DEVICE_SCHEME": "app",
            "MOBILE_FAST_DEVICE_APP_PATH": "/tmp/RevaFastDevice/app.app",
        }
    )
    return subprocess.run(
        [str(FAST_DEVICE), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_fast_device_release_reuses_derived_data_without_cleaning_native_state() -> None:
    result = run_fast_device("release")

    assert result.returncode == 0, result.stderr
    assert "xcodebuild" in result.stdout
    assert "-derivedDataPath" in result.stdout
    assert "RevaFastDevice" in result.stdout
    assert "APP_VARIANT=production" in result.stdout
    assert "device install app" in result.stdout
    assert "device process launch" in result.stdout
    assert "prebuild" not in result.stdout
    assert "pod install" not in result.stdout
    assert " clean" not in result.stdout


def test_fast_device_metro_supports_lan_and_explicit_tunnel() -> None:
    lan = run_fast_device("metro")
    tunnel = run_fast_device("metro", "--tunnel")

    assert lan.returncode == 0, lan.stderr
    assert "expo start --dev-client --lan" in lan.stdout
    assert tunnel.returncode == 0, tunnel.stderr
    assert "expo start --dev-client --tunnel" in tunnel.stdout


def test_fast_device_rejects_an_unavailable_xcode_device_before_build() -> None:
    env = os.environ.copy()
    env.update(
        {
            "MOBILE_FAST_DEVICE_DRY_RUN": "1",
            "MOBILE_FAST_DEVICE_DEVICE_ID": "device-id",
            "MOBILE_FAST_DEVICE_XCODE_UDID": "xcode-udid",
            "MOBILE_FAST_DEVICE_DDI_AVAILABLE": "false",
            "MOBILE_FAST_DEVICE_WORKSPACE": "ios/app.xcworkspace",
            "MOBILE_FAST_DEVICE_SCHEME": "app",
        }
    )
    result = subprocess.run(
        [str(FAST_DEVICE), "release"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "connect and unlock" in result.stderr.lower()
    assert "xcodebuild" not in result.stdout


def make_ota_runner(tmp_path: Path, mode: str) -> tuple[Path, Path]:
    runner = tmp_path / "fake-eas-update"
    counter = tmp_path / "attempts"
    runner.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
count=0
[[ -f \"${OTA_TEST_COUNTER}\" ]] && count=$(cat \"${OTA_TEST_COUNTER}\")
count=$((count + 1))
echo \"${count}\" > \"${OTA_TEST_COUNTER}\"
printf '%s\\n' \"$*\" >> \"${OTA_TEST_EAS_ARGS}\"
case \"${OTA_TEST_MODE}\" in
  transient)
    if [[ \"${count}\" == \"1\" ]]; then
      echo \"Asset processing timed out\" >&2
      exit 1
    fi
    ;;
  asset-timeout)
    if [[ \" $* \" != *\"reva-mobile-ota-js.\"* ]]; then
      echo \"Asset processing timed out for assets\" >&2
      exit 1
    fi
    ;;
  auth)
    echo \"Authentication failed: invalid token\" >&2
    exit 1
    ;;
  missing-ids)
    echo \"Update command completed without identifiers\"
    exit 0
    ;;
esac
echo \"Update group ID  11111111-1111-4111-8111-111111111111\"
echo \"iOS update ID    22222222-2222-4222-8222-222222222222\"
"""
    )
    runner.chmod(0o755)
    return runner, counter


def run_ota(
    tmp_path: Path,
    mode: str,
    *,
    force_no_bytecode: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    runner, counter = make_ota_runner(tmp_path, mode)
    expo_runner = tmp_path / "fake-expo-export"
    expo_runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "count=0\n"
        "[[ -f \"${OTA_TEST_EXPO_COUNTER}\" ]] && "
        "count=$(cat \"${OTA_TEST_EXPO_COUNTER}\")\n"
        "count=$((count + 1))\n"
        "echo \"${count}\" > \"${OTA_TEST_EXPO_COUNTER}\"\n"
        "printf '%s\\n' \"$*\" >> \"${OTA_TEST_EXPO_ARGS}\"\n"
    )
    expo_runner.chmod(0o755)
    anchor = tmp_path / "last-ota-commit"
    manifest = tmp_path / "release-manifest.json"
    env = os.environ.copy()
    env.update(
        {
            "OTA_ALLOW_DIRTY": "1",
            "OTA_EAS_RUNNER": str(runner),
            "OTA_EXPO_RUNNER": str(expo_runner),
            "OTA_ANCHOR_FILE": str(anchor),
            "OTA_MANIFEST_FILE": str(manifest),
            "OTA_TEST_COUNTER": str(counter),
            "OTA_TEST_MODE": mode,
            "OTA_TEST_EXPO_ARGS": str(tmp_path / "expo-args"),
            "OTA_TEST_EXPO_COUNTER": str(tmp_path / "expo-attempts"),
            "OTA_TEST_EAS_ARGS": str(tmp_path / "eas-args"),
            "OTA_AUDIT_LOG": str(tmp_path / "ota-audit.jsonl"),
            "REVA_RELEASE_LOCK_DIR": str(tmp_path / "release-lock"),
            "OTA_FORCE_NO_BYTECODE": "1" if force_no_bytecode else "0",
            "PATH": "/usr/bin:/bin",
        }
    )
    result = subprocess.run(
        [str(ROOT / "scripts" / "mobile-ota.sh"), "production", "test update"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, counter, anchor, manifest


def test_ota_retries_one_transient_failure_and_verifies_ids(tmp_path: Path) -> None:
    result, counter, anchor, manifest = run_ota(tmp_path, "transient")

    assert result.returncode == 0, result.stdout + result.stderr
    assert counter.read_text().strip() == "2"
    assert (tmp_path / "expo-attempts").read_text().strip() == "1"
    eas_attempts = (tmp_path / "eas-args").read_text().splitlines()
    assert len(eas_attempts) == 2
    assert eas_attempts[0] == eas_attempts[1]
    assert "--input-dir" in eas_attempts[0]
    assert "--skip-bundler" in eas_attempts[0]
    assert "11111111-1111-4111-8111-111111111111" in result.stdout
    assert "22222222-2222-4222-8222-222222222222" in result.stdout
    assert anchor.exists()
    payload = json.loads(manifest.read_text())
    assert payload["status"] == "published"
    assert payload["active_update_id"] == "22222222-2222-4222-8222-222222222222"
    assert payload["previous_known_good_update_id"] is None


def test_ota_falls_back_to_no_bytecode_after_repeated_asset_timeout(
    tmp_path: Path,
) -> None:
    result, counter, anchor, manifest = run_ota(tmp_path, "asset-timeout")

    assert result.returncode == 0, result.stdout + result.stderr
    assert counter.read_text().strip() == "2"
    assert (tmp_path / "expo-attempts").read_text().strip() == "2"
    expo_attempts = (tmp_path / "expo-args").read_text().splitlines()
    assert "--no-bytecode" not in expo_attempts[0]
    assert "--no-bytecode" in expo_attempts[1]
    assert "--skip-bundler" in result.stdout
    assert anchor.exists()
    assert json.loads(manifest.read_text())["status"] == "published"


def test_ota_can_force_no_bytecode_without_repeating_hermes_attempts(
    tmp_path: Path,
) -> None:
    result, counter, anchor, manifest = run_ota(
        tmp_path,
        "asset-timeout",
        force_no_bytecode=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert counter.read_text().strip() == "1"
    assert (tmp_path / "expo-attempts").read_text().strip() == "1"
    assert "--no-bytecode" in (tmp_path / "expo-args").read_text()
    assert anchor.exists()
    assert json.loads(manifest.read_text())["status"] == "published"


def test_ota_does_not_retry_authentication_failures(tmp_path: Path) -> None:
    result, counter, anchor, manifest = run_ota(tmp_path, "auth")

    assert result.returncode != 0
    assert counter.read_text().strip() == "1"
    assert not anchor.exists()
    assert not manifest.exists()
    audit_events = [
        json.loads(line)
        for line in (tmp_path / "ota-audit.jsonl").read_text().splitlines()
    ]
    assert audit_events[-1]["result"] == "failed"
    assert audit_events[-1]["failure_class"] == "non_retryable"
    assert set(audit_events[-1]) <= {
        "schema_version",
        "recorded_at",
        "platform",
        "channel",
        "environment",
        "runtime_version",
        "source_commit_sha",
        "main_commit_sha",
        "mobile_tree_digest",
        "artifact_variant",
        "attempt",
        "result",
        "failure_class",
        "duration_seconds",
        "group_id",
        "update_id",
    }


def test_ota_rejects_success_without_published_update_ids(tmp_path: Path) -> None:
    result, counter, anchor, manifest = run_ota(tmp_path, "missing-ids")

    assert result.returncode != 0
    assert counter.read_text().strip() == "1"
    assert "published identifier verification failed" in (result.stdout + result.stderr).lower()
    assert not anchor.exists()
    assert not manifest.exists()


def test_ota_manifest_keeps_previous_known_good_update(tmp_path: Path) -> None:
    first, _, _, manifest = run_ota(tmp_path, "success")
    assert first.returncode == 0, first.stdout + first.stderr

    second, _, _, _ = run_ota(tmp_path, "success")
    assert second.returncode == 0, second.stdout + second.stderr

    payload = json.loads(manifest.read_text())
    assert payload["previous_known_good_group_id"] == "11111111-1111-4111-8111-111111111111"
    assert payload["previous_known_good_update_id"] == "22222222-2222-4222-8222-222222222222"


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


def test_ota_manifest_records_source_main_and_relevant_tree(tmp_path: Path) -> None:
    result, _, _, manifest = run_ota(tmp_path, "success")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(manifest.read_text())
    assert len(payload["source_commit_sha"]) == 40
    assert len(payload["main_commit_sha"]) == 40
    assert len(payload["mobile_tree_digest"]) == 64
    assert payload["commit_sha"] in {
        payload["source_commit_sha"],
        payload["main_commit_sha"],
    }


def test_ota_rollback_defaults_to_dry_run(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({
        "status": "published",
        "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "previous_known_good_group_id": "11111111-1111-4111-8111-111111111111",
        "previous_known_good_update_id": "22222222-2222-4222-8222-222222222222",
    }))
    runner = tmp_path / "rollback-runner"
    called = tmp_path / "called"
    runner.write_text(f"#!/usr/bin/env bash\nprintf '%s' \"$*\" > '{called}'\n")
    runner.chmod(0o755)
    env = os.environ.copy()
    env.update({"OTA_MANIFEST_FILE": str(manifest), "OTA_EAS_RUNNER": str(runner)})

    result = subprocess.run(
        [str(ROOT / "scripts" / "mobile-ota-rollback.sh"), "production"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dry-run" in result.stdout
    assert not called.exists()


def test_ota_rollback_explains_when_manifest_has_no_known_good_target(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({
        "status": "published",
        "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    }))

    env = os.environ.copy()
    env["OTA_MANIFEST_FILE"] = str(manifest)
    result = subprocess.run(
        [str(ROOT / "scripts" / "mobile-ota-rollback.sh"), "production"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode != 0
    assert "没有 previous_known_good" in result.stderr


def test_ota_rollback_confirm_republishes_and_records_state(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({
        "status": "published",
        "active_group_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "active_update_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "previous_known_good_group_id": "11111111-1111-4111-8111-111111111111",
        "previous_known_good_update_id": "22222222-2222-4222-8222-222222222222",
    }))
    runner = tmp_path / "rollback-runner"
    called = tmp_path / "called"
    runner.write_text(f"#!/usr/bin/env bash\nprintf '%s' \"$*\" > '{called}'\n")
    runner.chmod(0o755)
    env = os.environ.copy()
    env.update({"OTA_MANIFEST_FILE": str(manifest), "OTA_EAS_RUNNER": str(runner)})

    result = subprocess.run(
        [str(ROOT / "scripts" / "mobile-ota-rollback.sh"), "production", "--confirm"],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    command = called.read_text()
    assert "update:republish" in command
    assert "--group 11111111-1111-4111-8111-111111111111" in command
    assert "--destination-channel production" in command
    payload = json.loads(manifest.read_text())
    assert payload["status"] == "rolled_back"
    assert payload["active_update_id"] == "22222222-2222-4222-8222-222222222222"
