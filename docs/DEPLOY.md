# 阿里云 ECS 部署指南

本文档介绍如何将健康管理系统部署到阿里云 ECS 服务器。

## 目录

- [1. 服务器要求](#1-服务器要求)
- [2. 环境准备](#2-环境准备)
- [3. 部署后端](#3-部署后端)
- [4. 部署前端](#4-部署前端)
- [5. 配置 Nginx](#5-配置-nginx)
- [6. 配置系统服务](#6-配置系统服务)
- [7. 安全设置](#7-安全设置)
- [8. 维护命令](#8-维护命令)

---

## 1. 服务器要求

### 推荐配置
- **操作系统**: Ubuntu 22.04 LTS / CentOS 7+
- **CPU**: 2核+
- **内存**: 4GB+
- **硬盘**: 40GB+
- **带宽**: 5Mbps+

### 开放端口
在阿里云安全组中开放以下端口：
- **22**: SSH
- **80**: HTTP
- **443**: HTTPS
- **3000**: 前端开发（可选）
- **8000**: 后端API（可选）

---

## 2. 环境准备

### 2.1 连接服务器

```bash
ssh root@your-server-ip
```

### 2.2 更新系统

```bash
# Ubuntu/Debian
apt update && apt upgrade -y

# CentOS
yum update -y
```

### 2.3 安装基础工具

```bash
# Ubuntu/Debian
apt install -y git curl wget vim htop

# CentOS
yum install -y git curl wget vim htop
```

### 2.4 安装 Python 3.12

```bash
# Ubuntu/Debian
apt install -y software-properties-common
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install -y python3.12 python3.12-venv python3.12-dev python3-pip

# 设置默认 Python
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
```

### 2.5 安装 Node.js 20

```bash
# 使用 NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 验证版本
node -v
npm -v
```

### 2.6 安装 Nginx

```bash
# Ubuntu/Debian
apt install -y nginx

# CentOS
yum install -y nginx

# 启动 Nginx
systemctl start nginx
systemctl enable nginx
```

---

## 3. 部署后端

### 3.1 创建应用目录

```bash
mkdir -p /opt/health-app
cd /opt/health-app
```

### 3.2 克隆代码

```bash
git clone https://github.com/itsoso/health-llm-driven.git .
```

### 3.3 配置后端环境

```bash
cd backend

# 创建虚拟环境
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装 Garmin Connect（如果需要）
pip install garminconnect
```

### 3.4 配置环境变量

```bash
# 创建 .env 文件
cat > .env << 'EOF'
# 数据库
DATABASE_URL=postgresql://health_user:your-postgres-password@localhost:5432/health_db

# OpenAI API（用于AI分析）
OPENAI_API_KEY=your-openai-api-key

# JWT密钥（生产环境请更换）
SECRET_KEY=your-super-secret-key-change-in-production

# Garmin凭证加密密钥（可选）
GARMIN_ENCRYPTION_KEY=your-garmin-encryption-key
EOF

# 设置权限
chmod 600 .env
```

### 3.5 初始化数据库

有两种方式初始化数据库：

#### 方式一：使用 Python ORM（推荐用于开发）

```bash
source venv/bin/activate
python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine)"
```

#### 方式二：使用 PostgreSQL 迁移脚本（推荐用于生产）

```bash
cd /opt/health-app/backend
source venv/bin/activate
python scripts/apply_managed_migrations.py
```

### 3.6 创建管理员用户

```bash
source venv/bin/activate
python scripts/create_user.py --email admin@example.com --password yourpassword --admin
```

> **提示**：`--admin` 参数会创建管理员账户，可以访问后台管理功能。

### 3.7 测试后端

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# 另开终端测试
curl http://localhost:8000/health
# 应返回: {"status":"healthy"}
```

---

## 4. 部署前端

### 4.1 配置前端环境

```bash
cd /opt/health-app/frontend

# 安装依赖
npm install
```

### 4.2 配置环境变量

```bash
# 创建 .env.local
cat > .env.local << 'EOF'
# 后端API地址（Nginx会代理，使用localhost即可）
BACKEND_URL=http://localhost:8000
EOF
```

### 4.3 构建生产版本

```bash
npm run build
```

### 4.4 测试前端

```bash
npm run start -- -p 3000

# 访问 http://your-server-ip:3000 测试
```

---

## 5. 配置 Nginx

### 5.1 创建 Nginx 配置

```bash
cat > /etc/nginx/sites-available/health-app << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # 改为你的域名或IP

    # 前端
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # 后端API代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 上传文件大小限制
        client_max_body_size 50M;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
EOF
```

### 5.2 启用配置

```bash
# 创建符号链接
ln -s /etc/nginx/sites-available/health-app /etc/nginx/sites-enabled/

# 删除默认配置（可选）
rm -f /etc/nginx/sites-enabled/default

# 测试配置
nginx -t

# 重载 Nginx
systemctl reload nginx
```

---

## 6. 配置系统服务

### 6.1 创建后端服务

```bash
cat > /etc/systemd/system/health-backend.service << 'EOF'
[Unit]
Description=Health App Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/health-app/backend
Environment=PATH=/opt/health-app/backend/venv/bin
ExecStart=/opt/health-app/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 6.2 创建前端服务

```bash
cat > /etc/systemd/system/health-frontend.service << 'EOF'
[Unit]
Description=Health App Frontend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/health-app/frontend
ExecStart=/usr/bin/npm run start -- -p 3000
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF
```

### 6.3 启动服务

```bash
# 重载 systemd
systemctl daemon-reload

# 启动服务
systemctl start health-backend
systemctl start health-frontend

# 设置开机自启
systemctl enable health-backend
systemctl enable health-frontend

# 查看状态
systemctl status health-backend
systemctl status health-frontend
```

---

## 7. 安全设置

### 7.1 配置 HTTPS（推荐）

使用 Let's Encrypt 免费证书：

```bash
# 安装 Certbot
apt install -y certbot python3-certbot-nginx

# 获取证书（需要先将域名解析到服务器IP）
certbot --nginx -d your-domain.com

# 自动续期测试
certbot renew --dry-run
```

### 7.2 配置防火墙

```bash
# Ubuntu (ufw)
ufw allow 22
ufw allow 80
ufw allow 443
ufw enable

# CentOS (firewalld)
firewall-cmd --permanent --add-port=22/tcp
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --reload
```

### 7.3 创建非 root 用户（推荐）

```bash
# 创建用户
useradd -m -s /bin/bash health

# 设置密码
passwd health

# 修改文件权限
chown -R health:health /opt/health-app

# 更新服务文件中的 User=health
sed -i 's/User=root/User=health/g' /etc/systemd/system/health-*.service
systemctl daemon-reload
systemctl restart health-backend health-frontend
```

---

## 8. 维护命令

### 更新代码

```bash
cd /opt/health-app

# 拉取最新代码
git pull

# 更新后端
cd backend
source venv/bin/activate
pip install -r requirements.txt

# 更新前端
cd ../frontend
npm install
npm run build

# 重启服务
systemctl restart health-backend health-frontend
```

### 数据库迁移

当更新代码涉及数据库结构变更时，需要执行迁移脚本：

```bash
# 备份数据库
pg_dump "$DATABASE_URL" | gzip > /opt/health-app/backups/db_$(date +%Y%m%d_%H%M%S).gz

# 执行受控 PostgreSQL 迁移
cd /opt/health-app/backend
source venv/bin/activate
python scripts/apply_managed_migrations.py

# 重启后端
systemctl restart health-backend
```

> **注意**：SQLite 在列已存在时会报错，这是正常的，可以忽略继续执行。

### 快速部署脚本

项目根目录提供了一键部署脚本：

```bash
cd /opt/health-app
./deploy.sh              # 完整部署（前端+后端）
./deploy.sh --backend-only  # 仅部署后端
./deploy.sh --frontend-only # 仅部署前端
./deploy.sh --no-logs       # 部署后不显示日志
```

### 查看日志

```bash
# 后端日志
journalctl -u health-backend -f

# 前端日志
journalctl -u health-frontend -f

# Nginx 日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### 备份数据库

```bash
# 备份
cp /opt/health-app/backend/health.db /backup/health-$(date +%Y%m%d).db

# 设置定时备份（每天凌晨2点）
echo "0 2 * * * cp /opt/health-app/backend/health.db /backup/health-\$(date +\%Y\%m\%d).db" | crontab -
```

### 重启所有服务

```bash
systemctl restart health-backend health-frontend nginx
```

---

## 快速部署脚本

将以上步骤整合为一个脚本：

```bash
#!/bin/bash
# deploy.sh - 一键部署脚本

set -e

echo "=== 健康管理系统部署脚本 ==="

# 更新系统
apt update && apt upgrade -y

# 安装依赖
apt install -y git curl wget vim nginx

# 安装 Python 3.12
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install -y python3.12 python3.12-venv python3.12-dev

# 安装 Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 克隆代码
mkdir -p /opt/health-app
cd /opt/health-app
git clone https://github.com/itsoso/health-llm-driven.git .

# 部署后端
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 部署前端
cd ../frontend
npm install
npm run build

echo "=== 部署完成！请配置 .env 文件和 Nginx ==="
```

---

## 常见问题

### Q: 访问返回 502 Bad Gateway
检查后端服务是否正常运行：
```bash
systemctl status health-backend
journalctl -u health-backend -n 50
```

### Q: 前端页面空白
检查前端构建和服务：
```bash
systemctl status health-frontend
journalctl -u health-frontend -n 50
```

### Q: API 请求失败
检查 Nginx 代理配置和后端日志：
```bash
nginx -t
tail -f /var/log/nginx/error.log
```

---

**祝部署顺利！** 🚀
