import shlex
from glob import glob
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PYTEST_SHARD_CATALOG = ROOT / ".github" / "ci" / "backend-pytest-shards.json"
RELEASE_TESTS = (
    "scripts/test_backup_security.py",
    "scripts/test_ci_change_scope.py",
    "scripts/test_deploy_script.py",
    "scripts/test_generate_api_types.py",
    "scripts/test_health_evidence_activation_runner.py",
    "scripts/test_release_lock.py",
    "scripts/test_release_rollback.py",
    "scripts/test_infrastructure_security.py",
    "scripts/test_mobile_fast_feedback_scripts.py",
    "scripts/test_runtime_state_release_transaction.py",
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


def test_ci_first_party_javascript_actions_use_node24_runtimes():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    expected_versions = {
        "actions/checkout": "v5",
        "actions/setup-python": "v6",
        "actions/setup-node": "v5",
        "actions/upload-artifact": "v6",
    }
    observed_versions = {action: set() for action in expected_versions}

    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            uses = str(step.get("uses") or "")
            action, separator, version = uses.partition("@")
            if separator and action in observed_versions:
                observed_versions[action].add(version)

    assert observed_versions == {
        action: {version} for action, version in expected_versions.items()
    }

    type_drift_node = next(
        step
        for step in workflow["jobs"]["type-drift"]["steps"]
        if str(step.get("uses") or "").startswith("actions/setup-node@")
    )
    assert type_drift_node["with"]["package-manager-cache"] is False


def test_dependency_heavy_python_jobs_share_the_builtin_pip_cache():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    for job_name in (
        "backend-test-shards",
        "backend-quality",
        "release-invariants",
        "agent-runtime-postgres",
        "type-drift",
    ):
        setup = next(
            step
            for step in jobs[job_name]["steps"]
            if str(step.get("uses") or "").startswith("actions/setup-python@")
        )
        assert setup["with"]["cache"] == "pip", job_name
        assert "backend/requirements.lock" in setup["with"][
            "cache-dependency-path"
        ], job_name


def test_ci_blocks_on_release_invariants_and_exercises_macos_bash3():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    release_job = jobs["release-invariants"]
    release_runs = _run_bodies(release_job)

    assert release_job["runs-on"] == "ubuntu-latest"
    for test_path in RELEASE_TESTS:
        assert test_path in release_runs

    release_needs = jobs["release-tests"]["needs"]
    assert "release-invariants" in release_needs
    assert (
        "RELEASE_INVARIANTS"
        in jobs["release-tests"]["steps"][0]["env"]
    )

    mac_runs = _run_bodies(jobs["mac-build"])
    assert "/bin/bash --version" in mac_runs
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
        "release_only",
        "full",
    ):
        assert output in outputs
        assert f"${{{{ steps.scope.outputs.{output} }}}}" == outputs[output]
    assert "scripts/ci_change_scope.py" in runs
    assert "github.event.before" in runs
    assert "github.event_name" in runs
    assert "--format github" in runs


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
    assert "check_secret_leaks.py" not in backend_runs
    assert "check_system_map.py" not in backend_runs
    assert "check_dossier_consistency.py" not in backend_runs


def test_docs_quality_runs_the_system_map_harness_in_isolation():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["docs-quality"]["steps"]
    install_step = next(
        step
        for step in steps
        if "scripts/system-map-requirements.txt" in str(step.get("run") or "")
    )
    install_command = str(install_step["run"])
    assert "pytest==9.1.1" in install_command

    harness_step = next(
        step
        for step in steps
        if "scripts/test_system_map_harness.py" in str(step.get("run") or "")
    )
    command = shlex.split(str(harness_step["run"]))
    assert command[:3] == ["python", "-m", "pytest"]
    assert command[command.index("-c") + 1] == "/dev/null"
    assert command[command.index("--rootdir") + 1] == "."
    assert "--noconftest" in command
    assert "-o" in command and "addopts=" in command
    assert "-p" in command and "no:cacheprovider" in command
    assert not any(argument.startswith("--cov") for argument in command)

    environment = harness_step["env"]
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["PYTEST_ADDOPTS"] == ""
    assert environment["PYTEST_PLUGINS"] == ""


def test_runtime_jobs_are_conditioned_on_conservative_scope_outputs():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    expected = {
        "backend-test-plan": "run_backend",
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
    assert "RELEASE_INVARIANTS" not in run


def test_release_aggregate_is_independent_from_backend_lane():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["release-tests"]
    needs = job["needs"]
    run = _run_bodies(job)

    assert "classify-changes" in needs
    assert "docs-quality" in needs
    assert "release-invariants" in needs
    assert "backend-test-shards" not in needs
    assert "RUN_RELEASE" in run
    assert "RELEASE_INVARIANTS" in run
    assert "release scope skipped by classifier" in run


def test_slow_shard_replacements_cover_predecessor_scopes_exactly_once():
    import json

    entries = {
        entry["label"]: {**entry, "paths": " ".join(entry["paths"])}
        for entry in json.loads(
            PYTEST_SHARD_CATALOG.read_text(encoding="utf-8")
        )["shards"]
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

    a_early_parts = expand(("a-action", "a-agenda", "a-early-rest"))
    a_early_original = {
        Path(path)
        for path in glob(str(backend / "tests/test_a*.py"))
        if not path.startswith(str(backend / "tests/test_agent_"))
        and Path(path).name != "test_app_store_demo_account.py"
        and not Path(path).name.startswith(
            (
                "test_ai",
                "test_air",
                "test_ambient",
                "test_anomaly",
                "test_answer",
                "test_api",
                "test_app_",
                "test_arbitration",
                "test_ask",
                "test_atomic",
                "test_auth",
            )
        )
    }
    assert set(a_early_parts) == a_early_original
    assert len(a_early_parts) == len(set(a_early_parts))

    d_parts = expand(("d-dedao", "d-diet", "d-data-device", "d-rest"))
    d_original = {Path(path) for path in glob(str(backend / "tests/test_d*.py"))}
    assert set(d_parts) == d_original
    assert len(d_parts) == len(set(d_parts))

    assert "agent-executor-a-h" not in entries
    assert "q-r" not in entries
    assert "a-early" not in entries
    assert "d" not in entries


def test_ci_uses_timing_balanced_workers_without_merging_pytest_processes():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    plan = jobs["backend-test-plan"]
    shards = jobs["backend-test-shards"]
    shard_runs = _run_bodies(shards)

    assert "build_ci_pytest_matrix.py" in _run_bodies(plan)
    assert "fromJson(needs.backend-test-plan.outputs.matrix)" in str(
        shards["strategy"]["matrix"]
    )
    assert "backend-test-plan" in shards["needs"]
    assert "run_ci_pytest_worker.py" in shard_runs
    assert "matrix.shards" in shard_runs
    assert shards["strategy"]["fail-fast"] is False


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
