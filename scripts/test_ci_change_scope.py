import importlib.util
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER = ROOT / "scripts" / "ci_change_scope.py"
PREFLIGHT = ROOT / "scripts" / "release-preflight.sh"


def _load_classifier():
    spec = importlib.util.spec_from_file_location("ci_change_scope", CLASSIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ci_change_scope")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_only_runtime_scopes(result: dict[str, bool], *enabled: str) -> None:
    runtime_keys = {
        "run_backend",
        "run_frontend",
        "run_mobile",
        "run_mac",
        "run_type_drift",
        "run_release",
        "release_only",
        "full",
    }
    expected = set(enabled)
    assert {key for key in runtime_keys if result[key]} == expected


def test_docs_only_changes_select_lightweight_checks() -> None:
    result = _load_classifier().classify_changes(
        [
            "docs/dossiers/2026-08-12-example.md",
            "docs/plans/example.md",
            "README.md",
        ]
    )

    assert result["docs_only"] is True
    assert result["run_docs"] is True
    _assert_only_runtime_scopes(result)


def test_backend_runtime_changes_include_locked_type_drift() -> None:
    result = _load_classifier().classify_changes(
        ["backend/app/api/today.py", "backend/tests/test_today.py"]
    )

    assert result["docs_only"] is False
    assert result["run_docs"] is True
    _assert_only_runtime_scopes(
        result,
        "run_backend",
        "run_type_drift",
    )


def test_release_only_changes_do_not_start_application_builds() -> None:
    classifier = _load_classifier()

    for path in (
        "deploy.sh",
        "backend/scripts/backup_db.sh",
        "backend/scripts/archive_backup_offsite.sh",
        "scripts/test_backup_security.py",
        "scripts/test_release_rollback.py",
    ):
        result = classifier.classify_changes([path])
        assert result["docs_only"] is False, path
        _assert_only_runtime_scopes(result, "run_release", "release_only")


def test_surface_changes_select_only_their_runtime_gate() -> None:
    classifier = _load_classifier()

    _assert_only_runtime_scopes(
        classifier.classify_changes(["mobile/components/Card.tsx"]),
        "run_mobile",
    )
    _assert_only_runtime_scopes(
        classifier.classify_changes(["frontend/src/app/page.tsx"]),
        "run_frontend",
    )
    _assert_only_runtime_scopes(
        classifier.classify_changes(["apps/mac/Sources/App.swift"]),
        "run_mac",
    )


def test_release_and_dependency_changes_fail_closed_to_full() -> None:
    classifier = _load_classifier()

    for path in (
        ".github/workflows/ci.yml",
        "scripts/ci_change_scope.py",
        "backend/requirements.lock",
        "mobile/package-lock.json",
        "packages/shared/src/types.ts",
    ):
        result = classifier.classify_changes([path])
        assert result["full"] is True, path
        _assert_only_runtime_scopes(
            result,
            "run_backend",
            "run_frontend",
            "run_mobile",
            "run_mac",
            "run_type_drift",
            "run_release",
            "full",
        )


def test_mixed_backend_and_release_changes_run_both_lanes() -> None:
    result = _load_classifier().classify_changes(
        ["backend/app/api/today.py", "deploy.sh"]
    )

    _assert_only_runtime_scopes(
        result,
        "run_backend",
        "run_type_drift",
        "run_release",
    )


def test_unknown_empty_and_workflow_dispatch_changes_fail_closed_to_full() -> None:
    classifier = _load_classifier()

    for paths, event_name in (
        (["unexpected/new-root/file.txt"], "push"),
        ([], "push"),
        (["docs/readme.md"], "workflow_dispatch"),
    ):
        result = classifier.classify_changes(paths, event_name=event_name)
        assert result["full"] is True


def test_cli_json_output_is_stable() -> None:
    result = subprocess.run(
        ["python3", str(CLASSIFIER), "--format", "json"],
        cwd=ROOT,
        input="mobile/app/index.tsx\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run_mobile"] is True


def _dry_run_preflight(changed_files: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "REVA_PREFLIGHT_DRY_RUN": "1",
            "REVA_PREFLIGHT_CHANGED_FILES": changed_files,
        }
    )
    return subprocess.run(
        [str(PREFLIGHT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_docs_preflight_stops_before_runtime_commands() -> None:
    result = _dry_run_preflight("docs/dossiers/example.md\n")

    assert result.returncode == 0, result.stderr
    assert "check_secret_leaks.py" in result.stdout
    assert "check_system_map.py" in result.stdout
    assert "check_dossier_consistency.py" in result.stdout
    assert "generate-api-types.sh" not in result.stdout
    assert "mobile-fast-test.sh" not in result.stdout
    assert "test_release_ci_contract.py" not in result.stdout


def test_backend_and_release_preflight_selects_contract_gates() -> None:
    result = _dry_run_preflight(
        "backend/app/api/today.py\nscripts/release-preflight.sh\n"
    )

    assert result.returncode == 0, result.stderr
    assert "generate-api-types.sh --check" in result.stdout
    assert "test_release_ci_contract.py" in result.stdout
    assert "gh run list" in result.stdout


def test_preflight_uses_controlled_python_for_all_python_checks() -> None:
    script = PREFLIGHT.read_text(encoding="utf-8")

    assert 'REVA_PREFLIGHT_PYTHON' in script
    assert 'command -v python3.12' in script
    assert 'printf \'%s\\n\' "${CHANGED_FILES}"; } | "${PREFLIGHT_PYTHON}"' in script
    assert '"${PREFLIGHT_PYTHON}" - "${BASELINE_JSON}"' in script
    assert 'run "${PREFLIGHT_PYTHON}" "${REPO_ROOT}/scripts/check_secret_leaks.py"' in script
    assert 'run "${PREFLIGHT_PYTHON}" "${REPO_ROOT}/scripts/check_system_map.py"' in script
