import hashlib
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o100)


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


def test_plain_ssh_write_failures_preserve_server_lease_for_reconciliation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    for function_name, next_marker in (
        ("backup_database() {", "# 记录当前 commit"),
        ("backup_remote_env() {", "upload_backend_env_file() {"),
        ("restart_frontend_service() {", "# 推送代码到 GitHub"),
        ("deploy_frontend() {", "validate_runtime_only_kb_staging() {"),
    ):
        start = script.index(function_name)
        end = script.index(next_marker, start)
        body = script[start:end]
        assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body


def test_release_cleanup_abandons_server_lease_on_hup_int_and_term():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("install_release_cleanup_traps() {")
    end = script.index("acquire_remote_release_lock() {", start)
    body = script[start:end]

    assert "abandon_remote_release_lock 129" in body
    assert "abandon_remote_release_lock 130" in body
    assert "abandon_remote_release_lock 143" in body


def test_env_sync_uses_external_backup_root_and_mode_0600():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'REMOTE_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"' in script
    assert 'ENV_BACKUP_DIR="$REMOTE_BACKUP_ROOT/env"' in script
    assert 'cp -p .env "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"' in script
    assert 'install -o root -g health-app -m 0640' in script


def test_env_sync_stages_candidate_and_only_deactivation_atomically_installs_live_env():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    upload_start = script.index("upload_backend_env_file() {")
    upload_end = script.index("validate_env_sync_safety() {", upload_start)
    upload_body = script[upload_start:upload_end]
    transaction_start = script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    transaction_end = script.index(
        "prove_health_evidence_deactivated_state() {",
        transaction_start,
    )
    transaction_body = script[transaction_start:transaction_end]
    execution_body = transaction_body[
        transaction_body.index("mutation_started=1") :
    ]

    assert "REMOTE_BACKEND_ENV_CANDIDATE" in upload_body
    assert "sha256sum -c" in upload_body
    assert 'scp "$temp_env" "$SERVER:$REMOTE_PATH/backend/.env"' not in upload_body
    assert 'mv -fT "$candidate_install_tmp" "$target_env"' in transaction_body
    install = execution_body.index(
        'install -o root -g health-app -m 0640'
    )
    sync_tmp = execution_body.index('sync -f "$candidate_install_tmp"')
    rename = execution_body.index(
        'mv -fT "$candidate_install_tmp" "$target_env"'
    )
    sync_parent = execution_body.index('sync -f "$target_env_dir"')
    revoke = execution_body.index("remove_runtime_authorization")
    assert revoke < install < sync_tmp < rename < sync_parent


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

    assert "if ! rollback_output=$(ssh" in rollback_body
    assert "return 1" in rollback_body
    assert "git checkout $ROLLBACK_COMMIT -- ." not in rollback_body
    assert "kb_quarantine=passed" in rollback_body
    assert "REMOTE_ROLLBACK_RUNNER" in rollback_body
    assert "$REMOTE_PATH/backend/scripts/rollback_release.sh" not in rollback_body
    assert "rollback_output=" in rollback_body
    assert "ROLLBACK_OK commit=$ROLLBACK_COMMIT kb_quarantine=passed" in rollback_body


def test_release_preflight_stages_rollback_code_and_failed_release_manifest():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index("remote_git_sync_command()", stage_start)
    stage_body = script[stage_start:stage_end]

    assert "rollback_release.sh" in stage_body
    assert "verify_runtime_schema_compatibility.py" in stage_body
    assert "quarantine_runtime_only_kb.py" in stage_body
    assert "review_manifest.json" in stage_body
    assert "shasum -a 256" in stage_body
    assert "sha256sum" in stage_body
    assert "git cat-file -e" in stage_body
    assert "git show" in stage_body
    assert "staged.sha256" in stage_body


def test_deploy_does_not_claim_services_are_blocked_when_rollback_fails():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "服务保持阻断状态" not in script
    assert "无法证明服务已停止" in script


def test_all_mode_captures_old_backend_sha_before_frontend_checkout(tmp_path):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "deploy.events"
    old_sha = "1" * 40
    new_sha = "2" * 40
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_HEAD={old_sha}
acquire_release_lock() {{ :; }}
acquire_remote_release_lock() {{ :; }}
install_release_cleanup_traps() {{ :; }}
assert_remote_release_lock() {{ :; }}
confirm_ota_drift() {{ :; }}
push_code() {{
    DEPLOY_EXPECTED_SHA={new_sha}
    printf 'push\\n' >> "$DEPLOY_EVENT_LOG"
}}
ssh() {{ printf '%s\\n' "$REMOTE_HEAD"; }}
deploy_frontend() {{
    REMOTE_HEAD={new_sha}
    printf 'frontend-checkout:%s\\n' "$REMOTE_HEAD" >> "$DEPLOY_EVENT_LOG"
}}
deploy_backend() {{
    save_rollback_point
    printf 'backend-floor:%s\\n' "$ROLLBACK_COMMIT" >> "$DEPLOY_EVENT_LOG"
    REMOTE_HEAD={new_sha}
}}
check_status() {{ printf 'status\\n' >> "$DEPLOY_EVENT_LOG"; }}
main --all --yes
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "DEPLOY_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "push",
        f"backend-floor:{old_sha}",
        f"frontend-checkout:{new_sha}",
        "status",
    ]


def test_frontend_build_refuses_revision_mismatch_before_npm_or_pm2(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "frontend.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
assert_remote_release_lock_if_acquired() {{ :; }}
verify_deployed_revision() {{ return 1; }}
ssh() {{ printf 'ssh:%s\\n' "$*" >> "$FRONTEND_EVENT_LOG"; }}
if deploy_frontend; then exit 91; fi
test ! -e "$FRONTEND_EVENT_LOG"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FRONTEND_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not event_log.exists()


def test_frontend_build_same_sha_does_not_mutate_runtime_or_backend_services(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "frontend.events"
    durable = tmp_path / "enabled.env"
    durable_bytes = (
        b"# commit=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        b"# guard_sha256=" + b"b" * 64 + b"\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    durable.write_bytes(durable_bytes)
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
assert_remote_release_lock_if_acquired() {{ :; }}
verify_deployed_revision() {{
    printf 'revision\\n' >> "$FRONTEND_EVENT_LOG"
}}
ssh() {{
    printf 'ssh:%s\\n' "$*" >> "$FRONTEND_EVENT_LOG"
    case "$*" in
      *systemctl*|*health-backend*|*celery*) return 92 ;;
    esac
}}
deploy_frontend
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FRONTEND_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert durable.read_bytes() == durable_bytes
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events[0] == "revision"
    assert events[-1] == "revision"
    assert len([event for event in events if event.startswith("ssh:")]) == 1
    assert all("systemctl" not in event for event in events)
    assert all("health-backend" not in event for event in events)
    assert all("celery" not in event for event in events)


def test_env_candidate_upload_interruption_never_touches_live_env(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    live_env = backend / ".env"
    live_bytes = (
        b"SECRET_VALUE=production-secret\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    live_env.write_bytes(live_bytes)
    stage = tmp_path / "stage"
    stage.mkdir(mode=0o700)
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    token = "env-stage-owner"
    (release_lock / "token").write_text(token + "\n", encoding="utf-8")
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "SECRET_VALUE=new-secret\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "scp",
        """#!/bin/bash
set -euo pipefail
source="$1"
destination="${2#*:}"
if [ "${FAKE_SCP_INTERRUPT:-0}" = "1" ]; then
  /usr/bin/head -c 8 "$source" > "$destination"
  exit 74
fi
/bin/cp "$source" "$destination"
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
source="${@: -2:1}"
target="${@: -1}"
/bin/cp "$source" "$target"
chmod 0400 "$target"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
if [ -d "$target" ]; then
  printf 'root:root:700\n'
else
  printf 'root:root:400\n'
fi
""",
    )
    _write_executable(
        bin_dir / "sync",
        "#!/bin/bash\nset -euo pipefail\ntest \"$1\" = -f\ntest -e \"$2\"\n",
    )
    _write_executable(
        bin_dir / "mv",
        "#!/bin/bash\nset -euo pipefail\ntest \"$1\" = -fT\n/bin/mv \"$2\" \"$3\"\n",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_BACKUP_PREFLIGHT_DIR={stage}
REMOTE_BACKEND_ENV_CANDIDATE={stage / "backend.env.candidate"}
REMOTE_RELEASE_LOCK_DIR={release_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
ssh() {{ shift; "$@"; }}
upload_backend_env_file "$ENV_FILE"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_ENV_FILE": str(deploy_env),
            "FAKE_SCP_INTERRUPT": "1",
        },
    )

    assert result.returncode != 0
    assert live_env.read_bytes() == live_bytes
    assert not (stage / "backend.env.candidate").exists()


def test_backend_deploy_establishes_guard_floor_before_system_kb_activation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    restart = deploy_body.index("systemctl restart health-backend")
    first_health = deploy_body.index("if ! verify_deployment; then")
    first_revision = deploy_body.index("verify_deployed_revision", first_health)
    guard_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "guard"',
        first_health,
    )
    guard_floor = deploy_body.index("ROLLBACK_COMMIT=\"$DEPLOY_EXPECTED_SHA\"")
    phase0_seed = deploy_body.index("python scripts/seed_system_kb_phase0.py")
    v2_import = deploy_body.index("python scripts/import_system_kb_v2_artifacts.py")
    second_health = deploy_body.index(
        "if ! verify_deployment; then",
        first_health + 1,
    )

    staged_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "staged"',
        second_health,
    )

    assert (
        restart
        < first_health
        < first_revision
        < guard_contract
        < guard_floor
        < phase0_seed
        < v2_import
        < second_health
        < staged_contract
    )


def test_backend_deploy_requires_runtime_only_feature_flag_off_during_guard_rollout():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    validator_start = script.index("validate_runtime_only_kb_staging() {")
    validator_end = script.index("deploy_backend() {", validator_start)
    validator_body = script[validator_start:validator_end]
    deploy_body = script[validator_end:]

    assert "review_manifest.json" in validator_body
    assert "generic_serving_allowed" in validator_body
    assert "HEALTH_EVIDENCE_RUNTIME_ENABLED" in validator_body
    assert "false" in validator_body
    assert 'pack.get("serving_allowed") is True' not in validator_body
    assert deploy_body.index("validate_runtime_only_kb_staging") < deploy_body.index(
        "sync_env"
    )


def test_backend_revokes_durable_runtime_before_checkout_or_kb_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    sync_guard = deploy_body.index("sync_env")
    revoke = deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    checkout = deploy_body.index("$remote_git_sync")
    migration = deploy_body.index("python scripts/apply_managed_migrations.py")
    kb_import = deploy_body.index(
        "python scripts/import_system_kb_v2_artifacts.py"
    )

    assert sync_guard < revoke < checkout < migration < kb_import

    deactivation_start = script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    deactivation_end = script.index(
        "prove_health_evidence_deactivated_state() {", deactivation_start
    )
    deactivation = script[deactivation_start:deactivation_end]
    execution = deactivation[deactivation.index("mutation_started=1") :]
    assert "enabled.env" in deactivation
    assert "sync -f" in deactivation
    assert "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" in deactivation
    assert "cgroup.procs" in deactivation
    assert "health-backend.socket" in deactivation
    assert 'systemctl stop "$unit"' in deactivation
    assert 'systemctl start "$unit"' in deactivation
    assert (
        "stop_and_prove_services_inactive() {"
        in deactivation
    )
    assert "verify_services_inactive" in deactivation
    stop = execution.index("stop_and_prove_services_inactive")
    install = execution.index(
        'install -o root -g health-app -m 0640'
    )
    revoke = execution.index("remove_runtime_authorization")
    start = execution.index('systemctl start "$unit"')
    process_false = execution.index("verify_process_environment_false")
    assert stop < revoke < install < start < process_false


def test_deactivation_delegates_before_remote_stage_or_live_mutation_and_proves_last_restart():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    sync_start = script.index("sync_env() {")
    sync_end = script.index("# 去激活事务", sync_start)
    sync_body = script[sync_start:sync_end]
    orchestration_start = script.index(
        "deactivate_health_evidence_runtime_before_mutation() {"
    )
    orchestration_end = script.index("# 部署后端", orchestration_start)
    orchestration = script[orchestration_start:orchestration_end]
    deploy_body = script[script.index("deploy_backend() {") :]

    assert sync_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < sync_body.index(
        "upload_backend_env_file"
    )
    assert orchestration.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        orchestration.index("run_health_evidence_deactivation_transaction")
    )
    assert orchestration.index(
        "run_health_evidence_deactivation_transaction"
    ) < orchestration.index("prove_health_evidence_deactivated_state")
    assert orchestration.index("prove_health_evidence_deactivated_state") < (
        orchestration.index("_REMOTE_RELEASE_LOCK_DELEGATED=0")
    )
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in orchestration

    last_backend_restart = deploy_body.index(
        "systemctl restart health-backend"
    )
    assert last_backend_restart < deploy_body.index(
        "prove_health_evidence_runtime_process_flag false",
        last_backend_restart,
    )


def test_guard_kb_and_rollback_never_overlap_unknown_remote_transactions():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {") :]
    rollback_start = script.index("rollback_deploy() {")
    rollback_end = script.index("# 部署后验证", rollback_start)
    rollback_body = script[rollback_start:rollback_end]
    guard_start = deploy_body.index("# 3. Guard phase")
    kb_start = deploy_body.index("# 5. KB activation phase")
    guard_body = deploy_body[guard_start:kb_start]
    kb_body = deploy_body[kb_start:]

    assert guard_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        guard_body.index("ssh $SERVER")
    )
    assert "远端事务结果不明确" in guard_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in guard_body
    assert kb_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        kb_body.index("ssh $SERVER")
    )
    assert "不与可能仍运行的 importer 并发回滚" in kb_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in kb_body
    assert rollback_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        rollback_body.index("ssh")
    )
    assert rollback_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0") > (
        rollback_body.index("ROLLBACK_OK")
    )


def test_generic_env_and_restart_revoke_durable_runtime_before_restart():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    env_start = main_body.index('"env")')
    env_end = main_body.index('"health-evidence")', env_start)
    env_body = main_body[env_start:env_end]
    restart_start = main_body.index('"restart")', env_end)
    restart_end = main_body.index('"push")', restart_start)
    restart_body = main_body[restart_start:restart_end]

    assert env_body.index("sync_env") < env_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    assert "restart_services" not in env_body
    assert restart_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    ) < restart_body.index("restart_frontend_service")


def test_frontend_only_never_mutates_backend_checkout_or_runtime_authorization():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    frontend_start = main_body.index('"frontend")')
    frontend_end = main_body.index('"backend")', frontend_start)
    frontend_body = main_body[frontend_start:frontend_end]
    deploy_start = script.index("deploy_frontend() {")
    deploy_end = script.index("validate_runtime_only_kb_staging() {", deploy_start)
    deploy_body = script[deploy_start:deploy_end]

    assert "deactivate_health_evidence_runtime_before_mutation" not in frontend_body
    assert deploy_body.count("verify_deployed_revision") == 2
    assert deploy_body.index("verify_deployed_revision") < deploy_body.index(
        "npm ci"
    )
    assert deploy_body.count(
        "git status --porcelain --untracked-files=all"
    ) == 2
    assert "remote_git_sync" not in deploy_body
    assert "git checkout" not in deploy_body


def test_post_import_staged_contract_failure_uses_quarantine_rollback():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {"):]
    contract_call = deploy_body.index(
        'verify_runtime_only_kb_contract "staged"'
    )
    rollback_call = deploy_body.index("rollback_deploy", contract_call)
    exit_call = deploy_body.index("exit 1", rollback_call)

    assert contract_call < rollback_call < exit_call


def test_health_evidence_activation_is_delegated_to_persistent_systemd_transaction():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("activate_health_evidence_runtime() {")
    end = script.index("# 查看服务状态", start)
    body = script[start:end]
    runner_start = script.index("run_health_evidence_activation_unit() {")
    runner_end = script.index(
        "prove_health_evidence_activation_state() {", runner_start
    )
    runner_body = script[runner_start:runner_end]

    precheck = body.index('verify_runtime_only_kb_contract "staged"')
    stage_delegated = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1", precheck)
    stage = body.index("stage_health_evidence_activation_artifacts")
    stage_clear = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0", stage)
    launch_delegated = body.index(
        "_REMOTE_RELEASE_LOCK_DELEGATED=1", stage_clear
    )
    launch = body.index("run_health_evidence_activation_unit")
    deadman = runner_body.index("ExecStopPost")
    recover_mode = runner_body.index("--recover-if-unverified")

    assert (
        precheck
        < stage_delegated
        < stage
        < stage_clear
        < launch_delegated
        < launch
    )
    assert deadman >= 0
    assert recover_mode >= 0
    assert "systemd-run" in runner_body
    assert "require_health_evidence_flag_value true" in body
    assert "sync_env" not in body
    assert "upload_backend_env_file" not in body
    assert "restart_health_runtime_services" not in body
    assert 'HEALTH_EVIDENCE_ACTIVATION_OK commit=$DEPLOY_EXPECTED_SHA' in body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body


def test_activation_stage_hashes_runner_candidate_guard_and_keeps_marker_outside():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("stage_health_evidence_activation_artifacts() (")
    end = script.index("activate_health_evidence_runtime() {", start)
    body = script[start:end]

    assert "activate_health_evidence_runtime.sh" in body
    assert "candidate.env" in body
    assert "guard.env" in body
    assert "staged.sha256" in body
    assert "sha256sum" in body
    assert "require_health_evidence_flag_value false" in body
    assert "require_health_evidence_flag_value true" in body
    assert "REMOTE_ACTIVATION_SUCCESS_MARKER" in body
    assert "dirname" not in body or "REMOTE_BACKUP_PREFLIGHT_DIR" in body


def test_activation_proof_uses_durable_authorization_and_real_process_flags():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_services_inactive() {", start
    )
    proof = script[start:end]

    assert "REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" in proof
    assert "guard_sha256" in proof
    assert "cgroup.procs" in proof
    assert "verify_process_environment" in proof
    assert 'HEALTH_EVIDENCE_RUNTIME_ENABLED=true' in proof
    assert 'flag_is_exact "$repo/backend/.env" false' in proof
    assert 'cmp -s "$guard_env" "$repo/backend/.env"' in proof
    assert 'cmp -s "$candidate_env" "$repo/backend/.env"' not in proof


def test_release_preflight_hashes_activation_runner_for_rollback_floor():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index("remote_git_sync_command()", stage_start)
    stage_body = script[stage_start:stage_end]
    rollback = (
        ROOT / "backend/scripts/rollback_release.sh"
    ).read_text(encoding="utf-8")

    assert "activate_health_evidence_runtime.sh" in stage_body
    assert "activate_health_evidence_runtime.sh" in rollback


def test_cli_has_dedicated_health_evidence_activation_mode():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "--activate-health-evidence" in script
    assert 'DEPLOY_MODE="health-evidence"' in script
    assert "activate_health_evidence_runtime" in script


def test_health_evidence_flag_parser_only_accepts_one_canonical_assignment(
    tmp_path,
):
    cases = (
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=false", "false", True),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=true", "true", True),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=1", "false", False),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=yes", "false", False),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=on", "false", False),
        ('HEALTH_EVIDENCE_RUNTIME_ENABLED="true"', "false", False),
        ("export HEALTH_EVIDENCE_RUNTIME_ENABLED=true", "false", False),
        (
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true",
            "false",
            False,
        ),
    )
    for index, (assignments, expected, allowed) in enumerate(cases):
        env_file = tmp_path / f"deploy-{index}.env"
        env_file.write_text(
            "\n".join(
                (
                    "DEPLOY_SERVER=fake-server",
                    "DEPLOY_PATH=/tmp/fake-health-app",
                    assignments,
                )
            )
            + "\n",
            encoding="utf-8",
        )
        harness = f"""
source {DEPLOY_SCRIPT!s}
require_health_evidence_flag_value {expected}
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )
        assert (result.returncode == 0) is allowed, (
            assignments,
            result.stdout,
            result.stderr,
        )


def test_generic_env_and_restart_paths_require_canonical_false():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_start = script.index("main() {")
    main_body = script[main_start:]

    env_start = main_body.index('"env")')
    env_end = main_body.index('"health-evidence")', env_start)
    restart_start = main_body.index('"restart")', env_end)
    restart_end = main_body.index('"push")', restart_start)
    assert "require_health_evidence_flag_value false" in main_body[env_start:env_end]
    assert (
        "require_health_evidence_flag_value false"
        in main_body[restart_start:restart_end]
    )


def test_mutating_deploy_modes_acquire_server_release_lease():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    acquire = main_body.index('acquire_remote_release_lock "deploy:${DEPLOY_MODE}"')
    execute = main_body.index("# 执行对应操作")

    assert acquire < execute
    assert '"all"|"frontend"|"backend"|"env"|"health-evidence"|"restart"' in main_body
    assert "assert_remote_release_lock" in main_body[acquire:execute]
    assert "push" not in main_body[acquire - 100 : acquire]


def test_server_release_lease_rejects_second_owner_and_only_owner_can_release(
    tmp_path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    remote_lock = tmp_path / "remote-release.lock"
    harness = f"""
source {DEPLOY_SCRIPT!s}
ssh() {{ shift; "$@"; }}
REVA_RELEASE_LOCK_TOKEN=owner-one
acquire_remote_release_lock first
first_token="$REMOTE_RELEASE_LOCK_TOKEN"
_REMOTE_RELEASE_LOCK_ACQUIRED=0
REMOTE_RELEASE_LOCK_TOKEN=
REVA_RELEASE_LOCK_TOKEN=owner-two
if acquire_remote_release_lock second; then
    exit 91
fi
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=wrong-owner
if release_remote_release_lock; then
    exit 92
fi
test -d "$REMOTE_RELEASE_LOCK_DIR"
REMOTE_RELEASE_LOCK_TOKEN="$first_token"
release_remote_release_lock
test ! -e "$REMOTE_RELEASE_LOCK_DIR"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "REMOTE_RELEASE_LOCK_DIR": str(remote_lock),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def _run_deactivation_orchestrator_harness(
    tmp_path: Path,
    *,
    transaction_ok: bool,
    proof_ok: bool,
    inactive_ok: bool,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / "deploy-deactivation.env"
    event_log = tmp_path / "deactivation.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=test-owner
assert_remote_release_lock() {{ :; }}
run_health_evidence_deactivation_transaction() {{
    printf 'run:delegated=%s\\n' "$_REMOTE_RELEASE_LOCK_DELEGATED" \
        >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_TRANSACTION_OK" = "1" ]
}}
prove_health_evidence_deactivated_state() {{
    printf 'prove\\n' >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_PROOF_OK" = "1" ]
}}
prove_health_evidence_services_inactive() {{
    printf 'inactive-proof\\n' >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_INACTIVE_OK" = "1" ]
}}
deactivate_health_evidence_runtime_before_mutation
deactivation_rc=$?
printf 'final:rc=%s:delegated=%s:abandoned=%s\\n' \
    "$deactivation_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$DEACTIVATION_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "DEACTIVATION_EVENT_LOG": str(event_log),
            "DEACTIVATION_TRANSACTION_OK": "1" if transaction_ok else "0",
            "DEACTIVATION_PROOF_OK": "1" if proof_ok else "0",
            "DEACTIVATION_INACTIVE_OK": "1" if inactive_ok else "0",
        },
    )
    return result, event_log.read_text(encoding="utf-8").splitlines()


def test_deactivation_orchestrator_clears_delegation_only_after_exact_proof(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=True,
        proof_ok=True,
        inactive_ok=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_deactivation_orchestrator_rejects_lost_ssh_even_if_state_proof_passes(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=False,
        proof_ok=True,
        inactive_ok=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "inactive-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_deactivation_orchestrator_preserves_lease_and_stage_on_unknown_result(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=False,
        proof_ok=False,
        inactive_ok=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "inactive-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def _run_deactivation_transaction_fixture(
    tmp_path: Path,
    *,
    fail_candidate_sync: bool,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    repo = tmp_path / "release"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    old_env = backend / ".env"
    old_env.write_text(
        "CONFIG_REVISION=old\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    stage = tmp_path / "stage"
    stage.mkdir()
    candidate = stage / "backend.env.candidate"
    candidate.write_text(
        "CONFIG_REVISION=new\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    candidate.chmod(0o400)
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    durable = tmp_path / "durable"
    durable.mkdir()
    (durable / "enabled.env").write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    runtime_state = tmp_path / "runtime-state"
    runtime_state.mkdir()
    (runtime_state / "enabled.env").write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    systemd_runtime = tmp_path / "systemd-runtime"
    systemd_runtime.mkdir()
    for unit in (
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        unit_dir = systemd_runtime / f"{unit}.d"
        unit_dir.mkdir()
        (unit_dir / "90-reva-health-evidence-activation.conf").write_text(
            "[Service]\nEnvironmentFile=/tmp/runtime-enabled.env\n",
            encoding="utf-8",
        )
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    token = "deactivation-owner"
    (release_lock / "token").write_text(token + "\n", encoding="utf-8")
    service_state = tmp_path / "service-state"
    service_state.mkdir()
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    unit_pids = {
        "health-backend": 3101,
        "celery-worker": 3201,
        "celery-beat": 3301,
    }
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        (service_state / f"{unit}.state").write_text(
            "active\n", encoding="utf-8"
        )
    for unit, pid in unit_pids.items():
        group = cgroup_root / "system.slice" / f"{unit}.service"
        group.mkdir(parents=True)
        (group / "cgroup.procs").write_text(f"{pid}\n", encoding="utf-8")
        process = proc_root / str(pid)
        process.mkdir()
        (process / "environ").write_bytes(
            b"PATH=/usr/bin\0HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0"
        )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    event_log = tmp_path / "deactivation-transaction.events"
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/bash
set -euo pipefail
normalize() { printf '%s' "${1%.service}"; }
state_file() { printf '%s/%s.state' "$FAKE_STATE_DIR" "$(normalize "$1")"; }
pid_for() {
  case "$(normalize "$1")" in
    health-backend) printf '3101' ;;
    celery-worker) printf '3201' ;;
    celery-beat) printf '3301' ;;
    *) printf '0' ;;
  esac
}
case "$1" in
  stop)
    unit="$2"
    printf 'stop:%s\n' "$unit" >> "$FAKE_EVENT_LOG"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  start)
    unit="$2"
    printf 'start:%s\n' "$unit" >> "$FAKE_EVENT_LOG"
    printf 'active\n' > "$(state_file "$unit")"
    pid="$(pid_for "$unit")"
    if [ "$pid" != "0" ]; then
      printf 'PATH=/usr/bin\\0HEALTH_EVIDENCE_RUNTIME_ENABLED=false\\0' \
        > "$FAKE_PROC_ROOT/$pid/environ"
    fi
    ;;
  show)
    unit="$2"
    case "$*" in
      *--property=ActiveState*) cat "$(state_file "$unit")" ;;
      *--property=MainPID*) pid_for "$unit"; printf '\n' ;;
      *--property=ControlGroup*)
        printf '/system.slice/%s.service\n' "$(normalize "$unit")"
        ;;
      *) exit 93 ;;
    esac
    ;;
  kill)
    unit="${@: -1}"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  daemon-reload) exit 0 ;;
  *) exit 92 ;;
esac
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
source="${@: -2:1}"
target="${@: -1}"
cp "$source" "$target"
chmod 0640 "$target"
printf 'install:%s\n' "$target" >> "$FAKE_EVENT_LOG"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
case "$target" in
  *backend.env.candidate) printf 'root:root:400\n' ;;
  */backend/.env|*/backend/.env.reva-release.tmp)
    printf 'root:health-app:640\n'
    ;;
  *) printf 'root:root:700\n' ;;
esac
""",
    )
    _write_executable(
        bin_dir / "sync",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-f"
if [ "${FAKE_FAIL_CANDIDATE_SYNC:-0}" = "1" ] &&
   [[ "$2" == *".env.reva-release.tmp" ]]; then
  exit 88
fi
test -e "$2"
printf 'sync:%s\n' "$2" >> "$FAKE_EVENT_LOG"
""",
    )
    _write_executable(
        bin_dir / "mv",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-fT"
/bin/mv "$2" "$3"
""",
    )
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_BACKEND_ENV_CANDIDATE={candidate}
REMOTE_BACKEND_ENV_CANDIDATE_SHA={candidate_hash}
REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR={durable}
REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR={runtime_state}
REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR={systemd_runtime}
REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT={cgroup_root}
REMOTE_HEALTH_EVIDENCE_PROC_ROOT={proc_root}
REMOTE_RELEASE_LOCK_DIR={release_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
ssh() {{ shift; "$@"; }}
run_health_evidence_deactivation_transaction
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_ENV_FILE": str(deploy_env),
            "FAKE_STATE_DIR": str(service_state),
            "FAKE_PROC_ROOT": str(proc_root),
            "FAKE_EVENT_LOG": str(event_log),
            "FAKE_FAIL_CANDIDATE_SYNC": (
                "1" if fail_candidate_sync else "0"
            ),
        },
    )
    return result, {
        "old_env": old_env,
        "candidate": candidate,
        "durable": durable,
        "runtime_state": runtime_state,
        "service_state": service_state,
        "proc_root": proc_root,
        "event_log": event_log,
    }


def test_deactivation_transaction_atomically_installs_then_proves_false(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert paths["old_env"].read_bytes() == paths["candidate"].read_bytes()
    assert not (paths["durable"] / "enabled.env").exists()
    assert not paths["runtime_state"].exists()
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "active"
    for pid in (3101, 3201, 3301):
        assert b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0" in (
            paths["proc_root"] / str(pid) / "environ"
        ).read_bytes()


def test_deactivation_sync_failure_keeps_old_env_and_contains_services(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=True,
    )

    assert result.returncode != 0
    assert paths["old_env"].read_text(encoding="utf-8").startswith(
        "CONFIG_REVISION=old\n"
    )
    assert not (paths["durable"] / "enabled.env").exists()
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"
    assert "start:" not in paths["event_log"].read_text(encoding="utf-8")


def _run_activation_orchestrator_harness(
    tmp_path: Path,
    *,
    proof_mode: str,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / f"deploy-{proof_mode}.env"
    event_log = tmp_path / f"activation-{proof_mode}.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=test-owner
verify_deployed_revision() {{ printf 'revision\\n' >> "$ACTIVATION_EVENT_LOG"; }}
verify_runtime_only_kb_contract() {{
    printf 'contract:%s\\n' "$1" >> "$ACTIVATION_EVENT_LOG"
}}
verify_systemd_activation_capability() {{
    printf 'systemd-capability\\n' >> "$ACTIVATION_EVENT_LOG"
}}
stage_health_evidence_activation_artifacts() {{
    printf 'stage\\n' >> "$ACTIVATION_EVENT_LOG"
}}
run_health_evidence_activation_unit() {{
    printf 'run:delegated=%s\\n' "$_REMOTE_RELEASE_LOCK_DELEGATED" \
        >> "$ACTIVATION_EVENT_LOG"
    [ "$ACTIVATION_PROOF_MODE" = "success" ]
}}
prove_health_evidence_activation_state() {{
    printf 'prove:%s\\n' "$1" >> "$ACTIVATION_EVENT_LOG"
    case "$ACTIVATION_PROOF_MODE:$1" in
        success:enabled|recovered:staged) return 0 ;;
        *) return 1 ;;
    esac
}}
prove_health_evidence_services_inactive() {{
    printf 'containment-proof\\n' >> "$ACTIVATION_EVENT_LOG"
    return 1
}}
activate_health_evidence_runtime
activation_rc=$?
printf 'final:rc=%s:delegated=%s:abandoned=%s\\n' \
    "$activation_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$ACTIVATION_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "ACTIVATION_EVENT_LOG": str(event_log),
            "ACTIVATION_PROOF_MODE": proof_mode,
        },
    )
    events = event_log.read_text(encoding="utf-8").splitlines()
    return result, events


def test_activation_orchestrator_releases_delegation_only_after_exact_success(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="success",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_activation_orchestrator_accepts_failure_only_after_exact_guard_proof(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="recovered",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "prove:staged",
        "final:rc=1:delegated=0:abandoned=0",
    ]


def test_activation_orchestrator_preserves_stage_and_lease_on_unknown_result(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="unknown",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "prove:staged",
        "containment-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]
