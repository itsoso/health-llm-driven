# 快速部署指南 - PostgreSQL + Redis + Celery

> 生成时间: 2026-01-22
> 用于完成 P0 优先级任务

---

## 🚀 一键部署（推荐）

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
bash scripts/complete_setup.sh
```

这个脚本会自动完成所有步骤！

---

## 📋 分步执行（如果一键部署失败）

### Step 1: 安装 PostgreSQL 和 Redis

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
bash scripts/setup_postgres_redis.sh
```

**如果遇到权限问题**，请手动执行：

```bash
# 修复目录权限
sudo chown -R $(whoami):admin /usr/local/var

# 然后重新运行脚本
bash scripts/setup_postgres_redis.sh
```

### Step 2: 备份 SQLite 数据库

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
cp health.db health.db.backup.$(date +%Y%m%d_%H%M%S)
ls -lh health.db.backup.*
```

### Step 3: 数据迁移

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
python scripts/migrate_sqlite_to_postgres.py
```

### Step 4: 启动 Celery

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
bash scripts/start_celery.sh
```

选择模式：
- **模式 1**: 前台运行（用于调试，可以看到实时日志）
- **模式 2**: 后台运行（生产环境，日志写入文件）

---

## ✅ 验证部署

### 1. 检查服务状态

```bash
# PostgreSQL
pg_isready
# 应该显示: accepting connections

# Redis
redis-cli ping
# 应该返回: PONG

# Celery Worker
pgrep -f "celery.*worker"
# 应该返回进程 ID

# Celery Beat
pgrep -f "celery.*beat"
# 应该返回进程 ID
```

### 2. 检查数据库连接

```bash
# 连接 PostgreSQL
psql -U health_user -d health_db

# 查看表
\dt

# 查看数据量
SELECT 'users' as table_name, COUNT(*) FROM users
UNION ALL
SELECT 'garmin_data', COUNT(*) FROM garmin_data
UNION ALL
SELECT 'workout_records', COUNT(*) FROM workout_records;

# 退出
\q
```

### 3. 检查 Celery 任务

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# 查看已注册的定时任务
celery -A app.celery_app inspect scheduled

# 查看 Worker 状态
celery -A app.celery_app inspect active

# 查看日志
tail -f logs/celery_worker.log
tail -f logs/celery_beat.log
```

---

## 📊 定时任务列表

| 任务名称 | 执行时间 | 说明 |
|---------|---------|------|
| `generate-daily-plan` | 每日 6:00 | 生成今日健康计划 |
| `sync-garmin-hourly` | 每小时 :30 分 | 同步所有用户 Garmin 数据 |
| `sleep-reminder` | 每日 22:00 | 发送睡眠提醒 |
| `weekly-report` | 每周一 9:00 | 生成周报 |
| `cleanup-expired-data` | 每日 3:00 | 清理过期数据 |

---

## 🔧 常用命令

### 启动服务

```bash
# 启动 PostgreSQL
brew services start postgresql@15

# 启动 Redis
brew services start redis

# 启动 Celery（后台）
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
nohup celery -A app.celery_app worker --loglevel=info --logfile=logs/celery_worker.log &
nohup celery -A app.celery_app beat --loglevel=info --logfile=logs/celery_beat.log &
```

### 停止服务

```bash
# 停止 PostgreSQL
brew services stop postgresql@15

# 停止 Redis
brew services stop redis

# 停止 Celery
pkill -f "celery.*worker"
pkill -f "celery.*beat"
```

### 重启服务

```bash
# 重启 PostgreSQL
brew services restart postgresql@15

# 重启 Redis
brew services restart redis

# 重启 Celery
pkill -f "celery.*worker"
pkill -f "celery.*beat"
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
bash scripts/start_celery.sh
```

---

## 🐛 故障排查

### PostgreSQL 无法启动

```bash
# 查看日志
tail -50 /usr/local/var/log/postgresql@15.log

# 检查数据目录
ls -la /usr/local/var/postgresql@15

# 重新初始化（谨慎！会删除数据）
rm -rf /usr/local/var/postgresql@15
initdb --locale=en_US.UTF-8 -E UTF-8 /usr/local/var/postgresql@15
brew services restart postgresql@15
```

### Redis 无法启动

```bash
# 查看日志
tail -50 /usr/local/var/log/redis.log

# 检查端口占用
lsof -i :6379

# 强制停止
pkill -9 redis-server

# 重新启动
brew services start redis
```

### Celery 任务不执行

```bash
# 检查 Redis 连接
redis-cli ping

# 检查 Worker 日志
tail -100 logs/celery_worker.log

# 检查 Beat 日志
tail -100 logs/celery_beat.log

# 手动触发任务（测试）
python -c "from app.tasks.health_analysis import generate_daily_plan_for_all; generate_daily_plan_for_all.delay()"
```

### 数据迁移失败

```bash
# 检查 PostgreSQL 连接
psql -U health_user -d health_db -c "SELECT 1;"

# 检查 SQLite 数据库
sqlite3 health.db ".tables"

# 查看详细错误
python scripts/migrate_sqlite_to_postgres.py 2>&1 | tee migration.log
```

---

## 📝 配置文件

### .env 配置示例

```bash
# PostgreSQL 配置
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=health_db
POSTGRES_USER=health_user
POSTGRES_PASSWORD=<production-db-secret>

# Redis 配置
REDIS_URL=redis://localhost:6379/0

# OpenAI 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# JWT 密钥
SECRET_KEY=your_secret_key_here

# 其他配置...
```

---

## 🎯 下一步

部署完成后：

1. **重启应用**，使用 PostgreSQL 数据库：
   ```bash
   cd /Users/liqiuhua/work/personal/health-llm-driven/backend
   pkill -f "uvicorn"
   python main.py
   ```

2. **验证功能**：
   - 访问 http://localhost:8000/docs
   - 测试 API 接口
   - 检查数据是否正常

3. **监控定时任务**：
   - 查看 Celery 日志
   - 验证定时任务是否按时执行

4. **备份数据**：
   - 定期备份 PostgreSQL 数据库
   - 保留 SQLite 备份文件

---

## 📚 相关文档

- [完整安装指南](POSTGRES_REDIS_SETUP.md)
- [Codex 重构报告](CODEX_REFACTOR_STATUS.md)
- [项目路线图](EXECUTOR_V2_ROADMAP.md)

---

## 🆘 需要帮助？

如果遇到问题：

1. 查看日志文件
2. 检查服务状态
3. 参考故障排查部分
4. 查看完整文档

---

> **提示**: 首次部署建议使用**一键部署脚本**，如果遇到问题再使用分步执行。
