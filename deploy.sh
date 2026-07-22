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
ENV_FILE="$SCRIPT_DIR/.env"

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
DEPLOY_EXPECTED_SHA=""

# 验证必要配置
if [[ -z "$SERVER" || -z "$REMOTE_PATH" ]]; then
    echo -e "${RED}✗${NC} 错误: .env 中缺少必要配置"
    echo "请确保配置了 DEPLOY_SERVER 和 DEPLOY_PATH"
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
    ssh "$SERVER" "rm -f '$REMOTE_DEPLOY_BUNDLE'; rm -rf '$REMOTE_BACKUP_PREFLIGHT_DIR'" >/dev/null 2>&1 || true
}

# 上传当前 HEAD 的 git bundle 到服务器,作为 GitHub 超时时的回退源。
# 前端/后端部署都调用它,所以两边都能走 bundle 回退。
upload_deploy_bundle() {
    local bundle
    bundle=$(mktemp)
    if ! git bundle create "$bundle" HEAD >/dev/null; then
        rm -f "$bundle"
        return 1
    fi
    if ! scp "$bundle" "$SERVER:$REMOTE_DEPLOY_BUNDLE" >/dev/null; then
        rm -f "$bundle"
        return 1
    fi
    rm "$bundle"
    trap cleanup_remote_release_artifacts EXIT
}

# 备份发生在远端 checkout 更新之前。先上传当前已核验 commit 的备份工具，
# 避免旧 checkout 缺少恢复演练或站外归档闸门。
stage_backup_preflight_scripts() {
    local scripts=(
        "$SCRIPT_DIR/backend/scripts/backup_db.sh"
        "$SCRIPT_DIR/backend/scripts/verify_backup_restore.sh"
        "$SCRIPT_DIR/backend/scripts/archive_backup_offsite.sh"
    )

    ssh "$SERVER" "install -d -m 0700 '$REMOTE_BACKUP_PREFLIGHT_DIR'"
    scp "${scripts[@]}" "$SERVER:$REMOTE_BACKUP_PREFLIGHT_DIR/"
    ssh "$SERVER" "chmod 0700 '$REMOTE_BACKUP_PREFLIGHT_DIR/'*.sh"
    trap cleanup_remote_release_artifacts EXIT
}

remote_git_sync_command() {
    if ! [[ "$DEPLOY_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
        print_error "缺少合法的 DEPLOY_EXPECTED_SHA，拒绝生成远端同步命令"
        return 1
    fi
    cat <<EOF
        echo '暂存服务器本地改动...' &&
        git stash push -m auto-deploy-stash >/dev/null &&
        echo '同步到已核验的 main commit $DEPLOY_EXPECTED_SHA...' &&
        ( (git fetch origin main && git cat-file -e '$DEPLOY_EXPECTED_SHA^{commit}') ||
          (echo 'git fetch origin 失败或缺少目标 commit, 使用上传的 deploy bundle...' &&
           git fetch '$REMOTE_DEPLOY_BUNDLE' HEAD && git cat-file -e '$DEPLOY_EXPECTED_SHA^{commit}') ) &&
        git checkout -B main '$DEPLOY_EXPECTED_SHA' &&
        test "\$(git rev-parse HEAD)" = '$DEPLOY_EXPECTED_SHA'
EOF
}

verify_deployed_revision() {
    local deployed_sha
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
    echo "  -f, --frontend  仅部署前端"
    echo "  -b, --backend   仅部署后端"
    echo "  -e, --env       仅同步 .env 到服务器"
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
    echo "  ./deploy.sh -f        # 仅部署前端"
    echo "  ./deploy.sh -b        # 仅部署后端"
    echo "  ./deploy.sh -e        # 仅同步环境变量"
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
    print_step "备份数据库..."
    # 备份早于远端 git checkout 更新，因此必须执行本次发布 commit 随附的脚本；
    # 数据库与站外归档配置仍从线上 backend/.env 加载。
    if ! stage_backup_preflight_scripts; then
        print_error "无法上传本次发布的数据库备份工具，阻断部署"
        return 1
    fi
    if ! ssh "$SERVER" "set -a; source '$REMOTE_PATH/backend/.env'; set +a; BACKUP_OFFSITE_REQUIRED=1 bash \"$REMOTE_BACKUP_RUNNER\""; then
        print_error "数据库备份、恢复演练或站外归档失败，阻断部署"
        return 1
    fi
    print_success "数据库备份、恢复演练和站外归档完成"
}

# 记录当前 commit 用于回滚
save_rollback_point() {
    ROLLBACK_COMMIT=$(ssh $SERVER "cd $REMOTE_PATH && git rev-parse HEAD" 2>/dev/null)
    if [[ -n "$ROLLBACK_COMMIT" ]]; then
        print_step "回滚点: ${ROLLBACK_COMMIT:0:8}"
    fi
}

# 回滚到上一个版本
rollback_deploy() {
    if [[ -z "$ROLLBACK_COMMIT" ]]; then
        print_error "无回滚点，请手动恢复"
        return 1
    fi
    print_warning "健康度不达标，自动回滚到 ${ROLLBACK_COMMIT:0:8}..."
    if ! ssh "$SERVER" \
        "bash '$REMOTE_PATH/backend/scripts/rollback_release.sh' '$REMOTE_PATH' '$ROLLBACK_COMMIT'"; then
        print_error "自动回滚未通过 exact-SHA 或数据库兼容健康验证"
        return 1
    fi
    print_success "代码已回滚到 ${ROLLBACK_COMMIT:0:8}，当前数据库结构兼容性已验证"
}

# 部署后验证（项目的 val_bpb 检查）
verify_deployment() {
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

    if [[ "$PASSED" == "true" ]]; then
        print_success "健康度: ${TOTAL}/60 ✅ PASS"
        return 0
    else
        print_error "健康度: ${TOTAL}/60 ❌ FAIL (阈值: ${DEPLOY_SCORE_THRESHOLD})"
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
        exit 1
    fi
}

# 备份服务器当前 backend/.env，避免环境变量同步覆盖后无法回退
backup_remote_env() {
    print_step "备份服务器 backend/.env..."

    ssh "$SERVER" "REMOTE_BACKEND='$REMOTE_PATH/backend' bash -s" <<'REMOTE_ENV_BACKUP'
set -euo pipefail
cd "$REMOTE_BACKEND"

if [ -f .env ]; then
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
    echo "已备份到工作树外: $ENV_BACKUP_DIR/.env.${BACKUP_TS}"
else
    echo "服务器 backend/.env 不存在，跳过备份"
fi
REMOTE_ENV_BACKUP

    print_success "服务器环境变量备份检查完成"
}

# 同步环境变量到服务器
sync_env() {
    print_step "同步 .env 到服务器..."

    # ── env 守卫(2026-07-12 事故加固,机械拦截,勿删)──────────────────
    # 事故:从陈旧 checkout 跑 deploy,sync_env 把缺 12 个 key + APP_ENV=development
    # 的本地 .env 推上 prod → 短信密钥丢失 + dev_code 回显洞重开。
    # 守卫1:本地 .env 必须是 prod 形态(APP_ENV=production + DEBUG=False)。
    # 守卫2:prod 现有的 key 本地缺失 → 说明本地 .env 陈旧,推送会删 prod 配置,硬退。
    # 逃生口:DEPLOY_ENV_FORCE=1(明知故犯,比如刻意删 key)。
    if [ "${DEPLOY_ENV_FORCE:-0}" != "1" ]; then
        if ! grep -q "^APP_ENV=production" "$ENV_FILE" || ! grep -q "^DEBUG=False" "$ENV_FILE"; then
            print_error "env 守卫:本地 .env 不是 prod 形态(需 APP_ENV=production + DEBUG=False)。"
            print_error "你可能在用 dev/陈旧 .env。修正后重试,或 DEPLOY_ENV_FORCE=1 强制。"
            exit 1
        fi
        _GUARD_REMOTE=$(mktemp)
        if scp -q "$SERVER:$REMOTE_PATH/backend/.env" "$_GUARD_REMOTE" 2>/dev/null; then
            _MISSING_KEYS=$(comm -13 \
                <(grep -vE '^#|^$' "$ENV_FILE" | sed -E 's/=.*//' | sort -u) \
                <(grep -vE '^#|^$' "$_GUARD_REMOTE" | sed -E 's/=.*//' | sort -u) | head -20)
            if [ -n "$_MISSING_KEYS" ]; then
                print_error "env 守卫:prod 上存在但本地 .env 缺失的 key(推送会把它们从 prod 删掉):"
                echo "$_MISSING_KEYS"
                print_error "先把这些 key 收敛进本地根 .env(scp prod 值回来),或 DEPLOY_ENV_FORCE=1 强制。"
                rm -f "$_GUARD_REMOTE"
                exit 1
            fi
        fi
        rm -f "$_GUARD_REMOTE"
    fi

    validate_langbridge_env
    backup_remote_env

    # 创建临时文件，过滤掉部署配置
    TEMP_ENV=$(mktemp)
    grep -v "^DEPLOY_SERVER=" "$ENV_FILE" | grep -v "^DEPLOY_PATH=" | grep -v "^#.*服务器信息" | grep -v "^# -.*deploy.sh" > "$TEMP_ENV"

    # 上传到服务器
    scp "$TEMP_ENV" "$SERVER:$REMOTE_PATH/backend/.env"
    rm "$TEMP_ENV"
    ssh "$SERVER" "chmod 600 '$REMOTE_PATH/backend/.env'"

    print_success "环境变量已同步到 $SERVER:$REMOTE_PATH/backend/.env (0600)"
}

# 仅重启服务
restart_services() {
    print_step "重启服务..."

    ssh $SERVER "
        echo '重启后端服务...' && \
        systemctl restart health-backend && \
        echo '重启 Celery worker & beat...' && \
        systemctl restart celery-worker celery-beat && \
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend
    "

    print_success "服务已重启"
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

    # 预上传 bundle,使前端也具备和后端一致的 GitHub 超时回退路径
    upload_deploy_bundle
    local remote_git_sync
    remote_git_sync="$(remote_git_sync_command)"

    ssh $SERVER "
        cd $REMOTE_PATH && \
        $remote_git_sync && \
        cd frontend && \
        echo '安装依赖...' && \
        npm install && \
        echo '正在构建前端...' && \
        npm run build && \
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend
    "

    verify_deployed_revision
    print_success "前端部署完成"
}

# 部署后端
deploy_backend() {
    print_step "部署后端..."

    # 1. 备份数据库 + 记录回滚点
    backup_database
    save_rollback_point

    # 2. 同步环境变量
    sync_env

    # GitHub 在服务器侧偶发超时；预先上传当前 HEAD 的 bundle，
    # 远端 git fetch 失败时仍可通过 deploy.sh 完成同一提交的部署。
    upload_deploy_bundle
    local remote_git_sync
    remote_git_sync="$(remote_git_sync_command)"

    # 3. 部署代码 (skill 同步可能失败 → 我们自己处理回滚, 临时关闭 set -e)
    set +e
    ssh $SERVER "
        cd $REMOTE_PATH && \
        $remote_git_sync && \
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
        python scripts/apply_managed_migrations.py && \
        unset MIGRATION_DATABASE_URL && \
        echo '补齐审核食物营养基准...' && \
        python scripts/seed_food_nutrition.py && \
        echo '写入系统知识库 Phase 0 种子...' && \
        python scripts/seed_system_kb_phase0.py && \
        echo '导入系统知识库 V2 扩展 artifacts...' && \
        python scripts/import_system_kb_v2_artifacts.py && \
        echo '重启后端服务...' && \
        systemctl restart health-backend && \
        echo '重启 Celery worker & beat...' && \
        systemctl restart celery-worker celery-beat && \
        echo '统计本地 skills...' && \
        find skills -maxdepth 2 -name SKILL.md | wc -l | xargs printf '  本地 SKILL.md: %s 个\\n'
    "
    SKILL_EXIT=$?
    set -e
    if [ $SKILL_EXIT -ne 0 ]; then
        if rollback_deploy; then
            print_error "后端部署 SSH 命令失败 (exit=$SKILL_EXIT)，代码已自动回滚并通过健康检查"
        else
            print_error "后端部署 SSH 命令失败 (exit=$SKILL_EXIT)，且自动回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    # 4. 部署后验证（快速失败）
    if ! verify_deployment; then
        if rollback_deploy; then
            print_error "部署健康检查失败，代码已自动回滚并通过健康检查"
        else
            print_error "部署健康检查失败，且自动回滚失败，无法证明服务已停止，请立即人工隔离主机"
        fi
        exit 1
    fi

    # 4.5 后端健康通过后再验证第一方 Agent skills manifest，避免冷启动误报。
    wait_for_agent_skills_manifest
    verify_deployed_revision

    print_success "后端部署完成"
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
            deploy_frontend
            deploy_backend
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
            sync_env
            restart_services
            ;;
        "restart")
            restart_services
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

    echo ""
    print_success "完成！"
    echo ""
}

# 运行主函数
main "$@"
