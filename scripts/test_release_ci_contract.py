from glob import glob
import os
from pathlib import Path
import subprocess
import textwrap

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_TESTS = (
    "scripts/test_ci_change_scope.py",
    "scripts/test_asc_profiles.py",
    "scripts/test_deploy_script.py",
    "scripts/test_frozen_shell_entrypoints.py",
    "scripts/test_generate_api_types.py",
    "scripts/test_health_evidence_activation_runner.py",
    "scripts/test_release_lock.py",
    "scripts/test_release_rollback.py",
    "scripts/test_infrastructure_security.py",
    "scripts/test_mobile_fast_feedback_scripts.py",
    "scripts/test_mobile_local_qr_script.py",
    "scripts/test_runtime_state_release_transaction.py",
    "scripts/test_release_pipeline.py",
    "scripts/test_run_all_tests.py",
    "scripts/test_validation_credential.py",
    "scripts/test_mobile_ota.py",
    "scripts/test_mobile_native_ota_compatibility.py",
    "scripts/test_ios_acceptance_harness.py",
    "scripts/test_sim_build.py",
    "scripts/test_release_production_state.py",
    "scripts/test_app_store_privileged_cli_freeze.py",
    "scripts/test_rokid_release_freeze.py",
    "scripts/test_locked_eas_cli.py",
    "scripts/test_mac_release_receipt.py",
    "scripts/test_mac_release_nginx.py",
    "scripts/test_release_step_proof.py",
    "scripts/test_release_ci_contract.py",
    "scripts/test_release_input_digest.py",
    "scripts/test_verify_locked_requirements.py",
)


def _run_bodies(job: dict) -> str:
    return "\n".join(
        str(step.get("run") or "")
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )


def _aggregate_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "CLASSIFIER_RESULT": "success",
            "DOCS_ONLY": "true",
            "RUN_DOCS": "true",
            "RUN_BACKEND": "false",
            "RUN_FRONTEND": "false",
            "RUN_MOBILE": "false",
            "RUN_RELEASE": "false",
            "RUN_MAC": "false",
            "RUN_TYPE_DRIFT": "false",
            "FULL": "false",
            "DOCS_QUALITY": "success",
            "TEST_SHARDS": "skipped",
            "QUALITY_GATES": "skipped",
            "RELEASE_INVARIANTS": "skipped",
            "RUNTIME_POSTGRES": "skipped",
            "MAC_BUILD": "skipped",
            "TYPE_DRIFT_RESULT": "skipped",
            "FRONTEND_BUILD": "skipped",
            "MOBILE_TYPECHECK": "skipped",
        }
    )
    environment.update(overrides)
    return environment


def _classifier_guard_source() -> str:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    source = _run_bodies(workflow["jobs"]["classify-changes"])
    marker = "python3 - <<'PY'\n"
    start = source.index(marker) + len(marker)
    end = source.index("\nPY\n", start)
    return textwrap.dedent(source[start:end])


def test_ci_blocks_on_release_invariants_and_exercises_macos_bash3():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    release_job = jobs["release-invariants"]
    release_runs = _run_bodies(release_job)

    assert release_job["runs-on"] == "ubuntu-latest"
    assert release_job.get("continue-on-error") is not True
    release_test_step = next(
        step
        for step in release_job["steps"]
        if step.get("name")
        == "Run deployment, rollback, planner, OTA, and acceptance invariants"
    )
    assert release_test_step.get("continue-on-error") is not True
    for test_path in RELEASE_TESTS:
        assert test_path in release_runs

    ruby_setup = next(
        step
        for step in release_job["steps"]
        if str(step.get("uses", "")).startswith("ruby/setup-ruby@")
    )
    assert ruby_setup["with"]["ruby-version"] == "3.3"
    xcodeproj_install = next(
        step
        for step in release_job["steps"]
        if step.get("name") == "Install pinned xcodeproj dependency"
    )
    assert (
        str(xcodeproj_install["run"]).strip()
        == "gem install xcodeproj --version 1.27.0 --no-document"
    )

    backend_needs = jobs["backend-tests"]["needs"]
    assert "release-invariants" in backend_needs
    assert "mac-build" in backend_needs
    assert "type-drift" in backend_needs
    assert "frontend-build" in backend_needs
    assert "mobile-typecheck" in backend_needs
    assert (
        "RELEASE_INVARIANTS"
        in jobs["backend-tests"]["steps"][0]["env"]
    )
    assert "RUN_MAC" in jobs["backend-tests"]["steps"][0]["env"]
    assert "MAC_BUILD" in jobs["backend-tests"]["steps"][0]["env"]
    assert "RUN_TYPE_DRIFT" in jobs["backend-tests"]["steps"][0]["env"]
    assert "TYPE_DRIFT_RESULT" in jobs["backend-tests"]["steps"][0]["env"]
    assert "FRONTEND_BUILD" in jobs["backend-tests"]["steps"][0]["env"]
    assert "MOBILE_TYPECHECK" in jobs["backend-tests"]["steps"][0]["env"]
    for name in (
        "DOCS_ONLY",
        "RUN_DOCS",
        "RUN_BACKEND",
        "RUN_FRONTEND",
        "RUN_MOBILE",
        "RUN_RELEASE",
        "RUN_MAC",
        "RUN_TYPE_DRIFT",
        "FULL",
    ):
        assert name in jobs["backend-tests"]["steps"][0]["env"]
    aggregate = str(jobs["backend-tests"]["steps"][0]["run"])
    classifier_check = aggregate.index(
        'for value in "$DOCS_ONLY" "$RUN_DOCS" "$RUN_BACKEND" '
    )
    release_check = aggregate.index(
        'if [[ "$RUN_RELEASE" == true && "$RELEASE_INVARIANTS" != success ]]'
    )
    mac_check = aggregate.index(
        'if [[ "$RUN_MAC" == true && "$MAC_BUILD" != success ]]'
    )
    type_drift_check = aggregate.index(
        'if [[ "$RUN_TYPE_DRIFT" == true && "$TYPE_DRIFT_RESULT" != success ]]'
    )
    frontend_check = aggregate.index(
        'if [[ "$RUN_FRONTEND" == true && "$FRONTEND_BUILD" != success ]]'
    )
    mobile_check = aggregate.index(
        'if [[ "$RUN_MOBILE" == true && "$MOBILE_TYPECHECK" != success ]]'
    )
    backend_skip = aggregate.index('if [[ "$RUN_BACKEND" != true ]]')
    assert classifier_check < release_check
    assert release_check < backend_skip
    assert mac_check < backend_skip
    assert type_drift_check < backend_skip
    assert frontend_check < backend_skip
    assert mobile_check < backend_skip

    mac_runs = _run_bodies(jobs["mac-build"])
    assert "/bin/bash --version" in mac_runs
    for script_path in (
        "apps/mac/scripts/package-app.sh",
        "apps/mac/scripts/release-dmg.sh",
        "scripts/mac-release-nginx-bootstrap.sh",
    ):
        assert script_path in mac_runs
    assert (
        "test_repository_trust_normalization_makes_tracked_seeds_"
        "readable_not_writable" in mac_runs
    )
    assert (
        "test_deactivation_proof_rejects_restart_of_only_celery_beat"
        in mac_runs
    )
    assert (
        "test_activation_restart_during_stability_window_recovers_to_guard"
        in mac_runs
    )
    assert (
        "test_release_rollback_restart_window_never_claims_success"
        in mac_runs
    )


def test_ci_classifies_changes_before_selecting_expensive_jobs():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    classify = jobs["classify-changes"]
    outputs = classify["outputs"]
    runs = _run_bodies(classify)

    for output in (
        "docs_only",
        "run_docs",
        "run_backend",
        "run_frontend",
        "run_mobile",
        "run_mac",
        "run_type_drift",
        "run_release",
        "full",
    ):
        assert output in outputs
        assert f"${{{{ steps.scope.outputs.{output} }}}}" == outputs[output]
    assert "scripts/ci_change_scope.py" in runs
    assert "github.event.before" in runs
    assert "github.event_name" in runs
    assert "--format github" in runs
    assert "git diff --name-status -z --find-renames" in runs
    assert "git diff --name-only" not in runs
    assert '--input-format name-status-z' in runs
    assert '> "$CHANGED_FILE"' in runs
    assert 'CHANGED_FILES="$(' not in runs
    assert "expected_keys" in runs
    assert "critical_change" in runs
    assert 'path.startswith((".github/", "scripts/"))' in runs
    assert 'path == "deploy.sh"' in runs
    assert 'values["full"] is not True' in runs


def test_classifier_guard_dynamically_rejects_false_scope_for_workflow_change(
    tmp_path: Path,
):
    false_scope = "\n".join(
        f"{name}=false"
        for name in (
            "docs_only",
            "run_docs",
            "run_backend",
            "run_frontend",
            "run_mobile",
            "run_mac",
            "run_type_drift",
            "run_release",
            "full",
        )
    )
    changed_file = tmp_path / "changed.z"
    changed_file.write_bytes(b"R100\0.github/workflows/ci.yml\0docs/ci.yml\0")
    result = subprocess.run(
        ["python3", "-c", _classifier_guard_source()],
        env={
            **os.environ,
            "SCOPE_OUTPUT": false_scope,
            "CHANGED_FILE": str(changed_file),
            "EVENT_NAME": "push",
        },
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "independent full-suite rule" in result.stderr


def test_required_aggregate_rejects_missing_or_invalid_classifier_outputs():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    aggregate = str(workflow["jobs"]["backend-tests"]["steps"][0]["run"])

    valid = subprocess.run(
        ["bash", "-c", aggregate],
        env=_aggregate_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr

    for name, value in (("RUN_RELEASE", ""), ("RUN_MOBILE", "maybe"), ("FULL", "1")):
        rejected = subprocess.run(
            ["bash", "-c", aggregate],
            env=_aggregate_environment(**{name: value}),
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected.returncode != 0, (name, value, rejected.stdout)
        assert "invalid or missing classifier output" in rejected.stderr


def test_required_aggregate_rejects_selected_frontend_or_mobile_failure():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    aggregate = str(workflow["jobs"]["backend-tests"]["steps"][0]["run"])

    for selected, result in (
        ({"RUN_FRONTEND": "true"}, {"FRONTEND_BUILD": "failure"}),
        ({"RUN_MOBILE": "true"}, {"MOBILE_TYPECHECK": "cancelled"}),
    ):
        rejected = subprocess.run(
            ["bash", "-c", aggregate],
            env=_aggregate_environment(**selected, **result),
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected.returncode != 0, (selected, result, rejected.stdout)


def test_docs_quality_is_mandatory_and_owns_lightweight_doc_gates():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    docs_job = jobs["docs-quality"]
    docs_runs = _run_bodies(docs_job)
    backend_runs = _run_bodies(jobs["backend-quality"])

    assert docs_job["needs"] == "classify-changes"
    assert "check_secret_leaks.py" in docs_runs
    assert "check_system_map.py" in docs_runs
    assert "check_dossier_consistency.py" in docs_runs
    assert "scripts/test_ci_change_scope.py" in docs_runs
    assert "scripts/test_release_ci_contract.py" in docs_runs
    assert "pytest==9.1.1" in docs_runs
    assert "PyYAML==6.0.3" in docs_runs
    assert "check_secret_leaks.py" not in backend_runs
    assert "check_system_map.py" not in backend_runs
    assert "check_dossier_consistency.py" not in backend_runs


def test_runtime_jobs_are_conditioned_on_conservative_scope_outputs():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    expected = {
        "backend-test-shards": "run_backend",
        "backend-quality": "run_backend",
        "release-invariants": "run_release",
        "agent-runtime-postgres": "run_backend",
        "frontend-build": "run_frontend",
        "mobile-typecheck": "run_mobile",
        "mac-build": "run_mac",
        "type-drift": "run_type_drift",
    }

    for job_name, output in expected.items():
        job = jobs[job_name]
        needs = job["needs"]
        assert "classify-changes" in ([needs] if isinstance(needs, str) else needs)
        assert f"needs.classify-changes.outputs.{output} == 'true'" in job["if"]


def test_backend_aggregate_passes_explicit_docs_only_skip_but_not_red_backend():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["backend-tests"]
    needs = job["needs"]
    run = _run_bodies(job)

    assert "classify-changes" in needs
    assert "docs-quality" in needs
    assert "RUN_BACKEND" in run
    assert "DOCS_QUALITY" in run
    assert "backend scope skipped by classifier" in run
    assert "TEST_SHARDS" in run
    assert "QUALITY_GATES" in run
    assert "RUNTIME_POSTGRES" in run


def test_slow_shard_replacements_cover_predecessor_scopes_exactly_once():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    entries = {
        entry["label"]: entry
        for entry in workflow["jobs"]["backend-test-shards"]["strategy"]["matrix"][
            "include"
        ]
    }
    backend = ROOT / "backend"

    def expand(labels: tuple[str, ...]) -> list[Path]:
        files: list[Path] = []
        for label in labels:
            for pattern in entries[label]["paths"].split():
                files.extend(Path(path) for path in glob(str(backend / pattern)))
        return files

    executor_parts = expand(
        (
            "agent-executor-a-d",
            "agent-executor-error-fast",
            "agent-executor-food",
            "agent-executor-g-h",
        )
    )
    executor_original = {
        Path(path)
        for path in glob(str(backend / "tests/test_agent_executor_[a-h]*.py"))
    }
    assert set(executor_parts) == executor_original
    assert len(executor_parts) == len(set(executor_parts))

    qr_parts = expand(
        (
            "q",
            "r-record-registration",
            "r-runtime-recovery",
            "r-other",
        )
    )
    qr_original = {
        Path(path) for path in glob(str(backend / "tests/test_[q-r]*.py"))
    }
    assert set(qr_parts) == qr_original
    assert len(qr_parts) == len(set(qr_parts))

    assert "agent-executor-a-h" not in entries
    assert "q-r" not in entries


def test_postgres_gate_runs_invitation_migration_and_merge_concurrency_without_skip():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["agent-runtime-postgres"]
    postgres_step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Run Runtime and medication PostgreSQL semantics"
    )
    run = str(postgres_step["run"])
    env = postgres_step["env"]

    assert env["TEST_DATABASE_URL"].startswith("postgresql://")
    assert env["REGISTRATION_INVITATION_ROLLOUT_ENABLED"] == "true"
    assert env["REGISTRATION_INVITATION_ENFORCEMENT_ENABLED"] == "true"
    assert (
        "tests/test_user_merge_security.py::"
        "test_postgres_concurrent_same_source_merge_has_one_winner_and_no_data_loss"
        in run
    )
    assert (
        "tests/test_registration_invitation_migration_postgres.py::"
        "test_postgres_managed_migration_is_replay_safe_and_enforces_contract"
        in run
    )
    assert "tests/test_invited_phone_registration_postgres.py" in run
    assert (
        "tests/test_registration_invitation_service.py::"
        "test_postgres_concurrent_grant_consumption_has_exactly_one_winner"
        in run
    )
