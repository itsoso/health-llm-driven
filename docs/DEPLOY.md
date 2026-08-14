# 阿里云 ECS 部署指南

> **CURRENT SAFETY OVERRIDE (2026-08-12): 本文仅保留历史架构与故障证据，所有下方会写
> production 的命令均不可执行。** 仓库内 bootstrap 可被同 UID 进程通过 Git refs/replace、
> shared `.git/info/attributes` + local clean/smudge filter、`.git/info/exclude` 隐藏的 untracked
> import shadow、`BASH_ENV`、`PYTHONPATH`/`sitecustomize` 绕过，因此 server backend/frontend/
> all/env/restart/push/evidence activation/App Review reset/coordinator 与用于发布的 raw SSH、
> 直接 `systemctl`/上传/构建旁路全部冻结并应在 mutation 前 exit 78。人工 release Gate 表示
> **STOP/BLOCK**，不是改用下方命令或 vendor/helper 的授权。
>
> `release.py`/`release.sh` plan/validate/publish、`release_production_state` 的联网模式和
> `deploy.sh` status/logs/inspect 也全部冻结；它们会进入 root SSH、带 token 的 vendor
> observation 或在 repo bootstrap 前暴露环境。冻结期只允许 offline evidence parser、
> 公开未认证 HTTPS、本地 Metro/iOS Simulator/test 及
> `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 的离线 IPA metadata/report（无安装
> manifest、安装二维码或可安装承诺）。bare `--no-upload` 与自动
> archive/export/signing/provisioning（尤其 `-allowProvisioningUpdates`）也冻结。EAS channel→branch
> 映射可能漂移或共用，因此所有 OTA/rollback 网络 writer 都冻结。未来恢复 production 必须另开 dossier，并由仓库外
> root-owned launcher 使用固定解释器、`env -i` allowlist、在仓库外 materialize 的 canonical
> Git archive/tree，完成 source/artifact/recovery proof 后再过新的独立 G4。当前 G5、G6 和
> App Store submission 均为 BLOCK；不得标记 `shipped`/`complete`。
> `mobile/package.json` 的 `npm run ios` 固定走 Simulator wrapper，不得向 npm/Expo 追加
> `--device`；wrapper 只从 available inventory 解析并锁定 exact Simulator UDID。物理 iOS
> repo CLI、连接/安装/验收冻结；仓库内 XCUITest 也只接受 exact available Simulator
> UDID。物理验收只能在未来解冻后由
> 仓库外获权人工证据流程完成。
>
> server-local DB migration/setup/admin utilities 属独立 manual admin Gate，不是自动发布器；
> 仅可在生产主机显式获权、留审计的事件中运行，且不得由自动 release 入口调用。下文历史
> 部署命令不能据此整体恢复。
>
> 仓库脚本的 rc78 只是 ordinary-invocation tombstone：`BASH_ENV` 与 caller-defined
> `exit`/`builtin` function 可在 guard 外改变 Bash 行为。`deploy.sh`/`_run-mobile-tf.sh`
> legacy 必须 literal-false、语法级不可达；runtime/operator 不得 source/extract/eval。
> 隔离测试可抽取 marker fixture 做无 writer/网络的协议回归，但不构成 release proof；`release-dmg.sh` 全入口
> 冻结，read-only checker 必须另立无 writer code 文件。真正 bootstrap boundary 仍在仓库外
> root-owned `env -i` launcher。
>
> Mac/nginx direct Python production CLI 也冻结；不调用 `release-dmg.sh` 的独立 test-only
> protocol fixture 与本地 `create-candidate` 仅在
> strict non-root + explicit test mode + 固定 non-production roots（macOS `/private/tmp` 或
> `/private/var/folders`；其他平台 `/tmp`，忽略 caller `TMPDIR`）下允许，且无发布权限。
> `deploy.sh --inspect-release-lock` 同样在读取 lock/env 前 exit 78；等待 repo-external
> root-owned inspector。
> Android 尚非 shipped/audited Mobile surface；`npm run android`/`expo run:android` 因自动
> native generation、debug signing 与 ADB install 也 earliest exit 78，无 native CLI 例外。
> `check_app_store_release_pack.py --final-submit` 会登录 production reviewer 并取得可写
> bearer token，同样冻结；仅非 final-submit 静态 pack 与纯静态 iOS config check 保留。

本文档原本介绍如何将健康管理系统部署到阿里云 ECS 服务器；以下操作段落现均为
**historical reference / DO NOT EXECUTE**。

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
