#!/bin/bash
# 生产环境一键部署脚本
# 适用于 Ubuntu/Debian/CentOS 服务器
# 生成时间: 2026-01-22

set -e

echo "=========================================="
echo "生产环境部署脚本"
echo "PostgreSQL + Redis + Celery"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检测操作系统
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VER=$VERSION_ID
else
    echo -e "${RED}无法检测操作系统${NC}"
    exit 1
fi

echo "检测到操作系统: $OS $VER"
echo ""

# 确认继续
read -p "确认在生产环境部署? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "部署已取消"
    exit 0
fi

# 切换到项目目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo ""
echo -e "${BLUE}=========================================="
echo "Step 1: 备份当前数据"
echo -e "==========================================${NC}"
echo ""

if [ -f "health.db" ]; then
    BACKUP_FILE="health.db.backup.$(date +%Y%m%d_%H%M%S)"
    cp health.db "$BACKUP_FILE"
    echo -e "${GREEN}✓ 数据库已备份: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}⚠ health.db 不存在${NC}"
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 2: 安装 PostgreSQL 和 Redis"
echo -e "==========================================${NC}"
echo ""

case $OS in
    ubuntu|debian)
        echo "使用 apt 安装..."
        sudo apt update
        sudo apt install -y postgresql postgresql-contrib redis-server python3-psycopg2
        ;;
    centos|rhel|fedora)
        echo "使用 yum 安装..."
        sudo yum install -y postgresql-server postgresql-contrib redis python3-psycopg2
        sudo postgresql-setup initdb
        ;;
    *)
        echo -e "${RED}不支持的操作系统: $OS${NC}"
        exit 1
        ;;
esac

echo -e "${GREEN}✓ PostgreSQL 和 Redis 安装完成${NC}"

echo ""
echo -e "${BLUE}=========================================="
echo "Step 3: 启动服务"
echo -e "==========================================${NC}"
echo ""

# 启动 PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql
echo -e "${GREEN}✓ PostgreSQL 已启动${NC}"

# 启动 Redis
sudo systemctl start redis
sudo systemctl enable redis
echo -e "${GREEN}✓ Redis 已启动${NC}"

sleep 3

echo ""
echo -e "${BLUE}=========================================="
echo "Step 4: 配置 PostgreSQL"
echo -e "==========================================${NC}"
echo ""

# 生成随机密码
DB_PASSWORD=$(openssl rand -base64 16)
echo "已生成随机数据库密码，并写入 backend/.env"
echo ""

# 创建数据库和用户
sudo -u postgres psql << EOF
CREATE USER health_user WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE health_db OWNER health_user;
GRANT ALL PRIVILEGES ON DATABASE health_db TO health_user;
\q
EOF

echo -e "${GREEN}✓ 数据库和用户创建完成${NC}"

# 配置 pg_hba.conf
PG_HBA=$(sudo -u postgres psql -t -P format=unaligned -c 'show hba_file')
echo "配置 PostgreSQL 认证..."
sudo sed -i.bak 's/local   all             all                                     peer/local   all             all                                     md5/' "$PG_HBA"
sudo sed -i 's/host    all             all             127.0.0.1\/32            ident/host    all             all             127.0.0.1\/32            md5/' "$PG_HBA"

# 重启 PostgreSQL
sudo systemctl restart postgresql
echo -e "${GREEN}✓ PostgreSQL 配置完成${NC}"

echo ""
echo -e "${BLUE}=========================================="
echo "Step 5: 配置 .env 文件"
echo -e "==========================================${NC}"
echo ""

# 备份 .env
if [ -f ".env" ]; then
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    echo "已备份现有 .env 文件"
fi

# 添加配置
if ! grep -q "POSTGRES_HOST" .env 2>/dev/null; then
    cat >> .env << EOF

# PostgreSQL 配置 (生产环境)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=health_db
POSTGRES_USER=health_user
POSTGRES_PASSWORD=$DB_PASSWORD

# Redis 配置
REDIS_URL=redis://localhost:6379/0
EOF
    echo -e "${GREEN}✓ .env 配置已更新${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL 配置已存在，请手动更新密码${NC}"
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 6: 安装 Python 依赖"
echo -e "==========================================${NC}"
echo ""

# 激活虚拟环境（如果存在）
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "已激活虚拟环境"
fi

# 安装依赖
pip install psycopg2-binary redis celery
echo -e "${GREEN}✓ Python 依赖安装完成${NC}"

echo ""
echo -e "${BLUE}=========================================="
echo "Step 7: 数据迁移"
echo -e "==========================================${NC}"
echo ""

if [ -f "health.db" ]; then
    echo "开始数据迁移..."
    echo "yes" | python scripts/migrate_sqlite_to_postgres.py

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 数据迁移成功${NC}"
    else
        echo -e "${RED}✗ 数据迁移失败${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ health.db 不存在，跳过迁移${NC}"
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 8: 配置 Celery 服务"
echo -e "==========================================${NC}"
echo ""

# 获取当前用户和组
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)
PROJECT_DIR=$(pwd)
VENV_PATH="$PROJECT_DIR/venv/bin"

# 创建日志和 PID 目录
sudo mkdir -p /var/log/celery
sudo mkdir -p /var/run/celery
sudo chown -R $CURRENT_USER:$CURRENT_GROUP /var/log/celery
sudo chown -R $CURRENT_USER:$CURRENT_GROUP /var/run/celery

# 创建 Celery Worker 服务
sudo tee /etc/systemd/system/celery-worker.service > /dev/null << EOF
[Unit]
Description=Celery Worker for Health App
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_PATH:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PATH/celery -A app.celery_app worker --loglevel=info --logfile=/var/log/celery/worker.log --pidfile=/var/run/celery/worker.pid --detach
ExecStop=/bin/kill -s TERM \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 创建 Celery Beat 服务
sudo tee /etc/systemd/system/celery-beat.service > /dev/null << EOF
[Unit]
Description=Celery Beat for Health App
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_PATH:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PATH/celery -A app.celery_app beat --loglevel=info --logfile=/var/log/celery/beat.log --pidfile=/var/run/celery/beat.pid --detach
ExecStop=/bin/kill -s TERM \$MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}✓ Celery 服务配置完成${NC}"

echo ""
echo -e "${BLUE}=========================================="
echo "Step 9: 启动 Celery"
echo -e "==========================================${NC}"
echo ""

# 重载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start celery-worker
sudo systemctl start celery-beat

# 设置开机自启
sudo systemctl enable celery-worker
sudo systemctl enable celery-beat

sleep 3

# 检查状态
if sudo systemctl is-active --quiet celery-worker; then
    echo -e "${GREEN}✓ Celery Worker 运行中${NC}"
else
    echo -e "${RED}✗ Celery Worker 启动失败${NC}"
fi

if sudo systemctl is-active --quiet celery-beat; then
    echo -e "${GREEN}✓ Celery Beat 运行中${NC}"
else
    echo -e "${RED}✗ Celery Beat 启动失败${NC}"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "部署完成！"
echo -e "==========================================${NC}"
echo ""
echo "数据库凭据已写入 backend/.env；请通过受控密钥管理保存，不要复制到日志或聊天。"
echo ""
echo "服务状态检查:"
echo "  sudo systemctl status postgresql"
echo "  sudo systemctl status redis"
echo "  sudo systemctl status celery-worker"
echo "  sudo systemctl status celery-beat"
echo ""
echo "查看日志:"
echo "  sudo tail -f /var/log/celery/worker.log"
echo "  sudo tail -f /var/log/celery/beat.log"
echo ""
echo "Celery 管理:"
echo "  celery -A app.celery_app inspect active"
echo "  celery -A app.celery_app inspect scheduled"
echo ""
echo "重启应用以使用 PostgreSQL:"
echo "  sudo systemctl restart your-app-service"
echo ""
