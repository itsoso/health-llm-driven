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
