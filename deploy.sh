#!/bin/bash

# ===========================================
# 健康应用部署脚本
#
# 配置文件: .env (本地管理，不被 git 追踪)
# 服务器配置从 .env 读取
# ===========================================

# Sourcing is inert: no options, output, environment, path, or functions.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    return 0
fi

# This exact help response is the only repository-local deploy CLI operation.
# Keep it and the unconditional freeze entirely in Bash builtins, before path
# resolution, environment reads, startup hooks, credentials, or tools.
if [[ "$#" -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
    builtin printf '%s\n' \
        'Usage: ./deploy.sh -h|--help' \
        '' \
        'Production repository entrypoints are frozen (exit 78).' \
        'Status, logs, release-lock inspection, deploy, restart, rollback, and publish require an external trusted Gate.'
    exit 0
fi
builtin printf '%s\n' \
    'Production repository entrypoints are frozen; use the manual release Gate.' >&2
exit 78

if [[ "REVA_UNREACHABLE_LEGACY" == "NEVER" ]]; then
# BEGIN UNREACHABLE LEGACY DEPLOY IMPLEMENTATION

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
RELEASE_STEP_PROOF_MODE="${RELEASE_STEP_PROOF_MODE:-shadow}"
REMOTE_RELEASE_PROOF_ROOT="${REMOTE_RELEASE_PROOF_ROOT:-/var/cache/health-app/release-proofs}"
REMOTE_BACKUP_PREFLIGHT_DIR="/tmp/health-app-backup-preflight-$$-$(date +%s)"
REMOTE_DEPLOY_BUNDLE="$REMOTE_BACKUP_PREFLIGHT_DIR/deploy.bundle"
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
REMOTE_RELEASE_LOCK_DIR="/var/lib/health-app/release-state/deploy.lock"
REMOTE_RELEASE_STATE_DIR="${REMOTE_RELEASE_STATE_DIR:-/var/lib/reva-release-state}"
REMOTE_RELEASE_LOCK_TOKEN=""
REMOTE_RELEASE_LOCK_LABEL=""
REMOTE_RELEASE_LOCK_STATE=""
REMOTE_RELEASE_SOURCE_SHA=""
REMOTE_RELEASE_SOURCE_TREE=""
REMOTE_RELEASE_REQUESTED_SHA=""
REMOTE_RELEASE_REQUESTED_TREE=""
REMOTE_RELEASE_SURFACE=""
REMOTE_RELEASE_OPERATION=""
REMOTE_RELEASE_CHANNEL=""
REMOTE_RELEASE_TRANSACTION_ID=""
REMOTE_RELEASE_BASELINE_DIGEST=""
REMOTE_RELEASE_REQUEST_DIGEST=""
REMOTE_RELEASE_TERMINAL_DIGEST=""
CANONICAL_RELEASE_ORIGIN_URL="https://github.com/itsoso/health-llm-driven.git"
_REMOTE_RELEASE_LOCK_ACQUIRED=0
_REMOTE_RELEASE_LOCK_DELEGATED=0
_REMOTE_RELEASE_LOCK_ABANDONED=0
_REMOTE_RELEASE_LOCK_ADOPTED=0
_REMOTE_RELEASE_LOCK_ALREADY_RELEASED=0

set_remote_backup_preflight_dir() {
    local stage_dir="$1"

    if [[ ! "$stage_dir" =~ ^/tmp/health-app-backup-preflight-([1-9][0-9]*-[1-9][0-9]*|[0-9a-f]{64})$ ]]; then
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
    REMOTE_DEPLOY_BUNDLE="$stage_dir/deploy.bundle"
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
case "$RELEASE_STEP_PROOF_MODE" in
    off|shadow|on) ;;
    *)
        echo -e "${RED}✗${NC} 错误: RELEASE_STEP_PROOF_MODE 只接受 off/shadow/on"
        exit 1
        ;;
esac
if [[ ! "$REMOTE_RELEASE_PROOF_ROOT" =~ ^/var/cache/health-app/[A-Za-z0-9._/-]+$ ||
      "$REMOTE_RELEASE_PROOF_ROOT" = *"/../"* ||
      "$REMOTE_RELEASE_PROOF_ROOT" = *"/.." ||
      "$REMOTE_RELEASE_PROOF_ROOT" = *"/./"* ||
      "$REMOTE_RELEASE_PROOF_ROOT" = *"/." ]]; then
    echo -e "${RED}✗${NC} 错误: REMOTE_RELEASE_PROOF_ROOT 格式不安全"
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
    local original_status=$?
    local unlock_status=0
    local allocation_aborted=0

    # A crash before the immutable stage is sealed has not crossed a
    # production-mutation boundary.  Reap that exact token-bound allocation
    # even when the caller conservatively set ABANDONED/DELEGATED.  A sealed
    # or mutating lease returns non-zero without changing one byte and remains
    # available for explicit recovery.
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" = "1" ]]; then
        if abort_remote_release_allocation >/dev/null 2>&1; then
            allocation_aborted=1
        fi
    fi
    if [[ "$allocation_aborted" != "1" &&
          "${_REMOTE_RELEASE_LOCK_ABANDONED:-0}" != "1" &&
          "${_REMOTE_RELEASE_LOCK_DELEGATED:-0}" != "1" ]]; then
        if release_remote_release_lock; then
            :
        else
            unlock_status=$?
        fi
    fi
    release_release_lock
    if [[ "$original_status" -eq 0 && "$unlock_status" -ne 0 ]]; then
        print_error "发布动作已完成，但服务器发布锁未安全释放"
        trap - EXIT
        exit 73
    fi
    return "$original_status"
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
        all|frontend|backend|env|health-evidence|app-store-review-reset|restart|mac-routes) ;;
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
    local adopt="${REVA_REMOTE_RELEASE_LOCK_ADOPT:-0}"
    local lock_output
    local adopted_stage
    local adopted_state
    local adopted_source
    local adopted_tree

    if [[ -n "${REVA_RELEASE_COORDINATOR_SOURCE_SHA:-}" ||
          -n "${REVA_RELEASE_COORDINATOR_SOURCE_TREE:-}" ]]; then
        REMOTE_RELEASE_REQUESTED_SHA="${REVA_RELEASE_COORDINATOR_SOURCE_SHA:-}"
        REMOTE_RELEASE_REQUESTED_TREE="${REVA_RELEASE_COORDINATOR_SOURCE_TREE:-}"
    else
        REMOTE_RELEASE_REQUESTED_SHA="$(
            trusted_release_git rev-parse HEAD 2>/dev/null
        )" || return 70
        REMOTE_RELEASE_REQUESTED_TREE="$(
            trusted_release_git rev-parse "${REMOTE_RELEASE_REQUESTED_SHA}^{tree}" \
                2>/dev/null
        )" || return 70
    fi
    if ! [[ "$REMOTE_RELEASE_REQUESTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法解析远端发布锁 source SHA"
        return 70
    fi
    if ! [[ "$REMOTE_RELEASE_REQUESTED_TREE" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法解析远端发布锁 source tree"
        return 70
    fi
    if ! trusted_release_git cat-file -e \
            "${REMOTE_RELEASE_REQUESTED_SHA}^{commit}" 2>/dev/null ||
       [[ "$(trusted_release_git rev-parse \
            "${REMOTE_RELEASE_REQUESTED_SHA}^{tree}" 2>/dev/null)" != \
            "$REMOTE_RELEASE_REQUESTED_TREE" ]]; then
        print_error "远端发布协调器 source SHA/tree 不匹配"
        return 70
    fi

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
    if [[ "$adopt" = "1" ]]; then
        token="${REVA_REMOTE_RELEASE_LOCK_TOKEN:-}"
    else
        if [[ -n "${REVA_REMOTE_RELEASE_LOCK_TOKEN:-}" ]]; then
            if [[ "$REMOTE_RELEASE_LOCK_DIR" = "/var/lib/health-app/release-state/deploy.lock" ]]; then
                print_error "新发布事务不接受调用者指定的远端 token"
                return 70
            fi
            # Unit/integration harnesses use an isolated non-production lock
            # path and deterministic owners to exercise ABA and recovery.
            token="$REVA_REMOTE_RELEASE_LOCK_TOKEN"
        else
            token="$(/usr/bin/python3 -I -c 'import secrets; print(secrets.token_hex(32))')" || {
                print_error "无法生成服务器发布锁的 256-bit 随机 token"
                return 70
            }
        fi
        if [[ "$REMOTE_RELEASE_LOCK_DIR" = "/var/lib/health-app/release-state/deploy.lock" ]] &&
           ! [[ "$token" =~ ^[0-9a-f]{64}$ ]]; then
            print_error "服务器发布锁 CSPRNG token 格式非法"
            return 70
        fi
    fi
    if [[ "$REMOTE_RELEASE_LOCK_DIR" = "/var/lib/health-app/release-state/deploy.lock" ]]; then
        if ! [[ "$token" =~ ^[0-9a-f]{64}$ ]]; then
            print_error "生产远端发布锁 token 必须是 256-bit canonical hex"
            return 70
        fi
    elif ! [[ "$token" =~ ^[A-Za-z0-9._:-]+$ ]]; then
        print_error "远端发布锁 token 格式非法"
        return 70
    fi
    if [[ "$adopt" != "0" && "$adopt" != "1" ]]; then
        print_error "REVA_REMOTE_RELEASE_LOCK_ADOPT 只接受 0/1"
        return 70
    fi
    if [[ "$adopt" = "1" && -z "${REVA_REMOTE_RELEASE_LOCK_TOKEN:-}" ]]; then
        print_error "显式接管远端发布锁必须提供原 REVA_REMOTE_RELEASE_LOCK_TOKEN"
        return 70
    fi
    REMOTE_RELEASE_SURFACE="${REVA_RELEASE_COORDINATOR_SURFACE:-server}"
    if [[ "$adopt" = "0" &&
          "$REMOTE_RELEASE_SURFACE" =~ ^(mobile|native|mac)$ ]]; then
        set_remote_backup_preflight_dir \
            "/tmp/health-app-backup-preflight-${token}"
    fi
    if [[ -n "${REVA_RELEASE_COORDINATOR_OPERATION:-}" ]]; then
        REMOTE_RELEASE_OPERATION="$REVA_RELEASE_COORDINATOR_OPERATION"
    elif [[ "$label" == deploy:* ]]; then
        REMOTE_RELEASE_OPERATION="${label#deploy:}"
    elif [[ "$REMOTE_RELEASE_LOCK_DIR" != "/var/lib/health-app/release-state/deploy.lock" ]]; then
        REMOTE_RELEASE_OPERATION="backend"
    else
        REMOTE_RELEASE_OPERATION="$label"
    fi
    REMOTE_RELEASE_CHANNEL="${REVA_RELEASE_COORDINATOR_CHANNEL:-production}"
    if [[ -n "${REVA_RELEASE_COORDINATOR_TRANSACTION:-}" ]]; then
        REMOTE_RELEASE_TRANSACTION_ID="$REVA_RELEASE_COORDINATOR_TRANSACTION"
    else
        REMOTE_RELEASE_TRANSACTION_ID="$(
            printf '%s' "$token" | /usr/bin/shasum -a 256 | /usr/bin/awk '{print substr($1, 1, 32)}'
        )" || return 70
    fi
    if [[ -n "${REVA_RELEASE_COORDINATOR_BASELINE_DIGEST:-}" ]]; then
        REMOTE_RELEASE_BASELINE_DIGEST="$REVA_RELEASE_COORDINATOR_BASELINE_DIGEST"
    else
        REMOTE_RELEASE_BASELINE_DIGEST="$(
            printf '%s\n%s\n%s\n' \
                "${REVA_EXPECTED_SERVER_SURFACES:-none}" \
                "$REMOTE_RELEASE_REQUESTED_SHA" \
                "$REMOTE_RELEASE_REQUESTED_TREE" |
                shasum -a 256 | awk '{print $1}'
        )" || return 70
    fi
    if [[ -n "${REVA_RELEASE_COORDINATOR_REQUEST_DIGEST:-}" ]]; then
        REMOTE_RELEASE_REQUEST_DIGEST="$REVA_RELEASE_COORDINATOR_REQUEST_DIGEST"
    else
        REMOTE_RELEASE_REQUEST_DIGEST="$(
            printf '%s\n%s\n%s\n' \
                "$label" "$REMOTE_RELEASE_REQUESTED_SHA" \
                "$REMOTE_RELEASE_REQUESTED_TREE" |
                shasum -a 256 | awk '{print $1}'
        )" || return 70
    fi
    REMOTE_RELEASE_TERMINAL_DIGEST="${REVA_RELEASE_COORDINATOR_TERMINAL_DIGEST:--}"
    if ! [[ "$REMOTE_RELEASE_SURFACE" =~ ^(server|mobile|native|mac)$ &&
          "$REMOTE_RELEASE_OPERATION" =~ ^(all|frontend|backend|env|health-evidence|app-store-review-reset|restart|mac-routes|forward|rollback|remote-build|publish|recover)$ &&
          "$REMOTE_RELEASE_CHANNEL" = "production" &&
          "$REMOTE_RELEASE_TRANSACTION_ID" =~ ^[0-9a-f]{32}$ &&
          "$REMOTE_RELEASE_BASELINE_DIGEST" =~ ^(-|[0-9a-f]{64})$ &&
          "$REMOTE_RELEASE_REQUEST_DIGEST" =~ ^[0-9a-f]{64}$ &&
          "$REMOTE_RELEASE_TERMINAL_DIGEST" =~ ^(-|[0-9a-f]{64})$ ]]; then
        print_error "远端发布协调器身份不符合固定 production 契约"
        return 70
    fi
    case "$REMOTE_RELEASE_SURFACE:$REMOTE_RELEASE_OPERATION" in
        server:all|server:frontend|server:backend|server:env|server:health-evidence|server:app-store-review-reset|server:restart|server:mac-routes|mobile:forward|mobile:rollback|native:remote-build|mac:publish|mac:recover|mac:rollback) ;;
        *)
            print_error "远端发布协调器 surface/operation 组合不受支持"
            return 70
            ;;
    esac
    if ! lock_output=$(remote_release_lock_command \
        acquire "$token" "$label" "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_RELEASE_REQUESTED_SHA" "$REMOTE_RELEASE_REQUESTED_TREE" \
        "$adopt" "$REMOTE_RELEASE_SURFACE" "$REMOTE_RELEASE_OPERATION" \
        "$REMOTE_RELEASE_CHANNEL" "$REMOTE_RELEASE_TRANSACTION_ID" \
        "$REMOTE_RELEASE_BASELINE_DIGEST" "$REMOTE_RELEASE_REQUEST_DIGEST" \
        "$REMOTE_RELEASE_TERMINAL_DIGEST"
    ); then
        echo "$lock_output" >&2
        print_error "无法获取服务器发布锁"
        return 73
    fi
    if [[ "$lock_output" = "REMOTE_RELEASE_LOCK_ALREADY_RELEASED" ]]; then
        if [[ "$adopt" != "1" ]]; then
            print_error "服务器返回了未经请求的已完成发布证明"
            return 73
        fi
        _REMOTE_RELEASE_LOCK_ACQUIRED=0
        _REMOTE_RELEASE_LOCK_ADOPTED=1
        _REMOTE_RELEASE_LOCK_ALREADY_RELEASED=1
        printf '%s\n' "$lock_output"
        return 0
    fi
    if [[ "$lock_output" == "REMOTE_RELEASE_LOCK_ADOPTED "* ]]; then
        if [[ "$adopt" != "1" ]]; then
            print_error "服务器返回了未经请求的发布锁接管证明"
            return 73
        fi
        local adopted_surface
        local adopted_operation
        local adopted_channel
        local adopted_transaction
        local adopted_baseline
        local adopted_request
        local adopted_terminal
        read -r adopted_state adopted_stage adopted_source adopted_tree \
            adopted_surface adopted_operation adopted_channel \
            adopted_transaction adopted_baseline adopted_request \
            adopted_terminal < <(
            printf '%s\n' "$lock_output" | awk '
                /^REMOTE_RELEASE_LOCK_ADOPTED state=(allocating|sealed|mutating|completed) stage=\/tmp\/health-app-backup-preflight-([1-9][0-9]*-[1-9][0-9]*|[0-9a-f]{64}) source_sha=[0-9a-f]{40} source_tree=[0-9a-f]{40} surface=(server|mobile|native|mac) operation=[A-Za-z0-9._:-]+ channel=production transaction_id=[0-9a-f]{32} baseline_digest=(-|[0-9a-f]{64}) request_digest=[0-9a-f]{64} terminal_digest=(-|[0-9a-f]{64})$/ {
                    matches += 1
                    state = $2
                    stage = $3
                    source = $4
                    tree = $5
                    surface = $6
                    operation = $7
                    channel = $8
                    transaction = $9
                    baseline = $10
                    request = $11
                    terminal = $12
                    sub(/^state=/, "", state)
                    sub(/^stage=/, "", stage)
                    sub(/^source_sha=/, "", source)
                    sub(/^source_tree=/, "", tree)
                    sub(/^surface=/, "", surface)
                    sub(/^operation=/, "", operation)
                    sub(/^channel=/, "", channel)
                    sub(/^transaction_id=/, "", transaction)
                    sub(/^baseline_digest=/, "", baseline)
                    sub(/^request_digest=/, "", request)
                    sub(/^terminal_digest=/, "", terminal)
                }
                END {
                    if (matches != 1) exit 1
                    print state, stage, source, tree, surface, operation, channel, transaction, baseline, request, terminal
                }
            '
        ) || {
            print_error "远端发布锁接管缺少精确 stage 证明"
            return 73
        }
        if ! git -C "$SCRIPT_DIR" cat-file -e "${adopted_source}^{commit}" ||
            [[ "$(git -C "$SCRIPT_DIR" rev-parse "${adopted_source}^{tree}")" != \
                "$adopted_tree" ]] ||
            ! git merge-base --is-ancestor \
                "$adopted_source" "$REMOTE_RELEASE_REQUESTED_SHA"; then
            print_error "既有远端发布 source 不是当前 main 的可验证祖先"
            return 73
        fi
        set_remote_backup_preflight_dir "$adopted_stage"
        REMOTE_RELEASE_LOCK_TOKEN="$token"
        REMOTE_RELEASE_LOCK_LABEL="$label"
        REMOTE_RELEASE_LOCK_STATE="$adopted_state"
        REMOTE_RELEASE_SOURCE_SHA="$adopted_source"
        REMOTE_RELEASE_SOURCE_TREE="$adopted_tree"
        REMOTE_RELEASE_SURFACE="$adopted_surface"
        REMOTE_RELEASE_OPERATION="$adopted_operation"
        REMOTE_RELEASE_CHANNEL="$adopted_channel"
        REMOTE_RELEASE_TRANSACTION_ID="$adopted_transaction"
        REMOTE_RELEASE_BASELINE_DIGEST="$adopted_baseline"
        REMOTE_RELEASE_REQUEST_DIGEST="$adopted_request"
        REMOTE_RELEASE_TERMINAL_DIGEST="$adopted_terminal"
        DEPLOY_EXPECTED_SHA="$adopted_source"
        _REMOTE_RELEASE_LOCK_ACQUIRED=1
        _REMOTE_RELEASE_LOCK_ADOPTED=1
        # Until durable status proves there is no active transaction (or a
        # terminal one has been safely reconciled), every early exit must
        # preserve the adopted owner's exact stage and lease.
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        if [[ "$adopted_state" = "allocating" &&
              "${REVA_REMOTE_RELEASE_LOCK_ALLOW_ALLOCATING_ADOPT:-0}" != "1" ]]; then
            if ! abort_remote_release_allocation; then
                print_error "未封存远端 allocation 无法安全回收"
                return 73
            fi
            unset REVA_REMOTE_RELEASE_LOCK_ADOPT
            unset REVA_REMOTE_RELEASE_LOCK_TOKEN
            _REMOTE_RELEASE_LOCK_ADOPTED=0
            _REMOTE_RELEASE_LOCK_ABANDONED=0
            acquire_remote_release_lock "$label"
            return
        fi
        return 0
    elif [[ "$lock_output" != \
        "REMOTE_RELEASE_LOCK_CREATED state=allocating stage=$REMOTE_BACKUP_PREFLIGHT_DIR source_sha=$REMOTE_RELEASE_REQUESTED_SHA source_tree=$REMOTE_RELEASE_REQUESTED_TREE" ]]; then
        print_error "远端发布锁创建缺少精确成功证明"
        return 73
    fi
    REMOTE_RELEASE_LOCK_TOKEN="$token"
    REMOTE_RELEASE_LOCK_LABEL="$label"
    REMOTE_RELEASE_LOCK_STATE="allocating"
    REMOTE_RELEASE_SOURCE_SHA="$REMOTE_RELEASE_REQUESTED_SHA"
    REMOTE_RELEASE_SOURCE_TREE="$REMOTE_RELEASE_REQUESTED_TREE"
    _REMOTE_RELEASE_LOCK_ACQUIRED=1
}

remote_release_lock_command() {
    local operation="$1"
    local token="${2:-$REMOTE_RELEASE_LOCK_TOKEN}"
    local label="${3:-${REMOTE_RELEASE_LOCK_LABEL:--}}"
    local stage="${4:-${REMOTE_BACKUP_PREFLIGHT_DIR:--}}"
    local source_sha="${5:-${REMOTE_RELEASE_SOURCE_SHA:--}}"
    local source_tree="${6:-${REMOTE_RELEASE_SOURCE_TREE:--}}"
    local adopt="${7:-0}"
    local surface="${8:-${REMOTE_RELEASE_SURFACE:--}}"
    local release_operation="${9:-${REMOTE_RELEASE_OPERATION:--}}"
    local channel="${10:-${REMOTE_RELEASE_CHANNEL:--}}"
    local transaction_id="${11:-${REMOTE_RELEASE_TRANSACTION_ID:--}}"
    local baseline_digest="${12:-${REMOTE_RELEASE_BASELINE_DIGEST:--}}"
    local request_digest="${13:-${REMOTE_RELEASE_REQUEST_DIGEST:--}}"
    local terminal_digest="${14:-${REMOTE_RELEASE_TERMINAL_DIGEST:--}}"

    ssh "$SERVER" /usr/bin/python3 - \
        "$operation" "$REMOTE_RELEASE_LOCK_DIR" "$token" "$label" \
        "$stage" "$source_sha" "$source_tree" "$adopt" \
        "$surface" "$release_operation" "$channel" "$transaction_id" \
        "$baseline_digest" "$request_digest" "$terminal_digest" <<'REMOTE_RELEASE_LOCK_PY'
import datetime
import os
import re
import stat
import sys

(
    operation,
    lock_path,
    token,
    label,
    stage_path,
    source_sha,
    source_tree,
    adopt,
    surface,
    release_operation,
    channel,
    transaction_id,
    baseline_digest,
    request_digest,
    terminal_digest,
) = sys.argv[1:]
canonical_lock = "/var/lib/health-app/release-state/deploy.lock"
expected_uid = 0 if lock_path == canonical_lock else os.geteuid()
expected_gid = 0 if lock_path == canonical_lock else None
lock_re = re.compile(r"/[A-Za-z0-9._/-]+")
token_re = re.compile(r"[A-Za-z0-9._:-]{1,128}")
canonical_token_re = re.compile(r"[0-9a-f]{64}")
label_re = re.compile(r"[A-Za-z0-9._:-]{1,128}")
surface_re = re.compile(r"(?:server|mobile|native|mac)")
operation_re = re.compile(
    r"(?:all|frontend|backend|env|health-evidence|app-store-review-reset|"
    r"restart|mac-routes|forward|rollback|remote-build|publish|recover)"
)
transaction_re = re.compile(r"[0-9a-f]{32}")
digest_re = re.compile(r"[0-9a-f]{64}")
stage_re = re.compile(
    r"/tmp/health-app-backup-preflight-(?:[1-9][0-9]*-[1-9][0-9]*|[0-9a-f]{64})"
)
sha_re = re.compile(r"[0-9a-f]{40}")
time_re = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
metadata_names = {
    "schema", "token", "label", "stage", "started_at", "source_sha",
    "source_tree", "state", "surface", "operation", "channel",
    "transaction_id", "baseline_digest", "request_digest", "terminal_digest"
}
surface_operations = {
    "server": {
        "all", "frontend", "backend", "env", "health-evidence",
        "app-store-review-reset", "restart", "mac-routes",
    },
    "mobile": {"forward", "rollback"},
    "native": {"remote-build"},
    "mac": {"publish", "recover", "rollback"},
}
stage_names = {
    "backup_db.sh", "verify_backup_restore.sh", "archive_backup_offsite.sh",
    "rollback_release.sh", "activate_health_evidence_runtime.sh",
    "verify_locked_requirements.py", "verify_runtime_schema_compatibility.py",
    "quarantine_runtime_only_kb.py", "runtime_state_release_transaction.py",
    "review_manifest.json", "health-backend-runtime-state.conf",
    "celery-worker-runtime-state.conf", "celery-beat-runtime-state.conf",
    "staged.sha256", "backend.env.rollback", "backend.env.candidate",
    "candidate.env", "guard.env", "deploy.bundle", "mac-release-nginx-bootstrap.sh",
    "mac_release_nginx_bootstrap.py", "mac-release-routes.conf",
    "mac-routes.source", "mac-routes.sha256",
}
activation_names = {"launch-intent", "success", "success.outcome"}
dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
read_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


def fail(message, code=73):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def safe_absolute(value, pattern):
    return (
        pattern.fullmatch(value) is not None
        and value != "/"
        and "/../" not in value
        and not value.endswith("/..")
        and "/./" not in value
        and not value.endswith("/.")
    )


if not safe_absolute(lock_path, lock_re):
    fail("unsafe lock path", 70)
if (
    canonical_token_re.fullmatch(token) is None
    if lock_path == canonical_lock
    else token_re.fullmatch(token) is None
):
    fail("unsafe lock identity", 70)
if operation != "handoff" and (
    label_re.fullmatch(label) is None
    or stage_re.fullmatch(stage_path) is None
    or sha_re.fullmatch(source_sha) is None
    or sha_re.fullmatch(source_tree) is None
    or surface_re.fullmatch(surface) is None
    or operation_re.fullmatch(release_operation) is None
    or release_operation not in surface_operations.get(surface, set())
    or channel != "production"
    or transaction_re.fullmatch(transaction_id) is None
    or (baseline_digest != "-" and digest_re.fullmatch(baseline_digest) is None)
    or digest_re.fullmatch(request_digest) is None
    or (terminal_digest != "-" and digest_re.fullmatch(terminal_digest) is None)
):
    fail("unsafe lock source metadata", 70)
if operation in {"complete", "finish"} and surface in {"mobile", "native", "mac"}:
    if digest_re.fullmatch(terminal_digest) is None:
        fail("terminal coordinator operation requires an exact digest", 70)
if adopt not in {"0", "1"}:
    fail("unsafe adoption flag", 70)

parent_path = os.path.dirname(lock_path)
lock_name = os.path.basename(lock_path)
try:
    parent_fd = os.open(parent_path, dir_flags)
except OSError as error:
    fail(f"cannot open lock parent: {error}")


def validate_directory(fd, *, mode, label_text):
    meta = os.fstat(fd)
    if (
        not stat.S_ISDIR(meta.st_mode)
        or meta.st_uid != expected_uid
        or (expected_gid is not None and meta.st_gid != expected_gid)
        or stat.S_IMODE(meta.st_mode) != mode
    ):
        fail(f"unsafe {label_text} directory")
    return meta


def read_regular(directory_fd, name, maximum=512):
    try:
        fd = os.open(name, read_flags, dir_fd=directory_fd)
    except OSError as error:
        fail(f"cannot open lock metadata {name}: {error}")
    try:
        meta = os.fstat(fd)
        if (
            not stat.S_ISREG(meta.st_mode)
            or meta.st_uid != expected_uid
            or (expected_gid is not None and meta.st_gid != expected_gid)
            or stat.S_IMODE(meta.st_mode) != 0o600
            or meta.st_nlink != 1
            or meta.st_size <= 0
            or meta.st_size > maximum
        ):
            fail(f"unsafe lock metadata {name}")
        data = os.read(fd, maximum + 1)
        if len(data) > maximum or os.read(fd, 1):
            fail(f"oversized lock metadata {name}")
        return data
    finally:
        os.close(fd)


def validate_lock_values(values, *, partial=False):
    validators = {
        "schema": lambda value: value == "2",
        "token": lambda value: (
            canonical_token_re.fullmatch(value) is not None
            if lock_path == canonical_lock
            else token_re.fullmatch(value) is not None
        ),
        "label": lambda value: label_re.fullmatch(value) is not None,
        "stage": lambda value: stage_re.fullmatch(value) is not None,
        "started_at": lambda value: time_re.fullmatch(value) is not None,
        "source_sha": lambda value: sha_re.fullmatch(value) is not None,
        "source_tree": lambda value: sha_re.fullmatch(value) is not None,
        "state": lambda value: value in {
            "allocating", "sealed", "mutating", "completed"
        },
        "surface": lambda value: surface_re.fullmatch(value) is not None,
        "operation": lambda value: operation_re.fullmatch(value) is not None,
        "channel": lambda value: value == "production",
        "transaction_id": lambda value: transaction_re.fullmatch(value) is not None,
        "baseline_digest": lambda value: (
            value == "-" or digest_re.fullmatch(value) is not None
        ),
        "request_digest": lambda value: digest_re.fullmatch(value) is not None,
        "terminal_digest": lambda value: (
            value == "-" or digest_re.fullmatch(value) is not None
        ),
    }
    if not partial and set(values) != metadata_names:
        fail("release lock metadata allowlist mismatch")
    if any(name not in validators or not validators[name](value) for name, value in values.items()):
        fail("invalid release lock metadata values")
    if (
        "surface" in values
        and "operation" in values
        and values["operation"] not in surface_operations[values["surface"]]
    ):
        fail("invalid release lock surface/operation pair")


def open_and_validate_lock(name=lock_name, *, partial=False):
    try:
        lock_fd = os.open(name, dir_flags, dir_fd=parent_fd)
    except OSError as error:
        fail(f"cannot safely open release lock: {error}")
    validate_directory(lock_fd, mode=0o700, label_text="release lock")
    names = set(os.listdir(lock_fd))
    if (not partial and names != metadata_names) or not names.issubset(metadata_names):
        os.close(lock_fd)
        fail("release lock metadata allowlist mismatch")
    values = {}
    for field in names:
        raw = read_regular(lock_fd, field)
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            os.close(lock_fd)
            fail(f"non-ASCII lock metadata {field}")
        if not text.endswith("\n") or "\n" in text[:-1]:
            os.close(lock_fd)
            fail(f"non-canonical lock metadata {field}")
        values[field] = text[:-1]
    validate_lock_values(values, partial=partial)
    if (
        not partial
        and values["state"] in {"sealed", "mutating", "completed"}
        and values["baseline_digest"] == "-"
    ):
        os.close(lock_fd)
        fail("bound release lock is missing its production baseline")
    if (
        not partial
        and values["state"] == "completed"
        and values["terminal_digest"] == "-"
    ):
        os.close(lock_fd)
        fail("completed release lock is missing its terminal proof")
    return lock_fd, values


def write_regular(directory_fd, name, value):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, expected_uid, expected_gid if expected_gid is not None else -1)
        payload = (value + "\n").encode("ascii")
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("short lock metadata write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_state(lock_fd, value):
    temp_name = f".{lock_name}.state-{token}"
    try:
        write_regular(parent_fd, temp_name, value)
        os.replace(
            temp_name,
            f"{lock_name}/state",
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(lock_fd)
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def replace_metadata(lock_fd, name, value):
    if name not in {"baseline_digest", "terminal_digest"}:
        fail("unsupported release metadata transition")
    recovery_kind = "baseline" if name == "baseline_digest" else "terminal"
    temp_name = f".{lock_name}.{recovery_kind}-{token}"
    try:
        write_regular(parent_fd, temp_name, value)
        os.replace(
            temp_name,
            f"{lock_name}/{name}",
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(lock_fd)
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


receipt_dir_name = "coordinator-receipts"
receipt_file_name = f"{transaction_id}.receipt"
receipt_fields = (
    "schema", "token", "label", "stage", "source_sha", "source_tree",
    "surface", "operation", "channel", "transaction_id",
    "baseline_digest", "request_digest", "terminal_digest",
)


def receipt_payload(values, terminal):
    payload_values = {
        "schema": "1",
        "token": values["token"],
        "label": values["label"],
        "stage": values["stage"],
        "source_sha": values["source_sha"],
        "source_tree": values["source_tree"],
        "surface": values["surface"],
        "operation": values["operation"],
        "channel": values["channel"],
        "transaction_id": values["transaction_id"],
        "baseline_digest": values["baseline_digest"],
        "request_digest": values["request_digest"],
        "terminal_digest": terminal,
    }
    return "".join(f"{name}={payload_values[name]}\n" for name in receipt_fields).encode("ascii")


def open_receipt_directory(*, create=False):
    if create:
        try:
            os.mkdir(receipt_dir_name, 0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    try:
        fd = os.open(receipt_dir_name, dir_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        fail(f"cannot safely open coordinator receipts: {error}")
    validate_directory(fd, mode=0o700, label_text="coordinator receipts")
    temporary_names = []
    for name in os.listdir(fd):
        if (
            re.fullmatch(r"[0-9a-f]{32}\.receipt", name) is None
            and re.fullmatch(
                r"\.[0-9a-f]{32}\.[A-Za-z0-9._:-]{1,128}\.receipt",
                name,
            ) is None
        ):
            os.close(fd)
            fail("coordinator receipt allowlist mismatch")
        if name.startswith("."):
            temporary_names.append(name)
    expected_temporary = f".{transaction_id}.{token}.receipt"
    if len(temporary_names) > 1 or (
        temporary_names and temporary_names[0] != expected_temporary
    ):
        os.close(fd)
        fail("pending coordinator receipt recovery blocks another transaction")
    return fd


def read_receipt(receipt_fd):
    if receipt_fd is None:
        return None
    try:
        return read_regular(receipt_fd, receipt_file_name, maximum=4096)
    except SystemExit:
        raise


def read_optional_receipt(receipt_fd):
    if receipt_fd is None:
        return None
    try:
        os.stat(receipt_file_name, dir_fd=receipt_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    return read_regular(receipt_fd, receipt_file_name, maximum=4096)


def write_terminal_receipt(values, terminal):
    payload = receipt_payload(values, terminal)
    receipt_fd = open_receipt_directory(create=True)
    temp_name = f".{transaction_id}.{token}.receipt"
    temporary_names = [
        name
        for name in os.listdir(receipt_fd)
        if name.startswith(f".{transaction_id}.")
    ]
    if len(temporary_names) > 1:
        os.close(receipt_fd)
        fail("multiple coordinator receipt recovery entries")
    if temporary_names:
        if temporary_names[0] != temp_name:
            os.close(receipt_fd)
            fail("coordinator receipt recovery ownership changed")
        temporary = read_regular(receipt_fd, temp_name, maximum=4096)
        if temporary != payload:
            os.close(receipt_fd)
            fail("coordinator receipt recovery identity changed")
        existing = read_optional_receipt(receipt_fd)
        if existing is None:
            os.rename(
                temp_name,
                receipt_file_name,
                src_dir_fd=receipt_fd,
                dst_dir_fd=receipt_fd,
            )
        elif existing == payload:
            os.unlink(temp_name, dir_fd=receipt_fd)
        else:
            os.close(receipt_fd)
            fail("coordinator transaction receipt identity changed")
        os.fsync(receipt_fd)
    existing = read_optional_receipt(receipt_fd)
    if existing is not None:
        if existing != payload:
            os.close(receipt_fd)
            fail("coordinator transaction receipt identity changed")
        os.close(receipt_fd)
        return
    fd = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        fd = os.open(temp_name, flags, 0o600, dir_fd=receipt_fd)
        os.fchmod(fd, 0o600)
        os.fchown(fd, expected_uid, expected_gid if expected_gid is not None else -1)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                fail("short coordinator receipt write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.rename(temp_name, receipt_file_name, src_dir_fd=receipt_fd, dst_dir_fd=receipt_fd)
        os.fsync(receipt_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temp_name, dir_fd=receipt_fd)
        except FileNotFoundError:
            pass
        os.close(receipt_fd)


def validate_terminal_receipt(values, terminal):
    receipt_fd = open_receipt_directory(create=False)
    existing = read_optional_receipt(receipt_fd)
    if receipt_fd is not None:
        os.close(receipt_fd)
    if existing != receipt_payload(values, terminal):
        fail("coordinator terminal receipt is missing or changed")


def validate_payload_directory(path, allowed_names, label_text):
    try:
        fd = os.open(path, dir_flags)
    except FileNotFoundError:
        return None
    except OSError as error:
        fail(f"cannot safely open {label_text}: {error}")
    validate_directory(fd, mode=0o700, label_text=label_text)
    names = set(os.listdir(fd))
    if not names.issubset(allowed_names):
        os.close(fd)
        fail(f"{label_text} allowlist mismatch")
    for name in names:
        try:
            entry_fd = os.open(name, read_flags, dir_fd=fd)
        except OSError as error:
            os.close(fd)
            fail(f"unsafe {label_text} entry: {error}")
        try:
            meta = os.fstat(entry_fd)
            if (
                not stat.S_ISREG(meta.st_mode)
                or meta.st_uid != expected_uid
                or (expected_gid is not None and meta.st_gid != expected_gid)
                or meta.st_nlink != 1
                or stat.S_IMODE(meta.st_mode)
                not in {0o400, 0o600, 0o644, 0o700, 0o755}
            ):
                fail(f"unsafe {label_text} entry metadata")
        finally:
            os.close(entry_fd)
    return fd


def detach_lock(lock_fd):
    tombstone = f".{lock_name}.released-{token}"
    try:
        os.stat(tombstone, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        fail("release lock tombstone already exists")
    os.rename(lock_name, tombstone, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    os.fsync(parent_fd)
    return tombstone


def delete_tombstone(lock_fd, tombstone):
    try:
        for name in sorted(metadata_names):
            try:
                os.unlink(name, dir_fd=lock_fd)
            except FileNotFoundError:
                pass
        os.fsync(lock_fd)
    finally:
        os.close(lock_fd)
    os.rmdir(tombstone, dir_fd=parent_fd)
    os.fsync(parent_fd)


def delete_payload(fd, path):
    if fd is None:
        return
    try:
        for name in os.listdir(fd):
            os.unlink(name, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.rmdir(path)


def list_recovery_siblings():
    prefix = f".{lock_name}."
    orphan_re = re.compile(
        rf"\.{re.escape(lock_name)}\.(alloc|state|baseline|terminal|released)-([A-Za-z0-9._:-]{{1,128}})"
    )
    mac_re = re.compile(
        rf"\.{re.escape(lock_name)}\.mac-(creating|phase|releasing)-"
        r"([A-Za-z0-9._:-]{1,128})"
    )
    entries = []
    for name in os.listdir(parent_fd):
        if not name.startswith(prefix):
            continue
        mac_match = mac_re.fullmatch(name)
        if mac_match is not None:
            entries.append((name, "mac", mac_match.group(1), mac_match.group(2)))
            continue
        match = orphan_re.fullmatch(name)
        if match is None:
            fail("unknown release lock recovery entry")
        entries.append((name, "generic", match.group(1), match.group(2)))
    if len(entries) > 1:
        fail("multiple release lock recovery entries")
    return entries


def inspect_orphan_siblings():
    entries = list_recovery_siblings()
    if entries and entries[0][1] == "mac":
        # Mac publishing shares this canonical lease but has its own durable
        # partial-rename protocol. Generic deploy never mutates or reaps Mac
        # residues; their mere presence blocks acquisition byte-for-byte.
        fail("pending Mac release lease recovery blocks generic deploy")
    orphans = [
        (name, kind, owner)
        for name, _family, kind, owner in entries
    ]
    return orphans


def recover_orphan_for_explicit_owner(orphan):
    name, kind, owner = orphan
    if kind in {"baseline", "terminal"}:
        if owner != token:
            fail(f"release {kind} recovery ownership changed")
        raw = read_regular(parent_fd, name)
        try:
            value = raw.decode("ascii")
        except UnicodeDecodeError:
            fail(f"non-ASCII release {kind} recovery entry")
        if not value.endswith("\n") or digest_re.fullmatch(value[:-1]) is None:
            fail(f"invalid release {kind} recovery entry")
        lock_fd, values = open_and_validate_lock(partial=True)
        expected_state = "allocating" if kind == "baseline" else "mutating"
        metadata_field = "baseline_digest" if kind == "baseline" else "terminal_digest"
        if values.get("token") != token or values.get("state") != expected_state:
            os.close(lock_fd)
            fail(f"release {kind} recovery identity mismatch")
        if values.get(metadata_field) == "-":
            os.replace(
                name,
                f"{lock_name}/{metadata_field}",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(lock_fd)
            os.fsync(parent_fd)
        elif values.get(metadata_field) == value[:-1]:
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        else:
            os.close(lock_fd)
            fail(f"release {kind} recovery value changed")
        os.close(lock_fd)
        return
    if kind == "state":
        if owner != token:
            fail("release state recovery ownership changed")
        raw = read_regular(parent_fd, name)
        try:
            value = raw.decode("ascii")
        except UnicodeDecodeError:
            fail("non-ASCII release state recovery entry")
        if value not in {"allocating\n", "sealed\n", "mutating\n", "completed\n"}:
            fail("invalid release state recovery entry")
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return
    if adopt != "1" or owner != token:
        fail("pending remote release cleanup requires explicit original owner")

    orphan_fd, values = open_and_validate_lock(name, partial=True)
    if "token" in values and values["token"] != token:
        os.close(orphan_fd)
        fail("release recovery token metadata mismatch")
    if "label" in values and values["label"] != label:
        os.close(orphan_fd)
        fail("release recovery label metadata mismatch")
    if kind == "alloc":
        delete_tombstone(orphan_fd, name)
        return

    stage_fd = None
    activation_fd = None
    if "stage" in values:
        stage_fd = validate_payload_directory(
            values["stage"], stage_names, "release stage"
        )
        activation_fd = validate_payload_directory(
            values["stage"] + ".activation-state",
            activation_names,
            "activation state",
        )
    # Validate every remaining byte before the first recovery write.  Payload
    # cleanup precedes metadata deletion, so an interruption remains
    # discoverable by this token-bound tombstone on the next invocation.
    delete_payload(stage_fd, values.get("stage", ""))
    delete_payload(
        activation_fd,
        values.get("stage", "") + ".activation-state",
    )
    delete_tombstone(orphan_fd, name)


def inspect_generic_recovery_entry(entry):
    name, family, kind, owner = entry
    if family != "generic":
        fail("generic recovery inspection received foreign entry")
    if kind == "state":
        raw = read_regular(parent_fd, name)
        try:
            value = raw.decode("ascii")
        except UnicodeDecodeError:
            fail("non-ASCII release state recovery entry")
        if value not in {"allocating\n", "sealed\n", "mutating\n", "completed\n"}:
            fail("invalid release state recovery entry")
        return "unknown"
    orphan_fd, values = open_and_validate_lock(name, partial=True)
    os.close(orphan_fd)
    if "token" in values and values["token"] != owner:
        fail("release recovery token metadata mismatch")
    return values.get("label", "unknown")


try:
    parent_meta = os.fstat(parent_fd)
    if (
        not stat.S_ISDIR(parent_meta.st_mode)
        or parent_meta.st_uid != expected_uid
        or (expected_gid is not None and parent_meta.st_gid != expected_gid)
        or stat.S_IMODE(parent_meta.st_mode) & 0o022
    ):
        fail("unsafe release lock parent")

    if operation == "handoff":
        entries = list_recovery_siblings()
        entry = entries[0] if entries else None
        if entry is not None and entry[1] == "mac":
            _name, _family, kind, owner = entry
            print(
                "REMOTE_RELEASE_HANDOFF status=mac-recovery "
                f"kind={kind} token={owner}"
            )
            raise SystemExit(0)
        try:
            os.stat(lock_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if entry is None:
                print("REMOTE_RELEASE_HANDOFF status=none")
            else:
                label_value = inspect_generic_recovery_entry(entry)
                _name, _family, kind, owner = entry
                print(
                    "REMOTE_RELEASE_HANDOFF status=recovery "
                    f"kind={kind} token={owner} label={label_value}"
                )
            raise SystemExit(0)
        lock_fd, values = open_and_validate_lock()
        os.close(lock_fd)
        if entry is not None:
            inspect_generic_recovery_entry(entry)
            if entry[3] != values["token"]:
                fail("active lock and recovery entry ownership mismatch")
        print(
            "REMOTE_RELEASE_HANDOFF status=active "
            f"token={values['token']} label={values['label']} "
            f"state={values['state']} stage={values['stage']} "
            f"source_sha={values['source_sha']} "
            f"source_tree={values['source_tree']} "
            f"surface={values['surface']} "
            f"operation={values['operation']} "
            f"channel={values['channel']} "
            f"transaction_id={values['transaction_id']} "
            f"baseline_digest={values['baseline_digest']} "
            f"request_digest={values['request_digest']} "
            f"terminal_digest={values['terminal_digest']}"
        )
    elif operation == "acquire":
        orphans = inspect_orphan_siblings()
        recovered_released = False
        if orphans:
            recovered_released = orphans[0][1] == "released"
            recover_orphan_for_explicit_owner(orphans[0])
        try:
            os.stat(lock_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if adopt == "1":
                if recovered_released:
                    print("REMOTE_RELEASE_LOCK_ALREADY_RELEASED")
                    raise SystemExit(0)
                fail("explicit remote release owner is missing")
            receipt_fd = open_receipt_directory(create=False)
            existing_receipt = read_optional_receipt(receipt_fd)
            if receipt_fd is not None:
                os.close(receipt_fd)
            if existing_receipt is not None:
                fail("coordinator transaction already has a terminal receipt")
            temporary = f".{lock_name}.alloc-{token}"
            try:
                os.mkdir(temporary, 0o700, dir_fd=parent_fd)
                temp_fd = os.open(temporary, dir_flags, dir_fd=parent_fd)
                try:
                    os.fchmod(temp_fd, 0o700)
                    os.fchown(
                        temp_fd,
                        expected_uid,
                        expected_gid if expected_gid is not None else -1,
                    )
                    values = {
                        "schema": "2",
                        "token": token,
                        "label": label,
                        "stage": stage_path,
                        "started_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "source_sha": source_sha,
                        "source_tree": source_tree,
                        "state": "allocating",
                        "surface": surface,
                        "operation": release_operation,
                        "channel": channel,
                        "transaction_id": transaction_id,
                        "baseline_digest": baseline_digest,
                        "request_digest": request_digest,
                        "terminal_digest": terminal_digest,
                    }
                    for field in sorted(values):
                        write_regular(temp_fd, field, values[field])
                    os.fsync(temp_fd)
                finally:
                    os.close(temp_fd)
                os.rename(
                    temporary, lock_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd
                )
                os.fsync(parent_fd)
            except BaseException:
                try:
                    temp_fd = os.open(temporary, dir_flags, dir_fd=parent_fd)
                except OSError:
                    pass
                else:
                    try:
                        for field in os.listdir(temp_fd):
                            if field in metadata_names:
                                os.unlink(field, dir_fd=temp_fd)
                        os.fsync(temp_fd)
                    finally:
                        os.close(temp_fd)
                    try:
                        os.rmdir(temporary, dir_fd=parent_fd)
                    except OSError:
                        pass
                raise
            print(
                "REMOTE_RELEASE_LOCK_CREATED state=allocating "
                f"stage={stage_path} source_sha={source_sha} "
                f"source_tree={source_tree}"
            )
        else:
            lock_fd, values = open_and_validate_lock()
            os.close(lock_fd)
            if adopt != "1":
                fail(
                    "remote release already active: "
                    f"label={values['label']} started={values['started_at']}"
                )
            if (
                values["token"] != token
                or values["label"] != label
                or values["stage"] != stage_path
                or values["source_sha"] != source_sha
                or values["source_tree"] != source_tree
                or values["surface"] != surface
                or values["operation"] != release_operation
                or values["channel"] != channel
                or values["transaction_id"] != transaction_id
                or not (
                    values["baseline_digest"] == baseline_digest
                    or (
                        adopt == "1"
                        and baseline_digest == "-"
                        and values["baseline_digest"] != "-"
                    )
                    or (
                        adopt == "1"
                        and values["state"] == "allocating"
                        and values["baseline_digest"] == "-"
                        and digest_re.fullmatch(baseline_digest) is not None
                    )
                )
                or values["request_digest"] != request_digest
                or not (
                    values["terminal_digest"] == terminal_digest
                    or (
                        adopt == "1"
                        and terminal_digest == "-"
                        and values["terminal_digest"] != "-"
                    )
                )
            ):
                fail("remote release adoption identity mismatch")
            print(
                "REMOTE_RELEASE_LOCK_ADOPTED "
                f"state={values['state']} stage={values['stage']} "
                f"source_sha={values['source_sha']} "
                f"source_tree={values['source_tree']} "
                f"surface={values['surface']} "
                f"operation={values['operation']} "
                f"channel={values['channel']} "
                f"transaction_id={values['transaction_id']} "
                f"baseline_digest={values['baseline_digest']} "
                f"request_digest={values['request_digest']} "
                f"terminal_digest={values['terminal_digest']}"
            )
    elif operation in {
        "assert", "bind", "seal", "mutate", "complete", "abort", "finish"
    }:
        orphans = inspect_orphan_siblings()
        if orphans:
            name, kind, owner = orphans[0]
            if owner != token:
                fail("remote release cleanup is still pending")
            if kind in {"state", "terminal"}:
                recover_orphan_for_explicit_owner((name, kind, owner))
            elif kind == "released" and operation == "finish":
                orphan_fd, orphan_values = open_and_validate_lock(
                    name, partial=True
                )
                if orphan_values.get("token") != token:
                    os.close(orphan_fd)
                    fail("released coordinator recovery identity mismatch")
                if set(orphan_values) != metadata_names:
                    os.close(orphan_fd)
                    fail("released coordinator recovery metadata incomplete")
                validate_terminal_receipt(
                    orphan_values, orphan_values["terminal_digest"]
                )
                if any(
                    orphan_values[field] != expected
                    for field, expected in {
                        "label": label,
                        "stage": stage_path,
                        "source_sha": source_sha,
                        "source_tree": source_tree,
                        "surface": surface,
                        "operation": release_operation,
                        "channel": channel,
                        "transaction_id": transaction_id,
                        "baseline_digest": baseline_digest,
                        "request_digest": request_digest,
                        "terminal_digest": terminal_digest,
                    }.items()
                ):
                    os.close(orphan_fd)
                    fail("released coordinator recovery identity changed")
                stage_fd = validate_payload_directory(
                    orphan_values["stage"], stage_names, "release stage"
                )
                activation_path = orphan_values["stage"] + ".activation-state"
                activation_fd = validate_payload_directory(
                    activation_path, activation_names, "activation state"
                )
                delete_payload(stage_fd, orphan_values["stage"])
                delete_payload(activation_fd, activation_path)
                delete_tombstone(orphan_fd, name)
                print("REMOTE_RELEASE_LOCK_ALREADY_RELEASED")
                raise SystemExit(0)
            else:
                fail("remote release cleanup is still pending")
        try:
            os.stat(lock_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if operation == "finish" and terminal_digest != "-":
                receipt_values = {
                    "token": token,
                    "label": label,
                    "stage": stage_path,
                    "source_sha": source_sha,
                    "source_tree": source_tree,
                    "surface": surface,
                    "operation": release_operation,
                    "channel": channel,
                    "transaction_id": transaction_id,
                    "baseline_digest": baseline_digest,
                    "request_digest": request_digest,
                }
                validate_terminal_receipt(receipt_values, terminal_digest)
                print("REMOTE_RELEASE_LOCK_ALREADY_RELEASED")
                raise SystemExit(0)
            fail("coordinator release lock is missing")
        lock_fd, values = open_and_validate_lock()
        if values["token"] != token:
            os.close(lock_fd)
            fail("release lock ownership changed")
        if operation not in {"bind", "complete"} and any(
            values[name] != expected
            for name, expected in {
                "label": label,
                "stage": stage_path,
                "source_sha": source_sha,
                "source_tree": source_tree,
                "surface": surface,
                "operation": release_operation,
                "channel": channel,
                "transaction_id": transaction_id,
                "baseline_digest": baseline_digest,
                "request_digest": request_digest,
                "terminal_digest": terminal_digest,
            }.items()
        ):
            os.close(lock_fd)
            fail("release lock coordinator identity changed")
        if operation == "assert":
            os.close(lock_fd)
            print(f"REMOTE_RELEASE_LOCK_ASSERTED state={values['state']}")
        elif operation == "bind":
            if (
                values["state"] not in {"allocating", "sealed"}
                or values["baseline_digest"] not in {"-", baseline_digest}
                or digest_re.fullmatch(baseline_digest) is None
                or any(
                    values[name] != expected
                    for name, expected in {
                        "label": label,
                        "stage": stage_path,
                        "source_sha": source_sha,
                        "source_tree": source_tree,
                        "surface": surface,
                        "operation": release_operation,
                        "channel": channel,
                        "transaction_id": transaction_id,
                        "request_digest": request_digest,
                    }.items()
                )
            ):
                os.close(lock_fd)
                fail("release lock bind identity mismatch")
            if values["baseline_digest"] == "-":
                if values["state"] != "allocating":
                    os.close(lock_fd)
                    fail("sealed release lock cannot have an unbound baseline")
                replace_metadata(lock_fd, "baseline_digest", baseline_digest)
            if values["state"] == "allocating":
                replace_state(lock_fd, "sealed")
                values["state"] = "sealed"
            os.close(lock_fd)
            print(f"REMOTE_RELEASE_LOCK_BOUND state={values['state']}")
        elif operation == "complete":
            if (
                values["surface"] not in {"mobile", "native", "mac"}
                or values["state"] not in {"mutating", "completed"}
                or digest_re.fullmatch(terminal_digest) is None
                or values["terminal_digest"] not in {"-", terminal_digest}
                or any(
                    values[name] != expected
                    for name, expected in {
                        "label": label,
                        "stage": stage_path,
                        "source_sha": source_sha,
                        "source_tree": source_tree,
                        "surface": surface,
                        "operation": release_operation,
                        "channel": channel,
                        "transaction_id": transaction_id,
                        "baseline_digest": baseline_digest,
                        "request_digest": request_digest,
                    }.items()
                )
            ):
                os.close(lock_fd)
                fail("release terminal proof identity mismatch")
            write_terminal_receipt(values, terminal_digest)
            if values["terminal_digest"] == "-":
                replace_metadata(lock_fd, "terminal_digest", terminal_digest)
            if values["state"] == "mutating":
                replace_state(lock_fd, "completed")
                values["state"] = "completed"
            os.close(lock_fd)
            print("REMOTE_RELEASE_LOCK_COMPLETED state=completed")
        elif operation in {"seal", "mutate"}:
            target = "sealed" if operation == "seal" else "mutating"
            if operation == "seal":
                allowed = {"allocating", "sealed"}
            elif values["surface"] in {"mobile", "native", "mac"}:
                allowed = {"sealed", "mutating"}
            else:
                allowed = {"allocating", "sealed", "mutating"}
            if values["state"] not in allowed:
                os.close(lock_fd)
                fail("invalid release lock state transition")
            if operation == "seal" and values["baseline_digest"] == "-":
                os.close(lock_fd)
                fail("release stage cannot seal before baseline binding")
            replace_state(lock_fd, target)
            os.close(lock_fd)
            print(f"REMOTE_RELEASE_LOCK_STATE state={target}")
        else:
            if operation == "abort" and values["state"] != "allocating":
                os.close(lock_fd)
                print(f"REMOTE_RELEASE_LOCK_NOT_ALLOCATING state={values['state']}")
                raise SystemExit(75)
            if (
                operation == "finish"
                and values["surface"] in {"mobile", "native", "mac"}
                and values["state"] != "completed"
            ):
                os.close(lock_fd)
                fail("coordinator finish requires a terminal-proven lease")
            if (
                operation == "finish"
                and values["surface"] in {"mobile", "native", "mac"}
            ):
                validate_terminal_receipt(values, values["terminal_digest"])
            stage_fd = validate_payload_directory(
                values["stage"], stage_names, "release stage"
            )
            activation_path = values["stage"] + ".activation-state"
            activation_fd = validate_payload_directory(
                activation_path, activation_names, "activation state"
            )
            # Every byte has been validated before the atomic lock detach.
            tombstone = detach_lock(lock_fd)
            delete_payload(stage_fd, values["stage"])
            delete_payload(activation_fd, activation_path)
            delete_tombstone(lock_fd, tombstone)
            print(
                "REMOTE_RELEASE_ALLOCATION_ABORTED"
                if operation == "abort"
                else "REMOTE_RELEASE_LOCK_RELEASED"
            )
    else:
        fail("unknown release lock operation", 70)
finally:
    os.close(parent_fd)
REMOTE_RELEASE_LOCK_PY
}

show_remote_release_lock_handoff() {
    builtin printf '%s\n' \
        "发布锁检查已冻结：等待仓库外受信检查器；不会读取或输出接管凭据。" >&2
    return 78
}

verify_expected_server_surfaces_under_lock() {
    local expected="${REVA_EXPECTED_SERVER_SURFACES:-}"
    local observed

    if [[ -z "$expected" ]]; then
        return 0
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ||
          ! "$REMOTE_RELEASE_LOCK_TOKEN" =~ ^[A-Za-z0-9._:-]{1,128}$ ]]; then
        print_error "服务器发布代际 CAS 缺少已持有的精确远端锁"
        return 73
    fi
    if ! observed="$(
        python3 "$SCRIPT_DIR/scripts/release_production_state.py" \
            server-under-lock "$REMOTE_RELEASE_LOCK_TOKEN"
    )"; then
        print_error "无法在服务器发布锁内复采生产代际"
        return 73
    fi
    if ! python3 - "$expected" "$observed" <<'PY'
import json
import re
import sys


def fail():
    raise SystemExit(73)


def parse(raw):
    try:
        value = json.loads(
            raw,
            object_pairs_hook=lambda pairs: dict(pairs),
            parse_constant=lambda _value: fail(),
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        fail()
    if not isinstance(value, list) or len(value) != 7:
        fail()
    patterns = (
        r"[0-9a-f]{40}", r"[0-9a-f]{64}", r"[0-9a-f]{40}",
        r"[0-9a-f]{64}", r"[0-9a-f]{40}", r"[0-9a-f]{64}",
        r"[0-9a-f]{64}",
    )
    for index, (item, pattern) in enumerate(zip(value, patterns)):
        if item is None and index in {2, 3, 4, 5, 6}:
            continue
        if not isinstance(item, str) or re.fullmatch(pattern, item) is None:
            fail()
    if (value[2] is None) != (value[3] is None):
        fail()
    if len({item is None for item in value[4:7]}) != 1:
        fail()
    return value


if parse(sys.argv[1]) != parse(sys.argv[2]):
    fail()
PY
    then
        print_error "服务器发布代际已变化；拒绝覆盖另一发布者的结果，请重新规划"
        return 73
    fi
    print_success "服务器发布代际 CAS 已在远端锁内核验"
}

capture_expected_server_surfaces_under_lock() {
    local observed
    local planned="${REVA_EXPECTED_SERVER_SURFACES:-}"
    local normalized

    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ||
          ! "$REMOTE_RELEASE_LOCK_TOKEN" =~ ^[A-Za-z0-9._:-]{1,128}$ ]]; then
        print_error "服务器生产代际只能在精确远端租约内采集"
        return 73
    fi
    if ! observed="$(
        python3 "$SCRIPT_DIR/scripts/release_production_state.py" \
            server-under-lock "$REMOTE_RELEASE_LOCK_TOKEN"
    )" || [[ -z "$observed" ]]; then
        print_error "无法在服务器发布锁内建立生产代际基线"
        return 73
    fi
    if ! normalized="$(python3 - "$observed" "$planned" <<'PY'
import json
import re
import sys


def fail():
    raise SystemExit(73)


def parse(raw):
    try:
        value = json.loads(raw, parse_constant=lambda _value: fail())
    except (TypeError, ValueError, json.JSONDecodeError):
        fail()
    if not isinstance(value, list) or len(value) != 7:
        fail()
    patterns = (
        r"[0-9a-f]{40}", r"[0-9a-f]{64}", r"[0-9a-f]{40}",
        r"[0-9a-f]{64}", r"[0-9a-f]{40}", r"[0-9a-f]{64}",
        r"[0-9a-f]{64}",
    )
    for index, (item, pattern) in enumerate(zip(value, patterns)):
        if item is None and index in {2, 3, 4, 5, 6}:
            continue
        if not isinstance(item, str) or re.fullmatch(pattern, item) is None:
            fail()
    if (value[2] is None) != (value[3] is None):
        fail()
    if len({item is None for item in value[4:7]}) != 1:
        fail()
    return value


observed = parse(sys.argv[1])
if sys.argv[2] and parse(sys.argv[2]) != observed:
    fail()
print(json.dumps(observed, separators=(",", ":")))
PY
    )"; then
        print_error "服务器生产代际与规划快照不一致；拒绝在锁内绑定"
        return 73
    fi
    REVA_EXPECTED_SERVER_SURFACES="$normalized"
    print_success "服务器发布代际基线已在远端锁内建立"
}

bind_expected_server_surfaces_under_lock() {
    local output
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ||
          -z "${REVA_EXPECTED_SERVER_SURFACES:-}" ]]; then
        print_error "服务器 baseline bind 缺少租约内生产快照"
        return 73
    fi
    REMOTE_RELEASE_BASELINE_DIGEST="$(
        printf '%s' "$REVA_EXPECTED_SERVER_SURFACES" |
            /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
    )" || return 73
    if ! [[ "$REMOTE_RELEASE_BASELINE_DIGEST" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "服务器 baseline digest 生成失败"
        return 73
    fi
    output="$(remote_release_lock_command bind)" || return 73
    if [[ "$output" != "REMOTE_RELEASE_LOCK_BOUND state=sealed" ]]; then
        print_error "服务器生产基线未获得 sealed 绑定证明"
        return 73
    fi
    REMOTE_RELEASE_LOCK_STATE="sealed"
}

assert_remote_release_lock() {
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ||
          -z "$REMOTE_RELEASE_LOCK_TOKEN" ]]; then
        print_error "服务器发布锁未持有"
        return 73
    fi
    local output
    output="$(remote_release_lock_command assert)" || return 73
    [[ "$output" == "REMOTE_RELEASE_LOCK_ASSERTED state="* ]] || return 73
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
    local output
    if ! output="$(remote_release_lock_command finish)" ||
        [[ "$output" != "REMOTE_RELEASE_LOCK_RELEASED" ]]; then
        print_error "服务器发布锁释放失败；保留锁以阻断并发发布"
        return 73
    fi
    _REMOTE_RELEASE_LOCK_ACQUIRED=0
    REMOTE_RELEASE_LOCK_TOKEN=""
    REMOTE_RELEASE_LOCK_LABEL=""
    REMOTE_RELEASE_LOCK_STATE=""
    REMOTE_RELEASE_SOURCE_SHA=""
    REMOTE_RELEASE_SOURCE_TREE=""
    REMOTE_RELEASE_SURFACE=""
    REMOTE_RELEASE_OPERATION=""
    REMOTE_RELEASE_CHANNEL=""
    REMOTE_RELEASE_TRANSACTION_ID=""
    REMOTE_RELEASE_BASELINE_DIGEST=""
    REMOTE_RELEASE_REQUEST_DIGEST=""
    REMOTE_RELEASE_TERMINAL_DIGEST=""
}

abort_remote_release_allocation() {
    local output
    if [[ "${_REMOTE_RELEASE_LOCK_ACQUIRED:-0}" != "1" ]]; then
        return 1
    fi
    output="$(remote_release_lock_command abort)" || return $?
    if [[ "$output" != "REMOTE_RELEASE_ALLOCATION_ABORTED" ]]; then
        return 73
    fi
    _REMOTE_RELEASE_LOCK_ACQUIRED=0
    REMOTE_RELEASE_LOCK_TOKEN=""
    REMOTE_RELEASE_LOCK_LABEL=""
    REMOTE_RELEASE_LOCK_STATE=""
    REMOTE_RELEASE_SOURCE_SHA=""
    REMOTE_RELEASE_SOURCE_TREE=""
    REMOTE_RELEASE_SURFACE=""
    REMOTE_RELEASE_OPERATION=""
    REMOTE_RELEASE_CHANNEL=""
    REMOTE_RELEASE_TRANSACTION_ID=""
    REMOTE_RELEASE_BASELINE_DIGEST=""
    REMOTE_RELEASE_REQUEST_DIGEST=""
    REMOTE_RELEASE_TERMINAL_DIGEST=""
}

validate_release_coordinator_environment() {
    local mode="$1"
    local surface="${REVA_RELEASE_COORDINATOR_SURFACE:-}"
    local operation="${REVA_RELEASE_COORDINATOR_OPERATION:-}"
    local channel="${REVA_RELEASE_COORDINATOR_CHANNEL:-}"
    local transaction="${REVA_RELEASE_COORDINATOR_TRANSACTION:-}"
    local request_digest="${REVA_RELEASE_COORDINATOR_REQUEST_DIGEST:-}"
    local baseline_digest="${REVA_RELEASE_COORDINATOR_BASELINE_DIGEST:-}"
    local stage="${REVA_RELEASE_COORDINATOR_STAGE:-}"
    local token="${REVA_REMOTE_RELEASE_LOCK_TOKEN:-}"
    local source_sha="${REVA_RELEASE_COORDINATOR_SOURCE_SHA:-}"
    local source_tree="${REVA_RELEASE_COORDINATOR_SOURCE_TREE:-}"
    local terminal_digest="${REVA_RELEASE_COORDINATOR_TERMINAL_DIGEST:-}"

    if [[ "$REMOTE_RELEASE_LOCK_DIR" = "/var/lib/health-app/release-state/deploy.lock" &&
          ( "$SERVER" != "root@39.98.206.178" ||
            "$REMOTE_PATH" != "/opt/health-app" ) ]]; then
        print_error "canonical production 协调器只允许固定服务器与部署根目录"
        return 70
    fi

    if ! [[ "$mode" =~ ^(begin|bind|assert|mutate|finish|abort|recover)$ &&
          "$surface" =~ ^(mobile|native|mac)$ &&
          "$channel" = "production" &&
          "$transaction" =~ ^[0-9a-f]{32}$ &&
          "$request_digest" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "远端发布协调器身份不符合固定 production 契约"
        return 70
    fi
    case "$surface:$operation" in
        mobile:forward|mobile:rollback|native:remote-build|mac:publish|mac:recover|mac:rollback) ;;
        *)
            print_error "远端发布协调器 surface/operation 组合不受支持"
            return 70
            ;;
    esac
    if [[ "$mode" = "begin" ]]; then
        if [[ -n "$token" || -n "$stage" || -n "$baseline_digest" ||
              -n "$source_sha" || -n "$source_tree" ||
              -n "$terminal_digest" ||
              "${REVA_REMOTE_RELEASE_LOCK_ADOPT:-0}" != "0" ]]; then
            print_error "协调器 begin 不接受调用者 token/stage/source/baseline/terminal 或接管标记"
            return 70
        fi
        return 0
    fi
    if ! [[ "$token" =~ ^[0-9a-f]{64}$ &&
          "$stage" =~ ^/tmp/health-app-backup-preflight-([1-9][0-9]*-[1-9][0-9]*|[0-9a-f]{64})$ &&
          "$source_sha" =~ ^[0-9a-f]{40}$ &&
          "$source_tree" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "远端发布协调器续作缺少精确 token/stage/source"
        return 70
    fi
    if [[ "$mode" = "abort" && "$baseline_digest" = "-" ]]; then
        return 0
    fi
    if ! [[ "$baseline_digest" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "远端发布协调器续作缺少精确 baseline digest"
        return 70
    fi
    if [[ "$mode" = "finish" ]] &&
       ! [[ "$terminal_digest" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "远端发布协调器 finish 缺少精确 terminal digest"
        return 70
    fi
    if [[ -n "$terminal_digest" ]] &&
       ! [[ "$terminal_digest" =~ ^[0-9a-f]{64}$ ]]; then
        print_error "远端发布协调器 terminal digest 格式非法"
        return 70
    fi
}

trusted_release_git() {
    /usr/bin/env -i \
        PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
        HOME="/var/empty" \
        LANG="C" \
        LC_ALL="C" \
        GIT_CONFIG_NOSYSTEM="1" \
        GIT_CONFIG_GLOBAL="/dev/null" \
        GIT_TERMINAL_PROMPT="0" \
        GIT_NO_REPLACE_OBJECTS="1" \
        /usr/bin/git --no-replace-objects -c core.hooksPath=/dev/null \
            -C "$SCRIPT_DIR" "$@"
}

trusted_release_network_git() {
    (
        cd / &&
        /usr/bin/env -i \
            PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
            HOME="/var/empty" \
            LANG="C" \
            LC_ALL="C" \
            GIT_CONFIG_NOSYSTEM="1" \
            GIT_CONFIG_GLOBAL="/dev/null" \
            GIT_TERMINAL_PROMPT="0" \
            GIT_NO_REPLACE_OBJECTS="1" \
            /usr/bin/git --no-replace-objects -c core.hooksPath=/dev/null "$@"
    )
}

verify_release_coordinator_source() {
    local dirty
    local branch
    local head_sha
    local head_tree
    local origin_urls
    local origin_push_urls
    local url_rewrites
    local remote_row
    local remote_sha
    local remote_ref
    local remote_extra

    dirty="$(trusted_release_git status --porcelain=v1 --untracked-files=all)" ||
        return 70
    if [[ -n "$dirty" ]]; then
        print_error "production 协调器只允许完全干净的发布源"
        return 70
    fi
    if branch="$(trusted_release_git symbolic-ref --quiet --short HEAD 2>/dev/null)"; then
        if [[ "$branch" != "main" ]]; then
            print_error "production 协调器只允许 main 或 exact origin/main detached HEAD"
            return 70
        fi
    else
        branch=""
    fi
    origin_urls="$(
        trusted_release_git config --local --get-all remote.origin.url
    )" || {
        print_error "production 协调器缺少 canonical origin"
        return 70
    }
    if [[ "$origin_urls" == *$'\n'* ||
          "$origin_urls" != "$CANONICAL_RELEASE_ORIGIN_URL" ]]; then
        print_error "production 协调器 origin 不等于固定仓库 authority"
        return 70
    fi
    origin_push_urls="$(
        trusted_release_git config --local --get-all remote.origin.pushurl 2>/dev/null || true
    )"
    url_rewrites="$(
        trusted_release_git config --local --get-regexp \
            '^url\..*\.(insteadOf|pushInsteadOf)$' 2>/dev/null || true
    )"
    if [[ -n "$origin_push_urls" || -n "$url_rewrites" ]]; then
        print_error "production 协调器拒绝 origin push override 或 URL rewrite"
        return 70
    fi
    local replace_refs
    replace_refs="$(
        trusted_release_git for-each-ref --format='%(refname)' refs/replace/
    )" || return 70
    if [[ -n "$replace_refs" ]]; then
        print_error "production 协调器拒绝 Git replacement refs"
        return 70
    fi
    head_sha="$(trusted_release_git rev-parse HEAD)" || return 70
    head_tree="$(trusted_release_git rev-parse "${head_sha}^{tree}")" || return 70
    remote_row="$(
        trusted_release_network_git ls-remote --exit-code \
            "$CANONICAL_RELEASE_ORIGIN_URL" refs/heads/main
    )" || return 70
    if [[ "$remote_row" == *$'\n'* ]]; then
        print_error "origin/main 返回歧义结果"
        return 70
    fi
    read -r remote_sha remote_ref remote_extra <<< "$remote_row"
    if ! [[ "$head_sha" =~ ^[0-9a-f]{40}$ &&
          "$head_tree" =~ ^[0-9a-f]{40}$ &&
          "$remote_sha" =~ ^[0-9a-f]{40}$ &&
          "$remote_ref" = "refs/heads/main" &&
          -z "$remote_extra" &&
          "$head_sha" = "$remote_sha" ]]; then
        print_error "production 协调器 source 必须精确等于远端 origin/main"
        return 70
    fi
    REVA_RELEASE_COORDINATOR_SOURCE_SHA="$head_sha"
    REVA_RELEASE_COORDINATOR_SOURCE_TREE="$head_tree"
    export REVA_RELEASE_COORDINATOR_SOURCE_SHA
    export REVA_RELEASE_COORDINATOR_SOURCE_TREE
}

begin_remote_release_coordinator() {
    validate_release_coordinator_environment begin || return $?
    verify_release_coordinator_source || return $?
    local label="coordinator:${REVA_RELEASE_COORDINATOR_SURFACE}:${REVA_RELEASE_COORDINATOR_OPERATION}"
    REVA_RELEASE_COORDINATOR_BASELINE_DIGEST="-"
    export REVA_RELEASE_COORDINATOR_BASELINE_DIGEST
    acquire_remote_release_lock "$label" || return $?
    printf '%s\n' \
        "REVA_RELEASE_COORDINATOR_BEGIN token=$REMOTE_RELEASE_LOCK_TOKEN stage=$REMOTE_BACKUP_PREFLIGHT_DIR source_sha=$REMOTE_RELEASE_SOURCE_SHA source_tree=$REMOTE_RELEASE_SOURCE_TREE surface=$REMOTE_RELEASE_SURFACE operation=$REMOTE_RELEASE_OPERATION channel=$REMOTE_RELEASE_CHANNEL transaction_id=$REMOTE_RELEASE_TRANSACTION_ID request_digest=$REMOTE_RELEASE_REQUEST_DIGEST"
    # The caller must now sample production under this exact lease and bind
    # the resulting baseline. Retain allocating state across this short,
    # explicit inter-process handoff; exact abort is the only safe cleanup.
    _REMOTE_RELEASE_LOCK_ABANDONED=1
}

adopt_remote_release_coordinator() {
    local mode="$1"
    local requested_baseline="${REVA_RELEASE_COORDINATOR_BASELINE_DIGEST:-}"
    local requested_terminal="${REVA_RELEASE_COORDINATOR_TERMINAL_DIGEST:--}"
    validate_release_coordinator_environment "$mode" || return $?
    set_remote_backup_preflight_dir "$REVA_RELEASE_COORDINATOR_STAGE"
    REVA_REMOTE_RELEASE_LOCK_ADOPT=1
    REVA_REMOTE_RELEASE_LOCK_ALLOW_ALLOCATING_ADOPT=1
    export REVA_REMOTE_RELEASE_LOCK_ADOPT
    export REVA_REMOTE_RELEASE_LOCK_ALLOW_ALLOCATING_ADOPT
    acquire_remote_release_lock \
        "coordinator:${REVA_RELEASE_COORDINATOR_SURFACE}:${REVA_RELEASE_COORDINATOR_OPERATION}" ||
        return $?
    if [[ "$mode" = "bind" ]]; then
        REMOTE_RELEASE_BASELINE_DIGEST="$requested_baseline"
    fi
    REMOTE_RELEASE_TERMINAL_DIGEST="$requested_terminal"
}

load_release_coordinator_context() {
    set_remote_backup_preflight_dir "$REVA_RELEASE_COORDINATOR_STAGE"
    REMOTE_RELEASE_LOCK_TOKEN="$REVA_REMOTE_RELEASE_LOCK_TOKEN"
    REMOTE_RELEASE_LOCK_LABEL="coordinator:${REVA_RELEASE_COORDINATOR_SURFACE}:${REVA_RELEASE_COORDINATOR_OPERATION}"
    REMOTE_RELEASE_SOURCE_SHA="$REVA_RELEASE_COORDINATOR_SOURCE_SHA"
    REMOTE_RELEASE_SOURCE_TREE="$REVA_RELEASE_COORDINATOR_SOURCE_TREE"
    REMOTE_RELEASE_SURFACE="$REVA_RELEASE_COORDINATOR_SURFACE"
    REMOTE_RELEASE_OPERATION="$REVA_RELEASE_COORDINATOR_OPERATION"
    REMOTE_RELEASE_CHANNEL="$REVA_RELEASE_COORDINATOR_CHANNEL"
    REMOTE_RELEASE_TRANSACTION_ID="$REVA_RELEASE_COORDINATOR_TRANSACTION"
    REMOTE_RELEASE_BASELINE_DIGEST="$REVA_RELEASE_COORDINATOR_BASELINE_DIGEST"
    REMOTE_RELEASE_REQUEST_DIGEST="$REVA_RELEASE_COORDINATOR_REQUEST_DIGEST"
    REMOTE_RELEASE_TERMINAL_DIGEST="${REVA_RELEASE_COORDINATOR_TERMINAL_DIGEST:--}"
}

bind_remote_release_coordinator() {
    adopt_remote_release_coordinator bind || return $?
    local output
    output="$(remote_release_lock_command bind)" || return $?
    if [[ "$output" != "REMOTE_RELEASE_LOCK_BOUND state=sealed" ]]; then
        print_error "远端发布协调器 baseline 绑定缺少 sealed 证明"
        return 73
    fi
    REMOTE_RELEASE_LOCK_STATE="sealed"
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    printf '%s\n' "$output"
}

assert_remote_release_coordinator() {
    adopt_remote_release_coordinator assert || return $?
    local output
    output="$(remote_release_lock_command assert)" || return $?
    if [[ ! "$output" =~ ^REMOTE_RELEASE_LOCK_ASSERTED\ state=(sealed|mutating)$ ]]; then
        print_error "远端发布协调器 assert 缺少 sealed/mutating 证明"
        return 73
    fi
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    printf '%s\n' "$output"
}

mutate_remote_release_coordinator() {
    adopt_remote_release_coordinator mutate || return $?
    local output
    output="$(remote_release_lock_command mutate)" || return $?
    if [[ "$output" != "REMOTE_RELEASE_LOCK_STATE state=mutating" ]]; then
        print_error "远端发布协调器 mutation 边界结果不明确"
        return 73
    fi
    REMOTE_RELEASE_LOCK_STATE="mutating"
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    printf '%s\n' "$output"
}

finish_remote_release_coordinator() {
    validate_release_coordinator_environment finish || return $?
    load_release_coordinator_context
    local complete_output=""
    local finish_output=""
    if complete_output="$(remote_release_lock_command complete)"; then
        if [[ "$complete_output" != \
              "REMOTE_RELEASE_LOCK_COMPLETED state=completed" ]]; then
            print_error "远端发布协调器 terminal proof 结果不明确"
            return 75
        fi
    fi
    if ! finish_output="$(remote_release_lock_command finish)"; then
        print_error "远端发布协调器终态/释放结果不明确；保留现场等待精确恢复"
        return 75
    fi
    if [[ "$finish_output" != "REMOTE_RELEASE_LOCK_RELEASED" &&
          "$finish_output" != "REMOTE_RELEASE_LOCK_ALREADY_RELEASED" ]]; then
        print_error "远端发布协调器缺少精确释放证明"
        return 75
    fi
    printf '%s\n' "REVA_RELEASE_COORDINATOR_FINISHED"
}

abort_remote_release_coordinator() {
    adopt_remote_release_coordinator abort || return $?
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    abort_remote_release_allocation || return $?
    _REMOTE_RELEASE_LOCK_ABANDONED=0
    printf '%s\n' "REVA_RELEASE_COORDINATOR_ABORTED"
}

recover_remote_release_coordinator() {
    validate_release_coordinator_environment recover || return $?
    if [[ "${REVA_RELEASE_COORDINATOR_TERMINAL_DIGEST:-}" =~ ^[0-9a-f]{64}$ ]]; then
        finish_remote_release_coordinator
        return $?
    fi
    load_release_coordinator_context
    local output
    if ! output="$(remote_release_lock_command assert)"; then
        print_error "无法读取精确 coordinator 现场；租约保持不变"
        return 75
    fi
    case "$output" in
        "REMOTE_RELEASE_LOCK_ASSERTED state=allocating")
            _REMOTE_RELEASE_LOCK_ACQUIRED=1
            abort_remote_release_allocation || return $?
            printf '%s\n' "REVA_RELEASE_COORDINATOR_RECOVERED outcome=aborted-allocation"
            ;;
        "REMOTE_RELEASE_LOCK_ASSERTED state=sealed")
            print_error "协调器已绑定但尚未跨 mutation 边界；请用原操作精确续作"
            return 75
            ;;
        "REMOTE_RELEASE_LOCK_ASSERTED state=mutating"|\
        "REMOTE_RELEASE_LOCK_ASSERTED state=completed")
            print_error "协调器已跨 mutation 边界；恢复必须提供锁内复证得到的 terminal digest"
            return 75
            ;;
        *)
            print_error "未知 coordinator 恢复状态"
            return 75
            ;;
    esac
}

seal_remote_release_stage() {
    local output
    output="$(remote_release_lock_command seal)" || return 73
    [[ "$output" == "REMOTE_RELEASE_LOCK_STATE state=sealed" ]] || return 73
    REMOTE_RELEASE_LOCK_STATE="sealed"
}

mark_remote_release_mutation_started() {
    local output
    output="$(remote_release_lock_command mutate)" || return 73
    [[ "$output" == "REMOTE_RELEASE_LOCK_STATE state=mutating" ]] || return 73
    REMOTE_RELEASE_LOCK_STATE="mutating"
}

# git bundle is written only while the token-bound root-only stage is still
# allocating. This function verifies that sealed artifact; it never writes a
# predictable root target in world-writable /tmp.
upload_deploy_bundle() {
    assert_remote_release_lock_if_acquired
    ssh "$SERVER" "
        set -euo pipefail
        test -f '$REMOTE_DEPLOY_BUNDLE'
        test ! -L '$REMOTE_DEPLOY_BUNDLE'
        test \"\$(stat -c '%U:%G:%a:%h' '$REMOTE_DEPLOY_BUNDLE')\" = root:root:600:1
        cd '$REMOTE_PATH'
        git bundle verify '$REMOTE_DEPLOY_BUNDLE' >/dev/null
        git bundle list-heads '$REMOTE_DEPLOY_BUNDLE' |
            awk -v expected='$DEPLOY_EXPECTED_SHA' '
                \$1 == expected { matches += 1 }
                END { exit(matches >= 1 ? 0 : 1) }
            '
    "
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
    local deploy_bundle

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
        verify_locked_requirements.py|\
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
        guard.env|\
        deploy.bundle)
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
        verify_locked_requirements.py
        verify_runtime_schema_compatibility.py
        quarantine_runtime_only_kb.py
        runtime_state_release_transaction.py
        review_manifest.json
        health-backend-runtime-state.conf
        celery-worker-runtime-state.conf
        celery-beat-runtime-state.conf
        deploy.bundle
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
        $2 == "deploy.bundle" {
            bundles += 1
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
            if (bundles != 1 ||
                (allowed != 14 &&
                 !(allowed == 16 && (backend_pair || activation_pair)))) {
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
        deploy_bundle="$(mktemp)" || return 1
        if ! git -C "$SCRIPT_DIR" bundle create "$deploy_bundle" HEAD >/dev/null; then
            rm -f -- "$deploy_bundle"
            return 1
        fi
        # The destination parent is the exact root-only stage just created by
        # this token. No unprivileged process can race inside it; a preexisting
        # basename aborts before scp, and exact regular metadata is rechecked
        # afterward without following links.
        if ! ssh "$SERVER" "test ! -e '$REMOTE_DEPLOY_BUNDLE' && test ! -L '$REMOTE_DEPLOY_BUNDLE'" ||
            ! scp "$deploy_bundle" "$SERVER:$REMOTE_DEPLOY_BUNDLE" ||
            ! ssh "$SERVER" "
                test -f '$REMOTE_DEPLOY_BUNDLE' &&
                test ! -L '$REMOTE_DEPLOY_BUNDLE' &&
                test \"\$(stat -c '%U:%G:%a:%h' '$REMOTE_DEPLOY_BUNDLE')\" = root:root:600:1 &&
                sync -f '$REMOTE_DEPLOY_BUNDLE' &&
                sync -f '$REMOTE_BACKUP_PREFLIGHT_DIR'
            "; then
            rm -f -- "$deploy_bundle"
            return 1
        fi
        rm -f -- "$deploy_bundle"
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
                verify_locked_requirements.py \
                verify_runtime_schema_compatibility.py \
                quarantine_runtime_only_kb.py \
                runtime_state_release_transaction.py \
                review_manifest.json \
                health-backend-runtime-state.conf \
                celery-worker-runtime-state.conf \
                celery-beat-runtime-state.conf \
                deploy.bundle \
                > staged.sha256 && \
            chmod 0400 staged.sha256 && \
            sync -f staged.sha256 && \
            sync -f '$REMOTE_BACKUP_PREFLIGHT_DIR'
        "; then
            return 1
        fi
    fi
    if ! seal_remote_release_stage; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "远端 release stage 已写入但未能原子封存；现场与租约保留"
        return 1
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
        )\" = 16
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
    echo "仅以下只读命令可执行:"
    echo "  -s, --status    查看服务器服务状态"
    echo "  -l, --logs      查看服务器日志"
    echo "  -h, --help      显示此帮助信息"
    echo ""
    echo "FROZEN (exit 78) — 所有生产写入必须走人工发布 Gate:"
    echo "  -a, --all | -f, --frontend | -b, --backend | -e, --env"
    echo "  -H, --activate-health-evidence | -R, --reset-app-store-review"
    echo "  -r, --restart | -p, --push"
    echo "  --bootstrap-mac-routes [rollback]"
    echo "  --bootstrap-mac-routes rollback"
    echo "  --publish-mac --version VERSION --build BUILD"
    echo "  --recover-mac-release | --rollback-mac-release"
    echo "  --release-coordinator-begin | --release-coordinator-bind"
    echo "  --release-coordinator-assert | --release-coordinator-mutate"
    echo "  --release-coordinator-finish | --release-coordinator-abort"
    echo "  --release-coordinator-recover"
    echo ""
    echo "配置文件: .env (本地管理，不被 git 追踪)"
    echo "  - DEPLOY_SERVER: 服务器地址 (当前: $SERVER)"
    echo "  - DEPLOY_PATH: 部署路径 (当前: $REMOTE_PATH)"
    echo ""
    echo "只读示例:"
    echo "  ./deploy.sh -s"
    echo "  ./deploy.sh -l"
    echo "  --inspect-release-lock  FROZEN (exit 78)；等待仓库外受信检查器"
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
        "REMOTE_RELEASE_STATE_DIR='$REMOTE_RELEASE_STATE_DIR' bash '$REMOTE_ROLLBACK_RUNNER' '$REMOTE_PATH' '$ROLLBACK_COMMIT' '$REMOTE_RELEASE_LOCK_DIR' '$REMOTE_RELEASE_LOCK_TOKEN'" 2>&1); then
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
            )" = "15"
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
    if [ "$current_count" = "15" ]; then
        for name in backend.env.rollback backend.env.candidate; do
            awk -v expected="$name" '
                $2 == expected { matches += 1 }
                END { exit(matches == 1 ? 0 : 1) }
            ' staged.sha256
        done
        exit 0
    fi
    test "$current_count" = "13"
    sha256sum \
        backup_db.sh \
        verify_backup_restore.sh \
        archive_backup_offsite.sh \
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
    )" = "15"
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

# Record the exact frontend process/build that passed the deployment health
# gate.  The production probe treats a missing receipt as unknown and rejects
# any present receipt that is not a root-owned, atomic, live-PM2 match.
write_frontend_runtime_receipt() {
    assert_remote_release_lock
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法为未知 revision 写入前端运行态收据"
        return 1
    fi

    if ! ssh "$SERVER" /usr/bin/python3 - \
        "$REMOTE_PATH" \
        "$DEPLOY_EXPECTED_SHA" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_FRONTEND_RUNTIME_RECEIPT'
import json
import os
import re
import secrets
import stat
import subprocess
import sys

repo_root, expected_sha, lock_path, lock_token = sys.argv[1:]
receipt_path = "/var/lib/health-app/release-state/frontend-runtime.json"
state_parent = os.path.dirname(os.path.dirname(receipt_path))
state_name = os.path.basename(os.path.dirname(receipt_path))
receipt_name = os.path.basename(receipt_path)
sha_re = re.compile(r"[0-9a-f]{40}")
path_re = re.compile(r"/[A-Za-z0-9._/-]+")
token_re = re.compile(r"[A-Za-z0-9._:-]+")
build_id_re = re.compile(r"[A-Za-z0-9._-]{1,128}")
safe_env = {
    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "HOME": "/root",
    "PM2_HOME": "/root/.pm2",
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    }
dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
read_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


def fail(message):
    raise RuntimeError(message)


def validate_safe_path(value, *, label):
    if (
        path_re.fullmatch(value) is None
        or value == "/"
        or "/../" in value
        or value.endswith("/..")
        or "/./" in value
        or value.endswith("/.")
    ):
        fail(f"unsafe {label}")


def open_directory(path, *, exact_mode=None, forbid_write=False):
    descriptor = os.open(path, dir_flags)
    metadata = os.fstat(descriptor)
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or (exact_mode is not None and mode != exact_mode)
        or (forbid_write and mode & 0o022)
    ):
        os.close(descriptor)
        fail(f"unsafe directory: {path}")
    return descriptor


def read_regular(directory_fd, name, *, mode, maximum):
    descriptor = os.open(name, read_flags, dir_fd=directory_fd)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            fail(f"unsafe regular file: {name}")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum or os.read(descriptor, 1):
            fail(f"oversized regular file: {name}")
        return raw
    finally:
        os.close(descriptor)


def assert_release_lock():
    lock_fd = open_directory(lock_path, exact_mode=0o700)
    try:
        raw = read_regular(lock_fd, "token", mode=0o600, maximum=256)
    finally:
        os.close(lock_fd)
    if raw != f"{lock_token}\n".encode("ascii"):
        fail("release lock ownership changed")


def run(argv, *, cwd=None):
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=safe_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        fail(f"command failed: {argv[0]}")
    return completed.stdout


if os.geteuid() != 0:
    fail("frontend runtime receipt requires root")
validate_safe_path(repo_root, label="repository path")
validate_safe_path(lock_path, label="release lock path")
if sha_re.fullmatch(expected_sha) is None:
    fail("invalid expected revision")
if token_re.fullmatch(lock_token) is None:
    fail("invalid release lock token")
assert_release_lock()

revision = run(
    [
        "/usr/bin/git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "filter.lfs.process=",
        "-c",
        "filter.lfs.required=false",
        "rev-parse",
        "HEAD",
    ],
    cwd=repo_root,
).strip()
dirty = run(
    [
        "/usr/bin/git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "filter.lfs.process=",
        "-c",
        "filter.lfs.required=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ],
    cwd=repo_root,
).strip()
if revision != expected_sha or dirty:
    fail("frontend checkout is not the clean expected revision")

processes = json.loads(run(["/usr/bin/pm2", "jlist"]))
if not isinstance(processes, list):
    fail("invalid PM2 process list")
matches = [
    process
    for process in processes
    if isinstance(process, dict) and process.get("name") == "health-frontend"
]
if len(matches) != 1:
    fail("ambiguous frontend PM2 process")
process = matches[0]
environment = process.get("pm2_env")
pid = process.get("pid")
uptime = environment.get("pm_uptime") if isinstance(environment, dict) else None
if (
    not isinstance(environment, dict)
    or environment.get("status") != "online"
    or isinstance(pid, bool)
    or not isinstance(pid, int)
    or pid <= 1
    or isinstance(uptime, bool)
    or not isinstance(uptime, int)
    or uptime <= 0
):
    fail("frontend PM2 identity is invalid")

build_id_path = os.path.join(repo_root, "frontend", ".next/BUILD_ID")
next_fd = open_directory(os.path.dirname(build_id_path), exact_mode=0o755)
try:
    build_id = read_regular(
        next_fd, os.path.basename(build_id_path), mode=0o644, maximum=256
    ).decode("ascii", errors="strict").strip()
finally:
    os.close(next_fd)
if build_id_re.fullmatch(build_id) is None:
    fail("invalid frontend BUILD_ID")

parent_fd = open_directory(state_parent, forbid_write=True)
try:
    try:
        os.mkdir(state_name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    state_fd = os.open(state_name, dir_flags, dir_fd=parent_fd)
finally:
    os.close(parent_fd)
try:
    state_metadata = os.fstat(state_fd)
    if (
        not stat.S_ISDIR(state_metadata.st_mode)
        or state_metadata.st_uid != 0
        or state_metadata.st_gid != 0
        or stat.S_IMODE(state_metadata.st_mode) != 0o700
    ):
        fail("unsafe frontend receipt directory")
    try:
        existing = os.stat(receipt_name, dir_fd=state_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    if existing is not None and (
        not stat.S_ISREG(existing.st_mode)
        or existing.st_uid != 0
        or existing.st_gid != 0
        or stat.S_IMODE(existing.st_mode) != 0o600
        or existing.st_nlink != 1
    ):
        fail("unsafe existing frontend runtime receipt")

    payload = {
        "schema_version": 1,
        "revision": revision,
        "pm2_pid": pid,
        "pm2_uptime_ms": uptime,
        "next_build_id": build_id,
        }
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary = f".{receipt_name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    write_flags |= os.O_CLOEXEC | os.O_NOFOLLOW
    temporary_fd = os.open(temporary, write_flags, 0o600, dir_fd=state_fd)
    try:
        os.fchmod(temporary_fd, 0o600)
        os.fchown(temporary_fd, 0, 0)
        view = memoryview(encoded)
        while view:
            written = os.write(temporary_fd, view)
            if written <= 0:
                fail("short frontend receipt write")
            view = view[written:]
        os.fsync(temporary_fd)
    finally:
        os.close(temporary_fd)
    try:
        assert_release_lock()
        os.replace(
            temporary,
            receipt_name,
            src_dir_fd=state_fd,
            dst_dir_fd=state_fd,
        )
        os.fsync(state_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=state_fd)
        except FileNotFoundError:
            pass
    assert_release_lock()
    if read_regular(state_fd, receipt_name, mode=0o600, maximum=16 * 1024) != encoded:
        fail("frontend runtime receipt verification failed")
finally:
    os.close(state_fd)

print("FRONTEND_RUNTIME_RECEIPT_OK")
REMOTE_FRONTEND_RUNTIME_RECEIPT
    then
        print_error "无法写入可验证的前端运行态收据"
        return 1
    fi
}

# 去激活事务已经完成 backend/Celery 的最后一次重启和逐 PID flag=false
# 证明；通用 env/restart 模式此后只能重启前端，不能再让后端越过证明点。
restart_frontend_service() {
    print_step "重启前端服务..."
    assert_remote_release_lock_if_acquired

    mark_remote_release_mutation_started
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
    print_step "核验 GitHub 发布源..."

    /usr/bin/python3 "$SCRIPT_DIR/scripts/check_secret_leaks.py"

    # 部署只允许已提交的 tracked 内容。未跟踪文件不会进入 git push 或
    # 远端 checkout，因此仅提示并忽略；绝不能在发布脚本里 git add -A，
    # 否则会误收并发会话或用户尚未准备提交的文件。
    local tracked_changes
    tracked_changes="$(trusted_release_git status --short --untracked-files=no)"
    if [[ -n "$tracked_changes" ]]; then
        print_error "检测到未提交的已跟踪更改，请先明确提交后再部署"
        echo "$tracked_changes"
        exit 1
    fi

    local untracked_files
    untracked_files="$(trusted_release_git ls-files --others --exclude-standard)"
    if [[ -n "$untracked_files" ]]; then
        print_warning "忽略未跟踪文件（不会进入本次部署）"
        echo "$untracked_files"
    fi

    CURRENT_BRANCH="$(trusted_release_git branch --show-current)"
    if [[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "main" ]]; then
        print_error "生产部署只允许从 main 或 exact origin/main detached HEAD 执行，当前分支: $CURRENT_BRANCH"
        exit 1
    fi
    DEPLOY_EXPECTED_SHA="$(trusted_release_git rev-parse HEAD)"
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法解析待部署 commit"
        exit 1
    fi

    # Production deployment consumes an already-pushed immutable main commit.
    # Committing/pushing is a separate workflow; deploy must not mutate GitHub.
    trusted_release_git fetch --quiet --no-tags "$CANONICAL_RELEASE_ORIGIN_URL" \
        "+refs/heads/main:refs/remotes/origin/main"
    local local_origin_main_sha
    local_origin_main_sha=$(trusted_release_git rev-parse refs/remotes/origin/main)
    local remote_main_output
    remote_main_output="$(
        trusted_release_network_git ls-remote --exit-code \
            "$CANONICAL_RELEASE_ORIGIN_URL" refs/heads/main
    )"
    local remote_main_sha
    local remote_main_ref
    local remote_main_extra
    if [[ "$remote_main_output" == *$'\n'* ]]; then
        print_error "canonical main 返回歧义结果"
        exit 1
    fi
    read -r remote_main_sha remote_main_ref remote_main_extra <<< "$remote_main_output"
    if [[ "$local_origin_main_sha" != "$DEPLOY_EXPECTED_SHA" ||
          "$remote_main_sha" != "$DEPLOY_EXPECTED_SHA" ||
          "$remote_main_ref" != "refs/heads/main" ||
          -n "$remote_main_extra" ]]; then
        print_error "origin/main 与本地 HEAD 不一致，拒绝部署 (local=${local_origin_main_sha:0:12} remote=${remote_main_sha:0:12})"
        exit 1
    fi
    print_success "发布源已核验为 exact origin/main: ${DEPLOY_EXPECTED_SHA:0:12}"
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

    mark_remote_release_mutation_started
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! ssh $SERVER "
        set -euo pipefail
        cd $REMOTE_PATH && \
        test \"\$(git rev-parse HEAD)\" = '$DEPLOY_EXPECTED_SHA' && \
        test -z \"\$(git status --porcelain --untracked-files=all)\" && \
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
        cd frontend && \
        frontend_dependency_proof_rc=0 && \
        python3 ../scripts/release_step_proof.py \
            check --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-dependencies \
            --workspace '$REMOTE_PATH/frontend' --root '$REMOTE_RELEASE_PROOF_ROOT' || \
            frontend_dependency_proof_rc=\$? && \
        case \"\$frontend_dependency_proof_rc\" in \
            0) echo '复用已验证的前端依赖' ;; \
            3) \
                if [ '$RELEASE_STEP_PROOF_MODE' != off ]; then \
                    python3 ../scripts/release_step_proof.py \
                        invalidate --profile frontend-dependencies \
                        --root '$REMOTE_RELEASE_PROOF_ROOT'; \
                fi && \
                echo '安装依赖...' && \
                npm ci && \
                test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
                test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
                python3 ../scripts/release_step_proof.py \
                    record --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-dependencies \
                    --workspace '$REMOTE_PATH/frontend' --root '$REMOTE_RELEASE_PROOF_ROOT' \
                ;; \
            *) exit \"\$frontend_dependency_proof_rc\" ;; \
        esac && \
        frontend_build_proof_rc=0 && \
        python3 ../scripts/release_step_proof.py \
            check --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-build \
            --workspace '$REMOTE_PATH/frontend' --root '$REMOTE_RELEASE_PROOF_ROOT' || \
            frontend_build_proof_rc=\$? && \
        frontend_build_receipt_pending=0 && \
        case \"\$frontend_build_proof_rc\" in \
            0) echo '复用已验证的前端构建产物' ;; \
            3) \
                if [ '$RELEASE_STEP_PROOF_MODE' != off ]; then \
                    python3 ../scripts/release_step_proof.py \
                        invalidate --profile frontend-build \
                        --root '$REMOTE_RELEASE_PROOF_ROOT'; \
                fi && \
                echo '正在构建前端...' && \
                npm run build && \
                frontend_build_receipt_pending=1 \
                ;; \
            *) exit \"\$frontend_build_proof_rc\" ;; \
        esac && \
        cd '$REMOTE_PATH' && \
        test \"\$(git rev-parse HEAD)\" = '$DEPLOY_EXPECTED_SHA' && \
        test -z \"\$(git status --porcelain --untracked-files=all)\" && \
        cd frontend && \
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend && \
        pm2 describe health-frontend >/dev/null && \
        frontend_http_ready=0 && \
        for attempt in \$(seq 1 20); do \
            if curl -fsS --max-time 10 http://127.0.0.1:3000/ >/dev/null; then \
                frontend_http_ready=1; \
                break; \
            fi; \
            sleep 1; \
        done && \
        test \"\$frontend_http_ready\" = 1 && \
        test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
        test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
        if [ \"\$frontend_build_receipt_pending\" = 1 ]; then \
            python3 ../scripts/release_step_proof.py \
                record --mode '$RELEASE_STEP_PROOF_MODE' --profile frontend-build \
                --workspace '$REMOTE_PATH/frontend' --root '$REMOTE_RELEASE_PROOF_ROOT'; \
        fi
    "; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "前端构建/重启结果不明确；发布锁与现场保留"
        return 1
    fi

    if ! write_frontend_runtime_receipt; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "前端运行态收据写入失败；发布锁与现场保留"
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
    mark_remote_release_mutation_started
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
        ( \
            set -euo pipefail; \
            python_dependency_proof_rc=0; \
            python ../scripts/release_step_proof.py \
                check --mode '$RELEASE_STEP_PROOF_MODE' --profile python-dependencies \
                --workspace '$REMOTE_PATH/backend' --root '$REMOTE_RELEASE_PROOF_ROOT' || \
                python_dependency_proof_rc=\$?; \
            case \"\$python_dependency_proof_rc\" in \
                0) \
                    python scripts/verify_locked_requirements.py requirements.lock && \
                    test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
                    test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
                    echo '复用已验证的 Python 依赖' \
                    ;; \
                3) \
                    if [ '$RELEASE_STEP_PROOF_MODE' != off ]; then \
                        python ../scripts/release_step_proof.py \
                            invalidate --profile python-dependencies \
                            --root '$REMOTE_RELEASE_PROOF_ROOT'; \
                    fi && \
                    echo '重建干净 Python 虚拟环境并安装依赖...' && \
                    python -m venv --clear venv && \
                    source venv/bin/activate && \
                    pip install --require-hashes -r requirements.lock -q && \
                    test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
                    test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
                    python scripts/verify_locked_requirements.py requirements.lock && \
                    python -m pip check && \
                    test -r '$REMOTE_RELEASE_LOCK_DIR/token' && \
                    test \"\$(cat '$REMOTE_RELEASE_LOCK_DIR/token')\" = '$REMOTE_RELEASE_LOCK_TOKEN' && \
                    python ../scripts/release_step_proof.py \
                        record --mode '$RELEASE_STEP_PROOF_MODE' --profile python-dependencies \
                        --workspace '$REMOTE_PATH/backend' --root '$REMOTE_RELEASE_PROOF_ROOT' \
                    ;; \
                *) exit \"\$python_dependency_proof_rc\" ;; \
            esac \
        ) && \
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
        SYSTEM_KB_IMPORT_PROOF_MODE="\${SYSTEM_KB_IMPORT_PROOF_MODE:-shadow}" \
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
        -eq 15
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
    mark_remote_release_mutation_started

    # Delegate before the first remote process that can delete/reseed demo
    # rows. A transport failure cannot distinguish "not started" from
    # "committed but response lost", so the mutating lease must be retained.
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    if ! reset_output=$(ssh "$SERVER" bash -s -- \
        "$REMOTE_PATH" \
        "$DEPLOY_EXPECTED_SHA" \
        "$REMOTE_RELEASE_LOCK_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" <<'REMOTE_APP_STORE_REVIEW_RESET'
set -euo pipefail
repo_path="$1"
expected_sha="$2"
release_lock_dir="$3"
release_lock_token="$4"

test -r "$release_lock_dir/token"
test "$(cat "$release_lock_dir/token")" = "$release_lock_token"
test "$(git -C "$repo_path" rev-parse HEAD)" = "$expected_sha"
cd "$repo_path/backend"
test -x venv/bin/python
test -r .env
set -a
set +u
source .env
set -u
set +a
: "${APP_STORE_REVIEW_DEMO_ACCOUNT:?missing review account in backend env}"
: "${APP_STORE_REVIEW_DEMO_PASSWORD:?missing review password in backend env}"

summary_path="$(mktemp /tmp/reva-app-store-review-reset.XXXXXX)"
chmod 600 "$summary_path"
trap 'rm -f -- "$summary_path"' EXIT
PYTHONPATH=. venv/bin/python scripts/seed_demo_account.py --secret-free >"$summary_path"
venv/bin/python - "$summary_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    summary = json.load(handle)
expected_keys = {
    "verification",
    "daily_plan_actions",
    "timeline_events",
    "demo_conversation_messages",
}
if set(summary) != expected_keys:
    raise SystemExit("unexpected secret-free summary schema")
if summary["verification"] != "PASS":
    raise SystemExit("demo verification did not pass")
if not isinstance(summary["daily_plan_actions"], int) or summary["daily_plan_actions"] < 1:
    raise SystemExit("daily plan is empty")
if not isinstance(summary["timeline_events"], int) or summary["timeline_events"] < 1:
    raise SystemExit("timeline is empty")
if summary["demo_conversation_messages"] != 2:
    raise SystemExit("fixed conversation is not pristine")
print("APP_STORE_REVIEW_RESET_OK")
PY
REMOTE_APP_STORE_REVIEW_RESET
    ); then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "App Store 审核演示数据重置失败"
        return 1
    fi
    if [[ "$reset_output" != "APP_STORE_REVIEW_RESET_OK" ]]; then
        _REMOTE_RELEASE_LOCK_ABANDONED=1
        print_error "App Store 审核演示数据重置缺少精确成功证明"
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
    local common_dir last_ota anchor_status
    common_dir=$(git -C "$SCRIPT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || {
        print_error "无法解析共享 OTA anchor 路径"
        return 1
    }
    if last_ota=$(python3 - "$common_dir" <<'PY'
import os
import re
import stat
import sys
from pathlib import Path

common = Path(sys.argv[1])
if not common.is_absolute():
    raise SystemExit("OTA anchor git common-dir must be absolute")

directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
directory_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def open_directory(name, *, parent_fd=None, private=False):
    try:
        descriptor = os.open(name, directory_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        raise SystemExit(3) from None
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        os.close(descriptor)
        raise OSError("directory is not owned by the current user")
    if private and stat.S_IMODE(metadata.st_mode) != 0o700:
        os.close(descriptor)
        raise OSError("directory mode is not 0700")
    return descriptor


common_fd = state_fd = mobile_fd = anchor_fd = None
try:
    common_fd = open_directory(common)
    state_fd = open_directory("reva-release-state", parent_fd=common_fd, private=True)
    mobile_fd = open_directory("mobile-ota", parent_fd=state_fd, private=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        anchor_fd = os.open("anchor.production", flags, dir_fd=mobile_fd)
    except FileNotFoundError:
        raise SystemExit(3) from None
    metadata = os.fstat(anchor_fd)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise OSError("anchor must be a current-owner 0600 single-link regular file")
    raw = os.read(anchor_fd, 256)
    if len(raw) == 256 or os.read(anchor_fd, 1):
        raise OSError("anchor is too large")
    try:
        value = raw.decode("ascii").strip()
    except UnicodeError as error:
        raise OSError("anchor is not ASCII") from error
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise OSError("anchor is not a full commit SHA")
    print(value)
except OSError as error:
    print(f"unsafe OTA anchor: {error}", file=sys.stderr)
    raise SystemExit(1)
finally:
    for descriptor in (anchor_fd, mobile_fd, state_fd, common_fd):
        if descriptor is not None:
            os.close(descriptor)
PY
    ); then
        :
    else
        anchor_status=$?
        if [[ "$anchor_status" -eq 3 ]]; then
            return 0
        fi
        print_error "共享 OTA anchor 安全校验失败"
        return "$anchor_status"
    fi
    if ! trusted_release_git cat-file -e "$last_ota" 2>/dev/null; then
        print_warning "OTA anchor commit ${last_ota:0:8} 在本地不存在 (可能被 rebase),跳过 drift 检查"
        return 0
    fi
    local mobile_commits
    mobile_commits=$(trusted_release_git log --oneline "${last_ota}..HEAD" -- mobile/ 2>/dev/null || true)
    if [[ -z "$mobile_commits" ]]; then
        return 0
    fi
    echo ""
    print_warning "检测到 mobile/ 自上次正式移动版 (${last_ota:0:8}) 后有未发布改动:"
    echo "$mobile_commits" | sed 's/^/    /'
    echo ""
    if [[ "${AUTO_YES:-0}" -eq 1 ]]; then
        print_warning "已通过 -y 继续服务器部署；移动端改动仍需人工原生构建与审核 Gate（production OTA 已冻结）"
        echo ""
        return 0
    fi
    if [[ ! -t 0 ]]; then
        # 非交互 (CI / 重定向),自动放行但提示
        print_warning "非交互环境自动继续服务器部署；移动端改动仍需人工原生构建与审核 Gate"
        echo ""
        return 0
    fi
    read -r -p "继续服务器部署并保持移动端改动未发布? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS])
            echo ""
            return 0
            ;;
        *)
            print_error "已取消；正式移动端请走人工原生构建与审核 Gate，preview 可单独 OTA"
            exit 1
            ;;
    esac
}

verify_remote_mac_route_release_stage() {
    ssh "$SERVER" bash -s -- \
        "$REMOTE_BACKUP_PREFLIGHT_DIR" \
        "$REMOTE_RELEASE_LOCK_TOKEN" \
        "$REMOTE_RELEASE_SOURCE_SHA" \
        "$REMOTE_RELEASE_SOURCE_TREE" <<'REMOTE_VERIFY_MAC_ROUTE_STAGE'
set -euo pipefail
stage_dir="$1"
expected_token="$2"
expected_sha="$3"
expected_tree="$4"

test -d "$stage_dir"
test ! -L "$stage_dir"
test "$(stat -c '%U:%G:%a' "$stage_dir")" = "root:root:700"
shopt -s nullglob dotglob
entries=("$stage_dir"/*)
test "${#entries[@]}" -eq 5
for entry in "${entries[@]}"; do
    name="${entry##*/}"
    case "$name" in
        mac-release-nginx-bootstrap.sh|mac_release_nginx_bootstrap.py|\
        mac-release-routes.conf|mac-routes.source|mac-routes.sha256) ;;
        *) echo "unknown immutable Mac route artifact: $name" >&2; exit 1 ;;
    esac
    test -f "$entry"
    test ! -L "$entry"
    test "$(stat -c '%U:%G:%h' "$entry")" = "root:root:1"
done
shopt -u nullglob dotglob
test "$(stat -c '%a' "$stage_dir/mac-release-nginx-bootstrap.sh")" = 700
test "$(stat -c '%a' "$stage_dir/mac_release_nginx_bootstrap.py")" = 600
test "$(stat -c '%a' "$stage_dir/mac-release-routes.conf")" = 600
test "$(stat -c '%a' "$stage_dir/mac-routes.source")" = 400
test "$(stat -c '%a' "$stage_dir/mac-routes.sha256")" = 400
awk -F= -v token="$expected_token" -v source="$expected_sha" \
    -v tree="$expected_tree" '
    $0 == "schema=1" { schema += 1; next }
    $0 == "token=" token { tokens += 1; next }
    $0 == "source_sha=" source { sources += 1; next }
    $0 == "source_tree=" tree { trees += 1; next }
    { exit 1 }
    END {
        if (NR != 4 || schema != 1 || tokens != 1 || sources != 1 || trees != 1) {
            exit 1
        }
    }
' "$stage_dir/mac-routes.source"
awk '
    NF != 2 || length($1) != 64 || $1 ~ /[^0-9a-f]/ { exit 1 }
    $2 == "mac-release-nginx-bootstrap.sh" { wrapper += 1; next }
    $2 == "mac_release_nginx_bootstrap.py" { helper += 1; next }
    $2 == "mac-release-routes.conf" { snippet += 1; next }
    $2 == "mac-routes.source" { source += 1; next }
    { exit 1 }
    END {
        if (NR != 4 || wrapper != 1 || helper != 1 || snippet != 1 || source != 1) {
            exit 1
        }
    }
' "$stage_dir/mac-routes.sha256"
(
    cd "$stage_dir"
    sha256sum --strict -c mac-routes.sha256 >/dev/null
)
REMOTE_VERIFY_MAC_ROUTE_STAGE
}

stage_mac_route_release_artifacts() {
    local snapshot_dir
    local relative_path
    local staged_name

    assert_remote_release_lock
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ &&
          "$REMOTE_RELEASE_SOURCE_TREE" =~ ^[0-9a-f]{40}$ &&
          "$REMOTE_RELEASE_SOURCE_SHA" = "$DEPLOY_EXPECTED_SHA" &&
          "$(git -C "$SCRIPT_DIR" rev-parse "${DEPLOY_EXPECTED_SHA}^{tree}")" = \
              "$REMOTE_RELEASE_SOURCE_TREE" ]]; then
        print_error "Mac 下载路由 stage 与发布锁 source/tree 不一致"
        return 1
    fi

    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" != "1" ]]; then
        snapshot_dir="$(mktemp -d)" || return 1
        chmod 0700 "$snapshot_dir"
        if ! git -C "$SCRIPT_DIR" archive "$DEPLOY_EXPECTED_SHA" \
            scripts/mac-release-nginx-bootstrap.sh \
            scripts/mac_release_nginx_bootstrap.py \
            infra/nginx/mac-release-routes.conf | tar -x -C "$snapshot_dir"; then
            rm -rf -- "$snapshot_dir"
            return 1
        fi
        if ! ssh "$SERVER" "
            umask 077 &&
            mkdir '$REMOTE_BACKUP_PREFLIGHT_DIR' &&
            test \"\$(stat -c '%U:%G:%a' '$REMOTE_BACKUP_PREFLIGHT_DIR')\" = root:root:700
        "; then
            rm -rf -- "$snapshot_dir"
            return 1
        fi
        for relative_path in \
            scripts/mac-release-nginx-bootstrap.sh \
            scripts/mac_release_nginx_bootstrap.py \
            infra/nginx/mac-release-routes.conf; do
            staged_name="${relative_path##*/}"
            if ! scp "$snapshot_dir/$relative_path" \
                "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/$staged_name"; then
                rm -rf -- "$snapshot_dir"
                return 1
            fi
        done
        rm -rf -- "$snapshot_dir"
        if ! ssh "$SERVER" bash -s -- \
            "$REMOTE_BACKUP_PREFLIGHT_DIR" \
            "$REMOTE_RELEASE_LOCK_TOKEN" \
            "$REMOTE_RELEASE_SOURCE_SHA" \
            "$REMOTE_RELEASE_SOURCE_TREE" <<'REMOTE_SEAL_MAC_ROUTE_STAGE'
set -euo pipefail
stage_dir="$1"
token="$2"
source_sha="$3"
source_tree="$4"
chmod 0700 "$stage_dir/mac-release-nginx-bootstrap.sh"
chmod 0600 "$stage_dir/mac_release_nginx_bootstrap.py" \
    "$stage_dir/mac-release-routes.conf"
printf 'schema=1\ntoken=%s\nsource_sha=%s\nsource_tree=%s\n' \
    "$token" "$source_sha" "$source_tree" > "$stage_dir/mac-routes.source"
chmod 0400 "$stage_dir/mac-routes.source"
(
    cd "$stage_dir"
    sha256sum \
        mac-release-nginx-bootstrap.sh \
        mac_release_nginx_bootstrap.py \
        mac-release-routes.conf \
        mac-routes.source > mac-routes.sha256
    chmod 0400 mac-routes.sha256
    sync -f mac-routes.sha256
    sync -f .
)
REMOTE_SEAL_MAC_ROUTE_STAGE
        then
            return 1
        fi
    fi

    if ! verify_remote_mac_route_release_stage; then
        print_error "Mac 下载路由 immutable stage 不完整或已被修改"
        return 1
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" != "1" ]]; then
        if ! seal_remote_release_stage; then
            _REMOTE_RELEASE_LOCK_ABANDONED=1
            print_error "Mac 下载路由 stage 封存结果不明确；现场与租约保留"
            return 1
        fi
    fi
}

# This one-time infrastructure transaction intentionally stays out of normal
# backend/frontend deploys.  Its wrapper pins the production host and SSH key;
# deploy.sh is only the explicit operator entry point.
bootstrap_mac_release_routes() {
    local snapshot_dir
    local relative_path
    local staged_name
    local expected_blob
    local actual_blob
    local action_output
    local expected_terminal_pattern

    assert_remote_release_lock
    # The pre-lock source proof can become stale while waiting for the server
    # lease. Re-run it under that lease before extracting or executing any
    # production mutation bytes.
    verify_mac_route_release_source
    assert_remote_release_lock
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "Mac 下载路由缺少已核验的 immutable source SHA"
        return 1
    fi
    stage_mac_route_release_artifacts
    snapshot_dir="$(mktemp -d)" || return 1
    chmod 0700 "$snapshot_dir"
    mkdir -p "$snapshot_dir/scripts" "$snapshot_dir/infra/nginx"
    for relative_path in \
        scripts/mac-release-nginx-bootstrap.sh \
        scripts/mac_release_nginx_bootstrap.py \
        infra/nginx/mac-release-routes.conf; do
        staged_name="${relative_path##*/}"
        if ! scp "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/$staged_name" \
            "$snapshot_dir/$relative_path"; then
            rm -rf -- "$snapshot_dir"
            print_error "无法读取 sealed Mac nginx bootstrap artifact"
            return 1
        fi
    done
    for relative_path in \
        scripts/mac-release-nginx-bootstrap.sh \
        scripts/mac_release_nginx_bootstrap.py \
        infra/nginx/mac-release-routes.conf; do
        expected_blob="$(git -C "$SCRIPT_DIR" rev-parse "$DEPLOY_EXPECTED_SHA:$relative_path")" || {
            rm -rf -- "$snapshot_dir"
            return 1
        }
        actual_blob="$(git -C "$SCRIPT_DIR" hash-object "$snapshot_dir/$relative_path")" || {
            rm -rf -- "$snapshot_dir"
            return 1
        }
        if [[ "$actual_blob" != "$expected_blob" ]]; then
            rm -rf -- "$snapshot_dir"
            print_error "immutable Mac nginx bootstrap blob 校验失败: $relative_path"
            return 1
        fi
    done
    chmod 0700 "$snapshot_dir/scripts/mac-release-nginx-bootstrap.sh"
    if ! verify_remote_mac_route_release_stage; then
        rm -rf -- "$snapshot_dir"
        print_error "Mac nginx bootstrap 执行前 stage 复核失败"
        return 1
    fi
    mark_remote_release_mutation_started
    _REMOTE_RELEASE_LOCK_DELEGATED=1
    _REMOTE_RELEASE_LOCK_ABANDONED=1
    if [[ "$MAC_ROUTE_ACTION" == "apply" ]]; then
        expected_terminal_pattern='^MAC_NGINX_BOOTSTRAP_OK outcome=(applied|recovered-applied|already-applied|tracked-baseline-already-installed)$'
    else
        expected_terminal_pattern='^MAC_NGINX_BOOTSTRAP_OK outcome=(rolled-back|recovered-rolled-back|already-rolled-back)$'
    fi
    if action_output="$(REVA_MAC_BOOTSTRAP_ENTRYPOINT=deploy.sh \
        MAC_NGINX_REMOTE_LOCK_DIR="$REMOTE_RELEASE_LOCK_DIR" \
        MAC_NGINX_REMOTE_LOCK_TOKEN="$REMOTE_RELEASE_LOCK_TOKEN" \
            "$snapshot_dir/scripts/mac-release-nginx-bootstrap.sh" "${MAC_ROUTE_ACTION}")" &&
       [[ "$action_output" =~ $expected_terminal_pattern ]] &&
       [[ "$(printf '%s\n' "$action_output" | wc -l | tr -d ' ')" == "1" ]]; then
        :
    else
        rm -rf -- "$snapshot_dir"
        print_error "Mac nginx route outcome is ambiguous; remote lease and transaction state retained"
        return 75
    fi
    rm -rf -- "$snapshot_dir"
    assert_remote_release_lock
    verify_mac_route_release_source
    assert_remote_release_lock
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    _REMOTE_RELEASE_LOCK_ABANDONED=0
    printf '%s\n' "$action_output"
}

verify_mac_route_release_source() {
    local dirty
    local branch
    local local_origin_main_sha
    local remote_main_output
    local remote_main_sha
    local current_sha
    local current_tree

    dirty="$(git -C "$SCRIPT_DIR" status --porcelain=v1 --untracked-files=all)" || return 1
    if [[ -n "$dirty" ]]; then
        print_error "Mac 下载路由 bootstrap 要求完全干净的工作树"
        echo "$dirty"
        return 1
    fi
    branch="$(git -C "$SCRIPT_DIR" branch --show-current)" || return 1
    if [[ -n "$branch" && "$branch" != "main" ]]; then
        print_error "Mac 下载路由 bootstrap 只允许 main 或 exact origin/main detached HEAD"
        return 1
    fi
    current_sha="$(git -C "$SCRIPT_DIR" rev-parse HEAD)" || return 1
    current_tree="$(git -C "$SCRIPT_DIR" rev-parse "${current_sha}^{tree}")" || return 1
    if ! [[ "$current_sha" =~ ^[0-9a-f]{40}$ &&
          "$current_tree" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "无法解析 Mac 下载路由 bootstrap source SHA"
        return 1
    fi
    git -C "$SCRIPT_DIR" fetch --quiet --prune origin main || return 1
    local_origin_main_sha="$(git -C "$SCRIPT_DIR" rev-parse refs/remotes/origin/main)" || return 1
    remote_main_output="$(git -C "$SCRIPT_DIR" ls-remote --exit-code origin refs/heads/main)" || return 1
    remote_main_sha="${remote_main_output%%[[:space:]]*}"
    if [[ "$local_origin_main_sha" != "$current_sha" ||
          "$remote_main_sha" != "$current_sha" ]]; then
        print_error "Mac 下载路由 bootstrap source 不是 exact remote main"
        return 1
    fi
    if [[ "${_REMOTE_RELEASE_LOCK_ADOPTED:-0}" = "1" ]]; then
        if ! [[ "$REMOTE_RELEASE_SOURCE_SHA" =~ ^[0-9a-f]{40}$ &&
              "$REMOTE_RELEASE_SOURCE_TREE" =~ ^[0-9a-f]{40}$ ]] ||
            ! git -C "$SCRIPT_DIR" cat-file -e \
                "${REMOTE_RELEASE_SOURCE_SHA}^{commit}" ||
            [[ "$(git -C "$SCRIPT_DIR" rev-parse \
                "${REMOTE_RELEASE_SOURCE_SHA}^{tree}")" != \
                "$REMOTE_RELEASE_SOURCE_TREE" ]] ||
            ! git -C "$SCRIPT_DIR" merge-base --is-ancestor \
                "$REMOTE_RELEASE_SOURCE_SHA" "$current_sha"; then
            print_error "Mac 下载路由 retained source A 不是 current main B 的可验证祖先"
            return 1
        fi
        DEPLOY_EXPECTED_SHA="$REMOTE_RELEASE_SOURCE_SHA"
    else
        DEPLOY_EXPECTED_SHA="$current_sha"
    fi
    print_success "Mac 下载路由 immutable source 已核验: ${DEPLOY_EXPECTED_SHA:0:12}"
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
    MAC_ROUTE_ACTION="apply"
    MAC_RELEASE_VERSION=""
    MAC_RELEASE_BUILD=""

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
            --bootstrap-mac-routes)
                DEPLOY_MODE="mac-routes"
                if [[ "${2:-}" == "rollback" ]]; then
                    MAC_ROUTE_ACTION="rollback"
                    shift 2
                else
                    shift
                fi
                ;;
            --publish-mac)
                DEPLOY_MODE="mac-publish"
                shift
                ;;
            --recover-mac-release)
                DEPLOY_MODE="mac-recover"
                shift
                ;;
            --rollback-mac-release)
                DEPLOY_MODE="mac-rollback"
                shift
                ;;
            --inspect-release-lock)
                DEPLOY_MODE="release-lock-inspect"
                shift
                ;;
            --release-coordinator-begin)
                DEPLOY_MODE="release-coordinator-begin"
                shift
                ;;
            --release-coordinator-bind)
                DEPLOY_MODE="release-coordinator-bind"
                shift
                ;;
            --release-coordinator-assert)
                DEPLOY_MODE="release-coordinator-assert"
                shift
                ;;
            --release-coordinator-mutate)
                DEPLOY_MODE="release-coordinator-mutate"
                shift
                ;;
            --release-coordinator-finish)
                DEPLOY_MODE="release-coordinator-finish"
                shift
                ;;
            --release-coordinator-abort)
                DEPLOY_MODE="release-coordinator-abort"
                shift
                ;;
            --release-coordinator-recover)
                DEPLOY_MODE="release-coordinator-recover"
                shift
                ;;
            --version)
                if [[ $# -lt 2 || -z "${2:-}" ]]; then
                    print_error "--version 缺少 VERSION"
                    exit 2
                fi
                MAC_RELEASE_VERSION="$2"
                shift 2
                ;;
            --build)
                if [[ $# -lt 2 || -z "${2:-}" ]]; then
                    print_error "--build 缺少 BUILD"
                    exit 2
                fi
                MAC_RELEASE_BUILD="$2"
                shift 2
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

    # Mac binary publication owns both the shared Git-common local lease and
    # the server-wide release lease inside its formal driver. Delegate before
    # this script acquires either lease so there is exactly one authority and
    # no nested-lock deadlock. The driver rejects direct mutating invocation.
    case "$DEPLOY_MODE" in
        "mac-publish")
            if [[ -z "$MAC_RELEASE_VERSION" || -z "$MAC_RELEASE_BUILD" ]]; then
                print_error "--publish-mac 必须同时提供 --version 和 --build"
                exit 2
            fi
            print_error "Mac 自动发布已冻结：统一发布事务的崩溃恢复尚未完成；请走人工 Gate。"
            exit 78
            ;;
        "mac-recover")
            if [[ -n "$MAC_RELEASE_VERSION" || -n "$MAC_RELEASE_BUILD" ]]; then
                print_error "--recover-mac-release 不接受 --version/--build"
                exit 2
            fi
            print_error "Mac 自动恢复已冻结：请由发布负责人执行人工恢复 Gate。"
            exit 78
            ;;
        "mac-rollback")
            if [[ -n "$MAC_RELEASE_VERSION" || -n "$MAC_RELEASE_BUILD" ]]; then
                print_error "--rollback-mac-release 不接受 --version/--build"
                exit 2
            fi
            print_error "Mac 自动回滚已冻结：请由发布负责人执行人工回滚 Gate。"
            exit 78
            ;;
        *)
            if [[ -n "$MAC_RELEASE_VERSION" || -n "$MAC_RELEASE_BUILD" ]]; then
                print_error "--version/--build 只能与 --publish-mac 一起使用"
                exit 2
            fi
            ;;
    esac

    if [[ "$DEPLOY_MODE" == "mac-routes" ]]; then
        print_error "Mac 下载路由变更已冻结：请走人工基础设施 Gate。"
        exit 78
    fi

    if [[ "$DEPLOY_MODE" == "release-lock-inspect" ]]; then
        show_remote_release_lock_handoff
        return
    fi
    case "$DEPLOY_MODE" in
        release-coordinator-begin)
            begin_remote_release_coordinator
            return
            ;;
        release-coordinator-bind)
            bind_remote_release_coordinator
            return
            ;;
        release-coordinator-assert)
            assert_remote_release_coordinator
            return
            ;;
        release-coordinator-mutate)
            mutate_remote_release_coordinator
            return
            ;;
        release-coordinator-finish)
            finish_remote_release_coordinator
            return
            ;;
        release-coordinator-abort)
            abort_remote_release_coordinator
            return
            ;;
        release-coordinator-recover)
            recover_remote_release_coordinator
            return
            ;;
    esac

    # Every enabled production mutation must bind to the literal canonical
    # repository before creating either the local or server-wide release lease.
    # This also makes deploy a consumer of an already-pushed exact main commit;
    # it never doubles as an ambient Git push workflow.
    case "$DEPLOY_MODE" in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart"|"push")
            verify_release_coordinator_source || exit $?
            ;;
    esac

    case $DEPLOY_MODE in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart"|"push"|"mac-routes")
            acquire_release_lock "deploy:${DEPLOY_MODE}"
            ;;
    esac
    if [[ "$DEPLOY_MODE" == "mac-routes" ]]; then
        verify_mac_route_release_source
    fi
    if [[ "$DEPLOY_MODE" == "mac-routes" && "$SERVER" != "root@39.98.206.178" ]]; then
        print_error "Mac 下载路由 bootstrap 只允许固定生产服务器"
        exit 1
    fi
    case $DEPLOY_MODE in
        "all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart"|"mac-routes")
            unset REVA_RELEASE_COORDINATOR_SURFACE
            unset REVA_RELEASE_COORDINATOR_OPERATION
            unset REVA_RELEASE_COORDINATOR_CHANNEL
            unset REVA_RELEASE_COORDINATOR_TRANSACTION
            unset REVA_RELEASE_COORDINATOR_REQUEST_DIGEST
            unset REVA_RELEASE_COORDINATOR_STAGE
            REVA_RELEASE_COORDINATOR_SURFACE="server"
            REVA_RELEASE_COORDINATOR_OPERATION="$DEPLOY_MODE"
            REVA_RELEASE_COORDINATOR_CHANNEL="production"
            REVA_RELEASE_COORDINATOR_BASELINE_DIGEST="-"
            acquire_remote_release_lock "deploy:${DEPLOY_MODE}"
            if [[ "${_REMOTE_RELEASE_LOCK_ALREADY_RELEASED:-0}" = "1" ]]; then
                print_success "已恢复并确认原发布事务完成；未重复执行生产变更"
                return 0
            fi
            install_release_cleanup_traps
            capture_expected_server_surfaces_under_lock
            bind_expected_server_surfaces_under_lock
            assert_remote_release_lock
            verify_expected_server_surfaces_under_lock
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
        "mac-routes")
            bootstrap_mac_release_routes
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

# END UNREACHABLE LEGACY DEPLOY IMPLEMENTATION

# Historical direct entrypoint remains inside the fixed false block, but is
# deliberately outside the test fixture's function-definition extraction.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
fi
