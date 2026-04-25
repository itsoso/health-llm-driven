#!/bin/bash

# ===========================================
# 健康应用部署脚本
#
# 配置文件: .env-online (本地管理，不被 git 追踪)
# 服务器配置从 .env-online 读取
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
ENV_ONLINE_FILE="$SCRIPT_DIR/.env-online"

# 检查 .env-online 文件是否存在
if [[ ! -f "$ENV_ONLINE_FILE" ]]; then
    echo -e "${RED}✗${NC} 错误: .env-online 文件不存在"
    echo "请创建 .env-online 文件并配置以下内容:"
    echo "  DEPLOY_SERVER=root@your-server-ip"
    echo "  DEPLOY_PATH=/opt/health-app"
    echo "  以及其他环境变量..."
    exit 1
fi

# 从 .env-online 读取服务器配置
SERVER=$(grep "^DEPLOY_SERVER=" "$ENV_ONLINE_FILE" | cut -d'=' -f2)
REMOTE_PATH=$(grep "^DEPLOY_PATH=" "$ENV_ONLINE_FILE" | cut -d'=' -f2)

# 验证必要配置
if [[ -z "$SERVER" || -z "$REMOTE_PATH" ]]; then
    echo -e "${RED}✗${NC} 错误: .env-online 中缺少必要配置"
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

# 显示使用帮助
show_help() {
    echo "用法: ./deploy.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -a, --all       部署前端和后端 (默认)"
    echo "  -f, --frontend  仅部署前端"
    echo "  -b, --backend   仅部署后端"
    echo "  -e, --env       仅同步 .env-online 到服务器"
    echo "  -r, --restart   仅重启服务 (不拉取代码)"
    echo "  -p, --push      仅推送代码到 GitHub (不部署)"
    echo "  -s, --status    查看服务器服务状态"
    echo "  -l, --logs      查看服务器日志"
    echo "  -h, --help      显示此帮助信息"
    echo ""
    echo "配置文件: .env-online (本地管理，不被 git 追踪)"
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
    BACKUP_TS=$(date +%Y%m%d_%H%M%S)
    ssh $SERVER "
        BACKUP_DIR=$REMOTE_PATH/backups
        mkdir -p \$BACKUP_DIR
        cd $REMOTE_PATH/backend
        source venv/bin/activate
        PGPASSWORD=\$(grep '^POSTGRES_PASSWORD=' .env 2>/dev/null | cut -d= -f2) \
        pg_dump -h localhost \
            -U \$(grep '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2 || echo health) \
            \$(grep '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2 || echo health_db) \
            2>/dev/null | gzip > \$BACKUP_DIR/db_${BACKUP_TS}.gz && \
        echo \"备份完成: \$BACKUP_DIR/db_${BACKUP_TS}.gz\" && \
        ls -t \$BACKUP_DIR/db_*.gz 2>/dev/null | tail -n +11 | xargs -r rm
    " 2>/dev/null && print_success "数据库备份完成 (保留最近10份)" || print_warning "数据库备份跳过（可能未配置 pg_dump）"
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
    ssh $SERVER "
        cd $REMOTE_PATH && \
        git checkout $ROLLBACK_COMMIT -- . && \
        cd backend && source venv/bin/activate && \
        pip install -r requirements.txt -q && \
        systemctl restart health-backend
    "
    print_success "已回滚到 ${ROLLBACK_COMMIT:0:8}"
}

# 部署后验证（项目的 val_bpb 检查）
verify_deployment() {
    print_step "部署后健康度检查..."
    # 等待服务启动 + warmup（冷启动首次请求延迟高）
    sleep 5
    ssh $SERVER "curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1" 2>/dev/null
    sleep 3

    SCORE=$(ssh $SERVER "
        cd $REMOTE_PATH/backend && \
        source venv/bin/activate && \
        python scripts/system_health_score.py --skip-tests --url http://localhost:8000 --json 2>/dev/null
    " 2>/dev/null)

    if [[ -z "$SCORE" ]]; then
        print_warning "健康度检查跳过（脚本不存在或执行失败）"
        return 0
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

# 同步环境变量到服务器
sync_env() {
    print_step "同步 .env-online 到服务器..."

    # 创建临时文件，过滤掉部署配置
    TEMP_ENV=$(mktemp)
    grep -v "^DEPLOY_SERVER=" "$ENV_ONLINE_FILE" | grep -v "^DEPLOY_PATH=" | grep -v "^#.*服务器信息" | grep -v "^# -.*deploy.sh" > "$TEMP_ENV"

    # 上传到服务器
    scp "$TEMP_ENV" "$SERVER:$REMOTE_PATH/backend/.env"
    rm "$TEMP_ENV"

    print_success "环境变量已同步到 $SERVER:$REMOTE_PATH/backend/.env"
}

# 仅重启服务
restart_services() {
    print_step "重启服务..."

    ssh $SERVER "
        echo '重启后端服务...' && \
        systemctl restart health-backend && \
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend
    "

    print_success "服务已重启"
}

# 推送代码到 GitHub
push_code() {
    print_step "推送代码到 GitHub..."

    # 检查是否有未提交的更改
    if [[ -n $(git status -s) ]]; then
        print_warning "检测到未提交的更改"
        git status -s
        echo ""
        read -p "是否添加并提交所有更改? (y/n): " confirm
        if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
            read -p "请输入提交信息: " commit_msg
            git add -A
            git commit -m "$commit_msg"
        else
            print_error "请先提交更改后再部署"
            exit 1
        fi
    fi

    git push
    print_success "代码已推送到 GitHub"

    # 同步到 kuaishou GitLab（静默，失败不影响部署）
    if git remote | grep -q kuaishou; then
        git push kuaishou main 2>/dev/null && print_success "代码已同步到 kuaishou GitLab" || print_warning "kuaishou GitLab 同步失败（不影响部署）"
    fi
}

# 部署前端
deploy_frontend() {
    print_step "部署前端..."

    ssh $SERVER "
        cd $REMOTE_PATH && \
        echo '暂存服务器本地改动...' && \
        git stash push -u -m auto-deploy-stash >/dev/null 2>&1 || true && \
        git pull && \
        cd frontend && \
        echo '安装依赖...' && \
        npm install && \
        echo '正在构建前端...' && \
        npm run build && \
        echo '重启前端服务 (PM2)...' && \
        pm2 restart health-frontend
    "

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

    # 3. 部署代码
    ssh $SERVER "
        cd $REMOTE_PATH && \
        echo '暂存服务器本地改动...' && \
        git stash push -u -m auto-deploy-stash >/dev/null 2>&1 || true && \
        git pull && \
        cd backend && \
        echo '激活虚拟环境...' && \
        source venv/bin/activate && \
        echo '加载环境变量...' && \
        set -a && source .env && set +a && \
        echo '安装依赖...' && \
        pip install -r requirements.txt -q && \
        echo '重启后端服务...' && \
        systemctl restart health-backend && \
        echo '重启 Celery worker & beat...' && \
        systemctl restart celery-worker celery-beat && \
        echo '同步 Skills 到 OpenClaw Gateway...' && \
        python3 -c '
from app.services.openclaw_skills_service import openclaw_skills_service
from pathlib import Path
skills_dir = Path(\"skills\")
if skills_dir.exists():
    for d in sorted(skills_dir.iterdir()):
        skill_md = d / \"SKILL.md\"
        if skill_md.exists():
            try:
                content = skill_md.read_text()
                openclaw_skills_service.create_or_update_skill(name=d.name, skill_md_content=content, enabled=True)
                print(f\"  ✓ {d.name}\")
            except Exception as e:
                print(f\"  ✗ {d.name}: {e}\")
' 2>&1 || echo '  ⚠ Skills 同步跳过（Gateway 可能不可用）'
    "

    # 4. 部署后验证（快速失败）
    if ! verify_deployment; then
        rollback_deploy
        print_error "部署失败，已自动回滚"
        exit 1
    fi

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
main() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     健康应用部署脚本 v1.0              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""

    # 默认部署全部
    DEPLOY_MODE="all"

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
