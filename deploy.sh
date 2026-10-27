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
if [[ "${1:-}" = "--activate-edu-login" ]]; then
    shift
    exec /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_edu_login.py" "$@"
fi
if [[ "${1:-}" = "--activate-kbase-login" ]]; then
    shift
    exec /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_kbase_login.py" "$@"
fi
if [[ "${1:-}" = "--neo-wechat" ]]; then
    shift
    exec /usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_neo_wechat.py" "$@"
fi
if [[ "${1:-}" = "--select-vision-model" ]]; then
    shift
    exec /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_vision_model.py" "$@"
fi
if [[ "${1:-}" = "--prepare-frontend-artifact" ]]; then
    shift
    exec /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_frontend_artifact.py" "$@"
fi
if [[ "${1:-}" = "--publish-frontend-no-backup" ]]; then
    shift
    exec /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_frontend_no_backup.py" "$@"
fi
if [[ "${1:-}" = "--publish-frontend" ]]; then
    echo "无备份策略冻结旧前端发布/重建入口；未执行外部操作" >&2
    exit 1
fi
if [[ "${1:-}" = "--rebuild-deployed-frontend" ]]; then
    echo "无备份策略冻结旧前端发布/重建入口；未执行外部操作" >&2
    exit 1
fi
if [[ "${1:-}" = "--security-hardening" ]]; then
    shift
    exec /usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_public_host.py" "$@"
fi
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
SERVER="${DEPLOY_SERVER:-$(grep "^DEPLOY_SERVER=" "$ENV_FILE" | cut -d'=' -f2)}"
REMOTE_PATH="${DEPLOY_PATH:-$(grep "^DEPLOY_PATH=" "$ENV_FILE" | cut -d'=' -f2)}"
REMOTE_DEPLOY_BUNDLE="/tmp/health-app-deploy-$$-$(date +%s).bundle"
REMOTE_BACKUP_PREFLIGHT_DIR="/tmp/health-app-backup-preflight-$$-$(date +%s)"
REMOTE_BACKUP_RUNNER="$REMOTE_BACKUP_PREFLIGHT_DIR/backup_db.sh"
REMOTE_VERIFY_RECENT_OFFSITE="$REMOTE_BACKUP_PREFLIGHT_DIR/verify_recent_offsite_backup.sh"
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
ENV_SYNC_SAFETY_VALIDATED_SHA=""
ROLLBACK_CANDIDATE_COMMIT=""
ROLLBACK_COMMIT=""
RUNTIME_STATE_RESUME_PHASE="NONE"
RUNTIME_STATE_RESUME_TARGET="none"
RUNTIME_STATE_ALREADY_FINALIZED=0
REMOTE_RELEASE_LOCK_DIR="${REMOTE_RELEASE_LOCK_DIR:-/var/lock/health-app-release}"
REMOTE_RELEASE_STATE_DIR="${REMOTE_RELEASE_STATE_DIR:-/var/lib/reva-release-state}"
REMOTE_RELEASE_LOCK_TOKEN=""
_REMOTE_RELEASE_LOCK_ACQUIRED=0
_REMOTE_RELEASE_LOCK_DELEGATED=0
_REMOTE_RELEASE_LOCK_ABANDONED=0
_REMOTE_RELEASE_LOCK_ADOPTED=0
REQUIREMENTS_LOCK_SHA=""
SYSTEM_KB_INPUT_SHA=""
SYSTEM_KB_LEGACY_INPUT_SHA=""
SYSTEM_KB_ACTIVATION_REQUIRED=1

set_remote_backup_preflight_dir() {
    local stage_dir="$1"

    if [[ ! "$stage_dir" =~ ^/tmp/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*$ ]]; then
        print_error "远端发布 stage 路径不符合固定契约"
        return 1
    fi
    REMOTE_BACKUP_PREFLIGHT_DIR="$stage_dir"
    REMOTE_BACKUP_RUNNER="$stage_dir/backup_db.sh"
    REMOTE_VERIFY_RECENT_OFFSITE="$stage_dir/verify_recent_offsite_backup.sh"
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

# Diagnostic milestones only: integer seconds since this Bash started. Never
# wrap release commands here: an if/&& wrapper would change errexit semantics.
release_timing_checkpoint() {
    [[ "${1:-}" =~ ^[a-z_]{1,48}$ ]] || return 64
    printf 'REVA_RELEASE_TIMING phase=%s shell_elapsed_seconds=%s\n' "$1" "$SECONDS" >&2
}

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
        all|frontend|backend|env|health-evidence|app-store-review-reset|restart) ;;
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

check_remote_vision_model_history() {
    local publisher_sha local_sha
    local_sha="$(git -C "$SCRIPT_DIR" rev-parse HEAD)" || return 70
    publisher_sha="${DEPLOY_SOURCE_SHA:-$local_sha}"
    if ! [[ "$publisher_sha" =~ ^[0-9a-f]{40}$ ]] || [[ "$publisher_sha" != "$local_sha" ]]; then
        print_error "模型配置审计检查必须绑定精确本地发布源码"
        return 70
    fi
    # Fixed readonly system Python bootstrap checks the staged entry BEFORE it
    # executes. Never import a checker from the mutable live checkout.
    ssh "$SERVER" /usr/bin/python3.12 -I -S -B - "$publisher_sha" <<'REMOTE_VISION_MODEL_HISTORY'
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
try:
    sha = sys.argv[1]
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValueError("invalid binding")
    root = Path("/var/lib/reva-release/vision-models")
    bridge_root = Path("/var/lib/reva-release/neo-wechat")
    roots = [path for path in (root, bridge_root) if os.path.lexists(path)]
    if not roots:
        raise SystemExit(0)
    source = Path("/var/lib/reva-release/bootstrap") / sha / "source"
    entry = source / "scripts/trusted_vision_model.py"
    for path in [*reversed(entry.parents), entry, *roots, source / ".git/config"]:
        info = path.lstat()
        expected = stat.S_ISREG if path in (entry, source / ".git/config") else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not expected(info.st_mode) or (expected == stat.S_ISREG and info.st_nlink != 1):
            raise ValueError("unsafe staged checker")
    environment = {"PATH":"/usr/bin:/bin", "HOME":"/root", "LC_ALL":"C",
                   "GIT_CONFIG_NOSYSTEM":"1", "GIT_CONFIG_GLOBAL":"/dev/null",
                   "GIT_CONFIG_SYSTEM":"/dev/null", "GIT_NO_REPLACE_OBJECTS":"1"}
    def git(*args):
        return subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                               "-C",str(source),*args],env=environment,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=30,text=True).stdout.strip()
    if git("rev-parse","HEAD") != sha:
        raise ValueError("staged revision differs")
    raw = entry.read_bytes()
    if len(raw) > 1000000 or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != git("rev-parse",sha+":scripts/trusted_vision_model.py"):
        raise ValueError("staged checker hash differs")
    os.execve("/usr/bin/python3.12",["/usr/bin/python3.12","-I","-S","-B",str(entry),"--check-history","--publisher-sha",sha],environment)
except Exception:
    print("vision model history admission failed",file=sys.stderr)
    raise SystemExit(70)
REMOTE_VISION_MODEL_HISTORY
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
    # Git replaces mktemp's inode; create under a private umask so SCP receives
    # a 0600 bundle without changing the caller's umask or relaxing remote gates.
    if ! [[ "$ROLLBACK_CANDIDATE_COMMIT" =~ ^[0-9a-f]{40}$ ]] ||
       [ "$(git rev-parse refs/reva-production 2>/dev/null || true)" != "$ROLLBACK_CANDIDATE_COMMIT" ] ||
       ! (umask 077; git bundle create "$bundle" HEAD "^$ROLLBACK_CANDIDATE_COMMIT" >/dev/null); then
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

# checkout 之前先上传当前精确 SHA 的发布工具；仅校验工具输入，不执行备份，
# 避免旧 checkout 缺少恢复演练或站外归档闸门。
stage_backup_preflight_scripts() {
    local scripts=(
        "$SCRIPT_DIR/backend/scripts/backup_db.sh"
        "$SCRIPT_DIR/backend/scripts/verify_backup_restore.sh"
        "$SCRIPT_DIR/backend/scripts/archive_backup_offsite.sh"
        "$SCRIPT_DIR/backend/scripts/verify_recent_offsite_backup.sh"
        "$SCRIPT_DIR/backend/scripts/rollback_release.sh"
        "$SCRIPT_DIR/backend/scripts/activate_health_evidence_runtime.sh"
        "$SCRIPT_DIR/backend/scripts/verify_locked_requirements.py"
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
        verify_recent_offsite_backup.sh|\
        rollback_release.sh|\
        activate_health_evidence_runtime.sh|\
        verify_locked_requirements.py|\
        verify_runtime_schema_compatibility.py|\
        quarantine_runtime_only_kb.py|\
        runtime_state_release_transaction.py|\
        review_manifest.json|\
        health-backend-runtime-state.conf|\
        celery-worker-runtime-state.conf|\
        celery-beat-runtime-state.conf|\
        staged.sha256)
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
        verify_recent_offsite_backup.sh
        rollback_release.sh
        activate_health_evidence_runtime.sh
        verify_locked_requirements.py
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
        $2 == "verify_recent_offsite_backup.sh" ||
        $2 == "rollback_release.sh" ||
        $2 == "activate_health_evidence_runtime.sh" ||
        $2 == "verify_locked_requirements.py" ||
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
        { exit 1 }
        END { if (allowed != 14) exit 1 }
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
                verify_recent_offsite_backup.sh \
                rollback_release.sh \
                activate_health_evidence_runtime.sh \
                verify_locked_requirements.py \
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
        preflight-code|prepare-code|install)
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
    local transaction_mode
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
    transaction_mode="$(runtime_state_status_field "$status_output" mode)" || transaction_mode=""
    if [[ "$transaction_mode" != "code-only-no-backup" ]]; then
        # A completely finalized legacy receipt is an idle baseline only. It
        # is never accepted as this new candidate's no-backup success proof.
        if [[ -z "$transaction_mode" && "$state_source" = "terminal" &&
              "$phase" = "COMMITTED" && "$release_target" = "candidate" &&
              "$next_action" = "none" &&
              "$old_sha" =~ ^[0-9a-f]{40}$ &&
              "$candidate_sha" =~ ^[0-9a-f]{40}$ &&
              "$old_sha" != "$candidate_sha" &&
              "$candidate_sha" != "$DEPLOY_EXPECTED_SHA" ]] &&
           [[ "$(runtime_state_status_field "$status_output" gate_armed)" = false &&
              "$(runtime_state_status_field "$status_output" gate_released)" = true ]]; then
            remote_head="$(ssh "$SERVER" "git -C '$REMOTE_PATH' rev-parse HEAD")" || return 1
            if [[ "$remote_head" = "$candidate_sha" ]]; then
                RUNTIME_STATE_RESUME_PHASE="NONE"
                RUNTIME_STATE_RESUME_TARGET="none"
                _REMOTE_RELEASE_LOCK_ABANDONED=0
                print_step "旧终态回执仅作为发布前 SHA 基线；未读取或恢复旧快照"
                return 0
            fi
        fi
        print_error "既有事务不是可接受的 idle baseline 或无备份 code-only 模式；现场与租约保留，未读取旧快照"
        return 1
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
        test \"\$(awk 'NF { count += 1 } END { print count + 0 }' staged.sha256)\" = 14
        test ! -e backend.env.rollback
        test ! -e backend.env.candidate
        sha256sum --strict -c staged.sha256 >/dev/null
    " || ! verify_live_env_matches_candidate; then
        print_error "code-only 续接制品或现行配置证明失败；现场与租约保留"
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
    # of this exact code-only candidate is the only safe point that arms cleanup.
    _REMOTE_RELEASE_LOCK_ABANDONED=1
}

remote_repository_trust_normalization_command() {
    cat <<'REMOTE_REPOSITORY_TRUST'
(
    set -euo pipefail
    echo '规范化受信发布工作树 ownership...'
    # This subshell is a caller's AND-list operand, where errexit is disabled.
    # Every proof/mutation must therefore propagate failure explicitly.
    test -d .git && test ! -L .git || exit 1
    chown root:root . || exit "$?"
    chmod 0755 . || exit "$?"
    chown -R root:root .git || exit "$?"
    chmod -R go-w .git || exit "$?"
    # Batch only index-selected paths; never recurse into ignored runtime data.
    # Validate all paths first, secure each parent once, then process bounded
    # argv batches. Isolated stdlib Python is independent of app dependencies.
    /usr/bin/python3 -I -S -B - <<'REVA_TRACKED_PERMISSIONS' || exit "$?"
import os
import stat
import subprocess

def require(condition):
    if not condition:
        raise ValueError('invalid tracked permission target')

def batches(command, paths):
    batch, size = [], 0
    for path in paths:
        cost = len(os.fsencode(path)) + 1
        require(cost <= 32768)
        if batch and (len(batch) >= 128 or size + cost > 32768):
            subprocess.run(command + batch, check=True)
            batch, size = [], 0
        batch.append(path)
        size += cost
    if batch:
        subprocess.run(command + batch, check=True)

try:
    raw = subprocess.check_output(['git', 'ls-files', '--stage', '-z'])
    require(bool(raw) and raw.endswith(b'\0'))
    paths, parents = set(), set()
    groups = {'100644': [], '100755': [], '120000': []}
    for entry in raw[:-1].split(b'\0'):
        metadata, path_bytes = entry.split(b'\t', 1)
        mode, oid, stage = metadata.decode('ascii').split()
        path = os.fsdecode(path_bytes)
        parts = path.split('/')
        require(mode in groups and stage == '0' and path not in paths)
        require(all(part not in ('', '.', '..', '.git') for part in parts))
        paths.add(path)
        for index in range(1, len(parts)):
            parent = '/'.join(parts[:index])
            if parent not in parents:
                require(stat.S_ISDIR(os.lstat(parent).st_mode))
                parents.add(parent)
        info = os.lstat(path)
        require(stat.S_ISLNK(info.st_mode) if mode == '120000' else
                stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        groups[mode].append(path)
    directories = sorted(parents, key=lambda path: (path.count('/'), path))
    batches(['chown', '-h', 'root:root', '--'], directories)
    batches(['chmod', '0755', '--'], directories)
    for mode, targets in groups.items():
        batches(['chown', '-h', 'root:root', '--'], targets)
        if mode != '120000':
            batches(['chmod', '0755' if mode == '100755' else '0644', '--'], targets)
except (OSError, ValueError, subprocess.SubprocessError):
    raise SystemExit('tracked permission normalization failed')
REVA_TRACKED_PERMISSIONS
    test "$(stat -c '%U:%G' .)" = "root:root" || exit 1
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
        echo '验证服务器工作树干净（不创建旧代码副本）...' &&
        test -z "\$(git status --porcelain)" &&
        echo '同步到已核验的 main commit $DEPLOY_EXPECTED_SHA...' &&
        ( (git fetch origin main && git cat-file -e '$DEPLOY_EXPECTED_SHA^{commit}') ||
          (echo 'git fetch origin 失败或缺少目标 commit, 使用上传的 deploy bundle...' &&
           git fetch '$REMOTE_DEPLOY_BUNDLE' HEAD && git cat-file -e '$DEPLOY_EXPECTED_SHA^{commit}') ) &&
        release_timing_checkpoint remote_git_fetch_completed &&
        git checkout -B main '$DEPLOY_EXPECTED_SHA' &&
        test "\$(git rev-parse HEAD)" = '$DEPLOY_EXPECTED_SHA' &&
        release_timing_checkpoint remote_git_checkout_completed &&
        $trust_normalization &&
        release_timing_checkpoint remote_permissions_completed
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
    echo "  -e, --env       当前禁止（无备份发布不支持配置变更）"
    echo "  -H, --activate-health-evidence  当前禁止（需无备份运行态变更协议）"
    echo "  -R, --reset-app-store-review  重置 App Store 审核演示数据（不改密码）"
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
    echo "  ./deploy.sh -R        # 受控重置审核账号演示数据与默认会话"
    echo "  ./deploy.sh -r        # 仅重启服务"
    echo "  ./deploy.sh -s        # 查看服务状态"
}

# ============================================================
# 部署安全：备份、验证、回滚 (借鉴 autoresearch 快速失败理念)
# ============================================================

HEALTH_CHECK_URL=""  # 在 deploy_backend/deploy_frontend 中设置
DEPLOY_SCORE_THRESHOLD=35  # 部署后健康度最低分（满分60，skip-tests模式）

# 准备并校验发布工具；禁止新增备份、恢复演练和站外归档。
backup_database() {
    local delegation_owner=0
    if [[ "${DEPLOY_DATABASE_BACKUP-0}" != "0" ]]; then
        print_error "无备份发布策略禁止 DEPLOY_DATABASE_BACKUP 启用备份；旧配置不构成授权"
        return 1
    fi
    print_step "准备无备份发布工具..."
    if [[ "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "1" ]]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=1
        delegation_owner=1
    fi
    if ! stage_backup_preflight_scripts; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "发布工具准备失败或结果未知；发布锁与现场保留"
        return 1
    fi
    if [ "$delegation_owner" -eq 1 ]; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
    fi
    print_success "发布工具已校验；未执行备份、恢复演练或站外归档"
}

# 记录当前 commit 作为发布前 SHA 证明（不复制旧代码）
save_rollback_point() {
    local rollback_commit
    rollback_commit=$(
        ssh "$SERVER" "cd '$REMOTE_PATH' && git rev-parse HEAD" 2>/dev/null ||
            true
    )
    if ! [[ "$rollback_commit" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法取得合法的发布前生产 SHA"
        return 1
    fi
    ROLLBACK_CANDIDATE_COMMIT="$rollback_commit"
    print_step "发布前 SHA: ${ROLLBACK_CANDIDATE_COMMIT:0:8}"
}

verify_rollback_point_schema_compatibility() {
    local probe_output

    assert_remote_release_lock
    if ! [[ "$ROLLBACK_CANDIDATE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "发布前 SHA 非法，拒绝兼容性预检"
        return 1
    fi
    print_step "验证当前生产 SHA 与实时 schema 兼容..."
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
    print_success "发布前生产 SHA 已验证并记录: ${ROLLBACK_COMMIT:0:12}"
}

verify_code_only_source_changes() {
    DAILY_JOURNEY_ADDITIVE=0
    if ! [[ "$ROLLBACK_CANDIDATE_COMMIT" =~ ^[0-9a-f]{40}$ &&
            "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无备份 source compatibility 缺少精确 SHA"
        return 1
    fi
    if ! git -C "$SCRIPT_DIR" diff --quiet "$ROLLBACK_CANDIDATE_COMMIT" "$DEPLOY_EXPECTED_SHA" -- \
        backend/migrations/managed backend/app/models infra/systemd/dropins; then
        local admission
        if ! admission=$(python3 "$SCRIPT_DIR/scripts/daily_journey_release.py" source-check \
            "$ROLLBACK_CANDIDATE_COMMIT" "$DEPLOY_EXPECTED_SHA" --source "$SCRIPT_DIR") ||
            [[ "$admission" != "DAILY_JOURNEY_ADDITIVE" ]]; then
            print_error "无备份发布拒绝未受审的 schema/models/runtime 变更；尚未停写"
            return 1
        fi
        DAILY_JOURNEY_ADDITIVE=1
    fi
}

daily_journey_release_command() {
    local phase="$1" loader
    [[ "$phase" = preflight || "$phase" = apply || "$phase" = readback ]] || return 1
    [[ "$REMOTE_PATH" = /opt/health-app && "$REMOTE_RELEASE_LOCK_DIR" = /var/lock/health-app-release ]] || return 1
    # Authenticate the immutable canonical helper before executing any of its
    # Python. No code/credential is uploaded, and no secret enters this argv.
    loader="$(cat <<'DAILY_JOURNEY_LOADER'
import hashlib, os, pathlib, re, stat, subprocess, sys
try:
    sha, old, token, phase = sys.argv[1:]
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('binding')
    source = pathlib.Path('/var/lib/reva-release/bootstrap') / sha / 'source'
    entry = source / 'scripts/daily_journey_release.py'
    for path in [*reversed(entry.parents), entry, source / '.git/config']:
        item = path.lstat()
        file = path in (entry, source / '.git/config')
        if item.st_uid != 0 or item.st_mode & 0o022 or not (stat.S_ISREG(item.st_mode) if file else stat.S_ISDIR(item.st_mode)) or (file and item.st_nlink != 1):
            raise ValueError('metadata')
    env = {'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1'}
    def git(*args):
        return subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-C',str(source),*args],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=30).stdout.strip()
    raw = entry.read_bytes()
    if git('rev-parse','HEAD') != sha.encode() or len(raw) > 1000000 or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest().encode() != git('rev-parse',sha+':scripts/daily_journey_release.py'):
        raise ValueError('source')
    executable = '/opt/health-app/backend/venv/bin/python'
    os.execve(executable,[executable,'-I','-B',str(entry),phase,old,sha,'--lease-token',token],env)
except Exception:
    print('DAILY_JOURNEY_RELEASE_BLOCKED: canonical helper admission failed',file=sys.stderr)
    raise SystemExit(70)
DAILY_JOURNEY_LOADER
)" || return 1
    printf '/usr/bin/python3.12 -I -S -B -c %q %q %q %q %q' \
        "$loader" "$DEPLOY_EXPECTED_SHA" "$ROLLBACK_CANDIDATE_COMMIT" "$REMOTE_RELEASE_LOCK_TOKEN" "$phase"
}

daily_journey_release_preflight() {
    [[ "${DAILY_JOURNEY_ADDITIVE:-0}" = 1 ]] || return 0
    local command output
    command="$(daily_journey_release_command preflight)" || return 1
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    if ! output=$(ssh "$SERVER" "$command") ||
       [[ "$output" != "DAILY_JOURNEY_PREFLIGHT_OK pending=1" &&
          "$output" != "DAILY_JOURNEY_READBACK_OK committed=1" ]]; then
        print_error "行程新增表预检未通过；未停写，原租约和迁移意图保留"
        return 1
    fi
    _REMOTE_RELEASE_LOCK_ABANDONED=0
    printf '%s\n' "$output"
}

# 回滚到上一个版本
rollback_deploy() {
    # No new rollback copy exists in code-only releases. Never invoke a legacy
    # restore script against the current candidate or release its evidence.
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    print_error "NEEDS_OPERATOR：无备份发布失败，未自动恢复旧代码/配置/运行态；发布锁与现场保留"
    return 1
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

    BACKEND_EXEC_START=$(ssh $SERVER \
        "systemctl show health-backend --property=ExecStart --value" \
        2>/dev/null)
    if [[ "$BACKEND_EXEC_START" != *"--workers 1"* ]] ||
       [[ "$BACKEND_EXEC_START" == *"--workers 2"* ]]; then
        print_error "Garmin MFA 单 worker 约束未生效，阻断部署"
        return 1
    fi

    sleep 2

    SCORE=$(ssh $SERVER "
        cd $REMOTE_PATH/backend && \
        source venv/bin/activate && \
        python scripts/system_health_score.py --skip-tests --allow-paused-runtime --url http://localhost:8000 --json 2>/dev/null
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
detail = circuit.get('detail')
deferred = payload.get('deferred_failures')
if not isinstance(detail, str) or not isinstance(deferred, list):
    raise SystemExit(1)
if circuit.get('healthy') is False:
    match = re.fullmatch(r'paused:reconciliation_detected:generation=([0-9]+):ack=([0-9]+)', detail)
    if (circuit.get('release_safe') is not True or
        deferred != ['agent_runtime_circuit'] or match is None):
        raise SystemExit(1)
    generation, acknowledged = map(int, match.groups())
    if not (0 <= acknowledged < generation):
        raise SystemExit(1)
elif circuit.get('healthy') is not True or deferred:
    raise SystemExit(1)
print(re.sub(r'[^A-Za-z0-9_.:=,-]', '_', detail)[:160])
" 2>/dev/null)

    if [[ -z "$TOTAL" || -z "$PASSED" || "$MAXIMUM" != "60" ||
          -z "$CRITICAL_FAILURES" || -z "$AGENT_RUNTIME_CIRCUIT" ]]; then
        print_error "健康度 JSON 契约无效，阻断部署"
        return 1
    fi

    if [[ "$PASSED" == "true" && "$CRITICAL_FAILURES" == "none" ]]; then
        if [[ "$AGENT_RUNTIME_CIRCUIT" == paused:* ]]; then
            print_warning "Runtime 恢复已延后，保留现有账号隔离: ${AGENT_RUNTIME_CIRCUIT}"
        fi
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

# 旧 env 备份入口明确冻结，普通发布只核对现行配置摘要
backup_remote_env() {
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    print_error "无备份策略禁止复制旧配置；未创建 env 备份或回退副本"
    return 1
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
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    print_error "无备份策略不支持 env 回退快照；发布锁与现场保留"
    return 1
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
    # Current production config is never downloaded or copied into a rollback
    # artifact. Validate the supplied input, then compare only its digest.
    local key value
    while read -r key value; do
        if ! require_canonical_env_assignment "$key" "$value"; then
            print_error "env 必须保持规范的 production/runtime 配置；无备份发布不支持配置变更"
            return 1
        fi
    done <<'CANONICAL_ENV'
APP_ENV production
DEBUG False
HEALTH_RUNTIME_DATA_DIR /var/lib/health-app/runtime
HEALTH_UPLOAD_DIR /var/lib/health-app/uploads
HEALTH_SKILLS_CACHE_DIR /var/cache/health-app/skills-hub
DEDAO_KBASE_REVIEW_ARTIFACT_DIR /var/lib/health-app/dedao-kbase/workspace
LEGACY_KNOWLEDGE_RUNTIME_ENABLED false
HEALTH_EVIDENCE_RUNTIME_ENABLED false
CANONICAL_ENV
}

verify_live_env_matches_candidate() {
    local candidate_hash proof
    candidate_hash="$(
        set -o pipefail
        awk '!/^DEPLOY_SERVER=/ && !/^DEPLOY_PATH=/ && !/^#.*服务器信息/ && !/^# -.*deploy\.sh/' "$ENV_FILE" |
            shasum -a 256 | awk 'NR == 1 { print $1 }'
    )" || return 1
    [[ "$candidate_hash" =~ ^[0-9a-f]{64}$ ]] || return 1
    if ! proof="$(ssh "$SERVER" bash -s -- \
        "$REMOTE_PATH/backend/.env" "$candidate_hash" <<'REMOTE_CODE_ONLY_ENV'
set -euo pipefail
live_env="$1"
expected_hash="$2"
test -f "$live_env"
test ! -L "$live_env"
test "$(stat -c '%h' "$live_env")" = 1
metadata="$(stat -c '%U:%G:%a' "$live_env")"
if [ "$metadata" != root:root:600 ] &&
   [ "$metadata" != root:root:640 ] &&
   [ "$metadata" != root:health-app:640 ]; then
    echo 'unsafe live env metadata' >&2
    exit 1
fi
actual_hash="$(sha256sum "$live_env" | awk 'NR == 1 { print $1 }')"
test "$actual_hash" = "$expected_hash"
printf 'CODE_ONLY_ENV_OK sha256=%s\n' "$actual_hash"
REMOTE_CODE_ONLY_ENV
    )"; then
        print_error "现行 env 与候选配置不同或权限不安全；配置尚未改变，无备份发布阻断"
        return 1
    fi
    if [[ "$proof" != "CODE_ONLY_ENV_OK sha256=$candidate_hash" ]]; then
        print_error "现行 env 摘要证明无效；配置尚未改变"
        return 1
    fi
}

validate_deploy_env_preflight() {
    local env_sha

    if [[ ! -r "$ENV_FILE" ]]; then
        print_error "待同步 env 文件不可读"
        return 1
    fi
    env_sha="$(shasum -a 256 "$ENV_FILE" | awk 'NR==1 {print $1}')"
    if ! [[ "$env_sha" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "无法计算待同步 env 文件摘要"
        return 1
    fi
    if [[ "$ENV_SYNC_SAFETY_VALIDATED_SHA" == "$env_sha" ]]; then
        verify_live_env_matches_candidate
        return $?
    fi
    print_step "部署前快速校验生产 env..."
    if ! validate_env_sync_safety || ! validate_langbridge_env; then
        return 1
    fi
    if ! verify_live_env_matches_candidate; then
        return 1
    fi
    ENV_SYNC_SAFETY_VALIDATED_SHA="$env_sha"
    print_success "生产 env 预检通过"
}

# 同步环境变量到服务器
sync_env() {
    print_step "验证无备份发布的现行配置..."
    validate_deploy_env_preflight || return 1
    print_success "现行 env 未改变；仅验证摘要与权限，未生成配置副本"
}

# 去激活事务已经完成 backend/Celery 的最后一次重启和逐 PID flag=false
# 证明；通用 env/restart 模式此后只能重启前端，不能再让后端越过证明点。
frontend_runtime_kind() {
    # A protected unit/receipt is a one-way migration marker. Unknown state or
    # transport failure cannot select the legacy root PM2 path.
    ssh "$SERVER" /bin/bash -s <<'FRONTEND_KIND'
set -euo pipefail
if test -e /etc/systemd/system/health-network-guard.service ||
   test -d /var/backups/health-app/host-security; then
    test "$(stat -c '%U:%a' /etc/systemd/system/health-frontend.service)" = root:644
    test "$(systemctl show health-frontend -p User --value)" = health-web
    systemctl is-enabled --quiet health-frontend
    systemctl is-active --quiet health-network-guard
    echo hardened
else
    pm2 jlist | /usr/bin/python3 -c '
import json,sys
items=[x for x in json.load(sys.stdin) if x.get("name")=="health-frontend"]
assert len(items)==1
p=items[0]["pm2_env"]
assert p.get("pm_cwd")=="/opt/health-app/frontend" and p.get("pm_exec_path")=="/usr/bin/npm"
assert p.get("status")=="online"
print("legacy")'
fi
FRONTEND_KIND
}

restart_frontend_service() {
    print_step "重启前端服务..."
    assert_remote_release_lock_if_acquired
    local runtime_kind
    runtime_kind=$(frontend_runtime_kind) || { print_error "无法确认前端运行身份，禁止降级"; return 1; }
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    case "$runtime_kind" in
        hardened) ssh "$SERVER" "systemctl restart health-frontend && systemctl is-active --quiet health-frontend" ;;
        legacy) ssh "$SERVER" "pm2 restart health-frontend && pm2 describe health-frontend >/dev/null" ;;
        *) return 1 ;;
    esac || {
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "前端重启结果不明确；发布锁与现场保留"
        return 1
    }
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
        if [[ -n "${DEPLOY_SOURCE_SHA:-}" ]]; then
            print_error "精确 revision 发布拒绝未跟踪文件"
            exit 1
        fi
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

    # The hosted release executor has read-only GitHub permissions. It already
    # verified canonical source and exact CI before invoking this script. This
    # option is source selection, NOT a credential or a bootstrap-trust bypass.
    if [[ -n "${DEPLOY_SOURCE_SHA:-}" ]]; then
        if ! [[ "$DEPLOY_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] ||
                [[ "$DEPLOY_SOURCE_SHA" != "$DEPLOY_EXPECTED_SHA" ]]; then
            print_error "精确 revision 与待部署 HEAD 不一致"
            exit 1
        fi
    else
        git push origin HEAD:main
    fi
    local remote_main_sha
    remote_main_sha=$(git ls-remote origin refs/heads/main | awk 'NR==1 {print $1}')
    if [[ "$remote_main_sha" != "$DEPLOY_EXPECTED_SHA" ]]; then
        print_error "origin/main 与本地 HEAD 不一致，拒绝部署"
        exit 1
    fi
    compute_release_input_digests
    print_success "已核验 origin/main: ${DEPLOY_EXPECTED_SHA:0:12}"

    # 同步到 kuaishou GitLab（静默，失败不影响部署）
    if [[ -z "${DEPLOY_SOURCE_SHA:-}" ]] && git remote | grep -q kuaishou; then
        git push kuaishou main 2>/dev/null && print_success "代码已同步到 kuaishou GitLab" || print_warning "kuaishou GitLab 同步失败（不影响部署）"
    fi
}

# 部署前端
deploy_frontend() {
    print_step "部署前端..."
    assert_remote_release_lock_if_acquired
    local runtime_kind
    runtime_kind=$(frontend_runtime_kind) || { print_error "无法确认前端运行身份，禁止 root 构建"; return 1; }
    if [[ "$runtime_kind" != legacy ]]; then
        print_error "已加固前端禁止 root 构建/PM2 回退；请使用受审隔离前端重建流程"
        return 1
    fi

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
        )" = "inactive" || return 1
    done
}

normalize_stopped_timeout_unit() {
    local unit="$1"
    local active_state
    local probe
    local value
    active_state="$(systemctl show "$unit" --property=ActiveState --value)" || return 1
    [ "$active_state" != "inactive" ] || return 0
    # A completed systemd stop timeout leaves a sticky failed state. Clear only
    # that known state, after proving no main/control process or cgroup remains.
    # Startup failures and unknown/partially stopped services remain blocking.
    case "$unit" in
        health-backend.service|celery-worker.service|celery-beat.service) ;;
        *) return 1 ;;
    esac
    [ "$active_state" = "failed" ] || return 1
    for probe in SubState:failed Result:timeout MainPID:0 ControlPID:0; do
        value="$(systemctl show "$unit" --property="${probe%%:*}" --value)" || return 1
        [ "$value" = "${probe#*:}" ] || return 1
    done
    local control_group
    control_group="$(systemctl show "$unit" --property=ControlGroup --value)" || return 1
    [ -z "$control_group" ] || return 1
    [ ! -e "$cgroup_root/system.slice/$unit" ] &&
        [ ! -L "$cgroup_root/system.slice/$unit" ] || return 1
    assert_release_lease || return 1
    systemctl reset-failed "$unit" || return 1
    assert_release_lease || return 1
    active_state="$(systemctl show "$unit" --property=ActiveState --value)" || return 1
    [ "$active_state" = "inactive" ] || return 1
    echo "DEACTIVATION_STOP_TIMEOUT_CLEARED unit=$unit"
}

stop_and_prove_services_inactive() {
    local unit
    # Socket first: no health probe may reactivate the backend while the
    # authorization and live environment are being changed.
    for unit in "${all_units[@]}"; do
        assert_release_lease
        if ! systemctl stop "$unit"; then
            [ "$(systemctl show "$unit" --property=ActiveState --value)" = "failed" ] || return 1
        fi
        normalize_stopped_timeout_unit "$unit" || return 1
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
        )" || return 1
        [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] && [ "$main_pid" -gt 1 ] || return 1
        control_group="$(
            systemctl show "$unit" --property=ControlGroup --value \
                2>/dev/null
        )" || return 1
        [[ "$control_group" =~ ^/[A-Za-z0-9_.@:/\\-]+$ ]] || return 1
        [[ "$control_group" != *"/../"* ]] || return 1
        procs_file="${cgroup_root}${control_group}/cgroup.procs"
        test -r "$procs_file" || return 1
        process_count=0
        main_pid_seen=0
        while IFS= read -r pid; do
            [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ "$pid" -gt 1 ] || return 1
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
                ' || return 1
        done <"$procs_file"
        [ "$process_count" -gt 0 ] && [ "$main_pid_seen" -eq 1 ] || return 1
    done
}

startup_service_snapshot() {
    local unit active sub result pid restarts entered group
    for unit in "${all_units[@]}"; do
        active="$(systemctl show "$unit" --property=ActiveState --value)" || return 1
        sub="$(systemctl show "$unit" --property=SubState --value)" || return 1
        result="$(systemctl show "$unit" --property=Result --value)" || return 1
        [ "$active" = active ] && [ "$result" = success ] || return 1
        if [ "$unit" = health-backend.socket ]; then
            case "$sub" in listening|running) ;; *) return 1 ;; esac
            printf '%s:%s\n' "$unit" "$sub"
            continue
        fi
        [ "$sub" = running ] || return 1
        pid="$(systemctl show "$unit" --property=MainPID --value)" || return 1
        restarts="$(systemctl show "$unit" --property=NRestarts --value)" || return 1
        entered="$(systemctl show "$unit" --property=ActiveEnterTimestampMonotonic --value)" || return 1
        group="$(systemctl show "$unit" --property=ControlGroup --value)" || return 1
        [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ "$pid" -gt 1 ] || return 1
        [[ "$restarts" =~ ^[0-9]+$ ]] || return 1
        [[ "$entered" =~ ^[1-9][0-9]*$ ]] || return 1
        printf '%s:%s:%s:%s:%s\n' "$unit" "$pid" "$restarts" "$entered" "$group"
    done
}

await_false_startup() {
    local attempt before after previous=""
    # Type=simple becoming active is not proof that exec/EnvironmentFile
    # handoff has completed. Require two unchanged, fully verified snapshots
    # across a polling interval; the outer proof still checks its 7s window.
    # Every predicate returns explicitly: errexit is disabled inside `if`.
    for ((attempt=0; attempt<30; attempt++)); do
        assert_release_lease || return 1
        verify_flag_file_false "$target_env" || return 1
        verify_runtime_authorization_absent || return 1
        if before="$(startup_service_snapshot)" &&
            verify_process_environment_false &&
            after="$(startup_service_snapshot)" && [ "$before" = "$after" ]; then
            assert_release_lease || return 1
            if [ -n "$previous" ] && [ "$previous" = "$after" ]; then
                return 0
            fi
            previous="$after"
        else
            previous=""
        fi
        if [ "$attempt" -lt 29 ]; then sleep 1 || return 1; fi
    done
    echo "DEACTIVATION_STARTUP_NOT_READY services=unverified" >&2
    return 1
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
await_false_startup
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

remote_dependency_sync_command() {
    if [[ ! "$REMOTE_RELEASE_STATE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ||
          "$REMOTE_RELEASE_STATE_DIR" = "/" ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/../"* ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/.." ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/./"* ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/." ||
          ! "$REQUIREMENTS_LOCK_SHA" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "发布依赖状态目录或 requirements digest 非法"
        return 70
    fi
    cat <<REMOTE_DEPENDENCY_SYNC
$(declare -f release_timing_checkpoint)
verify_backend_runtime_dependencies() {
    # Root metadata checks cannot prove that the backend can import new wheels.
    # Use the fixed service identity, clean environment and no production secret.
    /usr/sbin/runuser -u health-app -- /usr/bin/env -i PATH=/usr/bin:/bin \
        "\$(pwd -P)/venv/bin/python" -I -B scripts/verify_locked_requirements.py \
        --runtime-user health-app requirements.lock
}
sync_backend_dependencies() {
    # Pi is a required backend runtime; the Python lock cache cannot prove it.
    release_timing_checkpoint remote_pi_install_started || return "\$?"
    bash pi-runtime/install.sh || return "\$?"
    release_timing_checkpoint remote_pi_install_completed || return "\$?"
    release_state_dir='$REMOTE_RELEASE_STATE_DIR'
    requirements_marker="\${release_state_dir}/requirements-lock.sha256"
    requirements_expected='$REQUIREMENTS_LOCK_SHA'
    umask 077
    if [ ! -e "\${release_state_dir}" ]; then
        mkdir "\${release_state_dir}" || return 1
        chmod 700 "\${release_state_dir}" || return 1
    fi
    if ! test -d "\${release_state_dir}" ||
       ! test ! -L "\${release_state_dir}" ||
       [ "\$(stat -c '%U:%G:%a' "\${release_state_dir}")" != 'root:root:700' ]; then
        echo 'release state directory failed ownership/mode proof' >&2
        return 1
    fi
    marker_exists=0
    if [ -e "\${requirements_marker}" ] || [ -L "\${requirements_marker}" ]; then
        if ! test -f "\${requirements_marker}" ||
           ! test ! -L "\${requirements_marker}" ||
           [ "\$(stat -c '%U:%G:%a' "\${requirements_marker}")" != 'root:root:600' ] ||
           [ "\$(stat -c '%h' "\${requirements_marker}")" != '1' ]; then
            echo 'requirements marker failed ownership/link proof' >&2
            return 1
        fi
        marker_exists=1
    fi
    if [ "\${marker_exists}" = '1' ] &&
       [ "\$(cat "\${requirements_marker}")" = "\${requirements_expected}" ] &&
       python scripts/verify_locked_requirements.py requirements.lock &&
       python scripts/prune_unlocked_requirements.py --check requirements.lock &&
       python -m pip check &&
       verify_backend_runtime_dependencies; then
        echo 'dependency lock unchanged; verified install reused'
        return 0
    fi
    # A marker is only evidence for the environment that just failed
    # verification. Invalidate it durably before attempting any repair so an
    # uninstall/install failure cannot leave stale state looking reusable.
    if [ "\${marker_exists}" = '1' ]; then
        rm -f -- "\${requirements_marker}" || return 1
        sync -f "\${release_state_dir}" || return 1
    fi
    echo '安装锁定依赖...'
    # urllib3-future's wheel installs a .pth startup hook that replaces the
    # separately locked urllib3 tree on every Python startup.  Its upstream
    # source build supports the reviewed no-override mode, which preserves
    # both distributions and lets the service-identity RECORD proof inspect
    # the complete environment.  Repair an existing wheel install once; later
    # lock changes continue to select the hashed source archive without a full
    # reinstall.
    if compgen -G 'venv/lib/python*/site-packages/urllib3_future.pth' \
            >/dev/null; then
        (umask 022; URLLIB3_NO_OVERRIDE=1 \
            pip install --require-hashes -r requirements.lock \
                --no-binary urllib3-future --force-reinstall -q) || return 1
    else
        (umask 022; URLLIB3_NO_OVERRIDE=1 \
            pip install --require-hashes -r requirements.lock \
                --no-binary urllib3-future -q) || return 1
    fi
    if compgen -G 'venv/lib/python*/site-packages/urllib3_future.pth' \
            >/dev/null; then
        echo 'urllib3-future namespace override remains installed' >&2
        return 1
    fi
    # pip install does not remove packages deleted from the lock. ChromaDB has
    # no patched release for CVE-2026-45830/45831/45833, so remove any stale
    # legacy install before verifying or writing the lock marker.
    python -m pip uninstall --yes chromadb chroma-hnswlib || return 1
    python scripts/prune_unlocked_requirements.py requirements.lock || return 1
    python scripts/verify_locked_requirements.py requirements.lock || return 1
    python -m pip check || return 1
    verify_backend_runtime_dependencies || return 1
    requirements_marker_tmp="\$(mktemp "\${release_state_dir}/.requirements-lock.XXXXXX")" || return 1
    printf '%s\n' "\${requirements_expected}" > "\${requirements_marker_tmp}" || return 1
    chmod 600 "\${requirements_marker_tmp}" || return 1
    if [ "\$(stat -c '%U:%G:%a' "\${requirements_marker_tmp}")" != 'root:root:600' ] ||
       [ "\$(stat -c '%h' "\${requirements_marker_tmp}")" != '1' ]; then
        rm -f -- "\${requirements_marker_tmp}"
        return 1
    fi
    sync -f "\${requirements_marker_tmp}" || return 1
    mv -fT -- "\${requirements_marker_tmp}" "\${requirements_marker}" || return 1
    sync -f "\${release_state_dir}" || return 1
}
sync_backend_dependencies
REMOTE_DEPENDENCY_SYNC
}

compute_release_input_digests() {
    if [[ ! "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法为非精确 candidate 计算发布输入摘要"
        return 70
    fi
    REQUIREMENTS_LOCK_SHA="$(python3 "$SCRIPT_DIR/scripts/release_input_digest.py" \
        --repo "$SCRIPT_DIR" --commit "$DEPLOY_EXPECTED_SHA" --kind requirements)" || return 1
    SYSTEM_KB_INPUT_SHA="$(python3 "$SCRIPT_DIR/scripts/release_input_digest.py" \
        --repo "$SCRIPT_DIR" --commit "$DEPLOY_EXPECTED_SHA" --kind system-kb)" || return 1
    SYSTEM_KB_LEGACY_INPUT_SHA="$(python3 "$SCRIPT_DIR/scripts/release_input_digest.py" \
        --repo "$SCRIPT_DIR" --commit "$DEPLOY_EXPECTED_SHA" --kind system-kb-legacy)" || return 1
    if [[ ! "$REQUIREMENTS_LOCK_SHA" =~ ^[0-9a-f]{64}$ ||
          ! "$SYSTEM_KB_INPUT_SHA" =~ ^[0-9a-f]{64}$ ||
          ! "$SYSTEM_KB_LEGACY_INPUT_SHA" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "发布输入摘要格式非法"
        return 70
    fi
}

determine_system_kb_activation_need() {
    local result
    if [[ ! "$REMOTE_RELEASE_STATE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ||
          "$REMOTE_RELEASE_STATE_DIR" = "/" ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/../"* ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/.." ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/./"* ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/." ||
          ! "$SYSTEM_KB_INPUT_SHA" =~ ^[0-9a-f]{64}$ ||
          ! "$SYSTEM_KB_LEGACY_INPUT_SHA" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "System KB 状态目录或 digest 非法"
        return 70
    fi
    result="$(ssh "$SERVER" bash -s -- \
        "$REMOTE_RELEASE_STATE_DIR" "$SYSTEM_KB_INPUT_SHA" \
        "$SYSTEM_KB_LEGACY_INPUT_SHA" <<'REMOTE_KB_DIGEST_CHECK'
set -euo pipefail
state_dir="$1"
expected="$2"
legacy_expected="$3"
marker="${state_dir}/system-kb-input.sha256"
if [ ! -e "$state_dir" ]; then
    printf '%s\n' MISMATCH
    exit 0
fi
test -d "$state_dir"
test ! -L "$state_dir"
test "$(stat -c '%U:%G:%a' "$state_dir")" = 'root:root:700'
if [ -e "$marker" ] || [ -L "$marker" ]; then
    test -f "$marker"
    test ! -L "$marker"
    test "$(stat -c '%U:%G:%a' "$marker")" = 'root:root:600'
    test "$(stat -c '%h' "$marker")" = '1'
fi
if [ -f "$marker" ] && [ "$(cat "$marker")" = "$expected" ]; then
    printf '%s\n' MATCH
elif [ -f "$marker" ] && [ "$(cat "$marker")" = "$legacy_expected" ]; then
    printf '%s\n' LEGACY_MATCH
else
    printf '%s\n' MISMATCH
fi
REMOTE_KB_DIGEST_CHECK
    )" || {
        print_error "无法读取 System KB 发布输入状态"
        return 1
    }
    case "$result" in
        MATCH)
            SYSTEM_KB_ACTIVATION_REQUIRED=0
            print_success "System KB 输入摘要未变化，将跳过写入并保留只读验证"
            ;;
        LEGACY_MATCH)
            SYSTEM_KB_ACTIVATION_REQUIRED=0
            print_success "System KB 旧摘要与候选一致，将跳过写入并在终态升级 marker"
            ;;
        MISMATCH)
            SYSTEM_KB_ACTIVATION_REQUIRED=1
            print_step "System KB 输入摘要已变化或 marker 缺失，将执行完整写入"
            ;;
        *)
            print_error "System KB 输入状态返回非法: $result"
            return 1
            ;;
    esac
}

record_system_kb_input_digest() {
    if [[ ! "$REMOTE_RELEASE_STATE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ||
          "$REMOTE_RELEASE_STATE_DIR" = "/" ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/../"* ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/.." ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/./"* ||
          "$REMOTE_RELEASE_STATE_DIR" = *"/." ||
          ! "$SYSTEM_KB_INPUT_SHA" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "拒绝记录非法 System KB digest"
        return 70
    fi
    ssh "$SERVER" bash -s -- \
        "$REMOTE_RELEASE_STATE_DIR" "$SYSTEM_KB_INPUT_SHA" <<'REMOTE_KB_DIGEST_WRITE'
set -euo pipefail
state_dir="$1"
expected="$2"
marker="${state_dir}/system-kb-input.sha256"
umask 077
if [ ! -e "$state_dir" ]; then
    mkdir "$state_dir"
    chmod 700 "$state_dir"
fi
test -d "$state_dir"
test ! -L "$state_dir"
test "$(stat -c '%U:%G:%a' "$state_dir")" = 'root:root:700'
if [ -e "$marker" ] || [ -L "$marker" ]; then
    test -f "$marker"
    test ! -L "$marker"
    test "$(stat -c '%U:%G:%a' "$marker")" = 'root:root:600'
    test "$(stat -c '%h' "$marker")" = '1'
fi
marker_tmp="$(mktemp "${state_dir}/.system-kb-input.XXXXXX")"
trap 'rm -f -- "$marker_tmp"' EXIT
printf '%s\n' "$expected" > "$marker_tmp"
chmod 600 "$marker_tmp"
test "$(stat -c '%U:%G:%a' "$marker_tmp")" = 'root:root:600'
test "$(stat -c '%h' "$marker_tmp")" = '1'
sync -f "$marker_tmp"
mv -fT -- "$marker_tmp" "$marker"
sync -f "$state_dir"
trap - EXIT
REMOTE_KB_DIGEST_WRITE
}

# 部署后端
laya_service_command() {
    printf '/usr/bin/python3.12 -I -S -B %q %q --sha %q --lock %q --token %q --stage %q' \
        "/var/lib/reva-laya-release/verifiers/$DEPLOY_EXPECTED_SHA/verify_laya_no_backup.py" "$1" \
        "$DEPLOY_EXPECTED_SHA" "$REMOTE_RELEASE_LOCK_DIR" "$REMOTE_RELEASE_LOCK_TOKEN" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR"
}

prepare_laya_service() {
    assert_remote_release_lock
    # Export only reviewed blobs from the exact candidate bundle, before any
    # writer stops. Keep the existing immutable backend stage inventory intact.
    ssh "$SERVER" /usr/bin/python3.12 -I -S -B - \
        "$REMOTE_DEPLOY_BUNDLE" "$DEPLOY_EXPECTED_SHA" \
        "$REMOTE_RELEASE_LOCK_DIR" "$REMOTE_RELEASE_LOCK_TOKEN" \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" "$ROLLBACK_CANDIDATE_COMMIT" <<'REMOTE_LAYA_SOURCE'
import hashlib, json, os, re, stat, subprocess, sys, tempfile
from pathlib import Path
bundle, sha, lock, token, stage, old_sha = sys.argv[1:]
if not all(re.fullmatch(r'[0-9a-f]{40}', value) for value in (sha, old_sha)):
    raise SystemExit('invalid candidate SHA')
def private(path, mode):
    info = Path(path).lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode:
        raise SystemExit('invalid Laya source metadata')
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise SystemExit('invalid Laya source link count')
private(lock, 0o700)
private(stage, 0o700)
for name, expected in [('token', token + '\n'), ('stage', stage + '\n')]:
    path = Path(lock) / name
    private(path, 0o600)
    if path.read_text() != expected:
        raise SystemExit('Laya source lease mismatch')
private(bundle, 0o600)
base = Path('/var/lib/reva-laya-release')
base.mkdir(mode=0o700, exist_ok=True)
private(base, 0o700)
sources = base / 'sources'
sources.mkdir(mode=0o700, exist_ok=True)
private(sources, 0o700)
verifiers = base / 'verifiers'
verifiers.mkdir(mode=0o700, exist_ok=True)
private(verifiers, 0o700)
verifier = verifiers / sha
source = sources / sha
assets = ('install.py', 'serve.py', 'model-manifest.json', 'requirements.lock', 'reva-laya.service.in', 'encoder-config.json.b64', 'rl-agent-config.json.b64', 'tokenizer-config.json.b64', 'model-NOTICE.txt')
if not source.exists():
    source.mkdir(mode=0o700)
    verifier.mkdir(mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}
    with tempfile.TemporaryDirectory(dir=base, prefix='proof-') as proof:
        git = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
               '-c', 'protocol.file.allow=always', '-c', 'protocol.ext.allow=never']
        subprocess.run(git + ['init', '--bare', proof], env=env, check=True, stdout=subprocess.DEVNULL)
        production = Path('/opt/health-app')
        objects = production / '.git/objects'
        for path in (production, production / '.git', objects):
            info = path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or info.st_uid != 0 or info.st_mode & 0o022):
                raise SystemExit('invalid production object prerequisite')
        for name in ('alternates', 'http-alternates'):
            if os.path.lexists(objects / 'info' / name):
                raise SystemExit('production object prerequisite chains alternates')
        for root, directories, files in os.walk(objects, followlinks=False):
            entries = [(Path(root), True)]
            entries += [(Path(root) / name, True) for name in directories]
            entries += [(Path(root) / name, False) for name in files]
            for path, directory in entries:
                info = path.lstat()
                valid_type = stat.S_ISDIR if directory else stat.S_ISREG
                if (not valid_type(info.st_mode) or stat.S_ISLNK(info.st_mode)
                        or info.st_uid != 0 or info.st_mode & 0o022):
                    raise SystemExit('untrusted production Git object')
        live = subprocess.check_output(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
            '-C', str(production), 'rev-parse', 'HEAD'], env=env, text=True).strip()
        if live != old_sha:
            raise SystemExit('production object prerequisite revision mismatch')
        alternates = Path(proof) / 'objects/info/alternates'
        with alternates.open('x') as out:
            out.write(str(production / '.git/objects') + '\n')
            os.fchmod(out.fileno(), 0o600)
            out.flush()
            os.fsync(out.fileno())
        git += ['--git-dir=' + proof]
        subprocess.run(git + ['fetch', '--no-tags', bundle, 'HEAD'], env=env, check=True, timeout=120,
                       stdout=subprocess.DEVNULL)
        head = subprocess.check_output(git + ['rev-parse', 'FETCH_HEAD'], env=env, text=True).strip()
        if head != sha:
            raise SystemExit('Laya bundle candidate mismatch')
        verifier_data = subprocess.check_output(git + ['show', '--no-textconv', sha + ':backend/scripts/verify_laya_no_backup.py'], env=env)
        for name, data in [('verify_laya_no_backup.py', verifier_data),
                           ('source.json', json.dumps({'sha': sha, 'sha256': hashlib.sha256(verifier_data).hexdigest()}, sort_keys=True).encode())]:
            with (verifier / name).open('xb') as out:
                out.write(data)
                os.fchmod(out.fileno(), 0o400)
                out.flush()
                os.fsync(out.fileno())
        verifier_fd = os.open(verifier, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(verifier_fd)
        os.close(verifier_fd)
        hashes = {}
        for name in assets:
            data = subprocess.check_output(git + ['show', '--no-textconv', sha + ':infra/laya/' + name], env=env)
            path = source / name
            with path.open('xb') as out:
                out.write(data)
                os.fchmod(out.fileno(), 0o400)
                out.flush()
                os.fsync(out.fileno())
            hashes[name] = hashlib.sha256(data).hexdigest()
        old_probe = subprocess.run(git + ['grep', '-q', '-E',
            'decision_provider|DECISION_PROVIDER|decide_route|/v1/systemone|127[.]0[.]0[.]1:8092',
            old_sha, '--', 'backend/app'], env=env)
        if old_probe.returncode not in (0, 1):
            raise SystemExit('cannot prove old backend decision integration')
        with (source / 'source.json').open('x') as out:
            json.dump({'sha': sha, 'files': hashes, 'old_sha': old_sha,
                       'old_has_decisions': old_probe.returncode == 0}, out, sort_keys=True)
            os.fchmod(out.fileno(), 0o400)
            out.flush()
            os.fsync(out.fileno())
        fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)
private(source, 0o700)
private(source / 'source.json', 0o400)
proof = json.loads((source / 'source.json').read_text())
if proof.get('sha') != sha or proof.get('old_sha') != old_sha or set(proof.get('files', {})) != set(assets):
    raise SystemExit('Laya source proof mismatch')
for name in assets:
    private(source / name, 0o400)
    if hashlib.sha256((source / name).read_bytes()).hexdigest() != proof['files'][name]:
        raise SystemExit('Laya source hash mismatch')
private(verifier, 0o700)
if {p.name for p in verifier.iterdir()} != {'verify_laya_no_backup.py', 'source.json'}:
    raise SystemExit('Laya verifier inventory mismatch')
private(verifier / 'verify_laya_no_backup.py', 0o400)
private(verifier / 'source.json', 0o400)
binding = json.loads((verifier / 'source.json').read_text())
if binding != {'sha': sha, 'sha256': hashlib.sha256((verifier / 'verify_laya_no_backup.py').read_bytes()).hexdigest()}:
    raise SystemExit('Laya verifier binding mismatch')
os.execve('/usr/bin/python3.12', ['/usr/bin/python3.12', '-I', '-S', '-B', str(verifier / 'verify_laya_no_backup.py'),
          'provision', '--sha', sha, '--lock', lock, '--token', token, '--stage', stage],
          {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/nonexistent', 'LANG': 'C.UTF-8'})
REMOTE_LAYA_SOURCE
}

verify_laya_service() {
    assert_remote_release_lock
    ssh "$SERVER" "$(laya_service_command verify)"
}

# Guard-only stop proof: a sticky timeout may be normalized only after systemd
# reports no processes, control process, cgroup or queued operation.
guard_stop_backend_writers() {
    local lock_dir="$1" token="$2" cgroup_root="$3"
    local unit stop_ok guard_reason guard_state
    local units=(health-backend.socket health-backend.service celery-worker.service celery-beat.service)
    guard_stop_lease() {
        guard_reason=lease_changed
        test -r "$lock_dir/token" && test "$(cat "$lock_dir/token")" = "$token"
    }
    guard_stop_jobs() {
        local jobs
        guard_reason=systemd_jobs_query_failed
        jobs="$(systemctl list-jobs --no-legend --no-pager)" || return 2
        guard_reason=systemd_jobs_present
        [ -z "$jobs" ]
    }
    guard_stop_probe() {
        local target="$1" allow_timeout="$2" substate value property
        guard_reason=active_state_query_failed
        guard_state="$(systemctl show "$target" --property=ActiveState --value)" || return 2
        guard_reason=sub_state_query_failed
        substate="$(systemctl show "$target" --property=SubState --value)" || return 2
        if [ "$guard_state" = failed ]; then
            guard_reason=unexpected_failed_state
            [ "$allow_timeout" = 1 ] && [ "$target" != health-backend.socket ] && [ "$substate" = failed ] || return 2
            guard_reason=result_query_failed
            value="$(systemctl show "$target" --property=Result --value)" || return 2
            guard_reason=non_timeout_failure
            [ "$value" = timeout ] || return 2
        elif [ "$guard_state" != inactive ] || [ "$substate" != dead ]; then
            guard_reason=state_not_stopped
            return 1
        fi
        for property in MainPID ControlPID; do
            guard_reason="${property}_query_failed"
            value="$(systemctl show "$target" --property="$property" --value)" || return 2
            guard_reason="${property}_not_zero"
            [ "$value" = 0 ] || { [ "$target" = health-backend.socket ] && [ -z "$value" ]; } || return 1
        done
        guard_reason=control_group_query_failed
        value="$(systemctl show "$target" --property=ControlGroup --value)" || return 2
        guard_reason=control_group_not_empty
        [ -z "$value" ] || return 1
        guard_reason=cgroup_path_present
        [ ! -e "$cgroup_root/system.slice/$target" ] && [ ! -L "$cgroup_root/system.slice/$target" ] || return 1
        guard_stop_jobs
    }
    guard_stop_wait() {
        local target="$1" phase="$2" allow_timeout="$3" attempt status reason
        # systemctl stop can return before PID1/cgroup observations settle. Each
        # poll re-proves the lease; only a complete unchanged proof may pass.
        for ((attempt=1; attempt<=40; attempt++)); do
            if ! guard_stop_lease; then
                printf 'GUARD_STOP_REJECTED unit=%s phase=%s check=%s attempt=%s\n' "$target" "$phase" "$guard_reason" "$attempt" >&2
                return 1
            fi
            status=0
            if [ "$phase" = before_stop ]; then
                guard_stop_jobs || status=$?
            else
                guard_stop_probe "$target" "$allow_timeout" || status=$?
            fi
            reason="$guard_reason"
            if ! guard_stop_lease; then reason=lease_changed; status=2; fi
            guard_reason="$reason"
            if [ "$status" = 0 ]; then return 0; fi
            if [ "$status" = 2 ] || [ "$attempt" = 40 ]; then
                printf 'GUARD_STOP_REJECTED unit=%s phase=%s check=%s attempt=%s\n' "$target" "$phase" "$reason" "$attempt" >&2
                return 1
            fi
            if [ "$attempt" = 1 ]; then
                printf 'GUARD_STOP_WAIT unit=%s phase=%s check=%s\n' "$target" "$phase" "$reason"
            fi
            if ! sleep 0.25; then
                printf 'GUARD_STOP_REJECTED unit=%s phase=%s check=wait_sleep_failed\n' "$target" "$phase" >&2
                return 1
            fi
        done
        return 1
    }
    for unit in "${units[@]}"; do
        guard_stop_wait "$unit" before_stop 0 || return 1
        stop_ok=1
        systemctl stop "$unit" || stop_ok=0
        guard_stop_wait "$unit" after_stop 1 || return 1
        if [ "$guard_state" = failed ]; then
            if ! guard_stop_lease; then
                printf 'GUARD_STOP_REJECTED unit=%s phase=normalize check=lease_changed\n' "$unit" >&2
                return 1
            fi
            if ! systemctl reset-failed "$unit"; then
                printf 'GUARD_STOP_REJECTED unit=%s phase=normalize check=reset_failed\n' "$unit" >&2
                return 1
            fi
        elif [ "$stop_ok" != 1 ]; then
            printf 'GUARD_STOP_REJECTED unit=%s phase=after_stop check=stop_command_failed\n' "$unit" >&2
            return 1
        fi
        guard_stop_wait "$unit" after_normalize 0 || return 1
    done
    # Two complete rounds separated by a bounded interval prove the full writer
    # set remains stopped, rather than just checking each unit once in turn.
    local round
    for round in 1 2; do
        for unit in "${units[@]}"; do
            guard_stop_wait "$unit" final_set 0 || return 1
        done
        if [ "$round" = 1 ]; then sleep 0.25 || return 1; fi
    done
}

deploy_backend() {
    local runtime_state_preflight_complete=0
    local remote_dependency_sync
    local daily_journey_apply="true"
    local activate_laya_service
    activate_laya_service="$(laya_service_command activate)"

    release_timing_checkpoint backend_started
    print_step "部署后端..."
    assert_remote_release_lock_if_acquired
    remote_dependency_sync="$(remote_dependency_sync_command)" || return 1

    # runtime-only 医疗知识必须先让 hold-aware 代码成为健康回滚地板，
    # 且首阶段禁止生成新 evidence answer。
    validate_runtime_only_kb_staging

    # 环境错误必须在远端发布工具准备及停写之前失败。相同文件的
    # 摘要由后续上传阶段复用；文件若在预检后改变，则会自动重新校验。
    validate_deploy_env_preflight
    release_timing_checkpoint env_checked

    # 1. 准备无备份发布工具与发布前 SHA 小型证明
    backup_database
    determine_system_kb_activation_need
    inspect_runtime_state_transaction_before_deploy
    release_timing_checkpoint preparation_checked
    if [[ "$RUNTIME_STATE_ALREADY_FINALIZED" = "1" ]]; then
        verify_code_only_source_changes || return 1
        daily_journey_release_preflight || return 1
        if ! verify_laya_service ||
            ! prove_health_evidence_runtime_process_flag false ||
            ! verify_deployment ||
            ! verify_deployed_revision ||
            ! verify_runtime_only_kb_contract "staged"; then
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "已终结 candidate 的只读 post-gates 失败；现场与租约保留"
            return 1
        fi
        wait_for_agent_skills_manifest
        record_system_kb_input_digest
        print_success "持久事务已终结且 backend/System KB post-gates 复证通过"
        return 0
    fi
    if [[ "$RUNTIME_STATE_RESUME_PHASE" = "NONE" ]]; then
        save_rollback_point
        verify_rollback_point_schema_compatibility
        verify_code_only_source_changes || return 1
        daily_journey_release_preflight || return 1

        # All locally fallible transport and read-only transaction checks run
        # before live env/service mutation. A preflight RPC failure preserves
        # the exact stage because it may have recovered a durable ARMING intent.
        if ! upload_deploy_bundle; then
            print_error "candidate bundle 上传失败；服务与 live env 尚未变更"
            return 1
        fi
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        if ! run_runtime_state_transaction \
            preflight-code \
            "$ROLLBACK_CANDIDATE_COMMIT" \
            "$DEPLOY_EXPECTED_SHA"; then
            print_error "runtime state 只读预检失败；服务与 live env 尚未变更，现场与租约保留"
            return 1
        fi
        runtime_state_preflight_complete=1
        _REMOTE_RELEASE_LOCK_ABANDONED=0

        # 2. 同步环境变量并受控撤销运行时授权。
        release_timing_checkpoint env_staging_started
        if ! sync_env; then
            return 1
        fi
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        if ! prepare_laya_service; then
            print_error "Laya preparation failed; backend writers unchanged, release evidence retained"
            return 1
        fi
        # Arm preservation before the deactivation call: its exact-success
        # path clears delegation internally, so there must be no signal window
        # between live mutation and the caller restoring the preserve state.
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        release_timing_checkpoint deactivation_started
        if ! prove_health_evidence_runtime_process_flag false; then
            print_error "现行 runtime flag 不是安全关闭状态；服务尚未改变，发布阻断"
            return 1
        fi
    else
        print_step "沿用 code-only 持久事务的 SHA 与现行配置证明"
        verify_code_only_source_changes || return 1
        daily_journey_release_preflight || return 1
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
            preflight-code \
            "$ROLLBACK_CANDIDATE_COMMIT" \
            "$DEPLOY_EXPECTED_SHA"; then
            print_error "runtime state 续接预检失败；现场与租约保留"
            return 1
        fi
        if ! prepare_laya_service; then
            print_error "Laya resume preparation failed; existing release evidence retained"
            return 1
        fi
    fi
    if [[ "${DAILY_JOURNEY_ADDITIVE:-0}" = 1 ]]; then
        daily_journey_apply="$(daily_journey_release_command apply)" || return 1
    fi
    local remote_git_sync
    remote_git_sync="$(remote_git_sync_command)"

    release_timing_checkpoint guard_started

    # Group the generated dependency block so its function definitions cannot
    # escape the AND chain after a failed writer-stop or checkout proof.

    # 3. Guard phase：先启动新代码，不写入任何 System KB artifact。这样旧服务
    # 永远看不到新 runtime-only 文档，且健康失败可安全回到发布前代码。
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    set +e
    ssh $SERVER "
        $(declare -f guard_stop_backend_writers)
        $(declare -f release_timing_checkpoint)
        SECONDS=0
        release_timing_checkpoint remote_guard_started && \
        echo '停止后端 socket 与所有 writer...' && \
        guard_stop_backend_writers '$REMOTE_RELEASE_LOCK_DIR' '$REMOTE_RELEASE_LOCK_TOKEN' /sys/fs/cgroup && \
        release_timing_checkpoint remote_writers_stopped && \
        if [ '$RUNTIME_STATE_RESUME_PHASE' != 'COMMITTED' ]; then \
            /usr/bin/python3 '$REMOTE_RUNTIME_STATE_RUNNER' \
                prepare-code '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA' \
                '$REMOTE_RELEASE_LOCK_DIR' '$REMOTE_RELEASE_LOCK_TOKEN'; \
        fi && \
        release_timing_checkpoint remote_runtime_prepare_completed && \
        cd $REMOTE_PATH && \
        $remote_git_sync && \
        release_timing_checkpoint remote_checkout_completed && \
        $activate_laya_service && \
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
        {
        $remote_dependency_sync
        } && \
        release_timing_checkpoint remote_dependencies_completed && \
        if [ '${DAILY_JOURNEY_ADDITIVE:-0}' = 1 ]; then \
            $daily_journey_apply; \
        else \
            echo 'code-only：不执行数据库迁移，继续只读 schema 验证...'; \
        fi && \
        release_timing_checkpoint remote_schema_check_started && \
        unset MIGRATION_DATABASE_URL && \
        (cd '$REMOTE_BACKUP_PREFLIGHT_DIR' && \
            sha256sum --strict -c staged.sha256 >/dev/null) && \
        echo '启动服务前验证完整 runtime schema...' && \
        PYTHONPATH=. python '$REMOTE_BACKUP_PREFLIGHT_DIR/verify_runtime_schema_compatibility.py' && \
        release_timing_checkpoint remote_schema_completed && \
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
        echo '重启后端服务...' && \
        systemctl restart health-backend.socket && \
        systemctl restart health-backend && \
        echo '重启 Celery worker & beat...' && \
        systemctl restart celery-worker celery-beat && \
        release_timing_checkpoint remote_services_restarted && \
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
    release_timing_checkpoint guard_command_completed
    if ! verify_laya_service ||
        ! prove_health_evidence_runtime_process_flag false ||
        ! verify_deployed_revision; then
        # ssh rc=0 proves the remote command is terminal, so rollback can now
        # safely own a fresh delegated transaction.
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        rollback_deploy || true
        print_error "后端 guard 终态证明失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0

    # 4. 先验证 hold-aware guard；未通过时 KB 尚未写入。
    if ! verify_deployment; then
        rollback_deploy || true
        print_error "后端 guard 健康检查失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi

    if ! verify_deployed_revision; then
        rollback_deploy || true
        print_error "后端 guard revision 校验失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi

    if ! verify_runtime_only_kb_contract "guard"; then
        rollback_deploy || true
        print_error "后端 guard serving contract 失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi

    release_timing_checkpoint guard_gates_passed

    # 所有 guard Gate 通过后才提交 state transaction。commit 会精确删除
    # code-only 提交不删除既有 runtime 数据；失败保留现场，不自动恢复。
    if ! commit_runtime_state_transaction_after_guard; then
        exit 1
    fi

    # Guard 已健康：从现在起即使 KB activation 失败，也绝不回到不认识
    # generic hold 的旧代码。rollback runner 还会定向 archive 作为第二层防线。
    ROLLBACK_COMMIT="$DEPLOY_EXPECTED_SHA"
    print_success "generic-hold candidate 已通过 guard 验证: ${ROLLBACK_COMMIT:0:12}"

    release_timing_checkpoint kb_activation_started

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
        if [ '$SYSTEM_KB_ACTIVATION_REQUIRED' = '1' ]; then \
            echo '补齐审核食物营养基准...' && \
            python scripts/seed_food_nutrition.py && \
            echo '写入系统知识库 Phase 0 种子...' && \
            python scripts/seed_system_kb_phase0.py && \
            echo '导入系统知识库 V2 扩展 artifacts...' && \
            python scripts/import_system_kb_v2_artifacts.py; \
        else \
            echo 'System KB inputs unchanged; mutation skipped'; \
        fi
    "
    KB_EXIT=$?
    set -e
    if [ $KB_EXIT -ne 0 ]; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "System KB 远端事务结果不明确 (exit=$KB_EXIT)；不与可能仍运行的 importer 并发回滚"
        print_error "发布锁与现场保留，请先确认数据库事务与 advisory lock 已终止"
        exit 1
    fi

    release_timing_checkpoint kb_command_completed

    # 6. 数据激活后再次跑完整健康度；失败回到同一 guard SHA 并隔离 pack。
    if ! verify_deployment; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        rollback_deploy || true
        print_error "KB activation 后健康检查失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi

    if ! verify_deployed_revision; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        rollback_deploy || true
        print_error "KB activation 后 revision 校验失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi

    if ! verify_runtime_only_kb_contract "staged"; then
        _REMOTE_RELEASE_LOCK_DELEGATED=0
        rollback_deploy || true
        print_error "KB activation serving contract 失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0

    release_timing_checkpoint kb_gates_passed

    # 6.5 所有 fatal gate 通过后再验证第一方 Agent skills manifest。
    wait_for_agent_skills_manifest

    release_timing_checkpoint manifest_passed

    # Manifest generation can take long enough for a late service crash or
    # restart loop to appear. Re-prove the exact candidate, health, staged KB
    # contract, and a full process-stability window immediately before the
    # code-only transaction is finalized.
    if ! verify_laya_service ||
        ! prove_health_evidence_runtime_process_flag false ||
        ! verify_deployment ||
        ! verify_deployed_revision ||
        ! verify_runtime_only_kb_contract "staged"; then
        rollback_deploy || true
        print_error "最终 terminal gate 失败；NEEDS_OPERATOR，未执行自动恢复，发布锁与现场保留"
        exit 1
    fi

    release_timing_checkpoint terminal_gates_passed

    # 只有完整终态健康、revision 与 staged serving contract 都通过后，才
    # 记录本次输入摘要；任何中途失败都保持 marker 陈旧，下一次自动重跑写入。
    if ! record_system_kb_input_digest; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "System KB 输入摘要记录失败；发布锁与现场保留"
        exit 1
    fi

    # 只有 backend、System KB、revision、serving contract 和 manifest 全部
    # 走完，才清理可跨重启恢复的持久事务。SSH 结果不明时保留 lease/stage，
    # 由同 SHA 的 status/finalize 重入，绝不猜测式并发回滚。
    if ! finalize_runtime_state_transaction_after_all_gates; then
        exit 1
    fi

    release_timing_checkpoint finalized
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
        verify_recent_offsite_backup.sh \
        rollback_release.sh \
        activate_health_evidence_runtime.sh \
        verify_locked_requirements.py \
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
        -eq 16
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
                        exit(assignments == 1 && canonical == 1 ? 0 : 1)
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

reset_app_store_review_demo() {
    local reset_output

    DEPLOY_EXPECTED_SHA="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法确定本地发布 commit"
        return 1
    fi
    assert_remote_release_lock
    verify_deployed_revision
    print_step "重置 App Store 审核演示数据..."

    # The destructive remote reset can outlive SSH; preserve its lease until
    # both the command and its exact terminal receipt prove success.
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! reset_output=$(ssh "$SERVER" bash -s -- \
        "$REMOTE_PATH" \
        "$DEPLOY_EXPECTED_SHA" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" 2>/dev/null <<'REMOTE_APP_STORE_REVIEW_RESET'
set -euo pipefail
repo_path="$1"
expected_sha="$2"
release_lock_dir="$3"
release_lock_token="$4"

test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
test "$repo_path" = /opt/health-app
# This one canonical process proves the lease/source before loading credentials,
# runs the fixed --secret-free seeder and validates its exact bounded summary.
# It reads APP_STORE_REVIEW_DEMO_ACCOUNT / APP_STORE_REVIEW_DEMO_PASSWORD only
# from the metadata-checked production config; no shell source or venv startup.
/usr/bin/env -i PATH=/usr/bin:/bin HOME=/nonexistent /usr/bin/python3.12 -I -S -B - \
    "$expected_sha" "$release_lock_dir" "$release_lock_token" <<'PROVE_REVIEW_EXECUTION'
import os
import pathlib
import re
import runpy
import stat
import sys

sha, lease, token = sys.argv[1:]
if os.geteuid() != 0 or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("invalid reviewed execution context")
entry = pathlib.Path("/var/lib/reva-release/bootstrap") / sha / "source/scripts/trusted_review_reset.py"
for item in [*reversed(entry.parents), entry]:
    info = item.lstat()
    kind = stat.S_ISREG if item == entry else stat.S_ISDIR
    if info.st_uid != 0 or info.st_mode & 0o022 or not kind(info.st_mode):
        raise SystemExit("unsafe reviewed execution context")
    if item == entry and info.st_nlink != 1:
        raise SystemExit("unsafe reviewed execution entry")
sys.dont_write_bytecode = True
runpy.run_path(str(entry))["execute_review_maintenance"](sha, lease, token)
PROVE_REVIEW_EXECUTION
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
REMOTE_APP_STORE_REVIEW_RESET
    ); then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "App Store 审核演示数据重置失败或结果未知；发布锁与现场保留"
        return 1
    fi
    if [[ "$reset_output" != "APP_STORE_REVIEW_RESET_OK" ]]; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "App Store 审核演示数据重置缺少精确成功证明；发布锁与现场保留"
        return 1
    fi
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    _REMOTE_RELEASE_LOCK_ABANDONED=0
    print_success "App Store 审核演示数据已重置并通过非敏感验证"
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
            -R|--reset-app-store-review)
                DEPLOY_MODE="app-store-review-reset"
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

    case "$DEPLOY_MODE" in
        all|frontend|env|health-evidence)
            print_error "无备份发布暂不支持旧前端发布、配置变更或 runtime 激活；未获取发布锁、未改变线上服务"
            return 1
            ;;
    esac

    case $DEPLOY_MODE in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart"|"push")
            acquire_release_lock "deploy:${DEPLOY_MODE}"
            ;;
    esac
    case $DEPLOY_MODE in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart")
            check_remote_vision_model_history
            acquire_remote_release_lock "deploy:${DEPLOY_MODE}"
            install_release_cleanup_traps
            assert_remote_release_lock
            check_remote_vision_model_history
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
        "app-store-review-reset")
            reset_app_store_review_demo
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
