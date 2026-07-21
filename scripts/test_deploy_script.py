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


def test_deploy_requires_main_and_pushes_exact_head_to_origin_main():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'CURRENT_BRANCH="$(git branch --show-current)"' in script
    assert 'CURRENT_BRANCH" != "main"' in script
    assert "git push origin HEAD:main" in script
    assert "git ls-remote origin refs/heads/main" in script


def test_remote_checkout_and_post_deploy_revision_match_expected_sha():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "DEPLOY_EXPECTED_SHA" in script
    assert "verify_deployed_revision" in script
    assert "git rev-parse HEAD" in script
    assert "远端部署版本不匹配" in script


def test_automatic_rollback_uses_verified_release_runner_and_propagates_failure():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    rollback_start = script.index("rollback_deploy() {")
    rollback_end = script.index("# 部署后验证", rollback_start)
    rollback_body = script[rollback_start:rollback_end]

    assert "rollback_release.sh" in rollback_body
    assert "if ! ssh" in rollback_body
    assert "return 1" in rollback_body
    assert "git checkout $ROLLBACK_COMMIT -- ." not in rollback_body


def test_deploy_does_not_claim_services_are_blocked_when_rollback_fails():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "服务保持阻断状态" not in script
    assert "无法证明服务已停止" in script
