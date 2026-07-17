# PostgreSQL 和 Redis 安装配置指南

> 生成时间: 2026-01-22
> 用于完成 P0 优先级任务：数据库迁移和 Celery 定时任务上线

---

## 一、当前状态

### 已完成 ✅
- PostgreSQL@15 已通过 Homebrew 安装
- PostgreSQL 二进制文件路径: `/usr/local/opt/postgresql@15/bin`
- Redis 已下载但未完成安装（权限问题）

### 待完成 ❌
- PostgreSQL 数据目录初始化（权限问题）
- PostgreSQL 服务启动
- Redis 安装完成
- Redis 服务启动
- 数据库和用户创建
- 数据迁移

---

## 二、手动安装步骤

### Step 1: 修复目录权限

```bash
# 修复 /usr/local/var 目录权限
sudo chown -R $(whoami):admin /usr/local/var

# 如果上面的命令需要密码，请输入你的 macOS 用户密码
```

### Step 2: 初始化 PostgreSQL

```bash
# 添加 PostgreSQL 到 PATH
export PATH="/usr/local/opt/postgresql@15/bin:$PATH"
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

# 初始化数据库
initdb --locale=en_US.UTF-8 -E UTF-8 /usr/local/var/postgresql@15

# 启动 PostgreSQL 服务
brew services start postgresql@15

# 等待服务启动
sleep 5

# 验证服务状态
pg_isready
```

### Step 3: 完成 Redis 安装

```bash
# 完成 Redis 安装
brew postinstall redis

# 启动 Redis 服务
brew services start redis

# 验证 Redis 状态
redis-cli ping
# 应该返回: PONG
```

### Step 4: 创建 PostgreSQL 数据库和用户

```bash
export PATH="/usr/local/opt/postgresql@15/bin:$PATH"

# 创建用户
psql postgres -c "CREATE USER health_user WITH PASSWORD '<production-db-secret>';"

# 创建数据库
psql postgres -c "CREATE DATABASE health_db OWNER health_user;"

# 授权
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE health_db TO health_user;"

# 验证连接
psql -U health_user -d health_db -c "SELECT version();"
```

### Step 5: 配置 .env 文件

在 `backend/.env` 文件中添加以下配置：

```bash
# PostgreSQL 配置
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=health_db
POSTGRES_USER=health_user
POSTGRES_PASSWORD=<production-db-secret>

# Redis 配置
REDIS_URL=redis://localhost:6379/0
```

---

## 三、自动化脚本（推荐）

我已经为你创建了一个自动化安装脚本，执行以下命令：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
chmod +x scripts/setup_postgres_redis.sh
./scripts/setup_postgres_redis.sh
```

---

## 四、数据迁移步骤

### Step 1: 备份当前 SQLite 数据库

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 备份数据库
cp health.db health.db.backup.$(date +%Y%m%d_%H%M%S)

# 验证备份
ls -lh health.db.backup.*
```

### Step 2: 运行数据迁移脚本

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 方式1: 使用 Python 脚本（推荐）
python scripts/migrate_sqlite_to_postgres.py

# 方式2: 使用 pgloader（如果安装了）
brew install pgloader
pgloader health.db postgresql://health_user:<production-db-secret>@localhost/health_db
```

### Step 3: 验证数据迁移

```bash
# 连接到 PostgreSQL
psql -U health_user -d health_db

# 检查表
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

---

## 五、Celery 定时任务配置

### Step 1: 安装 Celery 依赖

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 确保已安装 celery 和 redis
pip install celery redis
```

### Step 2: 启动 Celery Worker

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 启动 Worker（在后台运行）
celery -A app.celery_app worker --loglevel=info --logfile=logs/celery_worker.log &

# 或者在前台运行（用于调试）
celery -A app.celery_app worker --loglevel=info
```

### Step 3: 启动 Celery Beat（定时任务调度器）

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 启动 Beat（在后台运行）
celery -A app.celery_app beat --loglevel=info --logfile=logs/celery_beat.log &

# 或者在前台运行（用于调试）
celery -A app.celery_app beat --loglevel=info
```

### Step 4: 验证定时任务

```bash
# 查看已注册的定时任务
celery -A app.celery_app inspect scheduled

# 查看 Worker 状态
celery -A app.celery_app inspect active

# 查看 Beat 日志
tail -f logs/celery_beat.log
```

---

## 六、定时任务列表

根据 `app/celery_app.py` 配置，以下定时任务将自动运行：

| 任务名称 | 执行时间 | 说明 |
|---------|---------|------|
| `generate-daily-plan` | 每日 6:00 | 生成今日健康计划 |
| `sync-garmin-hourly` | 每小时 :30 分 | 同步所有用户 Garmin 数据 |
| `sleep-reminder` | 每日 22:00 | 发送睡眠提醒 |
| `weekly-report` | 每周一 9:00 | 生成周报 |
| `cleanup-expired-data` | 每日 3:00 | 清理过期数据 |

---

## 七、故障排查

### PostgreSQL 无法启动

```bash
# 检查日志
tail -50 /usr/local/var/log/postgresql@15.log

# 检查端口占用
lsof -i :5432

# 重启服务
brew services restart postgresql@15
```

### Redis 无法启动

```bash
# 检查日志
tail -50 /usr/local/var/log/redis.log

# 检查端口占用
lsof -i :6379

# 重启服务
brew services restart redis
```

### Celery Worker 无法连接 Redis

```bash
# 检查 Redis 连接
redis-cli ping

# 检查 .env 配置
cat backend/.env | grep REDIS

# 重启 Worker
pkill -f "celery worker"
celery -A app.celery_app worker --loglevel=info
```

### 数据迁移失败

```bash
# 检查 PostgreSQL 连接
psql -U health_user -d health_db -c "SELECT 1;"

# 检查 SQLite 数据库
sqlite3 health.db ".tables"

# 查看迁移脚本日志
python scripts/migrate_sqlite_to_postgres.py --verbose
```

---

## 八、生产环境建议

### 1. 安全配置

```bash
# 修改 PostgreSQL 密码（生产环境）
psql postgres -c "ALTER USER health_user WITH PASSWORD '$(openssl rand -base64 32)';"

# 限制 PostgreSQL 远程访问（编辑 postgresql.conf）
# listen_addresses = 'localhost'

# 配置防火墙（如果需要）
# sudo ufw allow from 127.0.0.1 to any port 5432
```

### 2. 性能优化

```bash
# 编辑 PostgreSQL 配置
nano /usr/local/var/postgresql@15/postgresql.conf

# 推荐配置（根据服务器内存调整）
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
min_wal_size = 1GB
max_wal_size = 4GB
```

### 3. 备份策略

```bash
# 每日备份脚本
#!/bin/bash
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# PostgreSQL 备份
pg_dump -U health_user health_db > "$BACKUP_DIR/health_db_$DATE.sql"

# 压缩备份
gzip "$BACKUP_DIR/health_db_$DATE.sql"

# 删除 7 天前的备份
find "$BACKUP_DIR" -name "health_db_*.sql.gz" -mtime +7 -delete
```

### 4. 监控

```bash
# 安装 pgAdmin（可选）
brew install --cask pgadmin4

# 安装 Redis Commander（可选）
npm install -g redis-commander
redis-commander
```

---

## 九、快速检查清单

完成安装后，请执行以下检查：

- [ ] PostgreSQL 服务运行中 (`pg_isready`)
- [ ] Redis 服务运行中 (`redis-cli ping`)
- [ ] 数据库和用户已创建
- [ ] `.env` 文件已配置
- [ ] SQLite 数据已备份
- [ ] 数据迁移完成
- [ ] 数据完整性验证通过
- [ ] Celery Worker 运行中
- [ ] Celery Beat 运行中
- [ ] 定时任务已注册

---

## 十、联系支持

如果遇到问题，请提供以下信息：

1. 错误日志（PostgreSQL/Redis/Celery）
2. 系统信息（`uname -a`）
3. 安装版本（`psql --version`, `redis-server --version`）
4. 配置文件（`.env`，隐藏敏感信息）

---

> **重要提示**: 
> 1. 生产环境请使用强密码
> 2. 定期备份数据库
> 3. 监控 Celery 任务执行情况
> 4. 查看日志文件排查问题
