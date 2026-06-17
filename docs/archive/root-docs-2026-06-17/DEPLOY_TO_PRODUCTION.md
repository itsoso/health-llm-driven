# 🚀 生产环境快速部署指令

> 生成时间: 2026-01-22
> 目标: 在线上服务器执行 P0 任务

---

## 📦 准备工作（在本地执行）

### 1. 上传脚本到服务器

```bash
# 方式 1: 使用 scp
cd /Users/liqiuhua/work/personal/health-llm-driven
scp -r backend/scripts root@your-server:/opt/health-llm-driven/backend/

# 方式 2: 使用 rsync（推荐）
rsync -avz --exclude='__pycache__' \
  backend/scripts/ \
  root@your-server:/opt/health-llm-driven/backend/scripts/

# 方式 3: 如果使用 Git
# 在服务器上直接 pull 最新代码
ssh root@your-server "cd /opt/health-llm-driven && git pull"
```

---

## 🎯 一键部署（在服务器上执行）

### Step 1: SSH 连接到服务器

```bash
ssh root@your-server
```

### Step 2: 执行一键部署脚本

```bash
cd /opt/health-llm-driven/backend
bash scripts/production_setup.sh
```

**脚本会自动完成**:
- ✅ 备份 SQLite 数据库
- ✅ 安装 PostgreSQL 和 Redis
- ✅ 创建数据库和用户（自动生成强密码）
- ✅ 配置 .env 文件
- ✅ 迁移数据
- ✅ 配置 Celery 为系统服务
- ✅ 启动所有服务

**预计时间**: 10-15 分钟

---

## ✅ 验证部署

### 1. 检查服务状态

```bash
# 检查所有服务
sudo systemctl status postgresql redis celery-worker celery-beat

# 单独检查
sudo systemctl status postgresql
sudo systemctl status redis
sudo systemctl status celery-worker
sudo systemctl status celery-beat
```

### 2. 检查数据库

```bash
# 连接数据库（密码在部署脚本输出中）
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

### 3. 检查 Celery 任务

```bash
cd /opt/health-llm-driven/backend

# 激活虚拟环境
source venv/bin/activate

# 查看已注册的任务
celery -A app.celery_app inspect registered

# 查看定时任务
celery -A app.celery_app inspect scheduled

# 查看活动任务
celery -A app.celery_app inspect active
```

### 4. 查看日志

```bash
# Celery Worker 日志
sudo tail -f /var/log/celery/worker.log

# Celery Beat 日志
sudo tail -f /var/log/celery/beat.log

# 系统日志
sudo journalctl -u celery-worker -f
sudo journalctl -u celery-beat -f
```

---

## 🔄 重启应用

部署完成后，需要重启应用以使用 PostgreSQL：

```bash
# 如果使用 systemd
sudo systemctl restart health-app

# 如果使用 supervisor
sudo supervisorctl restart health-app

# 如果手动运行
pkill -f "uvicorn"
cd /opt/health-llm-driven/backend
nohup python main.py > logs/app.log 2>&1 &
```

---

## 📊 定时任务列表

部署完成后，以下任务将自动运行：

| 任务 | 执行时间 | 功能 |
|------|---------|------|
| `generate-daily-plan` | 每日 6:00 | 生成今日健康计划 |
| `sync-garmin-hourly` | 每小时 :30 | 同步 Garmin 数据 |
| `sleep-reminder` | 每日 22:00 | 发送睡眠提醒 |
| `weekly-report` | 每周一 9:00 | 生成周报 |
| `cleanup-expired-data` | 每日 3:00 | 清理过期数据 |

---

## 🔧 常用运维命令

### 服务管理

```bash
# 启动服务
sudo systemctl start celery-worker celery-beat

# 停止服务
sudo systemctl stop celery-worker celery-beat

# 重启服务
sudo systemctl restart celery-worker celery-beat

# 查看状态
sudo systemctl status celery-worker celery-beat

# 查看日志
sudo journalctl -u celery-worker -n 100
sudo journalctl -u celery-beat -n 100
```

### Celery 管理

```bash
cd /opt/health-llm-driven/backend
source venv/bin/activate

# 查看 Worker 状态
celery -A app.celery_app inspect active

# 查看定时任务
celery -A app.celery_app inspect scheduled

# 清空任务队列
celery -A app.celery_app purge

# 手动触发任务
python -c "from app.tasks.health_analysis import generate_daily_plan_for_all; generate_daily_plan_for_all.delay()"
```

### 数据库管理

```bash
# 备份数据库
pg_dump -U health_user health_db | gzip > backup_$(date +%Y%m%d).sql.gz

# 恢复数据库
gunzip < backup_20260122.sql.gz | psql -U health_user health_db

# 查看数据库大小
psql -U health_user -d health_db -c "SELECT pg_size_pretty(pg_database_size('health_db'));"
```

---

## 🐛 故障排查

### 问题 1: Celery Worker 无法启动

```bash
# 查看详细日志
sudo journalctl -u celery-worker -n 100 --no-pager

# 检查 Redis 连接
redis-cli ping

# 手动启动测试
cd /opt/health-llm-driven/backend
source venv/bin/activate
celery -A app.celery_app worker --loglevel=debug
```

### 问题 2: 数据迁移失败

```bash
# 检查 PostgreSQL 连接
psql -U health_user -d health_db -c "SELECT 1;"

# 查看迁移日志
cat /opt/health-llm-driven/backend/migration.log

# 手动重新迁移
cd /opt/health-llm-driven/backend
python scripts/migrate_sqlite_to_postgres.py
```

### 问题 3: 定时任务不执行

```bash
# 检查 Beat 状态
sudo systemctl status celery-beat

# 查看 Beat 日志
sudo tail -100 /var/log/celery/beat.log

# 重启 Beat
sudo systemctl restart celery-beat
```

---

## 🔒 安全建议

### 1. 修改数据库密码

部署脚本会自动生成强密码，请妥善保存！

如需修改：

```bash
# 生成新密码
NEW_PASSWORD=$(openssl rand -base64 24)

# 修改 PostgreSQL 密码
sudo -u postgres psql << EOF
ALTER USER health_user WITH PASSWORD '$NEW_PASSWORD';
\q
EOF

# 更新 .env 文件
nano /opt/health-llm-driven/backend/.env
# 修改 POSTGRES_PASSWORD=$NEW_PASSWORD
```

### 2. 配置防火墙

```bash
# 只允许必要的端口
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# PostgreSQL 和 Redis 只监听本地，不对外开放
```

### 3. 设置日志轮转

```bash
sudo tee /etc/logrotate.d/celery > /dev/null << EOF
/var/log/celery/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 $(whoami) $(id -gn)
    sharedscripts
    postrotate
        systemctl reload celery-worker celery-beat > /dev/null 2>&1 || true
    endscript
}
EOF
```

---

## 📋 部署检查清单

完成部署后，请逐项检查：

- [ ] PostgreSQL 服务运行中
- [ ] Redis 服务运行中
- [ ] 数据库和用户已创建
- [ ] 数据迁移完成
- [ ] 数据完整性验证通过
- [ ] Celery Worker 运行中
- [ ] Celery Beat 运行中
- [ ] 定时任务已注册（5 个）
- [ ] 应用已重启
- [ ] API 接口正常响应
- [ ] 日志正常输出
- [ ] 数据库密码已保存
- [ ] 防火墙已配置
- [ ] 日志轮转已设置

---

## 🎯 快速命令速查

```bash
# === 一键部署 ===
ssh root@your-server
cd /opt/health-llm-driven/backend
bash scripts/production_setup.sh

# === 检查状态 ===
sudo systemctl status postgresql redis celery-worker celery-beat

# === 查看日志 ===
sudo tail -f /var/log/celery/worker.log
sudo tail -f /var/log/celery/beat.log

# === 重启服务 ===
sudo systemctl restart celery-worker celery-beat

# === 验证任务 ===
celery -A app.celery_app inspect scheduled
```

---

## 📚 相关文档

- [生产环境部署指南](PRODUCTION_DEPLOYMENT.md) - 详细步骤
- [快速设置指南](QUICK_SETUP_GUIDE.md) - 本地开发
- [实施报告](P0_TASKS_IMPLEMENTATION.md) - 技术细节

---

## 📞 需要帮助？

如遇问题，请提供：
1. 服务器系统信息 (`cat /etc/os-release`)
2. 错误日志（Celery/PostgreSQL/Redis）
3. 服务状态 (`systemctl status`)
4. 部署脚本输出

---

> **重要提示**: 
> - 部署前务必备份数据
> - 建议在维护窗口执行
> - 保存好数据库密码
> - 部署后验证所有功能
