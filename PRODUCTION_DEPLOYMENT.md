# 生产环境部署指南 - PostgreSQL + Redis + Celery

> 生成时间: 2026-01-22
> 目标: 在线上服务器执行 P0 任务部署

---

## 🎯 部署目标

在生产服务器上完成：
1. PostgreSQL 数据库迁移
2. Redis 缓存部署
3. Celery 定时任务上线

---

## 📋 前置检查

### 1. 服务器信息

```bash
# 检查服务器信息
uname -a
cat /etc/os-release

# 检查 Python 版本
python3 --version

# 检查磁盘空间
df -h

# 检查内存
free -h
```

### 2. 备份当前数据

```bash
# 连接到服务器
ssh user@your-server

# 进入项目目录
cd /path/to/health-llm-driven/backend

# 备份 SQLite 数据库
cp health.db health.db.backup.$(date +%Y%m%d_%H%M%S)

# 验证备份
ls -lh health.db.backup.*
```

---

## 🚀 部署步骤

### Step 1: 上传脚本到服务器

```bash
# 在本地执行，上传脚本到服务器
cd /Users/liqiuhua/work/personal/health-llm-driven

# 上传所有脚本
scp backend/scripts/*.sh user@your-server:/path/to/health-llm-driven/backend/scripts/
scp backend/scripts/migrate_sqlite_to_postgres.py user@your-server:/path/to/health-llm-driven/backend/scripts/

# 或者使用 rsync
rsync -avz backend/scripts/ user@your-server:/path/to/health-llm-driven/backend/scripts/
```

### Step 2: 在服务器上安装 PostgreSQL 和 Redis

```bash
# SSH 连接到服务器
ssh user@your-server

# 进入项目目录
cd /path/to/health-llm-driven/backend

# 根据服务器系统选择安装方式

# === Ubuntu/Debian ===
sudo apt update
sudo apt install -y postgresql postgresql-contrib redis-server

# === CentOS/RHEL ===
sudo yum install -y postgresql-server postgresql-contrib redis

# === macOS (如果是 macOS 服务器) ===
brew install postgresql@15 redis
```

### Step 3: 配置 PostgreSQL

```bash
# 启动 PostgreSQL
# Ubuntu/Debian
sudo systemctl start postgresql
sudo systemctl enable postgresql

# CentOS/RHEL
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 创建数据库和用户
sudo -u postgres psql << EOF
CREATE USER health_user WITH PASSWORD 'your_secure_password_here';
CREATE DATABASE health_db OWNER health_user;
GRANT ALL PRIVILEGES ON DATABASE health_db TO health_user;
\q
EOF

# 配置 PostgreSQL 允许密码认证
sudo nano /etc/postgresql/*/main/pg_hba.conf
# 或
sudo nano /var/lib/pgsql/data/pg_hba.conf

# 修改以下行（将 peer 改为 md5）:
# local   all             all                                     md5
# host    all             all             127.0.0.1/32            md5

# 重启 PostgreSQL
sudo systemctl restart postgresql
```

### Step 4: 配置 Redis

```bash
# 启动 Redis
sudo systemctl start redis
sudo systemctl enable redis

# 验证 Redis
redis-cli ping
# 应该返回: PONG
```

### Step 5: 配置 .env 文件

```bash
cd /path/to/health-llm-driven/backend

# 备份现有 .env
cp .env .env.backup

# 添加 PostgreSQL 和 Redis 配置
cat >> .env << EOF

# PostgreSQL 配置
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=health_db
POSTGRES_USER=health_user
POSTGRES_PASSWORD=your_secure_password_here

# Redis 配置
REDIS_URL=redis://localhost:6379/0
EOF
```

### Step 6: 安装 Python 依赖

```bash
cd /path/to/health-llm-driven/backend

# 激活虚拟环境（如果有）
source venv/bin/activate

# 安装依赖
pip install psycopg2-binary redis celery
```

### Step 7: 执行数据迁移

```bash
cd /path/to/health-llm-driven/backend

# 运行迁移脚本
python scripts/migrate_sqlite_to_postgres.py

# 如果脚本需要修改，使用生产环境密码
# 编辑脚本中的 POSTGRES_URL
nano scripts/migrate_sqlite_to_postgres.py
# 修改: POSTGRES_URL = "postgresql://health_user:your_secure_password_here@localhost:5432/health_db"
```

### Step 8: 验证数据迁移

```bash
# 连接到 PostgreSQL
psql -U health_user -d health_db

# 查看表
\dt

# 检查数据量
SELECT 'users' as table_name, COUNT(*) FROM users
UNION ALL
SELECT 'garmin_data', COUNT(*) FROM garmin_data
UNION ALL
SELECT 'workout_records', COUNT(*) FROM workout_records;

# 退出
\q
```

### Step 9: 配置 Celery 为系统服务

创建 Celery Worker 服务：

```bash
sudo nano /etc/systemd/system/celery-worker.service
```

添加以下内容：

```ini
[Unit]
Description=Celery Worker for Health App
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=your_user
Group=your_group
WorkingDirectory=/path/to/health-llm-driven/backend
Environment="PATH=/path/to/health-llm-driven/backend/venv/bin"
ExecStart=/path/to/health-llm-driven/backend/venv/bin/celery -A app.celery_app worker --loglevel=info --logfile=/var/log/celery/worker.log --pidfile=/var/run/celery/worker.pid --detach
ExecStop=/bin/kill -s TERM $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

创建 Celery Beat 服务：

```bash
sudo nano /etc/systemd/system/celery-beat.service
```

添加以下内容：

```ini
[Unit]
Description=Celery Beat for Health App
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=your_user
Group=your_group
WorkingDirectory=/path/to/health-llm-driven/backend
Environment="PATH=/path/to/health-llm-driven/backend/venv/bin"
ExecStart=/path/to/health-llm-driven/backend/venv/bin/celery -A app.celery_app beat --loglevel=info --logfile=/var/log/celery/beat.log --pidfile=/var/run/celery/beat.pid --detach
ExecStop=/bin/kill -s TERM $MAINPID
Restart=always

[Install]
WantedBy=multi-user.target
```

创建日志和 PID 目录：

```bash
sudo mkdir -p /var/log/celery
sudo mkdir -p /var/run/celery
sudo chown -R your_user:your_group /var/log/celery
sudo chown -R your_user:your_group /var/run/celery
```

启动 Celery 服务：

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start celery-worker
sudo systemctl start celery-beat

# 设置开机自启
sudo systemctl enable celery-worker
sudo systemctl enable celery-beat

# 检查状态
sudo systemctl status celery-worker
sudo systemctl status celery-beat
```

### Step 10: 重启应用

```bash
# 如果使用 systemd 管理应用
sudo systemctl restart health-app

# 如果使用 supervisor
sudo supervisorctl restart health-app

# 如果手动运行
pkill -f "uvicorn"
cd /path/to/health-llm-driven/backend
nohup python main.py > logs/app.log 2>&1 &
```

---

## ✅ 验证部署

### 1. 检查服务状态

```bash
# PostgreSQL
sudo systemctl status postgresql

# Redis
sudo systemctl status redis

# Celery Worker
sudo systemctl status celery-worker

# Celery Beat
sudo systemctl status celery-beat
```

### 2. 检查日志

```bash
# Celery Worker 日志
sudo tail -f /var/log/celery/worker.log

# Celery Beat 日志
sudo tail -f /var/log/celery/beat.log

# PostgreSQL 日志
sudo tail -f /var/log/postgresql/postgresql-*.log

# Redis 日志
sudo tail -f /var/log/redis/redis-server.log
```

### 3. 测试定时任务

```bash
# 查看已注册的任务
celery -A app.celery_app inspect registered

# 查看定时任务
celery -A app.celery_app inspect scheduled

# 手动触发任务（测试）
python -c "from app.tasks.health_analysis import generate_daily_plan_for_all; generate_daily_plan_for_all.delay()"
```

---

## 🔒 安全加固

### 1. 修改默认密码

```bash
# 生成强密码
openssl rand -base64 32

# 修改 PostgreSQL 密码
sudo -u postgres psql << EOF
ALTER USER health_user WITH PASSWORD 'new_strong_password_here';
\q
EOF

# 更新 .env 文件
nano /path/to/health-llm-driven/backend/.env
```

### 2. 配置防火墙

```bash
# 确保 PostgreSQL 和 Redis 只监听本地
sudo ufw allow 22/tcp  # SSH
sudo ufw allow 80/tcp  # HTTP
sudo ufw allow 443/tcp # HTTPS
sudo ufw enable

# PostgreSQL 和 Redis 不对外开放
# 检查配置
sudo netstat -tlnp | grep -E "5432|6379"
```

### 3. 配置 PostgreSQL 安全

```bash
# 编辑 postgresql.conf
sudo nano /etc/postgresql/*/main/postgresql.conf

# 确保只监听本地
listen_addresses = 'localhost'

# 重启
sudo systemctl restart postgresql
```

---

## 📊 监控和维护

### 1. 设置日志轮转

```bash
# 创建 Celery 日志轮转配置
sudo nano /etc/logrotate.d/celery

# 添加以下内容
/var/log/celery/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 your_user your_group
    sharedscripts
    postrotate
        systemctl reload celery-worker celery-beat > /dev/null 2>&1 || true
    endscript
}
```

### 2. 设置监控告警

```bash
# 安装监控工具（可选）
pip install flower  # Celery 监控

# 启动 Flower
celery -A app.celery_app flower --port=5555 --basic_auth=admin:password
```

### 3. 定期备份

```bash
# 创建备份脚本
nano /path/to/backup_postgres.sh

# 添加以下内容
#!/bin/bash
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U health_user health_db | gzip > "$BACKUP_DIR/health_db_$DATE.sql.gz"
find "$BACKUP_DIR" -name "health_db_*.sql.gz" -mtime +7 -delete

# 添加到 crontab
crontab -e
# 添加: 0 2 * * * /path/to/backup_postgres.sh
```

---

## 🚨 回滚方案

如果部署出现问题，可以快速回滚：

```bash
# 1. 停止新服务
sudo systemctl stop celery-worker celery-beat

# 2. 恢复 .env 文件
cp .env.backup .env

# 3. 恢复 SQLite 数据库（如果需要）
cp health.db.backup.YYYYMMDD_HHMMSS health.db

# 4. 重启应用
sudo systemctl restart health-app
```

---

## 📋 部署检查清单

- [ ] 服务器信息已确认
- [ ] 当前数据已备份
- [ ] PostgreSQL 已安装并运行
- [ ] Redis 已安装并运行
- [ ] 数据库和用户已创建
- [ ] .env 文件已配置
- [ ] Python 依赖已安装
- [ ] 数据迁移已完成
- [ ] 数据完整性已验证
- [ ] Celery Worker 已启动
- [ ] Celery Beat 已启动
- [ ] 定时任务已注册
- [ ] 应用已重启
- [ ] 所有服务状态正常
- [ ] 日志正常输出
- [ ] 安全配置已完成
- [ ] 监控已设置
- [ ] 备份策略已配置

---

## 🎯 快速命令参考

```bash
# === 服务管理 ===
sudo systemctl status postgresql redis celery-worker celery-beat
sudo systemctl restart postgresql redis celery-worker celery-beat
sudo systemctl stop postgresql redis celery-worker celery-beat

# === 日志查看 ===
sudo tail -f /var/log/celery/worker.log
sudo tail -f /var/log/celery/beat.log
sudo journalctl -u celery-worker -f
sudo journalctl -u celery-beat -f

# === 数据库操作 ===
psql -U health_user -d health_db
pg_dump -U health_user health_db > backup.sql
psql -U health_user -d health_db < backup.sql

# === Celery 操作 ===
celery -A app.celery_app inspect active
celery -A app.celery_app inspect scheduled
celery -A app.celery_app purge  # 清空队列
```

---

## 📞 技术支持

如遇问题，请提供：
1. 服务器系统信息 (`uname -a`)
2. 错误日志（PostgreSQL/Redis/Celery）
3. 服务状态 (`systemctl status`)
4. 配置文件（隐藏敏感信息）

---

> **重要提示**: 
> 1. 生产环境务必使用强密码
> 2. 部署前务必备份数据
> 3. 建议在维护窗口执行
> 4. 准备好回滚方案
