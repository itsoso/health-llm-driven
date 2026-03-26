#!/bin/bash
# ============================================
# 健康管理系统 - 生产环境一键部署脚本
# 适用于：Ubuntu 22.04 / Debian 11+
# 阿里云服务器: 39.98.206.178
# ============================================

set -e  # 遇到错误立即退出

echo "=========================================="
echo "🚀 健康管理系统 - 生产环境部署"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 工作目录
WORK_DIR="/opt/health-llm-driven"
BACKEND_DIR="$WORK_DIR/backend"

# 步骤 1: 检查系统环境
echo -e "${YELLOW}[1/8] 检查系统环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3，请先安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 已安装: $(python3 --version)${NC}"

# 步骤 2: 安装系统依赖
echo -e "${YELLOW}[2/8] 安装系统依赖...${NC}"
apt-get update -qq
apt-get install -y -qq \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    git \
    curl \
    > /dev/null 2>&1
echo -e "${GREEN}✓ 系统依赖安装完成${NC}"

# 步骤 3: 创建工作目录
echo -e "${YELLOW}[3/8] 准备项目目录...${NC}"
if [ -d "$WORK_DIR" ]; then
    echo "项目目录已存在，备份旧版本..."
    mv "$WORK_DIR" "${WORK_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
echo -e "${GREEN}✓ 工作目录创建完成: $WORK_DIR${NC}"

# 步骤 4: 复制项目文件（假设已经上传到服务器）
echo -e "${YELLOW}[4/8] 检查项目文件...${NC}"
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}错误: 未找到 backend 目录，请先上传项目文件到 $WORK_DIR${NC}"
    echo "执行: scp -r ./health-llm-driven root@39.98.206.178:/opt/"
    exit 1
fi
echo -e "${GREEN}✓ 项目文件已就绪${NC}"

# 步骤 5: 配置数据库
echo -e "${YELLOW}[5/8] 配置 PostgreSQL 数据库...${NC}"
systemctl start postgresql
systemctl enable postgresql

# 创建数据库用户和数据库
su - postgres -c "psql -c \"CREATE USER health_user WITH PASSWORD 'HealthDB@2024$RANDOM';\"" || echo "用户已存在"
su - postgres -c "psql -c \"CREATE DATABASE health_db OWNER health_user;\"" || echo "数据库已存在"
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE health_db TO health_user;\""
echo -e "${GREEN}✓ 数据库配置完成${NC}"

# 步骤 6: 配置 Python 环境
echo -e "${YELLOW}[6/8] 配置 Python 虚拟环境...${NC}"
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate

# 安装依赖
echo "安装 Python 依赖..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install gunicorn -q
echo -e "${GREEN}✓ Python 环境配置完成${NC}"

# 步骤 7: 初始化数据库
echo -e "${YELLOW}[7/8] 初始化数据库表和索引...${NC}"
# 复制生产环境配置
if [ ! -f .env ]; then
    cp .env.production .env
    echo "请编辑 /opt/health-llm-driven/backend/.env 配置文件"
    echo "必须修改：POSTGRES_PASSWORD, OPENAI_API_KEY, CORS_ALLOW_ORIGINS"
fi

# 创建数据库表
python3 << 'PYTHON_EOF'
from app.database import engine, Base
try:
    Base.metadata.create_all(bind=engine)
    print("✓ 数据库表创建成功")
except Exception as e:
    print(f"✗ 数据库表创建失败: {e}")
    exit(1)
PYTHON_EOF

# 应用索引
if [ -f migrations/add_performance_indexes.sql ]; then
    PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2) \
    psql -h localhost -U health_user -d health_db -f migrations/add_performance_indexes.sql
    echo -e "${GREEN}✓ 数据库索引创建完成${NC}"
fi

# 步骤 8: 配置并启动服务
echo -e "${YELLOW}[8/8] 配置 Systemd 服务...${NC}"

# 创建 systemd 服务文件
cat > /etc/systemd/system/health-api.service << SERVICE_EOF
[Unit]
Description=Health Management System API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=root
Group=root
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
ExecStart=$BACKEND_DIR/venv/bin/gunicorn main:app \\
  --config $BACKEND_DIR/gunicorn.conf.py \\
  --workers 4 \\
  --worker-class uvicorn.workers.UvicornWorker \\
  --bind 0.0.0.0:8000 \\
  --access-logfile $BACKEND_DIR/logs/access.log \\
  --error-logfile $BACKEND_DIR/logs/error.log \\
  --log-level info

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# 创建日志目录
mkdir -p "$BACKEND_DIR/logs"

# 启动服务
systemctl daemon-reload
systemctl enable health-api
systemctl restart health-api

# 等待服务启动
sleep 3

# 检查服务状态
if systemctl is-active --quiet health-api; then
    echo -e "${GREEN}✓ API 服务启动成功${NC}"
else
    echo -e "${RED}✗ API 服务启动失败，查看日志：${NC}"
    journalctl -u health-api -n 50 --no-pager
    exit 1
fi

# 步骤 9: 配置 Nginx
echo -e "${YELLOW}配置 Nginx 反向代理...${NC}"
cat > /etc/nginx/sites-available/health-api << 'NGINX_EOF'
server {
    listen 80;
    server_name 39.98.206.178;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/health-api /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
echo -e "${GREEN}✓ Nginx 配置完成${NC}"

# 步骤 10: 验证部署
echo ""
echo "=========================================="
echo -e "${GREEN}🎉 部署完成！${NC}"
echo "=========================================="
echo ""
echo "服务状态："
systemctl status health-api --no-pager -l | head -10
echo ""
echo "健康检查："
sleep 2
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool || echo "API 尚未就绪"
echo ""
echo "=========================================="
echo "访问地址："
echo "  - API 文档: http://39.98.206.178/api/docs"
echo "  - 健康检查: http://39.98.206.178/api/v1/health"
echo "  - 主页: http://39.98.206.178/"
echo ""
echo "⚠️  下一步操作："
echo "  1. 编辑配置文件: nano $BACKEND_DIR/.env"
echo "  2. 修改数据库密码、OpenAI API Key、CORS 配置"
echo "  3. 重启服务: systemctl restart health-api"
echo "  4. 配置域名和 SSL 证书（可选）"
echo "=========================================="
