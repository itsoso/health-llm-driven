# 🚀 远程服务器部署 - 立即执行

> 生成时间: 2026-01-22
> 目标: 直接在服务器上部署并迁移数据库

---

## 📋 前置信息

请先确认以下信息：

```bash
# 服务器地址
SERVER_IP="your-server-ip"
SERVER_USER="root"  # 或其他用户

# 项目路径（服务器上）
PROJECT_PATH="/opt/health-llm-driven"  # 或实际路径
```

---

## 🎯 方案 A: 使用 Git 部署（推荐）

### Step 1: 提交并推送代码

```bash
# 在本地执行
cd /Users/liqiuhua/work/personal/health-llm-driven

# 添加所有新文件
git add backend/scripts/*.sh
git add backend/scripts/migrate_sqlite_to_postgres.py
git add *.md

# 提交
git commit -m "feat: 添加生产环境部署脚本和数据库迁移工具"

# 推送到远程仓库
git push origin main  # 或你的分支名
```

### Step 2: 在服务器上拉取代码

```bash
# SSH 连接到服务器
ssh $SERVER_USER@$SERVER_IP

# 进入项目目录
cd $PROJECT_PATH

# 拉取最新代码
git pull origin main

# 赋予脚本执行权限
chmod +x backend/scripts/*.sh
chmod +x backend/scripts/migrate_sqlite_to_postgres.py
```

### Step 3: 执行一键部署

```bash
# 在服务器上执行
cd $PROJECT_PATH/backend
bash scripts/production_setup.sh
```

---

## 🎯 方案 B: 直接上传脚本（快速）

### Step 1: 上传脚本到服务器

```bash
# 在本地执行
cd /Users/liqiuhua/work/personal/health-llm-driven

# 使用 rsync 上传（推荐）
rsync -avz --progress \
  backend/scripts/ \
  $SERVER_USER@$SERVER_IP:$PROJECT_PATH/backend/scripts/

# 或使用 scp
scp backend/scripts/*.sh \
  $SERVER_USER@$SERVER_IP:$PROJECT_PATH/backend/scripts/
scp backend/scripts/migrate_sqlite_to_postgres.py \
  $SERVER_USER@$SERVER_IP:$PROJECT_PATH/backend/scripts/
```

### Step 2: SSH 连接并执行

```bash
# SSH 连接
ssh $SERVER_USER@$SERVER_IP

# 赋予执行权限
chmod +x $PROJECT_PATH/backend/scripts/*.sh
chmod +x $PROJECT_PATH/backend/scripts/migrate_sqlite_to_postgres.py

# 执行部署
cd $PROJECT_PATH/backend
bash scripts/production_setup.sh
```

---

## 🎯 方案 C: 一键远程部署（最快）

创建一个本地脚本，自动完成所有操作：

```bash
# 在本地创建部署脚本
cat > /Users/liqiuhua/work/personal/health-llm-driven/deploy_remote.sh << 'EOF'
#!/bin/bash

# 配置信息
SERVER_USER="root"
SERVER_IP="your-server-ip"
PROJECT_PATH="/opt/health-llm-driven"

echo "🚀 开始远程部署..."
echo ""

# Step 1: 上传脚本
echo "📦 Step 1: 上传部署脚本..."
rsync -avz --progress \
  backend/scripts/ \
  $SERVER_USER@$SERVER_IP:$PROJECT_PATH/backend/scripts/

if [ $? -ne 0 ]; then
    echo "❌ 上传失败"
    exit 1
fi

echo "✅ 上传完成"
echo ""

# Step 2: 远程执行部署
echo "🔧 Step 2: 执行远程部署..."
ssh $SERVER_USER@$SERVER_IP << 'ENDSSH'
cd $PROJECT_PATH/backend
chmod +x scripts/*.sh scripts/migrate_sqlite_to_postgres.py
bash scripts/production_setup.sh
ENDSSH

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 部署完成！"
else
    echo ""
    echo "❌ 部署失败，请检查日志"
    exit 1
fi
EOF

# 赋予执行权限
chmod +x /Users/liqiuhua/work/personal/health-llm-driven/deploy_remote.sh

# 执行部署
cd /Users/liqiuhua/work/personal/health-llm-driven
./deploy_remote.sh
```

---

## 📝 详细步骤说明

### 部署脚本会自动完成以下操作：

1. ✅ **备份数据库**
   ```bash
   cp health.db health.db.backup.$(date +%Y%m%d_%H%M%S)
   ```

2. ✅ **安装依赖**
   - PostgreSQL 15
   - Redis
   - Python 依赖 (psycopg2-binary, redis, celery)

3. ✅ **配置 PostgreSQL**
   - 创建数据库 `health_db`
   - 创建用户 `health_user`
   - 自动生成强密码
   - 配置认证方式

4. ✅ **配置 Redis**
   - 启动 Redis 服务
   - 设置开机自启

5. ✅ **更新 .env 文件**
   - 添加 PostgreSQL 连接信息
   - 添加 Redis 连接信息

6. ✅ **数据迁移**
   - 从 SQLite 迁移到 PostgreSQL
   - 批量迁移（1000 行/批次）
   - 自动验证数据完整性

7. ✅ **配置 Celery**
   - 创建 systemd 服务
   - 配置 Worker 和 Beat
   - 启动并设置开机自启

8. ✅ **启动服务**
   - PostgreSQL
   - Redis
   - Celery Worker
   - Celery Beat

---

## ✅ 部署后验证

### 1. 检查服务状态

```bash
# 在服务器上执行
sudo systemctl status postgresql redis celery-worker celery-beat
```

### 2. 检查数据库

```bash
# 连接数据库（密码在部署输出中）
psql -U health_user -d health_db

# 查看表
\dt

# 检查数据量
SELECT 
    'users' as table_name, COUNT(*) as count FROM users
UNION ALL
SELECT 'garmin_data', COUNT(*) FROM garmin_data
UNION ALL
SELECT 'workout_records', COUNT(*) FROM workout_records
UNION ALL
SELECT 'diet_records', COUNT(*) FROM diet_records;

# 退出
\q
```

### 3. 检查 Celery 任务

```bash
cd $PROJECT_PATH/backend
source venv/bin/activate  # 如果使用虚拟环境

# 查看已注册的任务
celery -A app.celery_app inspect registered

# 查看定时任务
celery -A app.celery_app inspect scheduled
```

### 4. 查看日志

```bash
# Celery Worker 日志
sudo tail -f /var/log/celery/worker.log

# Celery Beat 日志
sudo tail -f /var/log/celery/beat.log

# 系统日志
sudo journalctl -u celery-worker -f
```

---

## 🔄 重启应用

部署完成后，需要重启应用以使用 PostgreSQL：

```bash
# 方式 1: 如果使用 systemd
sudo systemctl restart health-app

# 方式 2: 如果使用 supervisor
sudo supervisorctl restart health-app

# 方式 3: 如果手动运行
pkill -f "uvicorn"
cd $PROJECT_PATH/backend
source venv/bin/activate
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

## 🐛 常见问题

### 问题 1: 无法连接服务器

```bash
# 检查 SSH 连接
ssh -v $SERVER_USER@$SERVER_IP

# 检查防火墙
sudo ufw status
```

### 问题 2: 权限不足

```bash
# 使用 sudo 执行
sudo bash scripts/production_setup.sh

# 或切换到 root 用户
sudo su -
cd $PROJECT_PATH/backend
bash scripts/production_setup.sh
```

### 问题 3: PostgreSQL 安装失败

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# CentOS/RHEL
sudo yum install -y postgresql-server postgresql-contrib
sudo postgresql-setup initdb
```

### 问题 4: 数据迁移失败

```bash
# 检查 SQLite 数据库
ls -lh health.db

# 检查 PostgreSQL 连接
psql -U health_user -d health_db -c "SELECT 1;"

# 查看详细错误
python scripts/migrate_sqlite_to_postgres.py 2>&1 | tee migration.log
```

---

## 🔒 安全提示

### 1. 保存数据库密码

部署脚本会自动生成强密码，**务必保存**！

密码会显示在部署输出中：
```
生成的数据库密码: xxxxxxxxxxxxxxxxxx
请保存此密码！
```

### 2. 配置防火墙

```bash
# 只允许必要的端口
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# PostgreSQL 和 Redis 只监听本地
```

### 3. 定期备份

```bash
# 创建备份脚本
cat > /opt/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups"
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U health_user health_db | gzip > "$BACKUP_DIR/health_db_$DATE.sql.gz"
find "$BACKUP_DIR" -name "health_db_*.sql.gz" -mtime +7 -delete
EOF

chmod +x /opt/backup_db.sh

# 添加到 crontab（每天凌晨 2 点备份）
crontab -e
# 添加: 0 2 * * * /opt/backup_db.sh
```

---

## 📋 快速命令参考

```bash
# === 上传脚本 ===
rsync -avz backend/scripts/ $SERVER_USER@$SERVER_IP:$PROJECT_PATH/backend/scripts/

# === SSH 连接 ===
ssh $SERVER_USER@$SERVER_IP

# === 执行部署 ===
cd $PROJECT_PATH/backend
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

## 🎯 执行清单

- [ ] 确认服务器 IP 和用户
- [ ] 确认项目路径
- [ ] 上传部署脚本到服务器
- [ ] SSH 连接到服务器
- [ ] 执行 production_setup.sh
- [ ] 保存数据库密码
- [ ] 验证服务状态
- [ ] 检查数据迁移
- [ ] 验证 Celery 任务
- [ ] 重启应用
- [ ] 测试 API 接口

---

## 📞 需要帮助？

如遇问题，请提供：
1. 服务器系统信息 (`cat /etc/os-release`)
2. 部署脚本输出日志
3. 错误信息截图
4. 服务状态 (`systemctl status`)

---

> **现在就开始**: 
> 1. 修改上面的 `SERVER_IP` 和 `PROJECT_PATH`
> 2. 选择一个方案执行
> 3. 等待 10-15 分钟完成部署
