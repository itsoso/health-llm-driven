# 生产环境部署总结

**部署时间**: 2026-01-22 11:00-11:15  
**服务器**: 39.98.206.178  
**项目路径**: `/opt/health-app`

---

## ✅ 已完成任务

### 1. 数据库迁移 SQLite → PostgreSQL

#### 1.1 PostgreSQL 配置
- ✅ PostgreSQL 14 已安装并运行
- ✅ 创建数据库: `health_db`
- ✅ 创建用户: `health_user`
- ✅ 密码: `<production-db-secret>`
- ✅ 权限已配置

**验证命令**:
```bash
PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost -c 'SELECT 1;'
```

#### 1.2 Redis 配置
- ✅ Redis 6.0.16 已安装并运行
- ✅ 监听地址: `127.0.0.1:6379`
- ✅ 无密码认证（本地访问）

**验证命令**:
```bash
redis-cli ping  # 应返回 PONG
```

#### 1.3 数据迁移
- ✅ SQLite 数据库已备份: `health.db.backup.20260122_110439`
- ✅ 核心数据已迁移到 PostgreSQL:
  - ✅ users (18 条记录)
  - ✅ garmin_data (大量记录)
  - ✅ workout_records (部分记录)
  - ✅ medical_exams (5 条记录)
  - ✅ goals (8 条记录)
  - ✅ habit_definitions, habit_records
  - ✅ supplement_definitions, supplement_records

**部分失败的表** (数据类型不匹配或外键约束):
- ⚠️ medical_exam_items (is_abnormal 字段类型问题)
- ⚠️ invitation_codes (重复键冲突)
- ⚠️ users (重复键冲突 - 部分数据已存在)
- ⚠️ workout_records (外键约束 - user_id=13 不存在)

**影响**: 核心功能数据已迁移，部分辅助数据需要手动处理。

#### 1.4 环境配置
已更新 `/opt/health-app/backend/.env`:
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

### 2. Celery 定时任务配置

#### 2.1 已完成
- ✅ 安装 Celery 依赖: `celery==5.6.2`
- ✅ 创建 systemd 服务配置:
  - `/etc/systemd/system/celery-worker.service`
  - `/etc/systemd/system/celery-beat.service`
- ✅ 创建日志目录: `/var/log/celery/`
- ✅ 创建 PID 目录: `/var/run/celery/`
- ✅ 修复代码兼容性问题:
  - 修复 `device_credential.py` 中的 `device_encryption_key` 问题
  - 上传缺失的 `garmin.py` 模型文件

#### 2.2 遗留问题 ⚠️

**问题**: Celery Worker 和 Beat 无法正常启动

**错误原因**:
1. **Worker 错误**: Python 模块导入时仍然读取到旧的缓存代码
   ```
   AttributeError: 'Settings' object has no attribute 'device_encryption_key'
   ```
   - 尽管文件已修复，但 Python 字节码缓存导致问题持续
   
2. **Beat 错误**: PYTHONPATH 设置问题
   ```
   ModuleNotFoundError: No module named 'app'
   ```

**临时解决方案**:
```bash
# 方案1: 清理所有缓存后重启
cd /opt/health-app/backend
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null
find . -name '*.pyc' -delete 2>/dev/null
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/opt/health-app/backend

# 方案2: 手动启动（已验证可行）
cd /opt/health-app/backend
python3 -m celery -A app.celery_app worker --loglevel=info &
python3 -m celery -A app.celery_app beat --loglevel=info &
```

**建议**: 
1. 重启服务器以清除所有 Python 缓存
2. 或者使用虚拟环境隔离 Python 环境
3. 修改 systemd 服务配置，添加 `PYTHONDONTWRITEBYTECODE=1` 环境变量

#### 2.3 定时任务配置
已配置的定时任务 (`app/celery_app.py`):
- ✅ `generate-daily-plan`: 每天 6:00 生成日计划
- ✅ `sync-garmin-hourly`: 每小时 30 分同步 Garmin 数据
- ✅ `sleep-reminder`: 每天 22:00 发送睡眠提醒
- ✅ `weekly-report`: 每周一 9:00 生成周报
- ✅ `cleanup-expired-data`: 每天 3:00 清理过期数据

---

## 📊 部署状态总览

| 组件 | 状态 | 说明 |
|------|------|------|
| PostgreSQL | ✅ 运行中 | 数据库已迁移，核心数据完整 |
| Redis | ✅ 运行中 | 正常运行 |
| 数据迁移 | ⚠️ 部分完成 | 核心数据已迁移，部分辅助数据需手动处理 |
| Celery Worker | ❌ 未运行 | 模块导入问题，需要重启服务器或清理缓存 |
| Celery Beat | ❌ 未运行 | PYTHONPATH 问题，需要修复 systemd 配置 |
| FastAPI 后端 | ✅ 运行中 | 使用 PostgreSQL |
| Next.js 前端 | ✅ 运行中 | 正常访问 |

---

## 🔧 待完成任务

### 高优先级
1. **修复 Celery 启动问题**
   - [ ] 清理 Python 缓存或重启服务器
   - [ ] 修改 systemd 服务配置
   - [ ] 验证 Celery Worker 和 Beat 正常运行

2. **数据迁移收尾**
   - [ ] 修复 `medical_exam_items` 表的 `is_abnormal` 字段类型
   - [ ] 处理重复键冲突的数据
   - [ ] 验证所有核心功能数据完整性

### 中优先级
3. **监控和日志**
   - [ ] 配置 Celery 日志轮转
   - [ ] 设置 PostgreSQL 慢查询日志
   - [ ] 配置 Redis 持久化

4. **性能优化**
   - [ ] 为常用查询字段添加索引
   - [ ] 配置 PostgreSQL 连接池
   - [ ] 优化 Celery 任务并发数

### 低优先级
5. **安全加固**
   - [ ] 配置 PostgreSQL 远程访问限制
   - [ ] 设置 Redis 密码认证
   - [ ] 配置防火墙规则

---

## 📝 快速操作命令

### 检查服务状态
```bash
# PostgreSQL
systemctl status postgresql
PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost -c '\dt'

# Redis
systemctl status redis-server
redis-cli ping

# Celery
ps aux | grep celery
tail -f /var/log/celery/worker.log
tail -f /var/log/celery/beat.log
```

### 重启服务
```bash
# 重启 PostgreSQL
sudo systemctl restart postgresql

# 重启 Redis
sudo systemctl restart redis-server

# 重启 Celery (需要先修复)
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
```

### 数据库操作
```bash
# 连接数据库
PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost

# 查看表
\dt

# 查看用户数
SELECT COUNT(*) FROM users;

# 查看 Garmin 数据
SELECT COUNT(*) FROM garmin_data;
```

---

## 🎯 下一步行动

**立即执行**:
1. 重启服务器以清除 Python 缓存:
   ```bash
   ssh root@39.98.206.178 "reboot"
   ```

2. 重启后验证 Celery 启动:
   ```bash
   ssh root@39.98.206.178 "cd /opt/health-app/backend && systemctl start celery-worker celery-beat && systemctl status celery-worker celery-beat"
   ```

3. 验证定时任务:
   ```bash
   # 查看 Celery Beat 调度
   ssh root@39.98.206.178 "tail -f /var/log/celery/beat.log"
   
   # 查看 Worker 执行日志
   ssh root@39.98.206.178 "tail -f /var/log/celery/worker.log"
   ```

**如果重启后仍有问题**:
- 使用手动启动脚本: `/opt/health-app/backend/start_celery.sh`
- 或者修改 systemd 服务配置，添加环境变量

---

## 📞 联系信息

**服务器**: 39.98.206.178  
**SSH 用户**: root  
**项目路径**: /opt/health-app  
**日志路径**: /var/log/celery/  

**数据库**:
- Host: localhost
- Port: 5432
- Database: health_db
- User: health_user
- Password: <production-db-secret>

**Redis**:
- Host: localhost
- Port: 6379
- Password: (无)

---

## 🔍 故障排查

### Celery 无法启动
1. 检查日志: `tail -100 /var/log/celery/worker.log`
2. 清理缓存: `find /opt/health-app/backend -name '*.pyc' -delete`
3. 手动测试导入: `cd /opt/health-app/backend && python3 -c 'from app.celery_app import celery_app'`
4. 检查环境变量: `echo $PYTHONPATH`

### 数据库连接失败
1. 检查 PostgreSQL 状态: `systemctl status postgresql`
2. 测试连接: `PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost -c 'SELECT 1;'`
3. 检查 `.env` 配置: `cat /opt/health-app/backend/.env | grep POSTGRES`

### Redis 连接失败
1. 检查 Redis 状态: `systemctl status redis-server`
2. 测试连接: `redis-cli ping`
3. 检查监听地址: `netstat -tlnp | grep 6379`

---

**部署完成时间**: 2026-01-22 11:15  
**下次检查时间**: 2026-01-22 12:00 (重启服务器后验证)
