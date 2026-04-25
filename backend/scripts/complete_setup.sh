#!/bin/bash
# 完整安装和配置脚本
# 包含: PostgreSQL + Redis 安装 + 数据迁移 + Celery 启动
# 生成时间: 2026-01-22

set -e

echo "=========================================="
echo "Executor Life OS - 完整部署脚本"
echo "=========================================="
echo ""
echo "此脚本将执行以下操作:"
echo "1. 安装和配置 PostgreSQL"
echo "2. 安装和配置 Redis"
echo "3. 备份 SQLite 数据库"
echo "4. 迁移数据到 PostgreSQL"
echo "5. 启动 Celery Worker 和 Beat"
echo ""
read -p "确认继续? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "操作已取消"
    exit 0
fi

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 切换到 backend 目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo ""
echo -e "${BLUE}=========================================="
echo "Step 1: 安装 PostgreSQL 和 Redis"
echo -e "==========================================${NC}"
echo ""

if [ -f "scripts/setup_postgres_redis.sh" ]; then
    chmod +x scripts/setup_postgres_redis.sh
    bash scripts/setup_postgres_redis.sh
else
    echo -e "${RED}错误: scripts/setup_postgres_redis.sh 不存在${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 2: 备份 SQLite 数据库"
echo -e "==========================================${NC}"
echo ""

if [ -f "health.db" ]; then
    BACKUP_FILE="health.db.backup.$(date +%Y%m%d_%H%M%S)"
    cp health.db "$BACKUP_FILE"
    echo -e "${GREEN}✓ 数据库已备份: $BACKUP_FILE${NC}"
    ls -lh "$BACKUP_FILE"
else
    echo -e "${YELLOW}⚠ health.db 不存在，跳过备份${NC}"
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 3: 数据迁移"
echo -e "==========================================${NC}"
echo ""

if [ -f "health.db" ]; then
    echo "开始迁移数据..."
    python scripts/migrate_sqlite_to_postgres.py

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 数据迁移成功${NC}"
    else
        echo -e "${RED}✗ 数据迁移失败${NC}"
        echo "请检查日志并手动修复"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ health.db 不存在，跳过迁移${NC}"
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 4: 验证配置"
echo -e "==========================================${NC}"
echo ""

# 检查 .env 文件
if [ -f ".env" ]; then
    echo "检查 .env 配置..."

    if grep -q "POSTGRES_HOST" .env; then
        echo -e "${GREEN}✓ PostgreSQL 配置存在${NC}"
    else
        echo -e "${RED}✗ PostgreSQL 配置缺失${NC}"
        exit 1
    fi

    if grep -q "REDIS_URL" .env; then
        echo -e "${GREEN}✓ Redis 配置存在${NC}"
    else
        echo -e "${RED}✗ Redis 配置缺失${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ .env 文件不存在${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 5: 启动 Celery"
echo -e "==========================================${NC}"
echo ""

echo "是否立即启动 Celery? (yes/no)"
read -r start_celery

if [ "$start_celery" = "yes" ]; then
    chmod +x scripts/start_celery.sh
    bash scripts/start_celery.sh
else
    echo "跳过 Celery 启动"
    echo ""
    echo "稍后可以手动启动:"
    echo "  bash scripts/start_celery.sh"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "部署完成！"
echo -e "==========================================${NC}"
echo ""
echo "服务状态检查:"
echo "  PostgreSQL: pg_isready"
echo "  Redis: redis-cli ping"
echo "  Celery Worker: pgrep -f 'celery.*worker'"
echo "  Celery Beat: pgrep -f 'celery.*beat'"
echo ""
echo "查看日志:"
echo "  Celery Worker: tail -f logs/celery_worker.log"
echo "  Celery Beat: tail -f logs/celery_beat.log"
echo ""
echo "定时任务列表:"
echo "  celery -A app.celery_app inspect scheduled"
echo ""
echo "重启应用:"
echo "  pkill -f 'uvicorn'"
echo "  python main.py"
echo ""
