# Celery 启动问题修复指南

**问题**: Celery Worker 和 Beat 无法启动  
**原因**: Python 模块缓存和 PYTHONPATH 配置问题

---

## 🔍 问题分析

### 错误1: Worker 错误
```
AttributeError: 'Settings' object has no attribute 'device_encryption_key'
```
**原因**: Python 字节码缓存（`.pyc` 文件）导致读取旧代码

### 错误2: Beat 错误
```
ModuleNotFoundError: No module named 'app'
```
**原因**: PYTHONPATH 未正确设置

---

## ✅ 推荐解决方案：重启服务器

这是最简单、最彻底的解决方案：

```bash
# 1. 重启服务器
ssh root@39.98.206.178 "reboot"

# 2. 等待2分钟后重新连接
sleep 120

# 3. 启动 Celery
ssh root@39.98.206.178 "/opt/health-app/backend/start_celery_no_cache.sh"
```

**为什么重启有效**:
- ✅ 清除所有 Python 进程的内存缓存
- ✅ 清除所有导入的模块缓存
- ✅ 重新加载所有环境变量
- ✅ 确保使用最新的代码文件

---

## 🔧 替代方案：手动修复（不重启）

如果不想重启服务器，可以尝试以下步骤：

### 方案 A: 使用虚拟环境

```bash
ssh root@39.98.206.178 << 'ENDSSH'
cd /opt/health-app/backend

# 1. 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 清理缓存
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true

# 4. 启动 Celery
pkill -f 'celery' 2>/dev/null || true
sleep 2

celery -A app.celery_app worker --loglevel=info --detach \
    --pidfile=/var/run/celery/worker.pid \
    --logfile=/var/log/celery/worker.log

celery -A app.celery_app beat --loglevel=info --detach \
    --pidfile=/var/run/celery/beat.pid \
    --logfile=/var/log/celery/beat.log

# 5. 检查状态
sleep 5
ps aux | grep celery
ENDSSH
```

### 方案 B: 使用 systemd 服务

创建 systemd 服务配置：

```bash
ssh root@39.98.206.178 << 'ENDSSH'
# 1. 创建 Worker 服务
cat > /etc/systemd/system/celery-worker.service << 'EOF'
[Unit]
Description=Celery Worker
After=network.target postgresql.service redis-server.service

[Service]
Type=forking
User=root
WorkingDirectory=/opt/health-app/backend
Environment="PYTHONPATH=/opt/health-app/backend"
Environment="PYTHONDONTWRITEBYTECODE=1"
ExecStart=/usr/bin/python3 -B -m celery -A app.celery_app worker \
    --loglevel=info \
    --logfile=/var/log/celery/worker.log \
    --pidfile=/var/run/celery/worker.pid \
    --detach
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

# 2. 创建 Beat 服务
cat > /etc/systemd/system/celery-beat.service << 'EOF'
[Unit]
Description=Celery Beat
After=network.target postgresql.service redis-server.service

[Service]
Type=forking
User=root
WorkingDirectory=/opt/health-app/backend
Environment="PYTHONPATH=/opt/health-app/backend"
Environment="PYTHONDONTWRITEBYTECODE=1"
ExecStart=/usr/bin/python3 -B -m celery -A app.celery_app beat \
    --loglevel=info \
    --logfile=/var/log/celery/beat.log \
    --pidfile=/var/run/celery/beat.pid \
    --detach
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

# 3. 重新加载 systemd
systemctl daemon-reload

# 4. 启动服务
systemctl start celery-worker celery-beat

# 5. 设置开机自启
systemctl enable celery-worker celery-beat

# 6. 检查状态
systemctl status celery-worker celery-beat
ENDSSH
```

---

## 📋 验证步骤

### 1. 检查进程
```bash
ssh root@39.98.206.178 "ps aux | grep celery"
```

应该看到类似输出：
```
root  1234  celery worker
root  1235  celery beat
```

### 2. 检查日志
```bash
# Worker 日志
ssh root@39.98.206.178 "tail -50 /var/log/celery/worker.log"

# Beat 日志
ssh root@39.98.206.178 "tail -50 /var/log/celery/beat.log"
```

应该看到：
```
[2026-01-22 11:30:00] celery@hostname ready.
[2026-01-22 11:30:00] beat: Starting...
```

### 3. 验证定时任务
```bash
ssh root@39.98.206.178 "tail -f /var/log/celery/beat.log | grep sync-garmin"
```

应该看到：
```
Scheduler: Sending due task sync-garmin-6hourly
```

---

## 🎯 最终推荐

### 立即执行（推荐）

```bash
# 方案1: 重启服务器（最简单、最可靠）
ssh root@39.98.206.178 "reboot"

# 等待2分钟
sleep 120

# 启动 Celery
ssh root@39.98.206.178 "/opt/health-app/backend/start_celery_no_cache.sh"
```

### 或者使用 systemd（更规范）

```bash
# 配置 systemd 服务
# 复制上面"方案 B"的命令执行

# 之后每次重启只需：
ssh root@39.98.206.178 "systemctl restart celery-worker celery-beat"
```

---

## 🔍 故障排查

### 如果重启后仍然失败

1. **检查文件内容**
```bash
ssh root@39.98.206.178 "head -25 /opt/health-app/backend/app/models/device_credential.py | tail -10"
```

应该看到：
```python
ENCRYPTION_KEY = getattr(settings, "device_encryption_key", None) or getattr(settings, "garmin_encryption_key", None)
```

2. **手动测试导入**
```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && PYTHONPATH=/opt/health-app/backend python3 -c 'from app.celery_app import celery_app; print(celery_app)'"
```

应该输出：
```
<Celery health_app at 0x...>
```

3. **检查 Python 路径**
```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && python3 -c 'import sys; print(sys.path)'"
```

4. **清理所有缓存**
```bash
ssh root@39.98.206.178 "cd /opt/health-app/backend && find . -type d -name '__pycache__' | xargs rm -rf && find . -name '*.pyc' -delete"
```

---

## 📝 总结

| 方案 | 难度 | 可靠性 | 时间 | 推荐度 |
|------|------|--------|------|--------|
| 重启服务器 | ⭐ | ⭐⭐⭐⭐⭐ | 3分钟 | ⭐⭐⭐⭐⭐ |
| systemd 服务 | ⭐⭐⭐ | ⭐⭐⭐⭐ | 10分钟 | ⭐⭐⭐⭐ |
| 虚拟环境 | ⭐⭐ | ⭐⭐⭐ | 15分钟 | ⭐⭐⭐ |
| 手动启动 | ⭐ | ⭐⭐ | 5分钟 | ⭐⭐ |

**最终建议**: 
1. 先尝试重启服务器（最简单）
2. 如果还有问题，配置 systemd 服务（最规范）
3. 长期使用 systemd 管理 Celery

---

**创建时间**: 2026-01-22  
**下次更新**: 重启后验证
