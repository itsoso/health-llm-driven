import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAST_TEST = ROOT / "scripts" / "mobile-fast-test.sh"
FAST_DEVICE = ROOT / "scripts" / "mobile-fast-device.sh"


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
case \"${OTA_TEST_MODE}\" in
  transient)
    if [[ \"${count}\" == \"1\" ]]; then
      echo \"Asset processing timed out\" >&2
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


def run_ota(tmp_path: Path, mode: str) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    runner, counter = make_ota_runner(tmp_path, mode)
    anchor = tmp_path / "last-ota-commit"
    env = os.environ.copy()
    env.update(
        {
            "OTA_ALLOW_DIRTY": "1",
            "OTA_EAS_RUNNER": str(runner),
            "OTA_ANCHOR_FILE": str(anchor),
            "OTA_TEST_COUNTER": str(counter),
            "OTA_TEST_MODE": mode,
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
    return result, counter, anchor


def test_ota_retries_one_transient_failure_and_verifies_ids(tmp_path: Path) -> None:
    result, counter, anchor = run_ota(tmp_path, "transient")

    assert result.returncode == 0, result.stdout + result.stderr
    assert counter.read_text().strip() == "2"
    assert "11111111-1111-4111-8111-111111111111" in result.stdout
    assert "22222222-2222-4222-8222-222222222222" in result.stdout
    assert anchor.exists()


def test_ota_does_not_retry_authentication_failures(tmp_path: Path) -> None:
    result, counter, anchor = run_ota(tmp_path, "auth")

    assert result.returncode != 0
    assert counter.read_text().strip() == "1"
    assert not anchor.exists()


def test_ota_rejects_success_without_published_update_ids(tmp_path: Path) -> None:
    result, counter, anchor = run_ota(tmp_path, "missing-ids")

    assert result.returncode != 0
    assert counter.read_text().strip() == "1"
    assert "published identifier verification failed" in (result.stdout + result.stderr).lower()
    assert not anchor.exists()
