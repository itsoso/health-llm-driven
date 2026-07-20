from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_deploy_script_uses_root_env_as_single_source():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()

    assert 'ENV_FILE="$SCRIPT_DIR/.env"' in deploy_script
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

    assert "backup_remote_env()" in deploy_script
    assert "cp -p .env" in deploy_script
    assert ".env.backup.${BACKUP_TS}" in deploy_script
    assert deploy_script.index("backup_remote_env") < deploy_script.index("scp \"$TEMP_ENV\"")


def test_backend_deploy_seeds_curated_food_nutrition_before_restart():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()
    deploy_start = deploy_script.index("deploy_backend() {")
    deploy_end = deploy_script.index("# 查看服务状态", deploy_start)
    deploy_backend = deploy_script[deploy_start:deploy_end]

    migrations = deploy_backend.index("python scripts/apply_managed_migrations.py")
    food_seed = deploy_backend.index("python scripts/seed_food_nutrition.py")
    restart = deploy_backend.index("systemctl restart health-backend")

    assert migrations < food_seed < restart


def test_env_only_restart_refreshes_backend_and_celery_processes():
    deploy_script = (REPO_ROOT / "deploy.sh").read_text()
    restart_start = deploy_script.index("restart_services() {")
    restart_end = deploy_script.index("# 推送代码到 GitHub", restart_start)
    restart_services = deploy_script[restart_start:restart_end]

    assert "systemctl restart health-backend" in restart_services
    assert "systemctl restart celery-worker celery-beat" in restart_services


def test_secret_management_docs_cover_remote_env_backup_and_long_term_plan():
    docs = (REPO_ROOT / "docs/ops/secrets-management.md").read_text()

    assert ".env.backup.YYYYMMDD_HHMMSS" in docs
    assert "newest 20 backup files" in docs
    assert "SOPS" in docs
    assert "1Password" in docs
    assert "production secret manager" in docs
