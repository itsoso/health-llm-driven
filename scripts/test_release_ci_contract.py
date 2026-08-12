from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_TESTS = (
    "scripts/test_deploy_script.py",
    "scripts/test_health_evidence_activation_runner.py",
    "scripts/test_release_lock.py",
    "scripts/test_release_rollback.py",
    "scripts/test_infrastructure_security.py",
    "scripts/test_runtime_state_release_transaction.py",
    "scripts/test_release_ci_contract.py",
)


def _run_bodies(job: dict) -> str:
    return "\n".join(
        str(step.get("run") or "")
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )


def test_ci_blocks_on_release_invariants_and_exercises_macos_bash3():
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    release_job = jobs["release-invariants"]
    release_runs = _run_bodies(release_job)

    assert release_job["runs-on"] == "ubuntu-latest"
    for test_path in RELEASE_TESTS:
        assert test_path in release_runs

    backend_needs = jobs["backend-tests"]["needs"]
    assert "release-invariants" in backend_needs
    assert (
        "RELEASE_INVARIANTS"
        in jobs["backend-tests"]["steps"][0]["env"]
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
