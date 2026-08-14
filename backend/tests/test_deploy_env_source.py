from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_uses_root_env_as_single_source():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()

    assert 'ENV_FILE="${DEPLOY_ENV_FILE:-$SCRIPT_DIR/.env}"' in deploy_script
    assert ".env-online" not in deploy_script


def test_operator_docs_do_not_point_deploys_at_env_online():
    docs = "\n".join(
        [
            (REPO_ROOT / "AGENTS.md").read_text(),
            (REPO_ROOT / "CLAUDE.md").read_text(),
        ]
    )

    assert ".env-online" not in docs


def test_gitignore_only_ignores_root_env_file():
    gitignore = (REPO_ROOT / ".gitignore").read_text().splitlines()

    assert ".env" in gitignore
    assert ".env-online" not in gitignore


def test_deploy_script_backs_up_remote_env_before_syncing():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()
    sync_start = deploy_script.index("sync_env() {")
    sync_end = deploy_script.index("# 去激活事务", sync_start)
    sync_env = deploy_script[sync_start:sync_end]
    upload_start = deploy_script.index("upload_backend_env_file() {")
    upload_end = deploy_script.index("validate_env_sync_safety() {", upload_start)
    upload_env = deploy_script[upload_start:upload_end]

    assert "backup_remote_env()" in deploy_script
    assert 'ENV_BACKUP_DIR="$REMOTE_BACKUP_ROOT/env"' in deploy_script
    assert 'cp -p .env "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"' in deploy_script
    assert sync_env.index("backup_remote_env") < sync_env.index(
        'upload_backend_env_file "$ENV_FILE"'
    )
    assert 'upload_path="${REMOTE_BACKEND_ENV_CANDIDATE}.upload"' in upload_env
    assert 'scp "$temp_env" "$SERVER:$upload_path"' in upload_env
    assert '"$REMOTE_BACKEND_ENV_CANDIDATE"' in upload_env


def test_deploy_bundle_is_token_bound_inside_the_root_only_release_stage():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()

    assert (
        'REMOTE_DEPLOY_BUNDLE="$REMOTE_BACKUP_PREFLIGHT_DIR/deploy.bundle"'
        in deploy_script
    )
    assert '"$SERVER:$REMOTE_DEPLOY_BUNDLE"' in deploy_script
    assert "git fetch '$REMOTE_DEPLOY_BUNDLE' HEAD" in deploy_script
    assert "git fetch $REMOTE_DEPLOY_BUNDLE HEAD" not in deploy_script
    assert "trap cleanup_remote_release_artifacts EXIT" in deploy_script
    assert "test ! -e '$REMOTE_DEPLOY_BUNDLE'" in deploy_script
    assert "test ! -L '$REMOTE_DEPLOY_BUNDLE'" in deploy_script
    assert "root:root:600:1" in deploy_script
    assert '"deploy.bundle"' in deploy_script
    assert 'REMOTE_DEPLOY_BUNDLE="/tmp/health-app-deploy-' not in deploy_script
    assert '"$SERVER:/tmp/health-app-deploy.bundle"' not in deploy_script


def test_backend_deploy_activates_kb_only_after_guard_restart_and_contract():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()
    deploy_start = deploy_script.index("deploy_backend() {")
    deploy_end = deploy_script.index("# 查看服务状态", deploy_start)
    deploy_backend = deploy_script[deploy_start:deploy_end]

    migrations = deploy_backend.index("python scripts/apply_managed_migrations.py")
    guard_restart = deploy_backend.index("systemctl restart health-backend")
    guard_contract = deploy_backend.index('verify_runtime_only_kb_contract "guard"')
    rollback_floor = deploy_backend.index('ROLLBACK_COMMIT="$DEPLOY_EXPECTED_SHA"')
    food_seed = deploy_backend.index("python scripts/seed_food_nutrition.py")
    phase0_seed = deploy_backend.index("python scripts/seed_system_kb_phase0.py")
    v2_import = deploy_backend.index("python scripts/import_system_kb_v2_artifacts.py")
    # A resumed, already-finalized transaction has an earlier read-only staged
    # contract recheck. This ordering assertion is specifically about the
    # post-import activation gate, so anchor the search after the importer.
    staged_contract = deploy_backend.index(
        'verify_runtime_only_kb_contract "staged"', v2_import
    )

    assert (
        migrations
        < guard_restart
        < guard_contract
        < rollback_floor
        < food_seed
        < phase0_seed
        < v2_import
        < staged_contract
    )


def test_env_only_deactivation_refreshes_and_proves_all_backend_processes_false():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()
    main_start = deploy_script.index("main() {")
    env_start = deploy_script.index('"env")', main_start)
    env_end = deploy_script.index(";;", env_start)
    env_branch = deploy_script[env_start:env_end]
    transaction_start = deploy_script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    transaction_end = deploy_script.index(
        "prove_health_evidence_deactivated_state() {", transaction_start
    )
    transaction = deploy_script[transaction_start:transaction_end]
    mutation = transaction[transaction.index("mutation_started=1") :]

    assert env_branch.index("sync_env") < env_branch.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    for unit in (
        "health-backend.socket",
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        assert unit in transaction
    assert (
        mutation.index("stop_and_prove_services_inactive")
        < mutation.index("remove_runtime_authorization")
        < mutation.index('systemctl start "$unit"')
        < mutation.index("verify_process_environment_false")
    )


def test_secret_management_docs_cover_remote_env_backup_and_long_term_plan():
    docs = (REPO_ROOT / "docs/ops/secrets-management.md").read_text()

    assert "/var/backups/health-app/env" in docs
    assert "newest 20" in docs
    assert "SOPS" in docs
    assert "1Password" in docs
    assert "production secret manager" in docs
