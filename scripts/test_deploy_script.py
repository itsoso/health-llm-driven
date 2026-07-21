from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy.sh"


def test_backend_deploy_checks_health_before_skills_manifest():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    health_check = script.index("if ! verify_deployment; then")
    manifest_check = script.index("wait_for_agent_skills_manifest", health_check)

    assert health_check < manifest_check


def test_skills_manifest_check_uses_condition_wait_not_fixed_three_retries():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "wait_for_agent_skills_manifest" in script
    assert "for attempt in $(seq 1 12)" in script


def test_skills_manifest_check_does_not_embed_auth_token():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "Authorization: Bearer" not in script


def test_remote_sync_does_not_stash_untracked_runtime_files():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "git stash push -u" not in script
    assert "git stash push -m auto-deploy-stash" in script
    assert "auto-deploy-stash >/dev/null 2>&1 || true" not in script


def test_backup_and_health_score_failures_block_deploy():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    backup_start = script.index("backup_database() {")
    backup_end = script.index("# 记录当前 commit", backup_start)
    backup_body = script[backup_start:backup_end]
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "print_warning \"数据库备份失败" not in backup_body
    assert "return 1" in backup_body
    assert "健康度检查跳过" not in verify_body
    assert "健康度脚本无有效输出" in verify_body


def test_env_sync_uses_external_backup_root_and_mode_0600():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'REMOTE_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"' in script
    assert 'ENV_BACKUP_DIR="$REMOTE_BACKUP_ROOT/env"' in script
    assert 'cp -p .env "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"' in script
    assert 'chmod 600 \'$REMOTE_PATH/backend/.env\'' in script
