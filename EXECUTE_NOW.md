# 🚀 立即执行 - P0 任务部署

> **当前状态**: 所有脚本和文档已准备就绪！
> **执行时间**: 约 15-20 分钟
> **风险等级**: 低（已完整备份和验证机制）

---

## ⚡ 快速开始（3 步完成）

### Step 1: 修复权限（如果需要）

```bash
sudo chown -R $(whoami):admin /usr/local/var
```

**说明**: 这一步需要输入你的 macOS 用户密码

---

### Step 2: 一键部署

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
bash scripts/complete_setup.sh
```

**说明**: 
- 脚本会自动完成所有配置
- 遇到确认提示输入 `yes`
- 全程约 10-15 分钟

---

### Step 3: 验证部署

```bash
# 检查服务状态
pg_isready && echo "✓ PostgreSQL OK"
redis-cli ping && echo "✓ Redis OK"
pgrep -f "celery.*worker" && echo "✓ Celery Worker OK"
pgrep -f "celery.*beat" && echo "✓ Celery Beat OK"
```

**预期结果**: 所有检查都显示 OK

---

## 📋 脚本执行流程

`complete_setup.sh` 会自动执行以下操作：

1. ✅ 安装 PostgreSQL 15
2. ✅ 安装 Redis
3. ✅ 初始化 PostgreSQL 数据目录
4. ✅ 创建数据库和用户
5. ✅ 配置 .env 文件
6. ✅ 备份 SQLite 数据库
7. ✅ 迁移数据到 PostgreSQL
8. ✅ 验证数据完整性
9. ✅ 启动 Celery Worker
10. ✅ 启动 Celery Beat

---

## 🎯 部署后验证清单

- [ ] PostgreSQL 运行中 (`pg_isready`)
- [ ] Redis 运行中 (`redis-cli ping`)
- [ ] 数据库已创建 (`psql -U health_user -d health_db -c "\dt"`)
- [ ] 数据已迁移（检查表行数）
- [ ] Celery Worker 运行中
- [ ] Celery Beat 运行中
- [ ] 定时任务已注册 (`celery -A app.celery_app inspect scheduled`)

---

## 📊 定时任务列表

部署完成后，以下任务将自动运行：

| 任务 | 时间 | 功能 |
|------|------|------|
| 生成每日计划 | 每日 6:00 | AI 生成今日健康计划 |
| 同步 Garmin | 每小时 :30 | 自动同步健康数据 |
| 睡眠提醒 | 每日 22:00 | 推送睡眠提醒 |
| 周报生成 | 每周一 9:00 | 生成健康周报 |
| 数据清理 | 每日 3:00 | 清理过期数据 |

---

## 🔧 常用命令

### 查看日志

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend

# Celery Worker 日志
tail -f logs/celery_worker.log

# Celery Beat 日志
tail -f logs/celery_beat.log

# PostgreSQL 日志
tail -f /usr/local/var/log/postgresql@15.log
```

### 重启服务

```bash
# 重启 Celery
pkill -f "celery.*worker"
pkill -f "celery.*beat"
bash scripts/start_celery.sh

# 重启 PostgreSQL
brew services restart postgresql@15

# 重启 Redis
brew services restart redis
```

---

## 🆘 遇到问题？

### 问题 1: PostgreSQL 无法启动

```bash
# 查看日志
tail -50 /usr/local/var/log/postgresql@15.log

# 重新初始化（会清空数据，谨慎！）
rm -rf /usr/local/var/postgresql@15
initdb --locale=en_US.UTF-8 -E UTF-8 /usr/local/var/postgresql@15
brew services restart postgresql@15
```

### 问题 2: 数据迁移失败

```bash
# 检查连接
psql -U health_user -d health_db -c "SELECT 1;"

# 查看详细错误
python scripts/migrate_sqlite_to_postgres.py 2>&1 | tee migration.log
```

### 问题 3: Celery 无法启动

```bash
# 检查 Redis
redis-cli ping

# 查看错误日志
tail -100 logs/celery_worker.log
```

---

## 📚 详细文档

如需更多信息，请查看：

- [快速部署指南](QUICK_SETUP_GUIDE.md)
- [完整安装指南](POSTGRES_REDIS_SETUP.md)
- [实施报告](P0_TASKS_IMPLEMENTATION.md)

---

## ✨ 部署完成后

1. **重启应用**:
   ```bash
   cd /Users/liqiuhua/work/personal/health-llm-driven/backend
   pkill -f "uvicorn"
   python main.py
   ```

2. **测试 API**:
   - 访问 http://localhost:8000/docs
   - 测试健康检查接口

3. **监控定时任务**:
   - 查看 Celery 日志
   - 验证任务按时执行

---

> **现在就开始**: 复制上面的命令，在终端执行！
