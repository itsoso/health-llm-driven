#!/bin/bash

# ===========================================
# 健康应用部署脚本
# 服务器: 39.98.206.178
# 项目路径: /opt/health-app
# ===========================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 服务器配置
SERVER="root@39.98.206.178"
REMOTE_PATH="/opt/health-app"

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
    echo "  -p, --push      仅推送代码到 GitHub (不部署)"
    echo "  -s, --status    查看服务器服务状态"
    echo "  -l, --logs      查看服务器日志"
    echo "  -h, --help      显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  ./deploy.sh           # 部署全部"
    echo "  ./deploy.sh -f        # 仅部署前端"
    echo "  ./deploy.sh -b        # 仅部署后端"
    echo "  ./deploy.sh -s        # 查看服务状态"
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
}

# 部署前端
deploy_frontend() {
    print_step "部署前端..."
    
    ssh $SERVER "
        cd $REMOTE_PATH && \
        git pull && \
        cd frontend && \
        echo '正在构建前端...' && \
        npm run build && \
        echo '重启前端服务...' && \
        systemctl restart health-frontend
    "
    
    print_success "前端部署完成"
}

# 部署后端
deploy_backend() {
    print_step "部署后端..."
    
    ssh $SERVER "
        cd $REMOTE_PATH && \
        git pull && \
        cd backend && \
        echo '激活虚拟环境...' && \
        source venv/bin/activate && \
        echo '安装依赖...' && \
        pip install -r requirements.txt -q && \
        echo '重启后端服务...' && \
        systemctl restart health-backend
    "
    
    print_success "后端部署完成"
}

# 查看服务状态
check_status() {
    print_step "服务器服务状态..."
    echo ""
    
    ssh $SERVER "
        echo '=== 前端服务 ===' && \
        systemctl status health-frontend --no-pager | head -15 && \
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
