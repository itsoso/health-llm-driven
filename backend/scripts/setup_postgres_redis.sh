#!/bin/bash
# PostgreSQL 和 Redis 自动安装配置脚本
# 生成时间: 2026-01-22

set -e  # 遇到错误立即退出

echo "=================================="
echo "PostgreSQL & Redis 自动安装脚本"
echo "=================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 添加 PostgreSQL 到 PATH
export PATH="/usr/local/opt/postgresql@15/bin:$PATH"
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

echo -e "${YELLOW}Step 1: 检查 Homebrew...${NC}"
if ! command -v brew &> /dev/null; then
    echo -e "${RED}错误: Homebrew 未安装${NC}"
    echo "请先安装 Homebrew: https://brew.sh"
    exit 1
fi
echo -e "${GREEN}✓ Homebrew 已安装${NC}"
echo ""

echo -e "${YELLOW}Step 2: 检查 PostgreSQL 安装...${NC}"
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL 未安装，正在安装..."
    brew install postgresql@15
else
    echo -e "${GREEN}✓ PostgreSQL 已安装${NC}"
fi
echo ""

echo -e "${YELLOW}Step 3: 初始化 PostgreSQL 数据目录...${NC}"
if [ ! -d "/usr/local/var/postgresql@15" ]; then
    echo "正在初始化数据目录..."
    initdb --locale=en_US.UTF-8 -E UTF-8 /usr/local/var/postgresql@15
    echo -e "${GREEN}✓ 数据目录初始化完成${NC}"
else
    echo -e "${GREEN}✓ 数据目录已存在${NC}"
fi
echo ""

echo -e "${YELLOW}Step 4: 启动 PostgreSQL 服务...${NC}"
brew services start postgresql@15
echo "等待服务启动..."
sleep 5

if pg_isready > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL 服务运行中${NC}"
else
    echo -e "${RED}✗ PostgreSQL 服务启动失败${NC}"
    echo "请检查日志: tail -50 /usr/local/var/log/postgresql@15.log"
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 5: 创建数据库和用户...${NC}"

# 凭据必须由调用方提供，脚本不内置生产/开发通用密码。
DB_PASSWORD="${POSTGRES_PASSWORD:-${DB_PASSWORD:-}}"
if [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}✗ 未设置 POSTGRES_PASSWORD/DB_PASSWORD，拒绝创建数据库用户${NC}"
    exit 1
fi

# 创建用户
if psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='health_user'" | grep -q 1; then
    echo "用户 health_user 已存在"
else
    psql postgres -v db_password="$DB_PASSWORD" -c "CREATE USER health_user WITH PASSWORD :'db_password';"
    echo -e "${GREEN}✓ 用户创建成功${NC}"
fi

# 创建数据库
if psql postgres -lqt | cut -d \| -f 1 | grep -qw health_db; then
    echo "数据库 health_db 已存在"
else
    psql postgres -c "CREATE DATABASE health_db OWNER health_user;"
    echo -e "${GREEN}✓ 数据库创建成功${NC}"
fi

# 授权
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE health_db TO health_user;" > /dev/null 2>&1
echo -e "${GREEN}✓ 权限配置完成${NC}"
echo ""

echo -e "${YELLOW}Step 6: 验证 PostgreSQL 连接...${NC}"
if PGPASSWORD="$DB_PASSWORD" psql -U health_user -d health_db -c "SELECT version();" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PostgreSQL 连接测试成功${NC}"
else
    echo -e "${RED}✗ PostgreSQL 连接测试失败${NC}"
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 7: 检查 Redis 安装...${NC}"
if ! command -v redis-server &> /dev/null; then
    echo "Redis 未安装，正在安装..."
    brew install redis
else
    echo -e "${GREEN}✓ Redis 已安装${NC}"
fi
echo ""

echo -e "${YELLOW}Step 8: 启动 Redis 服务...${NC}"
brew services start redis
echo "等待服务启动..."
sleep 3

if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Redis 服务运行中${NC}"
else
    echo -e "${RED}✗ Redis 服务启动失败${NC}"
    echo "请检查日志: tail -50 /usr/local/var/log/redis.log"
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 9: 配置 .env 文件...${NC}"
ENV_FILE="../.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "创建 .env 文件..."
    touch "$ENV_FILE"
fi

# 检查并添加 PostgreSQL 配置
if ! grep -q "POSTGRES_HOST" "$ENV_FILE"; then
    echo "" >> "$ENV_FILE"
    echo "# PostgreSQL 配置" >> "$ENV_FILE"
    echo "POSTGRES_HOST=localhost" >> "$ENV_FILE"
    echo "POSTGRES_PORT=5432" >> "$ENV_FILE"
    echo "POSTGRES_DB=health_db" >> "$ENV_FILE"
    echo "POSTGRES_USER=health_user" >> "$ENV_FILE"
    echo "POSTGRES_PASSWORD=$DB_PASSWORD" >> "$ENV_FILE"
    echo -e "${GREEN}✓ PostgreSQL 配置已添加到 .env${NC}"
else
    echo "PostgreSQL 配置已存在"
fi

# 检查并添加 Redis 配置
if ! grep -q "REDIS_URL" "$ENV_FILE"; then
    echo "" >> "$ENV_FILE"
    echo "# Redis 配置" >> "$ENV_FILE"
    echo "REDIS_URL=redis://localhost:6379/0" >> "$ENV_FILE"
    echo -e "${GREEN}✓ Redis 配置已添加到 .env${NC}"
else
    echo "Redis 配置已存在"
fi
echo ""

echo "=================================="
echo -e "${GREEN}安装完成！${NC}"
echo "=================================="
echo ""
echo "下一步操作："
echo "1. 备份 SQLite 数据库:"
echo "   cp health.db health.db.backup.\$(date +%Y%m%d_%H%M%S)"
echo ""
echo "2. 运行数据迁移:"
echo "   python scripts/migrate_sqlite_to_postgres.py"
echo ""
echo "3. 启动 Celery Worker:"
echo "   celery -A app.celery_app worker --loglevel=info"
echo ""
echo "4. 启动 Celery Beat:"
echo "   celery -A app.celery_app beat --loglevel=info"
echo ""
echo "服务状态检查:"
echo "  PostgreSQL: pg_isready"
echo "  Redis: redis-cli ping"
echo ""
