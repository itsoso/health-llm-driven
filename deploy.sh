#!/bin/bash

# ===========================================
# 健康应用部署脚本
#
# 配置文件: .env (本地管理，不被 git 追踪)
# 服务器配置从 .env 读取
# ===========================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${DEPLOY_ENV_FILE:-$SCRIPT_DIR/.env}"
source "$SCRIPT_DIR/scripts/release_lock.sh"

# 检查 .env 文件是否存在
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}✗${NC} 错误: .env 文件不存在"
    echo "请创建 .env 文件并配置以下内容:"
    echo "  DEPLOY_SERVER=root@your-server-ip"
    echo "  DEPLOY_PATH=/opt/health-app"
    echo "  以及其他环境变量..."
    exit 1
fi

# 从 .env 读取服务器配置
SERVER=$(grep "^DEPLOY_SERVER=" "$ENV_FILE" | cut -d'=' -f2)
REMOTE_PATH=$(grep "^DEPLOY_PATH=" "$ENV_FILE" | cut -d'=' -f2)
REMOTE_DEPLOY_BUNDLE="/tmp/health-app-deploy-$$-$(date +%s).bundle"
REMOTE_BACKUP_PREFLIGHT_DIR="/tmp/health-app-backup-preflight-$$-$(date +%s)"
REMOTE_BACKUP_RUNNER="$REMOTE_BACKUP_PREFLIGHT_DIR/backup_db.sh"
REMOTE_ROLLBACK_RUNNER="$REMOTE_BACKUP_PREFLIGHT_DIR/rollback_release.sh"
REMOTE_ACTIVATION_RUNNER="$REMOTE_BACKUP_PREFLIGHT_DIR/activate_health_evidence_runtime.sh"
REMOTE_BACKEND_ENV_CANDIDATE="$REMOTE_BACKUP_PREFLIGHT_DIR/backend.env.candidate"
REMOTE_BACKEND_ENV_ROLLBACK="$REMOTE_BACKUP_PREFLIGHT_DIR/backend.env.rollback"
REMOTE_BACKEND_ENV_CANDIDATE_SHA=""
REMOTE_ACTIVATION_STATE_DIR="${REMOTE_BACKUP_PREFLIGHT_DIR}.activation-state"
REMOTE_ACTIVATION_SUCCESS_MARKER="$REMOTE_ACTIVATION_STATE_DIR/success"
REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR="${REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR:-/var/lib/reva-health-evidence-runtime}"
REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR="${REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR:-/run/reva-health-evidence-activation}"
REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR="${REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR:-/run/systemd/system}"
REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT="${REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT:-/sys/fs/cgroup}"
REMOTE_HEALTH_EVIDENCE_PROC_ROOT="${REMOTE_HEALTH_EVIDENCE_PROC_ROOT:-/proc}"
REMOTE_RUNTIME_STATE_RUNNER="$REMOTE_BACKUP_PREFLIGHT_DIR/runtime_state_release_transaction.py"
DEPLOY_EXPECTED_SHA=""
ROLLBACK_CANDIDATE_COMMIT=""
ROLLBACK_COMMIT=""
RUNTIME_STATE_RESUME_PHASE="NONE"
RUNTIME_STATE_RESUME_TARGET="none"
RUNTIME_STATE_ALREADY_FINALIZED=0
REMOTE_RELEASE_LOCK_DIR="${REMOTE_RELEASE_LOCK_DIR:-/var/lock/health-app-release}"
REMOTE_RELEASE_LOCK_TOKEN=""
_REMOTE_RELEASE_LOCK_ACQUIRED=0
_REMOTE_RELEASE_LOCK_DELEGATED=0
_REMOTE_RELEASE_LOCK_ABANDONED=0
_REMOTE_RELEASE_LOCK_ADOPTED=0

set_remote_backup_preflight_dir() {
    local stage_dir="$1"

    if [[ ! "$stage_dir" =~ ^/tmp/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*$ ]]; then
        print_error "远端发布 stage 路径不符合固定契约"
        return 1
    fi
    REMOTE_BACKUP_PREFLIGHT_DIR="$stage_dir"
    REMOTE_BACKUP_RUNNER="$stage_dir/backup_db.sh"
    REMOTE_ROLLBACK_RUNNER="$stage_dir/rollback_release.sh"
    REMOTE_ACTIVATION_RUNNER="$stage_dir/activate_health_evidence_runtime.sh"
    REMOTE_BACKEND_ENV_CANDIDATE="$stage_dir/backend.env.candidate"
    REMOTE_BACKEND_ENV_ROLLBACK="$stage_dir/backend.env.rollback"
    REMOTE_RUNTIME_STATE_RUNNER="$stage_dir/runtime_state_release_transaction.py"
    REMOTE_ACTIVATION_STATE_DIR="${stage_dir}.activation-state"
    REMOTE_ACTIVATION_SUCCESS_MARKER="$REMOTE_ACTIVATION_STATE_DIR/success"
}

# 验证必要配置
if [[ -z "$SERVER" || -z "$REMOTE_PATH" ]]; then
    echo -e "${RED}✗${NC} 错误: .env 中缺少必要配置"
    echo "请确保配置了 DEPLOY_SERVER 和 DEPLOY_PATH"
    exit 1
fi
if [[ ! "$SERVER" =~ ^[A-Za-z0-9._@:-]+$ ||
      ! "$REMOTE_PATH" =~ ^/[A-Za-z0-9._/-]+$ ||
      "$REMOTE_PATH" = "/" ||
      "$REMOTE_PATH" = *"/../"* ||
      "$REMOTE_PATH" = *"/.." ||
      "$REMOTE_PATH" = *"/./"* ||
      "$REMOTE_PATH" = *"/." ]]; then
    echo -e "${RED}✗${NC} 错误: DEPLOY_SERVER/DEPLOY_PATH 格式不安全"
    exit 1
fi

# 打印带颜色的消息
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

cleanup_remote_release_artifacts() {
    if [[ "${_REMOTE_RELEASE_LOCK_ABANDONED:-0}" != "1" &&
          "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "1" ]]; then
        ssh "$SERVER" \
            "rm -f '$REMOTE_DEPLOY_BUNDLE'; rm -rf '$REMOTE_BACKUP_PREFLIGHT_DIR' '$REMOTE_ACTIVATION_STATE_DIR'" \
            >/dev/null 2>&1 || true
        release_remote_release_lock || true
    fi
    release_release_lock
}

abandon_remote_release_lock() {
    local signal_exit="$1"
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    release_release_lock
    exit "$signal_exit"
}

install_release_cleanup_traps() {
    trap cleanup_remote_release_artifacts EXIT
    trap 'abandon_remote_release_lock 129' HUP
    trap 'abandon_remote_release_lock 130' INT
    trap 'abandon_remote_release_lock 143' TERM
}

arm_remote_release_cleanup_after_terminal_mode_success() {
    local mode="$1"

    case "$mode" in
        all|frontend|backend|env|health-evidence|restart) ;;
        *) return 0 ;;
    esac
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ]]; then
        print_error "terminal release mode 缺少远端发布锁"
        return 73
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "0" ]]; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "terminal release mode 仍有未协调的远端动作"
        return 73
    fi
    # Reaching this call means the selected mode returned only after its exact
    # terminal proof. This is the common adoption cleanup edge for frontend,
    # backend, env, restart, and controlled activation.
    _REMOTE_RELEASE_LOCK_ABANDONED=0
}

acquire_remote_release_lock() {
    local label="${1:-release}"
    local token
    local adopt="${REVA_RELEASE_LOCK_ADOPT:-0}"
    local lock_output
    local adopted_stage

    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" = "1" ]]; then
        return 0
    fi
    if [[ ! "$REMOTE_RELEASE_LOCK_DIR" =~ ^/[A-Za-z0-9._/-]+$ ||
          "$REMOTE_RELEASE_LOCK_DIR" = "/" ||
          "$REMOTE_RELEASE_LOCK_DIR" = *"/../"* ||
          "$REMOTE_RELEASE_LOCK_DIR" = *"/.." ||
          "$REMOTE_RELEASE_LOCK_DIR" = *"/./"* ||
          "$REMOTE_RELEASE_LOCK_DIR" = *"/." ]]; then
        print_error "远端发布锁路径不安全: $REMOTE_RELEASE_LOCK_DIR"
        return 70
    fi
    token="${REVA_RELEASE_LOCK_TOKEN:-$$-${RANDOM:-0}-$(date +%s)}"
    if ! [[ "$token" =~ ^[A-Za-z0-9._:-]+$ ]]; then
        print_error "远端发布锁 token 格式非法"
        return 70
    fi
    if [[ "$adopt" != "0" && "$adopt" != "1" ]]; then
        print_error "REVA_RELEASE_LOCK_ADOPT 只接受 0/1"
        return 70
    fi
    if [[ "$adopt" = "1" && -z "${REVA_RELEASE_LOCK_TOKEN:-}" ]]; then
        print_error "显式接管远端发布锁必须提供原 REVA_RELEASE_LOCK_TOKEN"
        return 70
    fi
    if ! lock_output=$(ssh "$SERVER" bash -s -- \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$token" \
        "$label" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$adopt" <<'REMOTE_RELEASE_LOCK'
set -euo pipefail
lock_dir="$1"
token="$2"
label="$3"
stage_dir="$4"
adopt="$5"
umask 077
if ! mkdir "$lock_dir" 2>/dev/null; then
    owner=$(cat "$lock_dir/label" 2>/dev/null || true)
    started=$(cat "$lock_dir/started_at" 2>/dev/null || true)
    if [ "$adopt" = "1" ]; then
        test -r "$lock_dir/token"
        test -r "$lock_dir/label"
        test -r "$lock_dir/stage"
        test "$(cat "$lock_dir/token")" = "$token"
        test "$(cat "$lock_dir/label")" = "$label"
        adopted_stage="$(cat "$lock_dir/stage")"
        [[ "$adopted_stage" =~ ^/tmp/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*$ ]]
        printf 'REMOTE_RELEASE_LOCK_ADOPTED stage=%s\n' "$adopted_stage"
        exit 0
    fi
    echo "remote release already active: label=${owner:-unknown} started=${started:-unknown}" >&2
    exit 73
fi
printf '%s\n' "$token" > "$lock_dir/token"
printf '%s\n' "$label" > "$lock_dir/label"
printf '%s\n' "$stage_dir" > "$lock_dir/stage"
date -u +%Y-%m-%dT%H:%M:%SZ > "$lock_dir/started_at"
printf 'REMOTE_RELEASE_LOCK_CREATED stage=%s\n' "$stage_dir"
REMOTE_RELEASE_LOCK
    ); then
        echo "$lock_output" >&2
        print_error "无法获取服务器发布锁"
        return 73
    fi
    if [[ "$adopt" = "1" ]]; then
        adopted_stage="$(
            printf '%s\n' "$lock_output" |
                awk '
                    /^REMOTE_RELEASE_LOCK_ADOPTED stage=\/tmp\/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*$/ {
                        matches += 1
                        value = $0
                        sub(/^REMOTE_RELEASE_LOCK_ADOPTED stage=/, "", value)
                    }
                    END {
                        if (matches != 1) exit 1
                        print value
                    }
                '
        )" || {
            print_error "远端发布锁接管缺少精确 stage 证明"
            return 73
        }
        set_remote_backup_preflight_dir "$adopted_stage"
        _REMOTE_RELEASE_LOCK_ADOPTED=1
        # Until durable status proves there is no active transaction (or a
        # terminal one has been safely reconciled), every early exit must
        # preserve the adopted owner's exact stage and lease.
        _REMOTE_RELEASE_LOCK_ABANDONED=1
    elif [[ "$lock_output" != "REMOTE_RELEASE_LOCK_CREATED stage=$REMOTE_BACKUP_PREFLIGHT_DIR" ]]; then
        print_error "远端发布锁创建缺少精确成功证明"
        return 73
    fi
    REMOTE_RELEASE_LOCK_TOKEN="$token"
    _REMOTE_RELEASE_LOCK_ACQUIRED=1
}

assert_remote_release_lock() {
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ||
          -z "$REMOTE_RELEASE_LOCK_TOKEN" ]]; then
        print_error "服务器发布锁未持有"
        return 73
    fi
    ssh "$SERVER" bash -s -- \
        "$REMOTE_RELEASE_LOCK_DIR" "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_RELEASE_ASSERT'
set -euo pipefail
lock_dir="$1"
expected="$2"
test -r "$lock_dir/token"
test "$(cat "$lock_dir/token")" = "$expected"
REMOTE_RELEASE_ASSERT
}

assert_remote_release_lock_if_acquired() {
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" = "1" ]]; then
        assert_remote_release_lock
    fi
}

release_remote_release_lock() {
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ]]; then
        return 0
    fi
    if ! ssh "$SERVER" bash -s -- \
        "$REMOTE_RELEASE_LOCK_DIR" "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_RELEASE_UNLOCK'
set -euo pipefail
lock_dir="$1"
expected="$2"
test -r "$lock_dir/token"
test "$(cat "$lock_dir/token")" = "$expected"
rm -f "$lock_dir/token" "$lock_dir/label" "$lock_dir/stage" "$lock_dir/started_at"
rmdir "$lock_dir"
REMOTE_RELEASE_UNLOCK
    then
        print_error "服务器发布锁释放失败；保留锁以阻断并发发布"
        return 73
    fi
    _REMOTE_RELEASE_LOCK_ACQUIRED=0
    REMOTE_RELEASE_LOCK_TOKEN=""
}

# 上传当前 HEAD 的 git bundle 到服务器,作为 GitHub 超时时的回退源。
# 前端/后端部署都调用它,所以两边都能走 bundle 回退。
upload_deploy_bundle() {
    local bundle
    local delegation_owner=0
    assert_remote_release_lock_if_acquired
    bundle=$(mktemp)
    if ! git bundle create "$bundle" HEAD >/dev/null; then
        rm -f "$bundle"
        return 1
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "1" ]]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=1
        delegation_owner=1
    fi
    if ! scp "$bundle" "$SERVER:$REMOTE_DEPLOY_BUNDLE" >/dev/null; then
        rm -f "$bundle"
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        return 1
    fi
    rm "$bundle"
    if [ "$delegation_owner" -eq 1 ]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
    fi
}

# 备份发生在远端 checkout 更新之前。先上传当前已核验 commit 的备份工具，
# 避免旧 checkout 缺少恢复演练或站外归档闸门。
stage_backup_preflight_scripts() {
    local scripts=(
        "$SCRIPT_DIR/backend/scripts/backup_db.sh"
        "$SCRIPT_DIR/backend/scripts/verify_backup_restore.sh"
        "$SCRIPT_DIR/backend/scripts/archive_backup_offsite.sh"
        "$SCRIPT_DIR/backend/scripts/rollback_release.sh"
        "$SCRIPT_DIR/backend/scripts/activate_health_evidence_runtime.sh"
        "$SCRIPT_DIR/backend/scripts/verify_runtime_schema_compatibility.py"
        "$SCRIPT_DIR/backend/scripts/quarantine_runtime_only_kb.py"
        "$SCRIPT_DIR/backend/scripts/runtime_state_release_transaction.py"
        "$SCRIPT_DIR/backend/data/system_kb_v2_seed/review_manifest.json"
        "$SCRIPT_DIR/infra/systemd/dropins/health-backend-runtime-state.conf"
        "$SCRIPT_DIR/infra/systemd/dropins/celery-worker-runtime-state.conf"
        "$SCRIPT_DIR/infra/systemd/dropins/celery-beat-runtime-state.conf"
    )
    local source_file
    local source_relative
    local staged_name
    local expected_hash
    local actual_hash

    assert_remote_release_lock_if_acquired
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "缺少合法 DEPLOY_EXPECTED_SHA，拒绝生成发布预检 artifacts"
        return 1
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" = "1" ]]; then
        # A resumed client must consume the exact immutable release stage left
        # by the interrupted owner. Never overwrite scripts, env snapshots, or
        # their manifest before the durable transaction status is inspected.
        if ! ssh "$SERVER" bash -s -- \
            "$REMOTE_BACKUP_PREFLIGHT_DIR" <<'REMOTE_REUSE_RELEASE_STAGE'
set -euo pipefail
stage_dir="$1"
test -d "$stage_dir"
test ! -L "$stage_dir"
test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
test -f "$stage_dir/staged.sha256"
test ! -L "$stage_dir/staged.sha256"
test "$(stat -c '%U:%G:%a' "$stage_dir/staged.sha256")" = \
    "root:root:400"
shopt -s nullglob dotglob
stage_artifact_count=0
for entry in "$stage_dir"/*; do
    name="${entry##*/}"
    case "$name" in
        backup_db.sh|\
        verify_backup_restore.sh|\
        archive_backup_offsite.sh|\
        rollback_release.sh|\
        activate_health_evidence_runtime.sh|\
        verify_runtime_schema_compatibility.py|\
        quarantine_runtime_only_kb.py|\
        runtime_state_release_transaction.py|\
        review_manifest.json|\
        health-backend-runtime-state.conf|\
        celery-worker-runtime-state.conf|\
        celery-beat-runtime-state.conf|\
        staged.sha256|\
        backend.env.rollback|\
        backend.env.candidate|\
        candidate.env|\
        guard.env)
            ;;
        *)
            echo "unknown immutable release artifact: $name" >&2
            exit 1
            ;;
    esac
    if [ "$name" = "staged.sha256" ]; then
        continue
    fi
    test -f "$entry"
    test ! -L "$entry"
    awk -v expected="$name" '
        $2 == expected { matches += 1 }
        END { exit(matches == 1 ? 0 : 1) }
    ' "$stage_dir/staged.sha256"
    stage_artifact_count=$((stage_artifact_count + 1))
done
shopt -u nullglob dotglob
manifest_artifact_count="$(
    awk 'NF { count += 1 } END { print count + 0 }' \
        "$stage_dir/staged.sha256"
)"
test "$stage_artifact_count" = "$manifest_artifact_count"
(
    cd "$stage_dir"
    sha256sum --strict -c staged.sha256 >/dev/null
    required=(
        backup_db.sh
        verify_backup_restore.sh
        archive_backup_offsite.sh
        rollback_release.sh
        activate_health_evidence_runtime.sh
        verify_runtime_schema_compatibility.py
        quarantine_runtime_only_kb.py
        runtime_state_release_transaction.py
        review_manifest.json
        health-backend-runtime-state.conf
        celery-worker-runtime-state.conf
        celery-beat-runtime-state.conf
    )
    for artifact in "${required[@]}"; do
        test -f "$artifact"
        test ! -L "$artifact"
        awk -v expected="$artifact" '
            $2 == expected &&
            length($1) == 64 &&
            $1 !~ /[^0-9a-f]/ {
                matches += 1
            }
            END { exit(matches == 1 ? 0 : 1) }
        ' staged.sha256
    done
    awk '
        NF != 2 { exit 1 }
        $2 == "backup_db.sh" ||
        $2 == "verify_backup_restore.sh" ||
        $2 == "archive_backup_offsite.sh" ||
        $2 == "rollback_release.sh" ||
        $2 == "activate_health_evidence_runtime.sh" ||
        $2 == "verify_runtime_schema_compatibility.py" ||
        $2 == "quarantine_runtime_only_kb.py" ||
        $2 == "runtime_state_release_transaction.py" ||
        $2 == "review_manifest.json" ||
        $2 == "health-backend-runtime-state.conf" ||
        $2 == "celery-worker-runtime-state.conf" ||
        $2 == "celery-beat-runtime-state.conf" {
            allowed += 1
            next
        }
        $2 == "backend.env.rollback" {
            backend_rollback += 1
            allowed += 1
            next
        }
        $2 == "backend.env.candidate" {
            backend_candidate += 1
            allowed += 1
            next
        }
        $2 == "candidate.env" {
            activation_candidate += 1
            allowed += 1
            next
        }
        $2 == "guard.env" {
            activation_guard += 1
            allowed += 1
            next
        }
        { exit 1 }
        END {
            backend_pair = backend_rollback == 1 &&
                backend_candidate == 1 &&
                activation_candidate == 0 &&
                activation_guard == 0
            activation_pair = backend_rollback == 0 &&
                backend_candidate == 0 &&
                activation_candidate == 1 &&
                activation_guard == 1
            if (allowed != 12 &&
                !(allowed == 14 && (backend_pair || activation_pair))) {
                exit 1
            }
        }
    ' staged.sha256
)
REMOTE_REUSE_RELEASE_STAGE
        then
            print_error "既有远端 release stage 不完整或已被修改；拒绝接管"
            return 1
        fi
    else
        if ! ssh "$SERVER" "
            umask 077 && \
            mkdir '$REMOTE_BACKUP_PREFLIGHT_DIR' && \
            test \"\$(stat -c '%U:%G:%a' '$REMOTE_BACKUP_PREFLIGHT_DIR')\" = 'root:root:700'
        "; then
            return 1
        fi
        if ! scp "${scripts[@]}" "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/"; then
            return 1
        fi
        if ! ssh "$SERVER" "
            chmod 0700 '$REMOTE_BACKUP_PREFLIGHT_DIR/'*.sh \
                '$REMOTE_RUNTIME_STATE_RUNNER' && \
            chmod 0600 '$REMOTE_BACKUP_PREFLIGHT_DIR/'*-runtime-state.conf
        "; then
            return 1
        fi
    fi

    for source_file in "${scripts[@]}"; do
        staged_name="${source_file##*/}"
        source_relative="${source_file#"$SCRIPT_DIR/"}"
        if ! git cat-file -e "${DEPLOY_EXPECTED_SHA}:${source_relative}"; then
            print_error "发布预检 artifact 不在待部署 commit: $source_relative"
            return 1
        fi
        expected_hash="$(
            git show "${DEPLOY_EXPECTED_SHA}:${source_relative}" \
                | shasum -a 256 \
                | awk '{print $1}'
        )"
        actual_hash="$(ssh "$SERVER" \
            "sha256sum '$REMOTE_BACKUP_PREFLIGHT_DIR/$staged_name' | awk '{print \$1}'" \
            2>/dev/null || true)"
        if [[ -z "$expected_hash" || "$actual_hash" != "$expected_hash" ]]; then
            print_error "发布预检 artifact 哈希不匹配: $staged_name"
            return 1
        fi
    done
    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" != "1" ]]; then
        if ! ssh "$SERVER" "
            cd '$REMOTE_BACKUP_PREFLIGHT_DIR' && \
            sha256sum \
                backup_db.sh \
                verify_backup_restore.sh \
                archive_backup_offsite.sh \
                rollback_release.sh \
                activate_health_evidence_runtime.sh \
                verify_runtime_schema_compatibility.py \
                quarantine_runtime_only_kb.py \
                runtime_state_release_transaction.py \
                review_manifest.json \
                health-backend-runtime-state.conf \
                celery-worker-runtime-state.conf \
                celery-beat-runtime-state.conf \
                > staged.sha256 && \
            chmod 0400 staged.sha256 && \
            sync -f staged.sha256 && \
            sync -f '$REMOTE_BACKUP_PREFLIGHT_DIR'
        "; then
            return 1
        fi
    fi
}

run_runtime_state_transaction() {
    local command="$1"
    local first_sha="${2:-}"
    local second_sha="${3:-}"
    local output
    local expected

    assert_remote_release_lock
    case "$command" in
        status)
            expected="RUNTIME_STATE_TRANSACTION_OK command=status"
            if ! output=$(ssh "$SERVER" \
                "/usr/bin/python3 '$REMOTE_RUNTIME_STATE_RUNNER' \
                    status '$REMOTE_RELEASE_LOCK_DIR' \
                    '$REMOTE_RELEASE_LOCK_TOKEN'" 2>&1); then
                echo "$output" >&2
                return 1
            fi
            ;;
        preflight|prepare|install)
            if ! [[ "$first_sha" =~ ^[0-9a-f]{40}$ &&
                  "$second_sha" =~ ^[0-9a-f]{40}$ ]]; then
                print_error "runtime state transaction SHA 非法"
                return 1
            fi
            expected="RUNTIME_STATE_TRANSACTION_OK command=$command"
            if ! output=$(ssh "$SERVER" \
                "/usr/bin/python3 '$REMOTE_RUNTIME_STATE_RUNNER' \
                    '$command' '$first_sha' '$second_sha' \
                    '$REMOTE_RELEASE_LOCK_DIR' \
                    '$REMOTE_RELEASE_LOCK_TOKEN'" 2>&1); then
                echo "$output" >&2
                return 1
            fi
            ;;
        restore|commit|release-gate|finalize)
            if ! [[ "$first_sha" =~ ^[0-9a-f]{40}$ ]]; then
                print_error "runtime state transaction SHA 非法"
                return 1
            fi
            expected="RUNTIME_STATE_TRANSACTION_OK command=$command"
            if ! output=$(ssh "$SERVER" \
                "/usr/bin/python3 '$REMOTE_RUNTIME_STATE_RUNNER' \
                    '$command' '$first_sha' \
                    '$REMOTE_RELEASE_LOCK_DIR' \
                    '$REMOTE_RELEASE_LOCK_TOKEN'" 2>&1); then
                echo "$output" >&2
                return 1
            fi
            ;;
        *)
            print_error "runtime state transaction command 非法"
            return 1
            ;;
    esac
    echo "$output"
    if [[ "$output" != *"$expected"* ]]; then
        print_error "runtime state transaction 缺少精确成功证明"
        return 1
    fi
}

commit_runtime_state_transaction_after_guard() {
    assert_remote_release_lock
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! run_runtime_state_transaction commit "$DEPLOY_EXPECTED_SHA"; then
        # A lost SSH connection does not prove whether remote commit is still
        # deleting legacy shelf files or writing its journal. Preserve the
        # lease and stage; never start a concurrent restore with the same token.
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "runtime state commit 结果不明确；发布锁与事务现场保留"
        print_error "确认远端 transaction terminal state 后再恢复"
        return 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0
}

finalize_runtime_state_transaction_after_all_gates() {
    assert_remote_release_lock
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! run_runtime_state_transaction finalize "$DEPLOY_EXPECTED_SHA"; then
        # Finalize atomically publishes a terminal marker and renames the
        # durable transaction before reaping it. A broken SSH session cannot
        # distinguish "not started" from "terminal rename already happened".
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "runtime state finalize 结果不明确；发布锁与事务现场保留"
        print_error "用同一 candidate SHA 的 status/finalize 完成终态协调"
        return 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    _REMOTE_RELEASE_LOCK_ABANDONED=0
}

runtime_state_status_field() {
    local payload="$1"
    local field="$2"

    printf '%s\n' "$payload" | awk -v field="$field" '
        /RUNTIME_STATE_TRANSACTION_OK command=status / {
            sentinels += 1
            for (position = 1; position <= NF; position += 1) {
                if (field == "phase" && $position ~ /^result=phase=/) {
                    value = $position
                    sub(/^result=phase=/, "", value)
                    matches += 1
                } else if ($position ~ ("^" field "=")) {
                    value = $position
                    sub(("^" field "="), "", value)
                    matches += 1
                }
            }
        }
        END {
            if (sentinels != 1 || matches != 1 || value == "") {
                exit 1
            }
            print value
        }
    '
}

inspect_runtime_state_transaction_before_deploy() {
    local status_output
    local phase
    local old_sha
    local candidate_sha
    local release_target
    local next_action
    local state_source
    local remote_head

    # A durable journal depends on the exact immutable stage (including both
    # env preimages) and the original lease token. Default to preserving both
    # until every status/provenance/HEAD/env proof reaches a known-safe exit.
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    if ! status_output="$(run_runtime_state_transaction status)"; then
        print_error "无法读取持久 runtime state transaction；现场与租约保留"
        return 1
    fi
    echo "$status_output"
    phase="$(runtime_state_status_field "$status_output" phase)" ||
        return 1
    old_sha="$(runtime_state_status_field "$status_output" old_sha)" ||
        return 1
    candidate_sha="$(
        runtime_state_status_field "$status_output" candidate_sha
    )" || return 1
    release_target="$(
        runtime_state_status_field "$status_output" release_target
    )" || return 1
    next_action="$(
        runtime_state_status_field "$status_output" next_action
    )" || return 1
    state_source="$(
        runtime_state_status_field "$status_output" state_source
    )" || return 1

    if [[ "$phase" = "NONE" ]]; then
        if [[ "$state_source" != "none" ]]; then
            print_error "NONE status 的 provenance 无效"
            return 1
        fi
        RUNTIME_STATE_RESUME_PHASE="NONE"
        RUNTIME_STATE_RESUME_TARGET="none"
        _REMOTE_RELEASE_LOCK_ABANDONED=0
        return 0
    fi
    if ! [[ "$old_sha" =~ ^[0-9a-f]{40}$ &&
          "$candidate_sha" =~ ^[0-9a-f]{40}$ &&
          "$old_sha" != "$candidate_sha" ]]; then
        print_error "持久 runtime state status 的 SHA 契约无效"
        return 1
    fi
    if [[ "$state_source" = "terminal" &&
          ( "$next_action" = "finalize" ||
            "$next_action" = "release-gate" ) ]]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=1
        if [[ "$next_action" = "finalize" ]]; then
            if ! run_runtime_state_transaction finalize "$candidate_sha"; then
                _REMOTE_RELEASE_LOCK_ABANDONED=1
                print_error "terminal candidate cleanup 结果不明确；租约与现场保留"
                return 1
            fi
        elif ! run_runtime_state_transaction release-gate "$old_sha"; then
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "terminal old cleanup 结果不明确；租约与现场保留"
            return 1
        fi
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        next_action="none"
    fi
    if [[ "$state_source" = "terminal" &&
          "$next_action" = "none" ]]; then
        remote_head="$(
            ssh "$SERVER" "git -C '$REMOTE_PATH' rev-parse HEAD" \
                2>/dev/null || true
        )"
        if [[ "$release_target" = "candidate" &&
              "$candidate_sha" = "$DEPLOY_EXPECTED_SHA" ]]; then
            if [[ "$remote_head" != "$candidate_sha" ]]; then
                print_error "terminal candidate marker 与远端 HEAD 不一致"
                return 1
            fi
            RUNTIME_STATE_ALREADY_FINALIZED=1
            RUNTIME_STATE_RESUME_PHASE="$phase"
            RUNTIME_STATE_RESUME_TARGET="candidate"
            ROLLBACK_CANDIDATE_COMMIT="$old_sha"
            ROLLBACK_COMMIT="$candidate_sha"
            print_warning "本次 candidate 的持久事务已完成；只重跑只读 post-gates"
            _REMOTE_RELEASE_LOCK_ABANDONED=0
            return 0
        fi
        RUNTIME_STATE_RESUME_PHASE="NONE"
        RUNTIME_STATE_RESUME_TARGET="none"
        _REMOTE_RELEASE_LOCK_ABANDONED=0
        return 0
    fi
    if [[ "$state_source" != "journal" &&
          "$state_source" != "preparing" ]]; then
        print_error "active runtime state status 的 provenance 无效"
        return 1
    fi
    if [[ "$candidate_sha" != "$DEPLOY_EXPECTED_SHA" ]]; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "未完成事务属于另一 candidate；拒绝跨 SHA 覆盖"
        print_error "status: phase=$phase candidate=${candidate_sha:0:12}"
        return 1
    fi
    case "$phase" in
        ARMING|PREPARED|INSTALLED|COMMITTING|COMMITTED) ;;
        *)
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "持久事务需要先完成既有 rollback/release-gate: phase=$phase action=$next_action"
            return 1
            ;;
    esac
    case "$release_target" in
        none|candidate) ;;
        *)
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "持久事务 release target 与 candidate resume 冲突"
            return 1
            ;;
    esac

    remote_head="$(
        ssh "$SERVER" "git -C '$REMOTE_PATH' rev-parse HEAD" 2>/dev/null ||
            true
    )"
    if [[ "$phase" = "INSTALLED" ||
          "$phase" = "COMMITTING" ||
          "$phase" = "COMMITTED" ]]; then
        if [[ "$remote_head" != "$candidate_sha" ]]; then
            print_error "持久事务 phase=$phase 但远端不是 candidate SHA"
            return 1
        fi
    elif [[ "$remote_head" != "$old_sha" &&
            "$remote_head" != "$candidate_sha" ]]; then
        print_error "ARMING/PREPARED 远端 SHA 不属于持久事务"
        return 1
    fi

    if ! ssh "$SERVER" "
        set -eu
        cd '$REMOTE_BACKUP_PREFLIGHT_DIR'
        test \"\$(
            awk 'NF { count += 1 } END { print count + 0 }' staged.sha256
        )\" = 14
        sha256sum --strict -c staged.sha256 >/dev/null
        test -f backend.env.candidate
        test ! -L backend.env.candidate
        test \"\$(stat -c '%U:%G:%a' backend.env.candidate)\" = root:root:400
        env_file='$REMOTE_PATH/backend/.env'
        test -r \"\$env_file\"
        cmp -s backend.env.candidate \"\$env_file\"
        awk '
            /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ { a += 1 }
            \$0 == \"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\" { e += 1 }
            END { exit(a == 1 && e == 1 ? 0 : 1) }
        ' \"\$env_file\"
        awk '
            /^HEALTH_RUNTIME_DATA_DIR=/ { a += 1 }
            \$0 == \"HEALTH_RUNTIME_DATA_DIR=/var/lib/health-app/runtime\" { e += 1 }
            END { exit(a == 1 && e == 1 ? 0 : 1) }
        ' \"\$env_file\"
        awk '
            /^HEALTH_UPLOAD_DIR=/ { a += 1 }
            \$0 == \"HEALTH_UPLOAD_DIR=/var/lib/health-app/uploads\" { e += 1 }
            END { exit(a == 1 && e == 1 ? 0 : 1) }
        ' \"\$env_file\"
        awk '
            /^HEALTH_SKILLS_CACHE_DIR=/ { a += 1 }
            \$0 == \"HEALTH_SKILLS_CACHE_DIR=/var/cache/health-app/skills-hub\" { e += 1 }
            END { exit(a == 1 && e == 1 ? 0 : 1) }
        ' \"\$env_file\"
        awk '
            /^DEDAO_KBASE_REVIEW_ARTIFACT_DIR=/ { a += 1 }
            \$0 == \"DEDAO_KBASE_REVIEW_ARTIFACT_DIR=/var/lib/health-app/dedao-kbase/workspace\" { e += 1 }
            END { exit(a == 1 && e == 1 ? 0 : 1) }
        ' \"\$env_file\"
        awk '
            /^LEGACY_KNOWLEDGE_RUNTIME_ENABLED=/ { a += 1 }
            \$0 == \"LEGACY_KNOWLEDGE_RUNTIME_ENABLED=false\" { e += 1 }
            END { exit(a == 1 && e == 1 ? 0 : 1) }
        ' \"\$env_file\"
    "; then
        print_error "持久事务 candidate env 终态证明失败"
        return 1
    fi

    RUNTIME_STATE_RESUME_PHASE="$phase"
    RUNTIME_STATE_RESUME_TARGET="$release_target"
    ROLLBACK_CANDIDATE_COMMIT="$old_sha"
    if [[ "$phase" = "COMMITTING" ||
          "$phase" = "COMMITTED" ||
          "$release_target" = "candidate" ]]; then
        ROLLBACK_COMMIT="$candidate_sha"
    else
        ROLLBACK_COMMIT="$old_sha"
    fi
    print_warning "续接持久 runtime state transaction: phase=$phase old=${old_sha:0:12} candidate=${candidate_sha:0:12}"
    # An active journal still depends on this exact stage and lease. Finalize
    # or an exact rollback proof is the only safe point that arms cleanup.
    _REMOTE_RELEASE_LOCK_ABANDONED=1
}

remote_repository_trust_normalization_command() {
    cat <<'REMOTE_REPOSITORY_TRUST'
(
    set -euo pipefail
    echo '规范化受信发布工作树 ownership...'
    chown root:root .
    chmod 0755 .
    chown -R root:root .git
    chmod -R go-w .git
    tracked_list="$(mktemp /tmp/reva-release-tracked.XXXXXX)"
    trap '/bin/rm -f -- "$tracked_list"' EXIT
    git ls-files --stage -z >"$tracked_list"
    tracked_count=0
    while IFS= read -r -d '' tracked_entry; do
        tracked_count=$((tracked_count + 1))
        metadata="${tracked_entry%%	*}"
        tracked_path="${tracked_entry#*	}"
        tracked_mode="${metadata%% *}"
        test -n "$tracked_path"
        test "$tracked_path" != "$tracked_entry"
        case "$tracked_mode" in
            100644)
                test -f "$tracked_path"
                test ! -L "$tracked_path"
                chown root:root -- "$tracked_path"
                chmod 0644 -- "$tracked_path"
                ;;
            100755)
                test -f "$tracked_path"
                test ! -L "$tracked_path"
                chown root:root -- "$tracked_path"
                chmod 0755 -- "$tracked_path"
                ;;
            120000)
                test -L "$tracked_path"
                chown -h root:root -- "$tracked_path"
                ;;
            *)
                echo "unsupported tracked mode: $tracked_mode" >&2
                exit 1
                ;;
        esac
        parent="$(dirname -- "$tracked_path")"
        while [ "$parent" != "." ]; do
            chown root:root -- "$parent"
            chmod 0755 -- "$parent"
            parent="$(dirname -- "$parent")"
        done
    done <"$tracked_list"
    test "$tracked_count" -gt 0
    test "$(stat -c '%U:%G' .)" = "root:root"
    /bin/rm -f -- "$tracked_list"
    trap - EXIT
)
REMOTE_REPOSITORY_TRUST
}

remote_git_sync_command() {
    local trust_normalization

    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "缺少合法的 DEPLOY_EXPECTED_SHA，拒绝生成远端同步命令"
        return 1
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ||
          -z "$REMOTE_RELEASE_LOCK_TOKEN" ]]; then
        print_error "缺少服务器发布锁，拒绝生成远端同步命令"
        return 1
    fi
    trust_normalization="$(
        remote_repository_trust_normalization_command
    )" || return 1
    cat <<EOF
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' &&
        test "\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')" = '$REMOTE_RELEASE_LOCK_TOKEN' &&
        echo '暂存服务器本地改动...' &&
        git stash push -m auto-deploy-stash >/dev/null &&
        echo '同步到已核验的 main commit $DEPLOY_EXPECTED_SHA...' &&
        ( (git fetch origin main && git cat-file -e '$DEPLOY_EXPECTED_SHA^{commit}') ||
          (echo 'git fetch origin 失败或缺少目标 commit, 使用上传的 deploy bundle...' &&
           git fetch '$REMOTE_DEPLOY_BUNDLE' HEAD && git cat-file -e '$DEPLOY_EXPECTED_SHA^{commit}') ) &&
        git checkout -B main '$DEPLOY_EXPECTED_SHA' &&
        test "\$(git rev-parse HEAD)" = '$DEPLOY_EXPECTED_SHA' &&
        $trust_normalization
EOF
}

verify_deployed_revision() {
    local deployed_sha
    assert_remote_release_lock_if_acquired
    deployed_sha=$(ssh "$SERVER" "cd '$REMOTE_PATH' && git rev-parse HEAD" 2>/dev/null || true)
    if [[ "$deployed_sha" != "$DEPLOY_EXPECTED_SHA" ]]; then
        print_error "远端部署版本不匹配: expected=$DEPLOY_EXPECTED_SHA actual=${deployed_sha:-missing}"
        return 1
    fi
    print_success "远端部署版本已核验: ${DEPLOY_EXPECTED_SHA:0:12}"
}

# 显示使用帮助
show_help() {
    echo "用法: ./deploy.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -a, --all       部署前端和后端 (默认)"
    echo "  -f, --frontend  重建远端已部署同一 SHA 的前端（新 commit 请用 --all）"
    echo "  -b, --backend   仅部署后端"
    echo "  -e, --env       仅同步 .env 到服务器"
    echo "  -H, --activate-health-evidence  受控启用健康证据运行时"
    echo "  -r, --restart   仅重启服务 (不拉取代码)"
    echo "  -p, --push      仅推送代码到 GitHub (不部署)"
    echo "  -s, --status    查看服务器服务状态"
    echo "  -l, --logs      查看服务器日志"
    echo "  -y, --yes       跳过 mobile/ drift 交互确认"
    echo "  -h, --help      显示此帮助信息"
    echo ""
    echo "配置文件: .env (本地管理，不被 git 追踪)"
    echo "  - DEPLOY_SERVER: 服务器地址 (当前: $SERVER)"
    echo "  - DEPLOY_PATH: 部署路径 (当前: $REMOTE_PATH)"
    echo ""
    echo "示例:"
    echo "  ./deploy.sh           # 部署全部"
    echo "  ./deploy.sh -f        # 重建远端当前同 SHA 的前端"
    echo "  ./deploy.sh -b        # 仅部署后端"
    echo "  ./deploy.sh -e        # 仅同步环境变量"
    echo "  ./deploy.sh -H        # 启用并验证健康证据运行时，失败自动恢复"
    echo "  ./deploy.sh -r        # 仅重启服务"
    echo "  ./deploy.sh -s        # 查看服务状态"
}

# ============================================================
# 部署安全：备份、验证、回滚 (借鉴 autoresearch 快速失败理念)
# ============================================================

HEALTH_CHECK_URL=""  # 在 deploy_backend/deploy_frontend 中设置
DEPLOY_SCORE_THRESHOLD=35  # 部署后健康度最低分（满分60，skip-tests模式）

# 备份数据库
backup_database() {
    local delegation_owner=0
    print_step "备份数据库..."
    if [[ "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "1" ]]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=1
        delegation_owner=1
    fi
    # 备份早于远端 git checkout 更新，因此必须执行本次发布 commit 随附的脚本；
    # 数据库与站外归档配置仍从线上 backend/.env 加载。
    if ! stage_backup_preflight_scripts; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "无法上传本次发布的数据库备份工具，阻断部署"
        print_error "远端 stage 结果不明确；发布锁与现场保留"
        return 1
    fi
    if ! ssh "$SERVER" "set -a; source '$REMOTE_PATH/backend/.env'; set +a; BACKUP_OFFSITE_REQUIRED=1 bash \"$REMOTE_BACKUP_RUNNER\""; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "数据库备份、恢复演练或站外归档失败，阻断部署"
        print_error "远端备份结果不明确；发布锁与现场保留"
        return 1
    fi
    if [ "$delegation_owner" -eq 1 ]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
    fi
    print_success "数据库备份、恢复演练和站外归档完成"
}

# 记录当前 commit 用于回滚
save_rollback_point() {
    local rollback_commit
    rollback_commit=$(
        ssh "$SERVER" "cd '$REMOTE_PATH' && git rev-parse HEAD" 2>/dev/null ||
            true
    )
    if ! [[ "$rollback_commit" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法取得合法的生产回滚点"
        return 1
    fi
    ROLLBACK_CANDIDATE_COMMIT="$rollback_commit"
    print_step "候选回滚点: ${ROLLBACK_CANDIDATE_COMMIT:0:8}"
}

verify_rollback_point_schema_compatibility() {
    local probe_output

    assert_remote_release_lock
    if ! [[ "$ROLLBACK_CANDIDATE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "回滚点 SHA 非法，拒绝兼容性预检"
        return 1
    fi
    print_step "验证当前生产回滚点与实时 schema 兼容..."
    if ! probe_output=$(ssh "$SERVER" "
        set -euo pipefail
        test -r '$REMOTE_RELEASE_LOCK_DIR/token'
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN'
        cd '$REMOTE_BACKUP_PREFLIGHT_DIR'
        sha256sum --strict -c staged.sha256 >/dev/null
        cd '$REMOTE_PATH'
        test \"\$(git rev-parse HEAD)\" = '$ROLLBACK_CANDIDATE_COMMIT'
        test -z \"\$(git status --porcelain --untracked-files=no)\"
        cd backend
        test -r .env
        env -u MIGRATION_DATABASE_URL PYTHONPATH=. \
            venv/bin/python '$REMOTE_BACKUP_PREFLIGHT_DIR/verify_runtime_schema_compatibility.py'
        test \"\$(git -C '$REMOTE_PATH' rev-parse HEAD)\" = '$ROLLBACK_CANDIDATE_COMMIT'
        test -z \"\$(git -C '$REMOTE_PATH' status --porcelain --untracked-files=no)\"
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN'
        printf 'ROLLBACK_POINT_SCHEMA_OK commit=%s\\n' '$ROLLBACK_CANDIDATE_COMMIT'
    " 2>&1); then
        echo "$probe_output" >&2
        print_error "当前生产 SHA 与实时 schema 不兼容；服务尚未变更，阻断部署"
        return 1
    fi
    echo "$probe_output"
    if [[ "$probe_output" != *"ROLLBACK_SCHEMA_PROBE_OK tables="* ||
          "$probe_output" != *"ROLLBACK_POINT_SCHEMA_OK commit=$ROLLBACK_CANDIDATE_COMMIT"* ]]; then
        print_error "回滚点 schema probe 缺少精确成功证明"
        return 1
    fi
    ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"
    print_success "生产回滚点已验证并记录: ${ROLLBACK_COMMIT:0:12}"
}

# 回滚到上一个版本
rollback_deploy() {
    if [[ -z "$ROLLBACK_COMMIT" ]]; then
        print_error "无回滚点，请手动恢复"
        return 1
    fi
    assert_remote_release_lock_if_acquired
    print_warning "健康度不达标，自动回滚到 ${ROLLBACK_COMMIT:0:8}..."
    local rollback_output
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! rollback_output=$(ssh "$SERVER" \
        "bash '$REMOTE_ROLLBACK_RUNNER' '$REMOTE_PATH' '$ROLLBACK_COMMIT' '$REMOTE_RELEASE_LOCK_DIR' '$REMOTE_RELEASE_LOCK_TOKEN'" 2>&1); then
        echo "$rollback_output" >&2
        print_error "自动回滚未通过 exact-SHA 或数据库兼容健康验证"
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        return 1
    fi
    echo "$rollback_output"
    local rollback_marker
    rollback_marker="ROLLBACK_OK commit=$ROLLBACK_COMMIT kb_quarantine=passed schema_probe=passed auth_probe=passed services=active process_flag=false"
    if ! printf '%s\n' "$rollback_output" | awk -v marker="$rollback_marker" '
        $0 == marker " runtime_state=restored" ||
        $0 == marker " runtime_state=candidate-retained" {
            accepted += 1
        }
        END { exit(accepted == 1 ? 0 : 1) }
    '; then
        print_error "自动回滚缺少精确成功证明，拒绝接受"
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        return 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    _REMOTE_RELEASE_LOCK_ABANDONED=0
    print_success "代码已回滚到 ${ROLLBACK_COMMIT:0:8}，runtime-only KB 已隔离且兼容性已验证 (kb_quarantine=passed)"
}

# 部署后验证（项目的 val_bpb 检查）
verify_deployment() {
    assert_remote_release_lock_if_acquired
    print_step "部署后健康度检查..."
    # 等待服务启动 + warmup。生产后端多 worker 冷启动可能超过固定 sleep,
    # 因此使用条件轮询，避免服务尚未 ready 时被误判并回滚。
    HEALTH_READY=0
    for attempt in $(seq 1 30); do
        if ssh $SERVER "curl -fsS --max-time 5 http://localhost:8000/api/v1/health > /dev/null" >/dev/null 2>&1; then
            HEALTH_READY=1
            break
        fi
        echo "  (等待后端健康检查 $attempt/30...)"
        sleep 2
    done

    if [[ "$HEALTH_READY" != "1" ]]; then
        print_error "后端健康检查超时"
        return 1
    fi

    sleep 2

    SCORE=$(ssh $SERVER "
        cd $REMOTE_PATH/backend && \
        source venv/bin/activate && \
        python scripts/system_health_score.py --skip-tests --url http://localhost:8000 --json 2>/dev/null
    " 2>/dev/null)

    if [[ -z "$SCORE" ]]; then
        print_error "健康度脚本无有效输出，阻断部署"
        return 1
    fi

    TOTAL=$(echo "$SCORE" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_score'])" 2>/dev/null)
    PASSED=$(echo "$SCORE" | python3 -c "import sys,json; print('true' if json.load(sys.stdin)['pass'] else 'false')" 2>/dev/null)
    MAXIMUM=$(echo "$SCORE" | python3 -c "import sys,json; print(json.load(sys.stdin)['max_possible'])" 2>/dev/null)
    CRITICAL_FAILURES=$(echo "$SCORE" | python3 -c "
import json
import re
import sys
payload = json.load(sys.stdin)
raw = payload.get('critical_failures')
if not isinstance(raw, list):
    raise SystemExit(1)
names = []
for value in raw:
    name = str(value)
    names.append(name if re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', name) else 'invalid')
print(','.join(names) if names else 'none')
" 2>/dev/null)
    AGENT_RUNTIME_CIRCUIT=$(echo "$SCORE" | python3 -c "
import json
import re
import sys
payload = json.load(sys.stdin)
dimensions = payload.get('dimensions')
if not isinstance(dimensions, dict):
    raise SystemExit(1)
circuit = dimensions.get('agent_runtime_circuit')
if not isinstance(circuit, dict):
    raise SystemExit(1)
detail = str(circuit.get('detail', 'missing'))
print(re.sub(r'[^A-Za-z0-9_.:=,-]', '_', detail)[:160])
" 2>/dev/null)

    if [[ -z "$TOTAL" || -z "$PASSED" || "$MAXIMUM" != "60" ||
          -z "$CRITICAL_FAILURES" || -z "$AGENT_RUNTIME_CIRCUIT" ]]; then
        print_error "健康度 JSON 契约无效，阻断部署"
        return 1
    fi

    if [[ "$PASSED" == "true" ]]; then
        print_success "健康度: ${TOTAL}/60 ✅ PASS"
        return 0
    else
        print_error "健康度: ${TOTAL}/60 ❌ FAIL (阈值: ${DEPLOY_SCORE_THRESHOLD})"
        print_error "健康度硬闸: critical_failures=${CRITICAL_FAILURES}; agent_runtime_circuit=${AGENT_RUNTIME_CIRCUIT}"
        return 1
    fi
}

wait_for_agent_skills_manifest() {
    print_step "验证 skills manifest 可达..."
    LOCAL_COUNT=$(find backend/skills -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')
    REMOTE_COUNT=0

    for attempt in $(seq 1 12); do
        REMOTE_COUNT=$(curl -sS --max-time 15 \
            "https://health.executor.life/api/skills/manifest.json" \
            | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('skills', [])))" 2>/dev/null || echo "0")
        if [ "$REMOTE_COUNT" != "0" ]; then
            break
        fi
        echo "  (尝试 $attempt/12: manifest 暂未就绪, 重试...)"
        sleep 5
    done

    if [ "$REMOTE_COUNT" = "0" ]; then
        print_warning "Skills manifest 12 次重试仍未就绪 — 后端健康已通过, 请稍后检查 /api/skills/manifest.json"
    elif [ "$LOCAL_COUNT" != "$REMOTE_COUNT" ]; then
        print_warning "Skills 数量不匹配: 本地 $LOCAL_COUNT vs 线上 $REMOTE_COUNT"
    else
        print_success "Skills 同步: 本地 $LOCAL_COUNT = 线上 $REMOTE_COUNT"
    fi
}

get_env_value() {
    local key="$1"
    grep -m1 "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-
}

require_health_evidence_flag_value() {
    local expected="$1"
    local source_env="${2:-$ENV_FILE}"
    local assignment_count
    local canonical_count

    if [[ "$expected" != "true" && "$expected" != "false" ]]; then
        print_error "health-evidence flag 校验器只接受 true/false"
        return 1
    fi
    if [[ ! -r "$source_env" ]]; then
        print_error "health-evidence flag 配置不可读"
        return 1
    fi
    assignment_count=$(awk '
        /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
            count += 1
        }
        END { print count + 0 }
    ' "$source_env")
    canonical_count=$(
        grep -Fxc "HEALTH_EVIDENCE_RUNTIME_ENABLED=$expected" "$source_env" \
            2>/dev/null || true
    )
    if [[ "$assignment_count" != "1" || "$canonical_count" != "1" ]]; then
        print_error \
            "HEALTH_EVIDENCE_RUNTIME_ENABLED 必须唯一且规范写为 $expected"
        return 1
    fi
}

validate_langbridge_env() {
    local registry_file="$SCRIPT_DIR/backend/app/services/llm/model_registry.py"

    if [[ "${ALLOW_MISSING_LANGBRIDGE_ENV:-0}" -eq 1 ]]; then
        print_warning "跳过 LangBridge 环境变量检查 (ALLOW_MISSING_LANGBRIDGE_ENV=1)"
        return 0
    fi

    if [[ ! -f "$registry_file" ]] || ! grep -q 'provider="langbridge-proxy"' "$registry_file"; then
        return 0
    fi

    local missing=()
    local base_url
    local api_key
    base_url="$(get_env_value "LANGBRIDGE_GATEWAY_BASE_URL")"
    api_key="$(get_env_value "LANGBRIDGE_GATEWAY_API_KEY")"

    [[ -n "$base_url" ]] || missing+=("LANGBRIDGE_GATEWAY_BASE_URL")
    [[ -n "$api_key" ]] || missing+=("LANGBRIDGE_GATEWAY_API_KEY")

    if [[ ${#missing[@]} -gt 0 ]]; then
        print_error ".env 缺少 LangBridge Gateway 配置: ${missing[*]}"
        echo "当前代码启用了 langbridge-proxy 商用模型；缺少这些变量会导致 mobile 模型选项被后端过滤。"
        echo "请在 .env 补齐后重新部署。确实要禁用商用模型时，可临时设置 ALLOW_MISSING_LANGBRIDGE_ENV=1。"
        return 1
    fi
}

# 备份服务器当前 backend/.env，避免环境变量同步覆盖后无法回退
backup_remote_env() {
    local delegation_owner=0
    local snapshot_mode="${1:-release}"
    if [[ "$snapshot_mode" != "release" &&
          "$snapshot_mode" != "rolling-only" ]]; then
        print_error "env 备份模式非法"
        return 1
    fi
    assert_remote_release_lock_if_acquired
    print_step "备份服务器 backend/.env..."
    if [[ "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "1" ]]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=1
        delegation_owner=1
    fi

    if ! ssh "$SERVER" bash -s -- \
        "$REMOTE_PATH/backend" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_BACKEND_ENV_ROLLBACK" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" \
        "$snapshot_mode" <<'REMOTE_ENV_BACKUP'
set -euo pipefail
remote_backend="$1"
stage_dir="$2"
rollback_snapshot="$3"
release_lock_dir="$4"
release_lock_token="$5"
snapshot_mode="$6"
case "$snapshot_mode" in
    release|rolling-only) ;;
    *) exit 1 ;;
esac
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
cd "$remote_backend"
test -f .env
test ! -L .env

REMOTE_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"
CONFIGURED_BACKUP_ROOT=$(grep -m1 '^HEALTH_BACKUP_ROOT=' .env 2>/dev/null | cut -d= -f2- || true)
if [ -n "$CONFIGURED_BACKUP_ROOT" ]; then
    REMOTE_BACKUP_ROOT="$CONFIGURED_BACKUP_ROOT"
fi
ENV_BACKUP_DIR="$REMOTE_BACKUP_ROOT/env"
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
mkdir -p "$ENV_BACKUP_DIR"
chmod 700 "$REMOTE_BACKUP_ROOT" "$ENV_BACKUP_DIR"
cp -p .env "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"
chmod 600 "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"
find "$ENV_BACKUP_DIR" -maxdepth 1 -type f -name '.env.*' -printf '%T@ %p\n' \
    | sort -nr | awk 'NR > 20 {sub(/^[^ ]+ /, ""); print}' | xargs -r rm --
if [ "$snapshot_mode" = "rolling-only" ]; then
    echo "已备份到工作树外: $ENV_BACKUP_DIR/.env.${BACKUP_TS}"
    exit 0
fi

if [ -e "$stage_dir" ]; then
    test -d "$stage_dir"
    test ! -L "$stage_dir"
else
    umask 077
    mkdir "$stage_dir"
fi
test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"

# The rollback snapshot preserves every pre-release key/path but guarantees
# the one safe base flag required by both old and new service processes. A
# predecessor that predates the flag is bootstrapped by appending false.
snapshot_tmp="$(mktemp "$stage_dir/.backend.env.rollback.XXXXXX")"
trap 'rm -f -- "$snapshot_tmp"' EXIT
awk '
    /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
        assignments += 1
        if ($0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false") {
            canonical += 1
            print "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
            next
        }
        invalid = 1
        next
    }
    { print }
    END {
        if (assignments > 1 || invalid == 1 || canonical > 1) {
            exit 1
        }
        if (assignments == 0) {
            print "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
        }
    }
' .env >"$snapshot_tmp"
chmod 0400 "$snapshot_tmp"
if [ -e "$rollback_snapshot" ]; then
    test -f "$rollback_snapshot"
    test ! -L "$rollback_snapshot"
    test "$(stat -c '%U:%G:%a' "$rollback_snapshot")" = "root:root:400"
    if cmp -s "$snapshot_tmp" "$rollback_snapshot"; then
        :
    else
        # A client can disconnect after the sealed candidate was installed
        # but before runtime-state prepare wrote ARMING. In that exact prefix,
        # preserve the old snapshot and require the live env to match the
        # already sealed candidate byte-for-byte.
        manifest="$stage_dir/staged.sha256"
        candidate_snapshot="$stage_dir/backend.env.candidate"
        test -f "$manifest"
        test ! -L "$manifest"
        (
            cd "$stage_dir"
            test "$(
                awk 'NF { count += 1 } END { print count + 0 }' staged.sha256
            )" = "14"
            sha256sum --strict -c staged.sha256 >/dev/null
        )
        test -f "$candidate_snapshot"
        test ! -L "$candidate_snapshot"
        test "$(stat -c '%U:%G:%a' "$candidate_snapshot")" = \
            "root:root:400"
        cmp -s "$snapshot_tmp" "$candidate_snapshot"
    fi
else
    install -o root -g root -m 0400 "$snapshot_tmp" \
        "${rollback_snapshot}.tmp"
    sync -f "${rollback_snapshot}.tmp"
    mv -fT "${rollback_snapshot}.tmp" "$rollback_snapshot"
    sync -f "$stage_dir"
    cmp -s "$snapshot_tmp" "$rollback_snapshot"
fi
test "$(stat -c '%U:%G:%a' "$rollback_snapshot")" = "root:root:400"
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
echo "已备份到工作树外并封存 release rollback env: $ENV_BACKUP_DIR/.env.${BACKUP_TS}"
REMOTE_ENV_BACKUP
    then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "远端 env 备份结果不明确；发布锁与现场保留"
        return 1
    fi

    if [ "$delegation_owner" -eq 1 ]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
    fi
    print_success "服务器环境变量备份检查完成"
}

upload_backend_env_file() {
    local source_env="$1"
    local temp_env
    local upload_path
    local candidate_hash
    local candidate_state

    assert_remote_release_lock_if_acquired
    if [[ ! -r "$source_env" ]]; then
        print_error "待上传 env 文件不可读"
        return 1
    fi
    temp_env=$(mktemp)
    chmod 600 "$temp_env"
    if ! awk '
        !/^DEPLOY_SERVER=/ &&
        !/^DEPLOY_PATH=/ &&
        !/^#.*服务器信息/ &&
        !/^# -.*deploy\.sh/
    ' "$source_env" > "$temp_env"; then
        rm -f "$temp_env"
        return 1
    fi
    if ! require_health_evidence_flag_value false "$temp_env"; then
        rm -f "$temp_env"
        return 1
    fi
    candidate_hash="$(shasum -a 256 "$temp_env" | awk '{print $1}')"
    if ! [[ "$candidate_hash" =~ ^[0-9a-f]{64}$ ]]; then
        rm -f "$temp_env"
        return 1
    fi
    upload_path="${REMOTE_BACKEND_ENV_CANDIDATE}.upload"

    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" = "1" ]]; then
        if ! candidate_state="$(ssh "$SERVER" bash -s -- \
            "$REMOTE_BACKUP_PREFLIGHT_DIR" \
            "$REMOTE_BACKEND_ENV_CANDIDATE" \
            "$candidate_hash" \
            "$REMOTE_RELEASE_LOCK_DIR" \
            "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ENV_CANDIDATE_REUSE'
set -euo pipefail
stage_dir="$1"
candidate_path="$2"
candidate_hash="$3"
release_lock_dir="$4"
release_lock_token="$5"
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
if [ ! -e "$candidate_path" ]; then
    printf 'missing\n'
    exit 0
fi
test -f "$candidate_path"
test ! -L "$candidate_path"
test "$(stat -c '%U:%G:%a' "$candidate_path")" = "root:root:400"
test "$(sha256sum "$candidate_path" | awk '{print $1}')" = "$candidate_hash"
printf 'matching\n'
REMOTE_ENV_CANDIDATE_REUSE
        )"; then
            rm -f "$temp_env"
            print_error "既有 candidate env 与当前 release 不一致；拒绝覆盖"
            return 1
        fi
        if [[ "$candidate_state" = "matching" ]]; then
            rm -f "$temp_env"
            REMOTE_BACKEND_ENV_CANDIDATE_SHA="$candidate_hash"
            return 0
        fi
        if [[ "$candidate_state" != "missing" ]]; then
            rm -f "$temp_env"
            print_error "既有 candidate env 状态证明无效"
            return 1
        fi
    fi

    # Upload only into the root-only release stage. The live backend/.env is
    # changed later, while services are inactive, by one same-filesystem rename.
    if ! ssh "$SERVER" bash -s -- \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ENV_STAGE_PREP'
set -euo pipefail
stage_dir="$1"
release_lock_dir="$2"
release_lock_token="$3"
safe_absolute_path() {
    local value="$1"
    [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] &&
        [ "$value" != "/" ] &&
        [[ "$value" != *"/../"* ]] &&
        [[ "$value" != *"/.." ]] &&
        [[ "$value" != *"/./"* ]] &&
        [[ "$value" != *"/." ]]
}
safe_absolute_path "$stage_dir"
safe_absolute_path "$release_lock_dir"
[[ "$release_lock_token" =~ ^[A-Za-z0-9._:-]+$ ]]
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
if [ -e "$stage_dir" ]; then
    test -d "$stage_dir"
    test ! -L "$stage_dir"
    test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
else
    umask 077
    mkdir "$stage_dir"
    test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
fi
REMOTE_ENV_STAGE_PREP
    then
        rm -f "$temp_env"
        return 1
    fi
    if ! scp "$temp_env" "$SERVER:$upload_path"; then
        rm -f "$temp_env"
        return 1
    fi
    rm -f "$temp_env"
    if ! ssh "$SERVER" bash -s -- \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$upload_path" \
        "$REMOTE_BACKEND_ENV_CANDIDATE" \
        "$candidate_hash" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ENV_STAGE_COMMIT'
set -euo pipefail
stage_dir="$1"
upload_path="$2"
candidate_path="$3"
candidate_hash="$4"
release_lock_dir="$5"
release_lock_token="$6"
trap 'rm -f -- "$upload_path"' EXIT
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
test -f "$upload_path"
test ! -L "$upload_path"
test "$(sha256sum "$upload_path" | awk '{print $1}')" = "$candidate_hash"
candidate_tmp="${candidate_path}.tmp"
rm -f -- "$candidate_tmp"
install -o root -g root -m 0400 "$upload_path" "$candidate_tmp"
sync -f "$candidate_tmp"
mv -fT "$candidate_tmp" "$candidate_path"
sync -f "$stage_dir"
test "$(stat -c '%U:%G:%a' "$candidate_path")" = "root:root:400"
printf '%s  %s\n' "$candidate_hash" "$candidate_path" | sha256sum -c -
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
REMOTE_ENV_STAGE_COMMIT
    then
        return 1
    fi
    REMOTE_BACKEND_ENV_CANDIDATE_SHA="$candidate_hash"
}

seal_release_env_snapshots() {
    assert_remote_release_lock
    if ! ssh "$SERVER" bash -s -- \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_BACKEND_ENV_ROLLBACK" \
        "$REMOTE_BACKEND_ENV_CANDIDATE" \
        "$REMOTE_BACKEND_ENV_CANDIDATE_SHA" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_SEAL_RELEASE_ENVS'
set -euo pipefail
stage_dir="$1"
rollback_snapshot="$2"
candidate_snapshot="$3"
candidate_hash="$4"
release_lock_dir="$5"
release_lock_token="$6"
manifest="$stage_dir/staged.sha256"
manifest_tmp="$stage_dir/.staged.sha256.env.tmp"
trap 'rm -f -- "$manifest_tmp"' EXIT
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
[[ "$candidate_hash" =~ ^[0-9a-f]{64}$ ]]
for snapshot in "$rollback_snapshot" "$candidate_snapshot"; do
    test -f "$snapshot"
    test ! -L "$snapshot"
    test "$(stat -c '%U:%G:%a' "$snapshot")" = "root:root:400"
done
test "$(sha256sum "$candidate_snapshot" | awk '{print $1}')" = \
    "$candidate_hash"
(
    cd "$stage_dir"
    sha256sum --strict -c staged.sha256 >/dev/null
    current_count="$(
        awk 'NF { count += 1 } END { print count + 0 }' staged.sha256
    )"
    if [ "$current_count" = "14" ]; then
        for name in backend.env.rollback backend.env.candidate; do
            awk -v expected="$name" '
                $2 == expected { matches += 1 }
                END { exit(matches == 1 ? 0 : 1) }
            ' staged.sha256
        done
        exit 0
    fi
    test "$current_count" = "12"
    sha256sum \
        backup_db.sh \
        verify_backup_restore.sh \
        archive_backup_offsite.sh \
        rollback_release.sh \
        activate_health_evidence_runtime.sh \
        verify_runtime_schema_compatibility.py \
        quarantine_runtime_only_kb.py \
        runtime_state_release_transaction.py \
        review_manifest.json \
        health-backend-runtime-state.conf \
        celery-worker-runtime-state.conf \
        celery-beat-runtime-state.conf \
        backend.env.rollback \
        backend.env.candidate \
        >"$manifest_tmp"
)
if [ -s "$manifest_tmp" ]; then
    chmod 0400 "$manifest_tmp"
    sync -f "$manifest_tmp"
    mv -fT "$manifest_tmp" "$manifest"
    sync -f "$stage_dir"
fi
(
    cd "$stage_dir"
    test "$(
        awk 'NF { count += 1 } END { print count + 0 }' staged.sha256
    )" = "14"
    sha256sum --strict -c staged.sha256 >/dev/null
)
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
REMOTE_SEAL_RELEASE_ENVS
    then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "release env 快照封存结果不明确；发布锁与现场保留"
        return 1
    fi
}

require_canonical_env_assignment() {
    local key="$1"
    local expected_value="$2"

    awk -v key="$key" -v canonical="$key=$expected_value" '
        $0 ~ ("^[[:space:]]*(export[[:space:]]+)?" key "[[:space:]]*=") {
            assignments += 1
        }
        $0 == canonical {
            exact += 1
        }
        END {
            exit(assignments == 1 && exact == 1 ? 0 : 1)
        }
    ' "$ENV_FILE"
}

validate_env_sync_safety() {
    # ── env 守卫(2026-07-12 事故加固,机械拦截,勿删)──────────────────
    # 事故:从陈旧 checkout 跑 deploy,sync_env 把缺 12 个 key + APP_ENV=development
    # 的本地 .env 推上 prod → 短信密钥丢失 + dev_code 回显洞重开。
    # 守卫1:本地 .env 必须是 prod 形态(APP_ENV=production + DEBUG=False)。
    # 守卫2:prod 现有的 key 本地缺失 → 说明本地 .env 陈旧,推送会删 prod 配置,硬退。
    # 逃生口:DEPLOY_ENV_FORCE=1(明知故犯,比如刻意删 key)。
    if [ "${DEPLOY_ENV_FORCE:-0}" != "1" ]; then
        if ! require_canonical_env_assignment APP_ENV production ||
            ! require_canonical_env_assignment DEBUG False ||
            ! require_canonical_env_assignment \
                HEALTH_RUNTIME_DATA_DIR \
                /var/lib/health-app/runtime ||
            ! require_canonical_env_assignment \
                HEALTH_UPLOAD_DIR \
                /var/lib/health-app/uploads ||
            ! require_canonical_env_assignment \
                HEALTH_SKILLS_CACHE_DIR \
                /var/cache/health-app/skills-hub ||
            ! require_canonical_env_assignment \
                DEDAO_KBASE_REVIEW_ARTIFACT_DIR \
                /var/lib/health-app/dedao-kbase/workspace ||
            ! require_canonical_env_assignment \
                LEGACY_KNOWLEDGE_RUNTIME_ENABLED \
                false; then
            print_error "env 守卫:本地 .env 缺少唯一规范的 production/runtime/uploads/cache/Dedao/legacy 配置。"
            print_error "你可能在用 dev/陈旧 .env。修正后重试,或 DEPLOY_ENV_FORCE=1 强制。"
            return 1
        fi
        local guard_remote
        local missing_keys
        guard_remote=$(mktemp)
        chmod 600 "$guard_remote"
        if scp -q "$SERVER:$REMOTE_PATH/backend/.env" "$guard_remote" \
            2>/dev/null; then
            missing_keys=$(comm -13 \
                <(grep -vE '^#|^$' "$ENV_FILE" |
                    sed -E 's/=.*//' | sort -u) \
                <(grep -vE '^#|^$' "$guard_remote" |
                    sed -E 's/=.*//' | sort -u) |
                head -20)
            if [ -n "$missing_keys" ]; then
                print_error "env 守卫:prod 上存在但本地 .env 缺失的 key(推送会把它们从 prod 删掉):"
                echo "$missing_keys"
                print_error "先把这些 key 收敛进本地根 .env(scp prod 值回来),或 DEPLOY_ENV_FORCE=1 强制。"
                rm -f "$guard_remote"
                return 1
            fi
        fi
        rm -f "$guard_remote"
    fi
}

# 同步环境变量到服务器
sync_env() {
    print_step "同步 .env 到服务器..."

    if ! validate_env_sync_safety || ! validate_langbridge_env; then
        return 1
    fi
    if ! backup_remote_env; then
        return 1
    fi
    # From the first remote stage write onward, a lost client must not delete
    # the evidence needed to decide whether the transition completed.
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! upload_backend_env_file "$ENV_FILE"; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "env candidate staging 结果不明确；发布锁与现场保留"
        return 1
    fi
    if [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        if ! seal_release_env_snapshots; then
            return 1
        fi
    fi

    print_success "发布前/候选 env 已封存并校验；live .env 尚未改变"
}

# 去激活事务已经完成 backend/Celery 的最后一次重启和逐 PID flag=false
# 证明；通用 env/restart 模式此后只能重启前端，不能再让后端越过证明点。
restart_frontend_service() {
    print_step "重启前端服务..."
    assert_remote_release_lock_if_acquired

    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! ssh $SERVER "
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend
    "; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "前端重启结果不明确；发布锁与现场保留"
        return 1
    fi
    if ! ssh "$SERVER" "pm2 describe health-frontend >/dev/null"; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "无法证明前端服务终态；发布锁与现场保留"
        return 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0

    print_success "前端服务已重启"
}

# 推送代码到 GitHub
push_code() {
    print_step "推送代码到 GitHub..."

    python3 "$SCRIPT_DIR/scripts/check_secret_leaks.py"

    # 部署只允许已提交的 tracked 内容。未跟踪文件不会进入 git push 或
    # 远端 checkout，因此仅提示并忽略；绝不能在发布脚本里 git add -A，
    # 否则会误收并发会话或用户尚未准备提交的文件。
    local tracked_changes
    tracked_changes="$(git status --short --untracked-files=no)"
    if [[ -n "$tracked_changes" ]]; then
        print_error "检测到未提交的已跟踪更改，请先明确提交后再部署"
        echo "$tracked_changes"
        exit 1
    fi

    local untracked_files
    untracked_files="$(git ls-files --others --exclude-standard)"
    if [[ -n "$untracked_files" ]]; then
        print_warning "忽略未跟踪文件（不会进入本次部署）"
        echo "$untracked_files"
    fi

    CURRENT_BRANCH="$(git branch --show-current)"
    if [[ "$CURRENT_BRANCH" != "main" ]]; then
        print_error "生产部署只允许从 main 执行，当前分支: ${CURRENT_BRANCH:-detached}"
        exit 1
    fi
    DEPLOY_EXPECTED_SHA="$(git rev-parse HEAD)"
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法解析待部署 commit"
        exit 1
    fi

    git push origin HEAD:main
    local remote_main_sha
    remote_main_sha=$(git ls-remote origin refs/heads/main | awk 'NR==1 {print $1}')
    if [[ "$remote_main_sha" != "$DEPLOY_EXPECTED_SHA" ]]; then
        print_error "origin/main 与本地 HEAD 不一致，拒绝部署"
        exit 1
    fi
    print_success "代码已推送并核验 origin/main: ${DEPLOY_EXPECTED_SHA:0:12}"

    # 同步到 kuaishou GitLab（静默，失败不影响部署）
    if git remote | grep -q kuaishou; then
        git push kuaishou main 2>/dev/null && print_success "代码已同步到 kuaishou GitLab" || print_warning "kuaishou GitLab 同步失败（不影响部署）"
    fi
}

# 部署前端
deploy_frontend() {
    print_step "部署前端..."
    assert_remote_release_lock_if_acquired

    # frontend 与 backend 共用仓库。纯前端路径绝不能 checkout 整仓，否则会
    # 在未迁移/未验证 backend 的情况下改变下一次进程启动所加载的代码。
    # all 模式先由 deploy_backend 完成 exact-SHA guard；frontend-only 只有在
    # 远端已经是该 SHA 时才允许 build。
    if ! verify_deployed_revision; then
        print_error "远端尚未部署本次整仓 SHA；请使用 --all 或先完成 backend guard"
        return 1
    fi

    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! ssh $SERVER "
        cd $REMOTE_PATH && \
        test \"\$(git rev-parse HEAD)\" = '$DEPLOY_EXPECTED_SHA' && \
        test -z \"\$(git status --porcelain --untracked-files=all)\" && \
        cd frontend && \
        echo '安装依赖...' && \
        npm ci && \
        echo '正在构建前端...' && \
        npm run build && \
        cd '$REMOTE_PATH' && \
        test \"\$(git rev-parse HEAD)\" = '$DEPLOY_EXPECTED_SHA' && \
        test -z \"\$(git status --porcelain --untracked-files=all)\" && \
        cd frontend && \
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend
    "; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "前端构建/重启结果不明确；发布锁与现场保留"
        return 1
    fi

    if ! verify_deployed_revision; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "前端构建后 revision 终态无法证明；发布锁与现场保留"
        return 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    print_success "前端部署完成"
}

validate_runtime_only_kb_staging() {
    local review_manifest="$SCRIPT_DIR/backend/data/system_kb_v2_seed/review_manifest.json"
    local runtime_pack_count

    if [[ ! -r "$review_manifest" ]]; then
        print_error "缺少 System KB review_manifest.json，无法验证 runtime-only 发布边界"
        return 1
    fi

    runtime_pack_count=$(python3 - "$review_manifest" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
packs = manifest.get("authority_packs", [])
if not isinstance(packs, list):
    raise SystemExit("authority_packs must be a list")
count = 0
for index, pack in enumerate(packs):
    if not isinstance(pack, dict):
        raise SystemExit(f"authority_packs[{index}] must be an object")
    if pack.get("serving_scope") == "health_evidence_runtime":
        if pack.get("generic_serving_allowed") is not False:
            raise SystemExit(
                f"authority_packs[{index}] must declare generic_serving_allowed=false"
            )
        count += 1
print(count)
PY
    ) || {
        print_error "runtime-only KB manifest 校验失败"
        return 1
    }

    if [[ "$runtime_pack_count" = "0" ]]; then
        return 0
    fi

    if ! require_health_evidence_flag_value false; then
        print_error "runtime-only KB 首阶段部署要求 HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
        print_error "先发布并验证 generic-hold guard 与 KB，再通过 env-only 阶段启用运行时"
        return 1
    fi
    print_success "runtime-only KB staged rollout: feature flag=false"
}

verify_runtime_only_kb_contract() {
    local phase="$1"
    if [[ "$phase" != "guard" && "$phase" != "staged" && "$phase" != "enabled" ]]; then
        print_error "未知 runtime-only KB contract phase: $phase"
        return 1
    fi

    assert_remote_release_lock_if_acquired
    print_step "验证 runtime-only KB serving contract ($phase)..."
    if ! ssh "$SERVER" "
        cd '$REMOTE_PATH/backend' && \
        source venv/bin/activate && \
        set -a && source .env && set +a && \
        PYTHONPATH=. python scripts/verify_runtime_only_kb_contract.py \
            --phase '$phase'
    "; then
        print_error "runtime-only KB serving contract 失败 ($phase)"
        return 1
    fi
    print_success "runtime-only KB serving contract 通过 ($phase)"
}

run_health_evidence_deactivation_transaction() {
    local candidate_path="-"
    local candidate_hash="-"

    if [[ -n "$REMOTE_BACKEND_ENV_CANDIDATE_SHA" ]]; then
        candidate_path="$REMOTE_BACKEND_ENV_CANDIDATE"
        candidate_hash="$REMOTE_BACKEND_ENV_CANDIDATE_SHA"
    fi

    ssh "$SERVER" bash -s -- \
        "$REMOTE_PATH" \
        "$REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" \
        "$candidate_path" \
        "$candidate_hash" \
        "$REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR" \
        "$REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR" \
        "$REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT" \
        "$REMOTE_HEALTH_EVIDENCE_PROC_ROOT" <<'REMOTE_DEACTIVATE_HEALTH_EVIDENCE'
set -Eeuo pipefail
repo_path="$1"
durable_state_dir="$2"
release_lock_dir="$3"
release_lock_token="$4"
candidate_path="$5"
candidate_hash="$6"
runtime_state_dir="$7"
runtime_systemd_dir="$8"
cgroup_root="$9"
proc_root="${10}"
target_env="$repo_path/backend/.env"
target_env_dir="$repo_path/backend"
candidate_install_tmp="$target_env_dir/.env.reva-release.tmp"
durable_enabled="$durable_state_dir/enabled.env"
runtime_enabled="$runtime_state_dir/enabled.env"
runtime_override_name="90-reva-health-evidence-activation.conf"
process_units=(
    health-backend.service
    celery-worker.service
    celery-beat.service
)
all_units=(
    health-backend.socket
    health-backend.service
    celery-worker.service
    celery-beat.service
)
mutation_started=0
deactivation_complete=0

safe_absolute_path() {
    local value="$1"
    [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] &&
        [ "$value" != "/" ] &&
        [[ "$value" != *"/../"* ]] &&
        [[ "$value" != *"/.." ]] &&
        [[ "$value" != *"/./"* ]] &&
        [[ "$value" != *"/." ]]
}

assert_release_lease() {
    test -r "$release_lock_dir/token" &&
        test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
}

verify_flag_file_false() {
    local env_file="$1"
    test -r "$env_file" &&
        test -f "$env_file" &&
        test ! -L "$env_file" &&
        awk '
            /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
                assignments += 1
            }
            $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" {
                canonical += 1
            }
            END {
                if (assignments != 1 || canonical != 1) {
                    exit 1
                }
            }
        ' "$env_file"
}

verify_flag_file_unset() {
    local env_file="$1"
    test -r "$env_file" &&
        test -f "$env_file" &&
        test ! -L "$env_file" &&
        awk '
            /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
                assignments += 1
            }
            END {
                if (assignments != 0) {
                    exit 1
                }
            }
        ' "$env_file"
}

verify_services_inactive() {
    local unit
    for unit in "${all_units[@]}"; do
        test "$(
            systemctl show "$unit" --property=ActiveState --value 2>/dev/null
        )" = "inactive"
    done
}

stop_and_prove_services_inactive() {
    local unit
    # Socket first: no health probe may reactivate the backend while the
    # authorization and live environment are being changed.
    for unit in "${all_units[@]}"; do
        assert_release_lease
        systemctl stop "$unit"
    done
    verify_services_inactive
}

verify_runtime_authorization_absent() {
    local unit
    local override_dir
    local override_path
    if [ -L "$durable_state_dir" ] ||
        [ -L "$runtime_systemd_dir" ] ||
        [ -e "$durable_enabled" ] || [ -L "$durable_enabled" ] ||
        [ -e "$runtime_state_dir" ] || [ -L "$runtime_state_dir" ]; then
        return 1
    fi
    for unit in "${process_units[@]}"; do
        override_dir="$runtime_systemd_dir/$unit.d"
        override_path="$override_dir/$runtime_override_name"
        if [ -L "$override_dir" ]; then
            return 1
        fi
        if [ -e "$override_path" ] || [ -L "$override_path" ]; then
            return 1
        fi
    done
}

verify_process_environment_unset() {
    local unit
    local main_pid
    local control_group
    local procs_file
    local pid
    local process_count
    local main_pid_seen
    for unit in "${process_units[@]}"; do
        main_pid="$(
            systemctl show "$unit" --property=MainPID --value 2>/dev/null
        )"
        if ! [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] ||
            [ "$main_pid" -le 1 ]; then
            return 1
        fi
        control_group="$(
            systemctl show "$unit" --property=ControlGroup --value \
                2>/dev/null
        )"
        if ! [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]] ||
            [[ "$control_group" = *"/../"* ]]; then
            return 1
        fi
        procs_file="${cgroup_root}${control_group}/cgroup.procs"
        if [ ! -r "$procs_file" ]; then
            return 1
        fi
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            if ! [[ "$pid" =~ ^[1-9][0-9]*$ ]] || [ "$pid" -le 1 ]; then
                return 1
            fi
            process_count=$((process_count + 1))
            if [ "$pid" = "$main_pid" ]; then
                main_pid_seen=1
            fi
            if ! LC_ALL=C tr '\000' '\n' <"$proc_root/$pid/environ" |
                awk '
                    /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ {
                        assignments += 1
                    }
                    END {
                        if (assignments != 0) {
                            exit 1
                        }
                    }
                '; then
                return 1
            fi
        done <"$procs_file"
        if [ "$process_count" -le 0 ] || [ "$main_pid_seen" -ne 1 ]; then
            return 1
        fi
    done
}

verify_process_environment_false() {
    local unit
    local main_pid
    local control_group
    local procs_file
    local pid
    local process_count
    local main_pid_seen
    for unit in "${process_units[@]}"; do
        main_pid="$(
            systemctl show "$unit" --property=MainPID --value 2>/dev/null
        )"
        [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && [ "$main_pid" -gt 1 ]
        control_group="$(
            systemctl show "$unit" --property=ControlGroup --value \
                2>/dev/null
        )"
        [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]]
        [[ "$control_group" != *"/../"* ]]
        procs_file="${cgroup_root}${control_group}/cgroup.procs"
        test -r "$procs_file"
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ "$pid" -gt 1 ]
            process_count=$((process_count + 1))
            if [ "$pid" = "$main_pid" ]; then
                main_pid_seen=1
            fi
            LC_ALL=C tr '\000' '\n' <"$proc_root/$pid/environ" |
                awk '
                    /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ {
                        assignments += 1
                    }
                    $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" {
                        canonical += 1
                    }
                    END {
                        if (assignments != 1 || canonical != 1) {
                            exit 1
                        }
                    }
                '
        done <"$procs_file"
        [ "$process_count" -gt 0 ] && [ "$main_pid_seen" -eq 1 ]
    done
}

install_candidate_env() {
    test "$candidate_path" != "-"
    assert_release_lease
    rm -f -- "$candidate_install_tmp"
    install -o root -g health-app -m 0640 \
        "$candidate_path" "$candidate_install_tmp"
    sync -f "$candidate_install_tmp"
    assert_release_lease
    mv -fT "$candidate_install_tmp" "$target_env"
    sync -f "$target_env_dir"
    assert_release_lease
    test "$(stat -c '%U:%G:%a' "$target_env")" = \
        "root:health-app:640"
    test "$(sha256sum "$target_env" | awk '{print $1}')" = \
        "$candidate_hash"
}

remove_runtime_authorization() {
    local unit
    local override_dir
    assert_release_lease
    verify_flag_file_false "$target_env"
    if [ -d "$durable_state_dir" ]; then
        test ! -L "$durable_state_dir"
        rm -f -- "$durable_enabled"
        sync -f "$durable_state_dir"
    fi
    test ! -e "$durable_enabled"
    for unit in "${process_units[@]}"; do
        override_dir="$runtime_systemd_dir/$unit.d"
        rm -f -- "$override_dir/$runtime_override_name"
        if [ -d "$override_dir" ]; then
            rmdir "$override_dir" >/dev/null 2>&1 || true
        fi
    done
    rm -f -- "$runtime_enabled"
    if [ -d "$runtime_state_dir" ]; then
        rmdir "$runtime_state_dir"
    fi
    systemctl daemon-reload
    assert_release_lease
}

contain_on_failure() {
    local original_rc=$?
    local containment_failed=0
    local unit
    trap - EXIT
    rm -f -- "$candidate_install_tmp" >/dev/null 2>&1 || true
    if [ "$mutation_started" -eq 1 ] &&
        [ "$deactivation_complete" -ne 1 ]; then
        # Once a canonical false base exists, revocation is safe and makes a
        # later host boot false as well. Any failure still leaves all services
        # stopped and the release lease/stage preserved for diagnosis.
        if verify_flag_file_false "$target_env"; then
            remove_runtime_authorization >/dev/null 2>&1 || true
        fi
        for unit in "${all_units[@]}"; do
            systemctl stop "$unit" >/dev/null 2>&1 || true
            systemctl kill --kill-who=all --signal=SIGKILL "$unit" \
                >/dev/null 2>&1 || true
            systemctl stop "$unit" >/dev/null 2>&1 || true
        done
        if ! verify_services_inactive; then
            containment_failed=1
        fi
    fi
    if [ "$containment_failed" -eq 1 ]; then
        echo "DEACTIVATION_CONTAINMENT_FAILED services=unverified" >&2
        exit 70
    fi
    exit "$original_rc"
}
trap contain_on_failure EXIT

safe_absolute_path "$repo_path"
safe_absolute_path "$durable_state_dir"
safe_absolute_path "$release_lock_dir"
safe_absolute_path "$runtime_state_dir"
safe_absolute_path "$runtime_systemd_dir"
safe_absolute_path "$cgroup_root"
safe_absolute_path "$proc_root"
[[ "$release_lock_token" =~ ^[A-Za-z0-9._:-]+$ ]]
assert_release_lease
if [ "$candidate_path" != "-" ]; then
    safe_absolute_path "$candidate_path"
    [[ "$candidate_hash" =~ ^[0-9a-f]{64}$ ]]
    test "$(stat -c '%U:%G:%a' "$candidate_path")" = "root:root:400"
    test "$(sha256sum "$candidate_path" | awk '{print $1}')" = \
        "$candidate_hash"
    verify_flag_file_false "$candidate_path"
else
    [ "$candidate_hash" = "-" ]
fi
legacy_flag_bootstrap=0
if verify_flag_file_false "$target_env"; then
    :
elif [ "$candidate_path" != "-" ] &&
    verify_flag_file_unset "$target_env" &&
    verify_runtime_authorization_absent &&
    verify_process_environment_unset; then
    # One-time bootstrap for a release whose predecessor predates this flag.
    # It is safe only when every live process is also unset and no durable or
    # runtime authorization exists. Services are stopped before the canonical
    # false candidate is installed, so no new-code process can observe an
    # implicit value.
    legacy_flag_bootstrap=1
else
    exit 1
fi

mutation_started=1
stop_and_prove_services_inactive
assert_release_lease

if [ "$legacy_flag_bootstrap" -eq 1 ]; then
    # There is nothing to revoke in the legacy state; prove that again after
    # stopping all writers, then establish the explicit false base first.
    verify_flag_file_unset "$target_env"
    verify_runtime_authorization_absent
    install_candidate_env
    verify_flag_file_false "$target_env"
    remove_runtime_authorization
else
    verify_flag_file_false "$target_env"
    # The old live base is already canonical false. Revoke and fsync
    # durable/run authorization before installing any new configuration, so
    # every crash prefix (including a host reboot) can only restart false.
    remove_runtime_authorization
    if [ "$candidate_path" != "-" ]; then
        install_candidate_env
    fi
fi
verify_flag_file_false "$target_env"
assert_release_lease

for unit in "${all_units[@]}"; do
    assert_release_lease
    systemctl start "$unit"
done
for unit in "${all_units[@]}"; do
    test "$(
        systemctl show "$unit" --property=ActiveState --value 2>/dev/null
    )" = "active"
done
verify_process_environment_false
assert_release_lease
verify_flag_file_false "$target_env"
test ! -e "$durable_enabled"
test ! -e "$runtime_state_dir"
deactivation_complete=1
trap - EXIT
echo "HEALTH_EVIDENCE_DEACTIVATED flag=false services=active"
REMOTE_DEACTIVATE_HEALTH_EVIDENCE
}

prove_health_evidence_deactivated_state() {
    local candidate_hash="-"
    if [[ -n "$REMOTE_BACKEND_ENV_CANDIDATE_SHA" ]]; then
        candidate_hash="$REMOTE_BACKEND_ENV_CANDIDATE_SHA"
    fi

    ssh "$SERVER" bash -s -- \
        "$REMOTE_PATH" \
        "$REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" \
        "$candidate_hash" \
        "$REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR" \
        "$REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR" \
        "$REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT" \
        "$REMOTE_HEALTH_EVIDENCE_PROC_ROOT" <<'REMOTE_DEACTIVATION_PROOF'
set -euo pipefail
repo_path="$1"
durable_state_dir="$2"
release_lock_dir="$3"
release_lock_token="$4"
candidate_hash="$5"
runtime_state_dir="$6"
runtime_systemd_dir="$7"
cgroup_root="$8"
proc_root="$9"
target_env="$repo_path/backend/.env"
durable_enabled="$durable_state_dir/enabled.env"
runtime_override_name="90-reva-health-evidence-activation.conf"
process_units=(
    health-backend.service
    celery-worker.service
    celery-beat.service
)
all_units=(
    health-backend.socket
    health-backend.service
    celery-worker.service
    celery-beat.service
)
SERVICE_STABILITY_SECONDS=7
stable_main_pid=()
stable_restart_count=()
stable_enter_timestamp=()
stable_socket_sub_state=""

safe_absolute_path() {
    local value="$1"
    [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] &&
        [ "$value" != "/" ] &&
        [[ "$value" != *"/../"* ]] &&
        [[ "$value" != *"/.." ]] &&
        [[ "$value" != *"/./"* ]] &&
        [[ "$value" != *"/." ]]
}
safe_absolute_path "$repo_path"
safe_absolute_path "$durable_state_dir"
safe_absolute_path "$release_lock_dir"
safe_absolute_path "$runtime_state_dir"
safe_absolute_path "$runtime_systemd_dir"
safe_absolute_path "$cgroup_root"
safe_absolute_path "$proc_root"
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
test -r "$target_env"
test -f "$target_env"
test ! -L "$target_env"
awk '
    /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
        assignments += 1
    }
    $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" {
        canonical += 1
    }
    END {
        if (assignments != 1 || canonical != 1) {
            exit 1
        }
    }
' "$target_env"
if [ "$candidate_hash" != "-" ]; then
    [[ "$candidate_hash" =~ ^[0-9a-f]{64}$ ]]
    test "$(sha256sum "$target_env" | awk '{print $1}')" = \
        "$candidate_hash"
fi
test ! -e "$durable_enabled"
test ! -e "$runtime_state_dir"
for unit in "${process_units[@]}"; do
    test ! -e "$runtime_systemd_dir/$unit.d/$runtime_override_name"
done
verify_service_metadata_snapshot() {
    local phase="$1"
    local unit
    local active_state
    local sub_state
    local result
    local main_pid
    local restart_count
    local enter_timestamp
    local process_index=0

    for unit in "${all_units[@]}"; do
        active_state="$(
            systemctl show "$unit" --property=ActiveState --value \
                2>/dev/null
        )"
        sub_state="$(
            systemctl show "$unit" --property=SubState --value \
                2>/dev/null
        )"
        result="$(
            systemctl show "$unit" --property=Result --value \
                2>/dev/null
        )"
        test "$active_state" = "active"
        test "$result" = "success"
        if [ "$unit" = "health-backend.socket" ]; then
            # systemd 249 reports an active bound socket as "running", while
            # newer releases may report "listening". Both are ready states;
            # still require the exact state to remain unchanged across the
            # stability window.
            case "$sub_state" in
                listening|running) ;;
                *) return 1 ;;
            esac
            if [ "$phase" = "record" ]; then
                stable_socket_sub_state="$sub_state"
            else
                test "$sub_state" = "$stable_socket_sub_state"
            fi
            continue
        fi
        test "$sub_state" = "running"
        main_pid="$(
            systemctl show "$unit" --property=MainPID --value \
                2>/dev/null
        )"
        restart_count="$(
            systemctl show "$unit" --property=NRestarts --value \
                2>/dev/null
        )"
        enter_timestamp="$(
            systemctl show "$unit" \
                --property=ActiveEnterTimestampMonotonic --value \
                2>/dev/null
        )"
        [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && [ "$main_pid" -gt 1 ]
        [[ "$restart_count" =~ ^[0-9]+$ ]]
        [[ "$enter_timestamp" =~ ^[1-9][0-9]*$ ]]
        if [ "$phase" = "record" ]; then
            stable_main_pid[$process_index]="$main_pid"
            stable_restart_count[$process_index]="$restart_count"
            stable_enter_timestamp[$process_index]="$enter_timestamp"
        else
            test "$main_pid" = "${stable_main_pid[$process_index]}"
            test "$restart_count" = \
                "${stable_restart_count[$process_index]}"
            test "$enter_timestamp" = \
                "${stable_enter_timestamp[$process_index]}"
        fi
        process_index=$((process_index + 1))
    done
}

verify_process_environment_false() {
    local unit
    local main_pid
    local control_group
    local procs_file
    local pid
    local process_count
    local main_pid_seen
    local process_index=0

    for unit in "${process_units[@]}"; do
        main_pid="$(
            systemctl show "$unit" --property=MainPID --value 2>/dev/null
        )"
        test "$main_pid" = "${stable_main_pid[$process_index]}"
        control_group="$(
            systemctl show "$unit" --property=ControlGroup --value \
                2>/dev/null
        )"
        [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]]
        [[ "$control_group" != *"/../"* ]]
        procs_file="${cgroup_root}${control_group}/cgroup.procs"
        test -r "$procs_file"
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ "$pid" -gt 1 ]
            process_count=$((process_count + 1))
            if [ "$pid" = "$main_pid" ]; then
                main_pid_seen=1
            fi
            LC_ALL=C tr '\000' '\n' <"$proc_root/$pid/environ" |
                awk '
                    /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ {
                        assignments += 1
                    }
                    $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" {
                        canonical += 1
                    }
                    END {
                        if (assignments != 1 || canonical != 1) {
                            exit 1
                        }
                    }
                '
        done <"$procs_file"
        [ "$process_count" -gt 0 ] && [ "$main_pid_seen" -eq 1 ]
        process_index=$((process_index + 1))
    done
}

verify_service_metadata_snapshot record
verify_process_environment_false
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
sleep "$SERVICE_STABILITY_SECONDS"
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
verify_service_metadata_snapshot compare
verify_process_environment_false
verify_service_metadata_snapshot compare
test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
REMOTE_DEACTIVATION_PROOF
}

prove_health_evidence_runtime_process_flag() {
    local expected="$1"
    if [[ "$expected" != "false" ]]; then
        print_error "通用发布只允许证明 runtime process flag=false"
        return 1
    fi
    prove_health_evidence_deactivated_state
}

deactivate_health_evidence_runtime_before_mutation() {
    local proof_rc
    local transaction_rc

    assert_remote_release_lock
    print_step "撤销持久 health-evidence 授权并证明真实服务 flag=false..."
    # Delegation starts before the first RPC that can stop a live service or
    # atomically replace production state. EXIT must preserve lease and stage
    # until an independent exact proof is obtained.
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if run_health_evidence_deactivation_transaction; then
        transaction_rc=0
    else
        transaction_rc=$?
    fi

    if prove_health_evidence_deactivated_state; then
        proof_rc=0
    else
        proof_rc=$?
    fi
    if [ "$transaction_rc" -eq 0 ] && [ "$proof_rc" -eq 0 ]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        print_success "持久 health-evidence 授权已撤销；真实服务 flag=false"
        return 0
    fi

    _REMOTE_RELEASE_LOCK_ABANDONED=1
    if prove_health_evidence_services_inactive; then
        print_error "health-evidence 去激活结果不完整 (exit=$transaction_rc)；服务已隔离，发布锁与现场保留"
    else
        print_error "health-evidence 去激活结果不明确；无法证明服务已停止，发布锁与现场保留"
    fi
    return 1
}

# 部署后端
deploy_backend() {
    local runtime_state_preflight_complete=0

    print_step "部署后端..."
    assert_remote_release_lock_if_acquired

    # runtime-only 医疗知识必须先让 hold-aware 代码成为健康回滚地板，
    # 且首阶段禁止生成新 evidence answer。
    validate_runtime_only_kb_staging

    # 1. 备份数据库 + 记录发布前回滚点
    backup_database
    inspect_runtime_state_transaction_before_deploy
    if [[ "$RUNTIME_STATE_ALREADY_FINALIZED" = "1" ]]; then
        if ! prove_health_evidence_runtime_process_flag false ||
            ! verify_deployment ||
            ! verify_deployed_revision ||
            ! verify_runtime_only_kb_contract "staged"; then
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "已终结 candidate 的只读 post-gates 失败；现场与租约保留"
            return 1
        fi
        wait_for_agent_skills_manifest
        print_success "持久事务已终结且 backend/System KB post-gates 复证通过"
        return 0
    fi
    if [[ "$RUNTIME_STATE_RESUME_PHASE" = "NONE" ]]; then
        save_rollback_point
        verify_rollback_point_schema_compatibility

        # All locally fallible transport and read-only transaction checks run
        # before live env/service mutation. A preflight RPC failure preserves
        # the exact stage because it may have recovered a durable ARMING intent.
        if ! upload_deploy_bundle; then
            print_error "candidate bundle 上传失败；服务与 live env 尚未变更"
            return 1
        fi
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        if ! run_runtime_state_transaction \
            preflight \
            "$ROLLBACK_CANDIDATE_COMMIT" \
            "$DEPLOY_EXPECTED_SHA"; then
            print_error "runtime state 只读预检失败；服务与 live env 尚未变更，现场与租约保留"
            return 1
        fi
        runtime_state_preflight_complete=1
        _REMOTE_RELEASE_LOCK_ABANDONED=0

        # 2. 同步环境变量并受控撤销运行时授权。
        if ! sync_env; then
            return 1
        fi
        # Arm preservation before the deactivation call: its exact-success
        # path clears delegation internally, so there must be no signal window
        # between live mutation and the caller restoring the preserve state.
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        if ! deactivate_health_evidence_runtime_before_mutation; then
            return 1
        fi
    else
        print_step "沿用持久事务中的已验证回滚点与 candidate env"
    fi

    if [[ "$runtime_state_preflight_complete" != "1" ]]; then
        # Resume keeps the existing journal's stage/lease authoritative across
        # every bundle or preflight failure.
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        if ! upload_deploy_bundle; then
            print_error "candidate bundle 上传失败；持久事务现场与租约保留"
            return 1
        fi
        if ! run_runtime_state_transaction \
            preflight \
            "$ROLLBACK_CANDIDATE_COMMIT" \
            "$DEPLOY_EXPECTED_SHA"; then
            print_error "runtime state 续接预检失败；现场与租约保留"
            return 1
        fi
    fi
    local remote_git_sync
    remote_git_sync="$(remote_git_sync_command)"

    # 3. Guard phase：先启动新代码，不写入任何 System KB artifact。这样旧服务
    # 永远看不到新 runtime-only 文档，且健康失败可安全回到发布前代码。
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    set +e
    ssh $SERVER "
        echo '停止后端 socket 与所有 writer...' && \
        systemctl stop health-backend.socket && \
        systemctl stop health-backend && \
        systemctl stop celery-worker celery-beat && \
        test \"\$(systemctl show health-backend.socket -p ActiveState --value)\" = inactive && \
        test \"\$(systemctl show health-backend -p ActiveState --value)\" = inactive && \
        test \"\$(systemctl show celery-worker -p ActiveState --value)\" = inactive && \
        test \"\$(systemctl show celery-beat -p ActiveState --value)\" = inactive && \
        if [ '$RUNTIME_STATE_RESUME_PHASE' != 'COMMITTED' ]; then \
            /usr/bin/python3 '$REMOTE_RUNTIME_STATE_RUNNER' \
                prepare '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA' \
                '$REMOTE_RELEASE_LOCK_DIR' '$REMOTE_RELEASE_LOCK_TOKEN'; \
        fi && \
        cd $REMOTE_PATH && \
        $remote_git_sync && \
        if [ '$RUNTIME_STATE_RESUME_PHASE' != 'COMMITTED' ]; then \
            /usr/bin/python3 '$REMOTE_RUNTIME_STATE_RUNNER' \
                install '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA' \
                '$REMOTE_RELEASE_LOCK_DIR' '$REMOTE_RELEASE_LOCK_TOKEN'; \
        fi && \
        cd backend && \
        echo '激活虚拟环境...' && \
        source venv/bin/activate && \
        echo '加载环境变量...' && \
        set -a && source .env && set +a && \
        echo '安装依赖...' && \
        pip install --require-hashes -r requirements.lock -q && \
        echo '执行受控数据库迁移...' && \
        test -r /etc/health-app/migration.env && \
        set -a && source /etc/health-app/migration.env && set +a && \
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
        python scripts/apply_managed_migrations.py && \
        unset MIGRATION_DATABASE_URL && \
        (cd '$REMOTE_BACKUP_PREFLIGHT_DIR' && \
            sha256sum --strict -c staged.sha256 >/dev/null) && \
        echo '启动服务前验证完整 runtime schema...' && \
        PYTHONPATH=. python '$REMOTE_BACKUP_PREFLIGHT_DIR/verify_runtime_schema_compatibility.py' && \
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
        echo '重启后端服务...' && \
        systemctl restart health-backend.socket && \
        systemctl restart health-backend && \
        echo '重启 Celery worker & beat...' && \
        systemctl restart celery-worker celery-beat && \
        echo '统计本地 skills...' && \
        find skills -maxdepth 2 -name SKILL.md | wc -l | xargs printf '  本地 SKILL.md: %s 个\\n'
    "
    CODE_EXIT=$?
    set -e
    if [ $CODE_EXIT -ne 0 ]; then
        # SSH 断连时远端命令可能仍在执行；不得把本地非零退出误当成远端
        # transaction terminal。保留 delegated lease 与完整现场，避免与 pip、
        # migration 或 systemd transition 并发回滚。
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "后端 guard 远端事务结果不明确 (exit=$CODE_EXIT)；不与可能仍运行的旧命令并发回滚"
        print_error "发布锁与现场保留，请先在服务器确认 transaction terminal state"
        exit 1
    fi
    if ! prove_health_evidence_runtime_process_flag false ||
        ! verify_deployed_revision; then
        # ssh rc=0 proves the remote command is terminal, so rollback can now
        # safely own a fresh delegated transaction.
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        if rollback_deploy; then
            print_error "后端 guard 终态证明失败，已自动回滚并通过健康检查"
        else
            print_error "后端 guard 终态证明失败，且自动回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0

    # 4. 先验证 hold-aware guard；未通过时 KB 尚未写入。
    if ! verify_deployment; then
        if rollback_deploy; then
            print_error "后端 guard 健康检查失败，代码已自动回滚并通过健康检查"
        else
            print_error "后端 guard 健康检查失败，且自动回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    if ! verify_deployed_revision; then
        if rollback_deploy; then
            print_error "后端 guard revision 校验失败，已自动回滚并通过健康检查"
        else
            print_error "后端 guard revision 校验失败，且自动回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    if ! verify_runtime_only_kb_contract "guard"; then
        if rollback_deploy; then
            print_error "后端 guard serving contract 失败，已自动回滚并通过健康检查"
        else
            print_error "后端 guard serving contract 失败，且自动回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    # 所有 guard Gate 通过后才提交 state transaction。commit 会精确删除
    # 已迁移的 legacy beat shelf；失败仍可从快照回到发布前 SHA。
    if ! commit_runtime_state_transaction_after_guard; then
        exit 1
    fi

    # Guard 已健康：从现在起即使 KB activation 失败，也绝不回到不认识
    # generic hold 的旧代码。rollback runner 还会定向 archive 作为第二层防线。
    ROLLBACK_COMMIT="$DEPLOY_EXPECTED_SHA"
    print_success "generic-hold guard 已成为回滚地板: ${ROLLBACK_COMMIT:0:12}"

    # 5. KB activation phase：此时线上已运行 hold-aware 新代码，feature flag=false。
    assert_remote_release_lock
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    set +e
    ssh $SERVER "
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
        cd $REMOTE_PATH/backend && \
        source venv/bin/activate && \
        set -a && source .env && set +a && \
        echo '补齐审核食物营养基准...' && \
        python scripts/seed_food_nutrition.py && \
        echo '写入系统知识库 Phase 0 种子...' && \
        python scripts/seed_system_kb_phase0.py && \
        echo '导入系统知识库 V2 扩展 artifacts...' && \
        python scripts/import_system_kb_v2_artifacts.py
    "
    KB_EXIT=$?
    set -e
    if [ $KB_EXIT -ne 0 ]; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "System KB 远端事务结果不明确 (exit=$KB_EXIT)；不与可能仍运行的 importer 并发回滚"
        print_error "发布锁与现场保留，请先确认数据库事务与 advisory lock 已终止"
        exit 1
    fi

    # 6. 数据激活后再次跑完整健康度；失败回到同一 guard SHA 并隔离 pack。
    if ! verify_deployment; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        if rollback_deploy; then
            print_error "KB activation 后健康检查失败，guard 代码保留且 runtime-only KB 已隔离"
        else
            print_error "KB activation 后健康检查失败，且隔离回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    if ! verify_deployed_revision; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        if rollback_deploy; then
            print_error "KB activation 后 revision 校验失败，guard 代码保留且 runtime-only KB 已隔离"
        else
            print_error "KB activation 后 revision 校验失败，且隔离回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    if ! verify_runtime_only_kb_contract "staged"; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        if rollback_deploy; then
            print_error "KB activation serving contract 失败，guard 代码保留且 runtime-only KB 已隔离"
        else
            print_error "KB activation serving contract 失败，且隔离回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0

    # 6.5 所有 fatal gate 通过后再验证第一方 Agent skills manifest。
    wait_for_agent_skills_manifest

    # Manifest generation can take long enough for a late service crash or
    # restart loop to appear. Re-prove the exact candidate, health, staged KB
    # contract, and a full process-stability window immediately before the
    # durable rollback snapshot is destroyed.
    if ! prove_health_evidence_runtime_process_flag false ||
        ! verify_deployment ||
        ! verify_deployed_revision ||
        ! verify_runtime_only_kb_contract "staged"; then
        if rollback_deploy; then
            print_error "最终 terminal gate 失败；candidate 已重新安装并通过回滚健康证明"
        else
            print_error "最终 terminal gate 失败且恢复失败；服务已隔离或需人工隔离"
        fi
        exit 1
    fi

    # 只有 backend、System KB、revision、serving contract 和 manifest 全部
    # 走完，才清理可跨重启恢复的持久事务。SSH 结果不明时保留 lease/stage，
    # 由同 SHA 的 status/finalize 重入，绝不猜测式并发回滚。
    if ! finalize_runtime_state_transaction_after_all_gates; then
        exit 1
    fi

    print_success "后端 guard + System KB staged deployment 完成；运行时仍保持 feature flag=false"
}

render_backend_env_file() {
    local source_env="$1"
    local target_env="$2"
    awk '
        !/^DEPLOY_SERVER=/ &&
        !/^DEPLOY_PATH=/ &&
        !/^#.*服务器信息/ &&
        !/^# -.*deploy\.sh/
    ' "$source_env" > "$target_env"
    chmod 600 "$target_env"
}

prepare_health_evidence_guard_env() {
    local candidate_env="$1"
    local target_env="$2"
    awk '
        $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=true" {
            print "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
            seen += 1
            next
        }
        /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
            invalid = 1
        }
        { print }
        END {
            if (seen != 1 || invalid == 1) {
                exit 1
            }
        }
    ' "$candidate_env" > "$target_env"
    chmod 600 "$target_env"
}

validate_health_evidence_activation_paths() {
    local value
    for value in \
        "$REMOTE_PATH" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_ACTIVATION_STATE_DIR" \
        "$REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" \
        "$REMOTE_RELEASE_LOCK_DIR"; do
        if [[ ! "$value" =~ ^/[A-Za-z0-9._/-]+$ ||
            "$value" = "/" ||
            "$value" = *"/../"* ||
            "$value" = *"/.." ||
            "$value" = *"/./"* ||
            "$value" = *"/." ]]; then
            print_error "health-evidence 激活路径不安全"
            return 1
        fi
    done
}

verify_systemd_activation_capability() {
    local unit_name
    unit_name="health-evidence-deadman-probe-${DEPLOY_EXPECTED_SHA:0:12}-$$.service"

    assert_remote_release_lock
    ssh "$SERVER" bash -s -- \
        "$unit_name" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_SYSTEMD_CAPABILITY'
set -euo pipefail
unit_name="$1"
release_lock="$2"
release_token="$3"
[[ "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.service$ ]]
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"
probe_dir="$(mktemp -d /tmp/health-evidence-deadman-probe.XXXXXX)"
chmod 0700 "$probe_dir"
marker="$probe_dir/exec-stop-post-ran"
trap 'rm -f "$marker"; rmdir "$probe_dir" >/dev/null 2>&1 || true; systemctl reset-failed "$unit_name" >/dev/null 2>&1 || true' EXIT
touch_bin="$(command -v touch)"
[[ "$touch_bin" =~ ^/[A-Za-z0-9._/-]+$ ]]

set +e
systemd-run \
    --unit="$unit_name" \
    --wait \
    --property=Type=oneshot \
    --property=RemainAfterExit=no \
    --property=Restart=no \
    --property=TimeoutStartSec=30s \
    --property=TimeoutStopSec=30s \
    --property="ExecStopPost=$touch_bin $marker" \
    /bin/false \
    >/dev/null 2>&1
set -e

test -f "$marker"
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"
REMOTE_SYSTEMD_CAPABILITY
}

stage_health_evidence_activation_artifacts() (
    set -e
    local candidate_env
    local candidate_as_guard
    local guard_env
    local staged_candidate_env
    local staged_guard_env
    local candidate_hash
    local guard_hash

    candidate_env=$(mktemp)
    candidate_as_guard=$(mktemp)
    guard_env=$(mktemp)
    staged_candidate_env=$(mktemp)
    staged_guard_env=$(mktemp)
    trap 'rm -f "$candidate_env" "$candidate_as_guard" "$guard_env" \
        "$staged_candidate_env" "$staged_guard_env"' EXIT

    validate_health_evidence_activation_paths
    validate_env_sync_safety
    validate_langbridge_env

    render_backend_env_file "$ENV_FILE" "$candidate_env"
    require_health_evidence_flag_value true "$candidate_env"
    prepare_health_evidence_guard_env "$candidate_env" "$candidate_as_guard"
    require_health_evidence_flag_value false "$candidate_as_guard"

    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" = "1" ]]; then
        # Adoption is read-only with respect to the original release stage.
        # Consume only the already-sealed candidate/guard pair and the
        # root-owned durable attempt state left by the interrupted owner.
        stage_backup_preflight_scripts
        scp -q \
            "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/candidate.env" \
            "$staged_candidate_env"
        scp -q \
            "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/guard.env" \
            "$staged_guard_env"
        chmod 600 "$staged_candidate_env" "$staged_guard_env"
        require_health_evidence_flag_value true "$staged_candidate_env"
        require_health_evidence_flag_value false "$staged_guard_env"
        if ! cmp -s "$candidate_env" "$staged_candidate_env" ||
            ! cmp -s "$candidate_as_guard" "$staged_guard_env"; then
            print_error "本地 activation 配置与既有封存事务不一致"
            return 1
        fi
        ssh "$SERVER" bash -s -- \
            "$REMOTE_ACTIVATION_STATE_DIR" <<'REMOTE_ACTIVATION_STATE_REUSE'
set -euo pipefail
state_dir="$1"
test -d "$state_dir"
test ! -L "$state_dir"
test "$(stat -c '%U:%G:%a' "$state_dir")" = "root:root:700"
shopt -s nullglob dotglob
for entry in "$state_dir"/*; do
    name="${entry##*/}"
    case "$name" in
        launch-intent|success|success.outcome) ;;
        *) exit 1 ;;
    esac
    test -f "$entry"
    test ! -L "$entry"
    test "$(stat -c '%U:%G:%a' "$entry")" = "root:root:400"
    test "$(stat -c '%h' "$entry")" = "1"
done
shopt -u nullglob dotglob
if test -e "$state_dir/success"; then
    test -e "$state_dir/launch-intent"
    test -e "$state_dir/success.outcome"
fi
if test -e "$state_dir/success.outcome"; then
    test -e "$state_dir/launch-intent"
fi
REMOTE_ACTIVATION_STATE_REUSE
        return
    fi

    backup_remote_env rolling-only

    # The recovery guard is the exact remote config that just passed the staged
    # semantic probe. Activation is allowed to change only the one feature flag.
    scp -q "$SERVER:$REMOTE_PATH/backend/.env" "$guard_env"
    chmod 600 "$guard_env"
    require_health_evidence_flag_value false "$guard_env"
    if ! cmp -s "$candidate_as_guard" "$guard_env"; then
        print_error "本地 candidate 除 feature flag 外与线上 staged guard 不一致"
        print_error "请先以 flag=false 独立同步并验证环境，再执行受控启用"
        return 1
    fi

    stage_backup_preflight_scripts
    scp "$candidate_env" \
        "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/candidate.env"
    scp "$guard_env" \
        "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/guard.env"

    candidate_hash=$(shasum -a 256 "$candidate_env" | awk '{print $1}')
    guard_hash=$(shasum -a 256 "$guard_env" | awk '{print $1}')
    ssh "$SERVER" bash -s -- \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_ACTIVATION_STATE_DIR" \
        "$candidate_hash" \
        "$guard_hash" <<'REMOTE_ACTIVATION_STAGE'
set -euo pipefail
stage_dir="$1"
state_dir="$2"
candidate_hash="$3"
guard_hash="$4"

test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
test -f "$stage_dir/candidate.env"
test ! -L "$stage_dir/candidate.env"
test -f "$stage_dir/guard.env"
test ! -L "$stage_dir/guard.env"
test "$(sha256sum "$stage_dir/candidate.env" | awk '{print $1}')" = \
    "$candidate_hash"
test "$(sha256sum "$stage_dir/guard.env" | awk '{print $1}')" = "$guard_hash"
chmod 0400 "$stage_dir/candidate.env" "$stage_dir/guard.env"

rm -f "$stage_dir/staged.sha256"
(
    cd "$stage_dir"
    sha256sum \
        backup_db.sh \
        verify_backup_restore.sh \
        archive_backup_offsite.sh \
        rollback_release.sh \
        activate_health_evidence_runtime.sh \
        verify_runtime_schema_compatibility.py \
        quarantine_runtime_only_kb.py \
        runtime_state_release_transaction.py \
        review_manifest.json \
        health-backend-runtime-state.conf \
        celery-worker-runtime-state.conf \
        celery-beat-runtime-state.conf \
        candidate.env \
        guard.env \
        > staged.sha256
    chmod 0400 staged.sha256
    test "$(awk 'NF {count += 1} END {print count + 0}' staged.sha256)" \
        -eq 14
    sha256sum -c staged.sha256 >/dev/null
)

umask 077
mkdir "$state_dir"
test "$(stat -c '%U:%G:%a' "$state_dir")" = "root:root:700"
sync -f "$state_dir"
REMOTE_ACTIVATION_STAGE
)

run_health_evidence_activation_unit() {
    local unit_name="$1"
    local candidate_env="$REMOTE_BACKUP_PREFLIGHT_DIR/candidate.env"
    local guard_env="$REMOTE_BACKUP_PREFLIGHT_DIR/guard.env"
    local outcome_file="${REMOTE_ACTIVATION_SUCCESS_MARKER}.outcome"

    ssh "$SERVER" bash -s -- \
        "$unit_name" \
        "$REMOTE_ACTIVATION_RUNNER" \
        "$REMOTE_PATH" \
        "$DEPLOY_EXPECTED_SHA" \
        "$candidate_env" \
        "$guard_env" \
        "$REMOTE_ACTIVATION_SUCCESS_MARKER" \
        "$outcome_file" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ACTIVATION_UNIT'
set -euo pipefail
unit_name="$1"
runner="$2"
repo="$3"
expected_sha="$4"
candidate_env="$5"
guard_env="$6"
success_marker="$7"
outcome_file="$8"
release_lock="$9"
release_token="${10}"
state_dir="$(dirname "$success_marker")"
intent_file="$state_dir/launch-intent"
intent_temp=""

safe_path() {
    local value="$1"
    [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]]
    [[ "$value" != "/" ]]
    [[ "$value" != *"/../"* && "$value" != *"/.." ]]
    [[ "$value" != *"/./"* && "$value" != *"/." ]]
}
[[ "$unit_name" =~ ^[A-Za-z0-9_.@-]+\.service$ ]]
[[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$release_token" =~ ^[A-Za-z0-9._:-]+$ ]]
for path in \
    "$runner" "$repo" "$candidate_env" "$guard_env" \
    "$success_marker" "$outcome_file" "$release_lock" \
    "$state_dir" "$intent_file"; do
    safe_path "$path"
done
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"
test "$(stat -c '%U:%G:%a' "$state_dir")" = "root:root:700"
test ! -e "$intent_file"
test ! -e "$success_marker"
test ! -e "$outcome_file"

# Persist the exact launch intent before the first systemd/D-Bus RPC. An
# adopted client may launch only when this durable negative evidence is absent.
lease_hash="$(
    printf '%s' "$release_token" | sha256sum | awk '{print $1}'
)"
intent_temp="$(mktemp "$state_dir/.launch-intent.XXXXXX")"
trap 'rm -f -- "$intent_temp"' EXIT
printf '%s\n' \
    "commit=$expected_sha" \
    "unit=$unit_name" \
    "lease_sha256=$lease_hash" >"$intent_temp"
chmod 0400 "$intent_temp"
sync -f "$intent_temp"
ln "$intent_temp" "$intent_file"
rm -f -- "$intent_temp"
intent_temp=""
sync -f "$state_dir"
test "$(stat -c '%U:%G:%a' "$intent_file")" = "root:root:400"
test "$(stat -c '%h' "$intent_file")" = "1"

deadman="/bin/bash $runner --recover-if-unverified $repo $expected_sha $candidate_env $guard_env $success_marker $release_lock $release_token"
systemd-run \
    --unit="$unit_name" \
    --wait \
    --property=Type=oneshot \
    --property=RemainAfterExit=no \
    --property=Restart=no \
    --property=KillMode=control-group \
    --property=UMask=0077 \
    --property=TimeoutStartSec=20min \
    --property=TimeoutStopSec=15min \
    --property=StandardOutput=journal \
    --property=StandardError=journal \
    --property="ExecStopPost=$deadman" \
    /bin/bash "$runner" \
        --activate \
        "$repo" \
        "$expected_sha" \
        "$candidate_env" \
        "$guard_env" \
        "$success_marker" \
        "$release_lock" \
        "$release_token"
REMOTE_ACTIVATION_UNIT
}

prove_health_evidence_activation_state() {
    local phase="$1"
    local unit_name="$2"

    ssh "$SERVER" bash -s -- \
        "$phase" \
        "$unit_name" \
        "$REMOTE_PATH" \
        "$DEPLOY_EXPECTED_SHA" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR/candidate.env" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR/guard.env" \
        "$REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" \
        "$REMOTE_ACTIVATION_SUCCESS_MARKER" \
        "${REMOTE_ACTIVATION_SUCCESS_MARKER}.outcome" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ACTIVATION_PROOF'
set -euo pipefail
test "$#" -eq 11
phase="$1"
unit_name="$2"
repo="$3"
expected_sha="$4"
candidate_env="$5"
guard_env="$6"
durable_state_dir="$7"
success_marker="$8"
outcome_file="$9"
release_lock="${10}"
release_token="${11}"
durable_enabled="$durable_state_dir/enabled.env"
state_dir="$(dirname "$success_marker")"
intent_file="$state_dir/launch-intent"
expected_success="HEALTH_EVIDENCE_ACTIVATION_OK commit=$expected_sha flag=true health=passed auth_probe=passed score=passed contract=enabled services=active"
case "$phase" in
    enabled)
        expected_outcome="HEALTH_EVIDENCE_DEADMAN_NOOP commit=$expected_sha authorization=verified"
        ;;
    staged)
        expected_outcome="HEALTH_EVIDENCE_DEADMAN_RECOVERED commit=$expected_sha flag=false health=passed contract=staged services=active"
        ;;
    *)
        exit 2
        ;;
esac

[[ "$repo" =~ ^/[A-Za-z0-9._/-]+$ ]]
[[ "$repo" != "/" && "$repo" != *"/../"* && "$repo" != *"/.." ]]
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"

# Every terminal outcome must be bound to a durable intent written before the
# launch RPC. This prevents an adopter from mistaking an unrelated/stale
# outcome for the exact release attempt it owns.
test -f "$intent_file"
test ! -L "$intent_file"
test "$(stat -c '%U:%G:%a' "$intent_file")" = "root:root:400"
test "$(stat -c '%h' "$intent_file")" = "1"
lease_hash="$(
    printf '%s' "$release_token" | sha256sum | awk '{print $1}'
)"
intent_unit="$(
    awk -F= '
        NR == 1 && $1 == "commit" { commit += 1; next }
        NR == 2 && $1 == "unit" { unit += 1; value = $2; next }
        NR == 3 && $1 == "lease_sha256" { lease += 1; next }
        { exit 1 }
        END {
            if (NR != 3 || commit != 1 || unit != 1 || lease != 1) {
                exit 1
            }
            print value
        }
    ' "$intent_file"
)"
test "$(sed -n '1p' "$intent_file")" = "commit=$expected_sha"
test "$(sed -n '3p' "$intent_file")" = "lease_sha256=$lease_hash"
intent_prefix="${expected_sha:0:12}"
[[ "$intent_unit" =~ ^health-evidence-activation-${intent_prefix}-[1-9][0-9]*\.service$ ]]

# The exact outcome file is written only after ExecStart/ExecStopPost reaches a
# terminal proof. It is per-attempt and lives in a freshly-created root-only dir.
test -f "$outcome_file"
test ! -L "$outcome_file"
test "$(stat -c '%U:%G:%a' "$outcome_file")" = "root:root:400"
test "$(stat -c '%h' "$outcome_file")" = "1"
cmp -s "$outcome_file" <(printf '%s\n' "$expected_outcome")

flag_is_exact() {
    local env_file="$1"
    local expected="$2"
    awk -v expected="$expected" '
        /^[[:space:]]*(export[[:space:]]+)?HEALTH_EVIDENCE_RUNTIME_ENABLED[[:space:]]*=/ {
            assignments += 1
        }
        $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=" expected {
            canonical += 1
        }
        END {
            exit(assignments == 1 && canonical == 1 ? 0 : 1)
        }
    ' "$env_file"
}

verify_root_owned_nonwritable() {
    local path="$1"
    local metadata
    local mode

    metadata="$(stat -c '%U:%G:%a' "$path")"
    [[ "$metadata" =~ ^root:root:([0-7]{3,4})$ ]]
    mode="${BASH_REMATCH[1]}"
    (( (8#$mode & 8#022) == 0 ))
}

verify_git_metadata_trust() {
    local git_config="$repo/.git/config"
    local git_dir="$repo/.git"
    local git_head="$git_dir/HEAD"
    local main_ref="$git_dir/refs/heads/main"
    local metadata_entry
    local metadata_listing

    [ "$(id -u)" = "0" ]
    test -d "$repo"
    test ! -L "$repo"
    test -d "$git_dir"
    test ! -L "$git_dir"
    test -f "$git_config"
    test ! -L "$git_config"
    test ! -e "$git_dir/config.worktree"
    test ! -e "$git_dir/objects/info/alternates"
    test ! -e "$git_dir/objects/info/http-alternates"
    test -f "$git_head" && test ! -L "$git_head"
    test -f "$main_ref" && test ! -L "$main_ref"
    test "$(/bin/cat "$git_head")" = "ref: refs/heads/main"
    test "$(/bin/cat "$main_ref")" = "$expected_sha"
    verify_root_owned_nonwritable "$repo"

    umask 077
    metadata_listing="$(
        /usr/bin/mktemp /tmp/reva-health-git-metadata.XXXXXX
    )"
    if ! /usr/bin/find "$git_dir" -xdev -print0 >"$metadata_listing"; then
        /bin/rm -f -- "$metadata_listing"
        return 1
    fi
    while IFS= read -r -d '' metadata_entry; do
        if test -L "$metadata_entry" ||
            ! verify_root_owned_nonwritable "$metadata_entry"; then
            /bin/rm -f -- "$metadata_listing"
            return 1
        fi
    done <"$metadata_listing"
    /bin/rm -f -- "$metadata_listing"
}

trusted_git() {
    local git_dir="$repo/.git"
    local proof_git
    local proof_root
    local protected_config
    local rc

    umask 077
    proof_root="$(
        /usr/bin/mktemp -d /tmp/reva-health-git-proof.XXXXXX
    )" || return 1
    proof_git="$proof_root/git"
    protected_config="$proof_root/global.config"
    if ! /bin/mkdir -m 0700 -- \
        "$proof_git" "$proof_git/objects" "$proof_git/refs" ||
        ! printf '%s\n' "$expected_sha" >"$proof_git/HEAD" ||
        ! printf '%s\n' \
            '[core]' \
            '    repositoryformatversion = 0' \
            '    filemode = true' \
            '    bare = false' >"$proof_git/config" ||
        ! printf '[safe]\n\tdirectory = %s\n' \
            "$repo" >"$protected_config" ||
        ! /bin/chmod 0600 \
            "$proof_git/HEAD" "$proof_git/config" "$protected_config"; then
        /bin/rm -rf -- "$proof_root"
        return 1
    fi
    if ! /usr/bin/env -i \
        HOME=/nonexistent \
        PATH=/usr/bin:/bin \
        LC_ALL=C \
        GIT_ATTR_NOSYSTEM=1 \
        GIT_ALTERNATE_OBJECT_DIRECTORIES= \
        GIT_CONFIG_NOSYSTEM=1 \
        GIT_CONFIG_GLOBAL="$protected_config" \
        GIT_OBJECT_DIRECTORY="$git_dir/objects" \
        GIT_OPTIONAL_LOCKS=0 \
        /usr/bin/git --no-optional-locks --no-replace-objects \
        -c core.fsmonitor=false \
        -c core.hooksPath=/dev/null \
        --git-dir="$proof_git" \
        --work-tree="$repo" \
        read-tree "$expected_sha"; then
        /bin/rm -rf -- "$proof_root"
        return 1
    fi
    if /usr/bin/env -i \
        HOME=/nonexistent \
        PATH=/usr/bin:/bin \
        LC_ALL=C \
        GIT_ATTR_NOSYSTEM=1 \
        GIT_ALTERNATE_OBJECT_DIRECTORIES= \
        GIT_CONFIG_NOSYSTEM=1 \
        GIT_CONFIG_GLOBAL="$protected_config" \
        GIT_OBJECT_DIRECTORY="$git_dir/objects" \
        GIT_OPTIONAL_LOCKS=0 \
        /usr/bin/git --no-optional-locks --no-replace-objects \
        -c core.fsmonitor=false \
        -c core.hooksPath=/dev/null \
        --git-dir="$proof_git" \
        --work-tree="$repo" \
        "$@"; then
        rc=0
    else
        rc=$?
    fi
    /bin/rm -rf -- "$proof_root"
    return "$rc"
}

verify_tracked_worktree_trust() {
    local component
    local current
    local listing
    local parent
    local relative
    local target

    umask 077
    listing="$(
        /usr/bin/mktemp /tmp/reva-health-tracked-paths.XXXXXX
    )" || return 1
    if ! trusted_git ls-files -z >"$listing"; then
        /bin/rm -f -- "$listing"
        return 1
    fi
    while IFS= read -r -d '' relative; do
        [[ -n "$relative" && "$relative" != /* ]] || {
            /bin/rm -f -- "$listing"
            return 1
        }
        [[ "/$relative/" != *"/../"* && "/$relative/" != *"/./"* ]] || {
            /bin/rm -f -- "$listing"
            return 1
        }
        current="$repo"
        if [[ "$relative" = */* ]]; then
            parent="${relative%/*}"
            while [[ -n "$parent" ]]; do
                component="${parent%%/*}"
                [[ -n "$component" ]] || {
                    /bin/rm -f -- "$listing"
                    return 1
                }
                current="$current/$component"
                test -d "$current" &&
                    test ! -L "$current" &&
                    verify_root_owned_nonwritable "$current" || {
                    /bin/rm -f -- "$listing"
                    return 1
                }
                if [[ "$parent" = "$component" ]]; then
                    break
                fi
                parent="${parent#*/}"
            done
        fi
        target="$repo/$relative"
        if test -L "$target"; then
            :
        elif test -f "$target" || test -d "$target"; then
            verify_root_owned_nonwritable "$target" || {
                /bin/rm -f -- "$listing"
                return 1
            }
        else
            /bin/rm -f -- "$listing"
            return 1
        fi
    done <"$listing"
    /bin/rm -f -- "$listing"
}

verify_repo_revision() {
    local actual_sha
    local status_output

    verify_git_metadata_trust
    actual_sha="$(trusted_git rev-parse HEAD)"
    test "$actual_sha" = "$expected_sha"
    verify_tracked_worktree_trust
    status_output="$(
        trusted_git status --porcelain --untracked-files=all
    )"
    test -z "$status_output"
}

verify_process_environment() {
    local expected="$1"
    local unit
    local main_pid
    local control_group
    local procs_file
    local pid
    local process_count
    local main_pid_seen
    for unit in \
        health-backend.service celery-worker.service celery-beat.service; do
        main_pid="$(
            systemctl show "$unit" --property=MainPID --value 2>/dev/null
        )"
        [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && [ "$main_pid" -gt 1 ]
        control_group="$(
            systemctl show "$unit" --property=ControlGroup --value \
                2>/dev/null
        )"
        [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]]
        [[ "$control_group" != *"/../"* ]]
        procs_file="/sys/fs/cgroup${control_group}/cgroup.procs"
        test -r "$procs_file"
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ "$pid" -gt 1 ]
            process_count=$((process_count + 1))
            if [ "$pid" = "$main_pid" ]; then
                main_pid_seen=1
            fi
            LC_ALL=C tr '\000' '\n' <"/proc/$pid/environ" |
                awk -v expected="$expected" '
                    /^HEALTH_EVIDENCE_RUNTIME_ENABLED=/ {
                        assignments += 1
                    }
                    $0 == "HEALTH_EVIDENCE_RUNTIME_ENABLED=" expected {
                        canonical += 1
                    }
                    END {
                        exit(
                            assignments == 1 && canonical == 1 ? 0 : 1
                        )
                    }
                '
        done <"$procs_file"
        [ "$process_count" -gt 0 ] && [ "$main_pid_seen" -eq 1 ]
    done
}

verify_repo_revision
for service in \
    health-backend.socket health-backend celery-worker celery-beat; do
    test "$(systemctl show "$service" --property=ActiveState --value)" = \
        "active"
done

case "$phase" in
    enabled)
        test -f "$success_marker"
        test ! -L "$success_marker"
        test "$(stat -c '%U:%G:%a' "$success_marker")" = \
            "root:root:400"
        test "$(stat -c '%h' "$success_marker")" = "1"
        cmp -s "$success_marker" <(printf '%s\n' "$expected_success")
        flag_is_exact "$candidate_env" true
        flag_is_exact "$guard_env" false
        flag_is_exact "$repo/backend/.env" false
        cmp -s "$guard_env" "$repo/backend/.env"
        guard_hash="$(sha256sum "$guard_env" | awk '{print $1}')"
        expected_durable="$(mktemp)"
        printf '%s\n' \
            "# commit=$expected_sha" \
            "# guard_sha256=$guard_hash" \
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true" >"$expected_durable"
        cmp -s "$expected_durable" "$durable_enabled"
        rm -f -- "$expected_durable"
        flag_is_exact "$durable_enabled" true
        test ! -e "/run/reva-health-evidence-activation"
        for unit in \
            health-backend.service celery-worker.service celery-beat.service; do
            test ! -e \
                "/run/systemd/system/$unit.d/90-reva-health-evidence-activation.conf"
        done
        verify_process_environment true
        ;;
    staged)
        test ! -e "$success_marker"
        flag_is_exact "$guard_env" false
        flag_is_exact "$repo/backend/.env" false
        cmp -s "$guard_env" "$repo/backend/.env"
        test ! -e "$durable_enabled"
        test ! -e "/run/reva-health-evidence-activation"
        verify_process_environment false
        ;;
    *)
        exit 2
        ;;
esac

(
    cd "$repo/backend"
    if [ "$phase" = "enabled" ]; then
        HEALTH_EVIDENCE_RUNTIME_ENABLED=true \
            PYTHONPATH=. \
            venv/bin/python scripts/verify_runtime_only_kb_contract.py \
                --phase "$phase"
    else
        env -u HEALTH_EVIDENCE_RUNTIME_ENABLED \
            PYTHONPATH=. \
            venv/bin/python scripts/verify_runtime_only_kb_contract.py \
                --phase "$phase"
    fi
) >/dev/null
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"
REMOTE_ACTIVATION_PROOF
}

prove_health_evidence_activation_not_launched() {
    ssh "$SERVER" bash -s -- \
        "$REMOTE_ACTIVATION_STATE_DIR" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ACTIVATION_NOT_LAUNCHED'
set -euo pipefail
state_dir="$1"
release_lock="$2"
release_token="$3"
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"
test -d "$state_dir"
test ! -L "$state_dir"
test "$(stat -c '%U:%G:%a' "$state_dir")" = "root:root:700"
# launch-intent is atomically persisted and fsynced before the first D-Bus
# call. Therefore an entirely empty trusted state dir is durable proof that
# this exact sealed attempt has never launched.
test -z "$(find "$state_dir" -mindepth 1 -maxdepth 1 -print -quit)"
REMOTE_ACTIVATION_NOT_LAUNCHED
}

prove_health_evidence_services_inactive() {
    ssh "$SERVER" bash -s -- \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_ACTIVATION_CONTAINMENT'
set -euo pipefail
release_lock="$1"
release_token="$2"
test -r "$release_lock/token"
test "$(cat "$release_lock/token")" = "$release_token"
for service in \
    health-backend.socket health-backend celery-worker celery-beat; do
    test "$(systemctl show "$service" --property=ActiveState --value)" = \
        "inactive"
done
REMOTE_ACTIVATION_CONTAINMENT
}

activate_health_evidence_runtime() {
    local unit_name
    local launch_rc
    local adopted="${_REMOTE_RELEASE_LOCK_ADOPTED:-0}"

    if ! require_health_evidence_flag_value true; then
        print_error "受控启用要求本地 HEALTH_EVIDENCE_RUNTIME_ENABLED=true"
        return 1
    fi
    if ! verify_deployed_revision; then
        print_error "启用前 revision 校验失败"
        return 1
    fi

    unit_name="health-evidence-activation-${DEPLOY_EXPECTED_SHA:0:12}-$$.service"

    if [[ "$adopted" = "1" ]]; then
        # The adopted owner starts in preserve mode. Validate the original
        # sealed stage without writing it, then reconcile a terminal outcome
        # before evaluating any pre-launch staged contract.
        _REMOTE_RELEASE_LOCK_DELEGATED=1
        if ! stage_health_evidence_activation_artifacts; then
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "既有 health-evidence 激活事务不完整或已被修改"
            return 1
        fi
        if prove_health_evidence_activation_state enabled "$unit_name"; then
            _REMOTE_RELEASE_LOCK_DELEGATED=0
            _REMOTE_RELEASE_LOCK_ABANDONED=0
            print_success "既有 health-evidence 激活事务已证明成功"
            return 0
        fi
        if prove_health_evidence_activation_state staged "$unit_name"; then
            _REMOTE_RELEASE_LOCK_DELEGATED=0
            _REMOTE_RELEASE_LOCK_ABANDONED=0
            print_error "既有 health-evidence 激活事务已恢复到 flag=false guard"
            return 1
        fi
        if ! prove_health_evidence_activation_not_launched; then
            _REMOTE_RELEASE_LOCK_DELEGATED=1
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "既有 activation 已有 launch-intent 但尚无可信终态；现场与租约保留"
            return 1
        fi
    fi

    if ! verify_runtime_only_kb_contract "staged"; then
        if [[ "$adopted" = "1" ]]; then
            _REMOTE_RELEASE_LOCK_DELEGATED=1
            _REMOTE_RELEASE_LOCK_ABANDONED=1
        fi
        print_error "启用前 staged serving contract 失败"
        return 1
    fi

    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! verify_systemd_activation_capability; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "服务器 systemd 未通过 ExecStopPost deadman 能力探针"
        return 1
    fi
    if [[ "$adopted" != "1" ]]; then
        if ! stage_health_evidence_activation_artifacts; then
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "无法生成不可变 health-evidence 激活事务"
            return 1
        fi
        _REMOTE_RELEASE_LOCK_DELEGATED=0
    fi

    # Delegate before the first D-Bus/RPC that can create the persistent unit.
    # Any SSH/client interruption after this point keeps stage + lease in place.
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if run_health_evidence_activation_unit "$unit_name"; then
        launch_rc=0
    else
        launch_rc=$?
    fi

    if prove_health_evidence_activation_state enabled "$unit_name"; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        _REMOTE_RELEASE_LOCK_ABANDONED=0
        print_success "health-evidence runtime 已受控启用并通过真实 runtime eval"
        return 0
    fi

    if prove_health_evidence_activation_state staged "$unit_name"; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        _REMOTE_RELEASE_LOCK_ABANDONED=0
        print_error "health-evidence runtime 启用失败 (exit=$launch_rc)，已恢复并复验 flag=false guard"
        return 1
    fi

    _REMOTE_RELEASE_LOCK_ABANDONED=1
    if prove_health_evidence_services_inactive; then
        print_error "health-evidence runtime 未能恢复；service/socket 已隔离，发布锁与现场保留"
    else
        print_error "health-evidence runtime 结果不明确，无法证明服务已停止；发布锁与现场保留"
    fi
    return 1
}

# 查看服务状态
check_status() {
    print_step "服务器服务状态..."
    echo ""

    ssh $SERVER "
        echo '=== 前端服务 (PM2) ===' && \
        pm2 list && \
        echo '' && \
        echo '=== 后端服务 ===' && \
        systemctl status health-backend --no-pager | head -15
    "
}

# 查看日志
view_logs() {
    echo "选择要查看的日志:"
    echo "  1) 前端日志"
    echo "  2) 后端日志"
    echo "  3) 两者都看"
    read -p "请选择 (1/2/3): " choice

    case $choice in
        1)
            ssh $SERVER "journalctl -u health-frontend -n 50 --no-pager"
            ;;
        2)
            ssh $SERVER "journalctl -u health-backend -n 50 --no-pager"
            ;;
        3)
            ssh $SERVER "
                echo '=== 前端日志 ===' && \
                journalctl -u health-frontend -n 30 --no-pager && \
                echo '' && \
                echo '=== 后端日志 ===' && \
                journalctl -u health-backend -n 30 --no-pager
            "
            ;;
        *)
            print_error "无效选项"
            ;;
    esac
}

# 主函数
# 部署前检查 mobile/ 自上次 production OTA 以来的漂移; 有未推送的 mobile 改动就提示
# 默认交互式询问 [y/N], 用 -y/--yes 跳过
confirm_ota_drift() {
    local anchor_file="$SCRIPT_DIR/.last-ota-commit"
    if [[ ! -f "$anchor_file" ]]; then
        return 0
    fi
    local last_ota
    last_ota=$(tr -d '[:space:]' < "$anchor_file")
    if [[ -z "$last_ota" ]]; then
        return 0
    fi
    if ! git -C "$SCRIPT_DIR" cat-file -e "$last_ota" 2>/dev/null; then
        print_warning "OTA anchor commit ${last_ota:0:8} 在本地不存在 (可能被 rebase),跳过 drift 检查"
        return 0
    fi
    local mobile_commits
    mobile_commits=$(git -C "$SCRIPT_DIR" log --oneline "${last_ota}..HEAD" -- mobile/ 2>/dev/null || true)
    if [[ -z "$mobile_commits" ]]; then
        return 0
    fi
    echo ""
    print_warning "检测到 mobile/ 自上次 OTA (${last_ota:0:8}) 后有未推送改动:"
    echo "$mobile_commits" | sed 's/^/    /'
    echo ""
    if [[ "${AUTO_YES:-0}" -eq 1 ]]; then
        print_warning "已通过 -y 跳过确认; 部署完后请记得 ./scripts/mobile-ota.sh production"
        echo ""
        return 0
    fi
    if [[ ! -t 0 ]]; then
        # 非交互 (CI / 重定向),自动放行但提示
        print_warning "非交互环境,自动继续; 部署完后请记得 ./scripts/mobile-ota.sh production"
        echo ""
        return 0
    fi
    read -r -p "继续部署? 部署后再 OTA 也可以 [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS])
            echo ""
            return 0
            ;;
        *)
            print_error "已取消; 建议先跑 ./scripts/mobile-ota.sh production"
            exit 1
            ;;
    esac
}

main() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     健康应用部署脚本 v1.0              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""

    # 默认部署全部
    DEPLOY_MODE="all"
    AUTO_YES=0

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -a|--all)
                DEPLOY_MODE="all"
                shift
                ;;
            -f|--frontend)
                DEPLOY_MODE="frontend"
                shift
                ;;
            -b|--backend)
                DEPLOY_MODE="backend"
                shift
                ;;
            -e|--env)
                DEPLOY_MODE="env"
                shift
                ;;
            -H|--activate-health-evidence)
                DEPLOY_MODE="health-evidence"
                shift
                ;;
            -r|--restart)
                DEPLOY_MODE="restart"
                shift
                ;;
            -p|--push)
                DEPLOY_MODE="push"
                shift
                ;;
            -s|--status)
                DEPLOY_MODE="status"
                shift
                ;;
            -l|--logs)
                DEPLOY_MODE="logs"
                shift
                ;;
            -y|--yes)
                AUTO_YES=1
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                print_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done

    case $DEPLOY_MODE in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"restart"|"push")
            acquire_release_lock "deploy:${DEPLOY_MODE}"
            ;;
    esac
    case $DEPLOY_MODE in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"restart")
            acquire_remote_release_lock "deploy:${DEPLOY_MODE}"
            install_release_cleanup_traps
            assert_remote_release_lock
            ;;
    esac

    # 部署前先检查 mobile/ drift — 抓住"忘了 OTA"的常见错
    case $DEPLOY_MODE in
        "all"|"frontend"|"backend")
            confirm_ota_drift
            ;;
    esac

    # 执行对应操作
    case $DEPLOY_MODE in
        "all")
            push_code
            deploy_backend
            deploy_frontend
            echo ""
            check_status
            ;;
        "frontend")
            push_code
            deploy_frontend
            ;;
        "backend")
            push_code
            deploy_backend
            ;;
        "env")
            if ! require_health_evidence_flag_value false; then
                print_error "通用 -e 只允许保持健康证据运行时为 false；启用请使用 --activate-health-evidence"
                exit 1
            fi
            sync_env
            deactivate_health_evidence_runtime_before_mutation
            ;;
        "health-evidence")
            push_code
            activate_health_evidence_runtime
            ;;
        "restart")
            if ! require_health_evidence_flag_value false; then
                print_error "通用 restart 只允许 flag=false；flag=true 请使用 --activate-health-evidence 受控重启"
                exit 1
            fi
            deactivate_health_evidence_runtime_before_mutation
            restart_frontend_service
            ;;
        "push")
            push_code
            ;;
        "status")
            check_status
            ;;
        "logs")
            view_logs
            ;;
    esac

    arm_remote_release_cleanup_after_terminal_mode_success "$DEPLOY_MODE"

    echo ""
    print_success "完成！"
    echo ""
}

# 运行主函数。测试可 source 本文件并对部署边界做真实故障演练。
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
