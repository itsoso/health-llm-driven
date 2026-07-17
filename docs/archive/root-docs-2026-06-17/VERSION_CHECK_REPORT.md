# 线上系统版本检查报告

**检查时间**: 2026-01-22 11:20  
**服务器**: 39.98.206.178

---

## ✅ 版本状态总览

| 组件 | 线上版本 | 本地版本 | 状态 | 说明 |
|------|---------|---------|------|------|
| Git Commit | ed254bc | ed254bc | ✅ 一致 | 最新提交已同步 |
| 后端代码 | 2026-01-22 11:13 | 2026-01-22 11:14 | ✅ 最新 | Garmin优化已部署 |
| 前端构建 | 2026-01-21 15:19 | - | ⚠️ 需更新 | 构建时间较旧 |
| 小程序代码 | 2026-01-08 12:33 | - | ⚠️ 需更新 | 2周未更新 |

---

## 📊 详细检查结果

### 1. 后端服务 (FastAPI)

#### 1.1 服务状态
```
✅ 运行中
进程: /opt/health-app/backend/venv/bin/python3.12
端口: 127.0.0.1:8000
启动时间: 2026-01-21 (运行中)
```

#### 1.2 关键文件版本
```bash
# Celery 配置
✅ celery_app.py - 2026-01-22 11:13 (已包含6小时同步配置)
   - sync-garmin-6hourly: 每6小时同步 ✅
   - schedule: crontab(hour="*/6", minute=0) ✅

# Session 管理器
✅ garmin_session_manager.py - 2026-01-22 11:13 (已优化)
   - SESSION_TTL_HOURS = 24 ✅
   - MIN_DELAY_SECONDS = 10 ✅
   - MAX_DELAY_SECONDS = 60 ✅
```

#### 1.3 数据库
```
✅ PostgreSQL 14 - 运行中
✅ Redis 6.0.16 - 运行中
✅ 数据已迁移到 PostgreSQL
```

#### 1.4 Celery 定时任务
```
⚠️ 状态未知 - 需要重启才能应用新配置

建议执行:
ssh root@39.98.206.178 "cd /opt/health-app/backend && pkill -f 'celery' && python3 -m celery -A app.celery_app worker --loglevel=info --detach --pidfile=/var/run/celery/worker.pid --logfile=/var/log/celery/worker.log && python3 -m celery -A app.celery_app beat --loglevel=info --detach --pidfile=/var/run/celery/beat.pid --logfile=/var/log/celery/beat.log"
```

---

### 2. 前端服务 (Next.js)

#### 2.1 Web 前端
```
✅ 运行中
进程: next-server (v14.2.35)
端口: 30001
构建时间: 2026-01-21 15:19
```

**状态**: 
- ✅ 服务正常运行
- ⚠️ 构建时间距今 1 天，建议重新构建以获取最新代码

**更新方法**:
```bash
# 1. 拉取最新代码
ssh root@39.98.206.178 "cd /opt/health-app && git pull"

# 2. 重新构建前端
ssh root@39.98.206.178 "cd /opt/health-app/frontend && npm run build"

# 3. 重启服务
ssh root@39.98.206.178 "pm2 restart health-frontend"
```

#### 2.2 小程序
```
⚠️ 代码较旧
最后更新: 2026-01-08 12:33 (14天前)
路径: /opt/health-app/packages/mini-program/
```

**状态**: 
- ⚠️ 小程序代码 2 周未更新
- ⚠️ 可能缺少最近的功能更新和 bug 修复

**更新方法**:
```bash
# 1. 本地构建小程序
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp

# 2. 上传到微信开发者工具
# 使用微信开发者工具打开 dist 目录
# 点击"上传"按钮，提交审核

# 3. 或者同步到服务器
rsync -avz packages/mini-program/ root@39.98.206.178:/opt/health-app/packages/mini-program/
```

---

## 🔍 验证方法

### 1. 验证后端 API
```bash
# 测试健康检查
curl http://39.98.206.178:8000/api/health

# 测试 Garmin 同步配置
curl http://39.98.206.178:8000/api/admin/celery/schedule

# 查看 Session 统计
curl http://39.98.206.178:8000/api/admin/garmin/session-stats
```

### 2. 验证前端
```bash
# 访问 Web 前端
curl -I http://39.98.206.178:30001

# 检查页面标题
curl http://39.98.206.178:30001 | grep -o '<title>.*</title>'
```

### 3. 验证 Celery
```bash
# 查看 Beat 日志（定时任务调度）
ssh root@39.98.206.178 "tail -50 /var/log/celery/beat.log"

# 查看 Worker 日志（任务执行）
ssh root@39.98.206.178 "tail -50 /var/log/celery/worker.log"

# 检查进程
ssh root@39.98.206.178 "ps aux | grep celery"
```

### 4. 验证数据库
```bash
# 连接 PostgreSQL
ssh root@39.98.206.178 "PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost -c 'SELECT COUNT(*) FROM users;'"

# 检查最近的数据
ssh root@39.98.206.178 "PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost -c 'SELECT COUNT(*) FROM garmin_data WHERE record_date >= CURRENT_DATE - INTERVAL 7 days;'"
```

---

## 📋 待更新清单

### 高优先级 🔴

1. **重启 Celery 服务**
   - 目的: 应用新的 6 小时同步配置
   - 影响: Garmin 数据同步频率
   - 预计时间: 2 分钟
   ```bash
   ssh root@39.98.206.178 "/opt/health-app/backend/start_celery.sh"
   ```

### 中优先级 🟡

2. **更新前端构建**
   - 目的: 获取最新的前端代码
   - 影响: 用户界面和功能
   - 预计时间: 5 分钟
   ```bash
   ssh root@39.98.206.178 "cd /opt/health-app && git pull && cd frontend && npm run build && pm2 restart health-frontend"
   ```

### 低优先级 🟢

3. **更新小程序**
   - 目的: 同步最新功能
   - 影响: 小程序用户体验
   - 预计时间: 15 分钟（包括审核）
   ```bash
   # 本地构建并上传
   cd packages/mini-program && npm run build:weapp
   # 使用微信开发者工具上传
   ```

---

## 🎯 推荐操作流程

### 立即执行（5分钟内）

```bash
# 1. 重启 Celery（应用 Garmin 优化）
ssh root@39.98.206.178 "cd /opt/health-app/backend && pkill -f 'celery' && sleep 2 && python3 -m celery -A app.celery_app worker --loglevel=info --detach --pidfile=/var/run/celery/worker.pid --logfile=/var/log/celery/worker.log && python3 -m celery -A app.celery_app beat --loglevel=info --detach --pidfile=/var/run/celery/beat.pid --logfile=/var/log/celery/beat.log"

# 2. 验证 Celery 启动
ssh root@39.98.206.178 "sleep 5 && ps aux | grep celery && tail -20 /var/log/celery/beat.log"
```

### 今天完成（30分钟内）

```bash
# 3. 更新前端
ssh root@39.98.206.178 "cd /opt/health-app && git pull && cd frontend && npm run build"

# 4. 重启前端服务
ssh root@39.98.206.178 "pm2 restart health-frontend"
```

### 本周完成（1小时内）

```bash
# 5. 构建小程序
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp

# 6. 使用微信开发者工具上传
# 打开微信开发者工具 → 选择 dist 目录 → 上传
```

---

## 📈 版本对比详情

### Git 提交历史
```
线上: ed254bc - feat: 修改首页title为'个人健康记录 | 个人助理 个人记录'，www.executor.life重定向到westwetlandtech.com
本地: ed254bc - (相同)

✅ Git 版本一致
```

### 关键配置对比

| 配置项 | 线上值 | 期望值 | 状态 |
|--------|--------|--------|------|
| Garmin 同步频率 | 每6小时 | 每6小时 | ✅ |
| Session 有效期 | 24小时 | 24小时 | ✅ |
| 用户间延迟 | 10-60秒 | 10-60秒 | ✅ |
| PostgreSQL | 运行中 | 运行中 | ✅ |
| Redis | 运行中 | 运行中 | ✅ |
| Celery Worker | ⚠️ 待重启 | 运行中 | ⚠️ |
| Celery Beat | ⚠️ 待重启 | 运行中 | ⚠️ |

---

## 🔔 监控建议

### 每日检查
```bash
# 检查服务状态
ssh root@39.98.206.178 "ps aux | grep -E '(uvicorn|next-server|celery)' | grep -v grep"

# 检查同步日志
ssh root@39.98.206.178 "tail -50 /var/log/celery/worker.log | grep -E '(成功|失败|Garmin)'"
```

### 每周检查
```bash
# 检查数据增长
ssh root@39.98.206.178 "PGPASSWORD='<production-db-secret>' psql -U health_user -d health_db -h localhost -c 'SELECT COUNT(*) as total_records, MAX(record_date) as latest_date FROM garmin_data;'"

# 检查错误日志
ssh root@39.98.206.178 "tail -100 /var/log/celery/worker.log | grep ERROR"
```

---

## 📝 总结

### 当前状态
- ✅ **后端代码**: 最新（包含 Garmin 优化）
- ✅ **数据库**: PostgreSQL 已迁移并运行
- ⚠️ **Celery**: 需要重启以应用新配置
- ⚠️ **前端**: 构建时间较旧，建议更新
- ⚠️ **小程序**: 2周未更新

### 关键操作
1. **立即**: 重启 Celery（应用 Garmin 6小时同步）
2. **今天**: 更新前端构建
3. **本周**: 更新小程序版本

### 风险评估
- 🟢 **低风险**: 后端服务稳定运行
- 🟡 **中风险**: Celery 未重启，新配置未生效
- 🟢 **低风险**: 前端功能正常，但可能缺少最新特性

---

**检查完成时间**: 2026-01-22 11:20  
**下次检查建议**: 2026-01-23 (重启 Celery 后验证)
