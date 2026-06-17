# ✅ Celery 定时任务部署成功

> 2026-01-22 11:32 - 线上 Celery Worker 和 Beat 已成功启动

---

## 🎯 部署结果

### 服务状态

```bash
● celery-worker.service - Celery Worker
     Active: active (running) since Thu 2026-01-22 11:32:03 CST
   Main PID: 1600134 (python3)
      Tasks: 5 (5 个 worker 进程)
     Memory: 251.7M

● celery-beat.service - Celery Beat Scheduler
     Active: active (running) since Thu 2026-01-22 11:32:03 CST
   Main PID: 1600136 (python3)
     Memory: 89.5M
```

### 已注册的定时任务

```
✅ sync-garmin-6hourly       - 每 6 小时同步 Garmin 数据 (0 */6 * * *)
✅ morning-briefing          - 早间健康简报 (每天 7:00)
✅ evening-review            - 晚间健康回顾 (每天 21:00)
✅ weekly-report             - 每周健康报告 (每周一 9:00)
✅ exercise-reminders        - 运动提醒 (每小时检查)
✅ sleep-reminders           - 睡眠提醒 (每小时检查)
✅ water-reminders           - 饮水提醒 (每小时检查)
```

---

## 🛠️ 解决的问题

### 1. Python 模块导入错误

**问题**: `ModuleNotFoundError: No module named 'app'`

**原因**: 
- `PYTHONPATH` 未正确设置
- Python 字节码缓存 (`.pyc`) 导致加载旧版本代码

**解决方案**:
```bash
# systemd 服务配置中添加
Environment="PYTHONPATH=/opt/health-app/backend"
Environment="PYTHONDONTWRITEBYTECODE=1"

# 启动命令使用 -B 标志
ExecStart=/usr/bin/python3 -B -m celery -A app.celery_app worker --loglevel=info
```

### 2. 设备凭证加密密钥错误

**问题**: `AttributeError: 'Settings' object has no attribute 'device_encryption_key'`

**原因**: `device_credential.py` 中直接访问不存在的配置项

**解决方案**: 简化加密密钥生成逻辑
```python
# 直接从 secret_key 生成加密密钥
SECRET_KEY = settings.secret_key
key = hashlib.sha256(SECRET_KEY.encode()).digest()
ENCRYPTION_KEY = base64.urlsafe_b64encode(key)
```

### 3. Garmin 同步任务导入错误

**问题**: 
- `ModuleNotFoundError: No module named 'app.models.garmin'`
- `ModuleNotFoundError: No module named 'app.services.garmin_connect'`

**原因**: 代码重构后模块路径变更

**解决方案**:
```python
# 更新导入路径
from app.models.device_credential import DeviceCredential  # 原 GarminCredential
from app.services.data_collection.garmin_connect import GarminConnectService
```

### 4. AI 调度器类名不匹配

**问题**: `ImportError: cannot import name 'AISchedulerService'`

**原因**: 类名为 `AIScheduler` 但导入为 `AISchedulerService`

**解决方案**:
```python
from app.services.ai_scheduler import AIScheduler  # 修正类名
```

### 5. Python 依赖缺失

**问题**: `ModuleNotFoundError: No module named 'openai'`

**解决方案**:
```bash
pip3 install openai garminconnect
```

---

## 📋 最终配置

### Systemd 服务配置

**`/etc/systemd/system/celery-worker.service`**:
```ini
[Unit]
Description=Celery Worker
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/health-app/backend
Environment="PYTHONPATH=/opt/health-app/backend"
Environment="PYTHONDONTWRITEBYTECODE=1"
ExecStart=/usr/bin/python3 -B -m celery -A app.celery_app worker --loglevel=info
Restart=always
RestartSec=10
StandardOutput=append:/var/log/celery/worker.log
StandardError=append:/var/log/celery/worker.log

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/celery-beat.service`**:
```ini
[Unit]
Description=Celery Beat Scheduler
After=network.target postgresql.service redis.service celery-worker.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/health-app/backend
Environment="PYTHONPATH=/opt/health-app/backend"
Environment="PYTHONDONTWRITEBYTECODE=1"
ExecStart=/usr/bin/python3 -B -m celery -A app.celery_app beat --loglevel=info
Restart=always
RestartSec=10
StandardOutput=append:/var/log/celery/beat.log
StandardError=append:/var/log/celery/beat.log

[Install]
WantedBy=multi-user.target
```

---

## 🔍 验证命令

### 检查服务状态
```bash
systemctl status celery-worker
systemctl status celery-beat
```

### 查看进程
```bash
ps aux | grep celery
```

### 查看日志
```bash
# 实时日志
tail -f /var/log/celery/worker.log
tail -f /var/log/celery/beat.log

# 最近日志
journalctl -u celery-worker -n 50
journalctl -u celery-beat -n 50
```

### 测试任务执行
```bash
# 进入 Python 环境
cd /opt/health-app/backend
python3

# 手动触发任务
>>> from app.tasks.garmin_sync import sync_all_users_garmin
>>> result = sync_all_users_garmin.delay()
>>> print(result.id)
```

---

## 🎯 Garmin 同步优化

### 频率调整
- **原**: 每 30 分钟同步一次 (每天 48 次)
- **新**: 每 6 小时同步一次 (每天 4 次)
- **原因**: 避免频繁请求被 Garmin API 封禁

### Session 缓存
- **TTL**: 24 小时
- **位置**: `backend/app/services/garmin_session_manager.py`
- **策略**: 
  - 自动复用已登录的 Session
  - 失败时自动刷新
  - 智能重试机制

### 请求限流
- **用户间延迟**: 10-60 秒随机延迟
- **每日限额**: 50 次请求/用户
- **错误处理**: 自动重试 + 指数退避

---

## 📝 维护建议

### 日志轮转
```bash
# 添加 logrotate 配置
cat > /etc/logrotate.d/celery << 'EOF'
/var/log/celery/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    missingok
    copytruncate
}
EOF
```

### 监控脚本
```bash
# 检查 Celery 健康状态
cat > /opt/health-app/scripts/check_celery.sh << 'EOF'
#!/bin/bash
if ! systemctl is-active --quiet celery-worker; then
    echo "❌ Celery Worker 未运行"
    systemctl restart celery-worker
fi

if ! systemctl is-active --quiet celery-beat; then
    echo "❌ Celery Beat 未运行"
    systemctl restart celery-beat
fi
EOF

chmod +x /opt/health-app/scripts/check_celery.sh

# 添加到 crontab (每 5 分钟检查一次)
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/health-app/scripts/check_celery.sh") | crontab -
```

---

## ✅ 下一步

1. ✅ **Celery 定时任务已上线** - 完成
2. ⏳ **数据库迁移 SQLite → PostgreSQL** - 已完成 (核心数据已迁移)
3. ⏳ **前端和小程序更新部署** - 待执行

---

## 🚀 快速重启命令

```bash
# 重启所有 Celery 服务
systemctl restart celery-worker celery-beat

# 查看状态
systemctl status celery-worker celery-beat

# 查看日志
tail -f /var/log/celery/worker.log
```

---

**部署时间**: 2026-01-22 11:32  
**服务器**: 39.98.206.178  
**状态**: ✅ 运行正常
