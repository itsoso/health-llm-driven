# 🚀 开始部署 - 从这里开始

> 生成时间: 2026-01-22
> 目标: 在线上服务器部署 PostgreSQL + Redis + Celery

---

## ⚡ 最快方式（推荐）

### 一键远程部署

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
./deploy_to_server.sh
```

**脚本会提示你输入**:
- 服务器 IP 地址
- 服务器用户名（默认 root）
- 项目路径（默认 /opt/health-llm-driven）

然后自动完成所有部署！

---

## 📋 部署流程

### 脚本会自动执行：

1. ✅ 测试 SSH 连接
2. ✅ 上传部署脚本到服务器
3. ✅ 远程执行部署
   - 备份 SQLite 数据库
   - 安装 PostgreSQL 和 Redis
   - 创建数据库和用户
   - 迁移数据
   - 配置 Celery 服务
   - 启动所有服务

**预计时间**: 10-15 分钟

---

## 🎯 其他方式

### 方式 1: 使用 Git

```bash
# 1. 提交代码
git add .
git commit -m "feat: 添加部署脚本"
git push

# 2. 在服务器上拉取
ssh root@your-server
cd /opt/health-llm-driven
git pull
chmod +x backend/scripts/*.sh
bash backend/scripts/production_setup.sh
```

### 方式 2: 手动上传

```bash
# 1. 上传脚本
rsync -avz backend/scripts/ root@your-server:/opt/health-llm-driven/backend/scripts/

# 2. SSH 执行
ssh root@your-server
cd /opt/health-llm-driven/backend
bash scripts/production_setup.sh
```

---

## ✅ 部署后验证

### 1. 检查服务状态

```bash
ssh root@your-server
sudo systemctl status postgresql redis celery-worker celery-beat
```

### 2. 检查数据库

```bash
# 连接数据库（密码在部署输出中）
psql -U health_user -d health_db

# 查看表和数据
\dt
SELECT 'users', COUNT(*) FROM users;
\q
```

### 3. 查看日志

```bash
sudo tail -f /var/log/celery/worker.log
sudo tail -f /var/log/celery/beat.log
```

### 4. 重启应用

```bash
sudo systemctl restart health-app
# 或
pkill -f "uvicorn" && cd /opt/health-llm-driven/backend && nohup python main.py &
```

---

## 📊 定时任务

部署完成后，以下任务将自动运行：

| 任务 | 时间 | 功能 |
|------|------|------|
| 生成每日计划 | 每日 6:00 | AI 生成健康计划 |
| 同步 Garmin | 每小时 :30 | 自动同步数据 |
| 睡眠提醒 | 每日 22:00 | 推送提醒 |
| 周报生成 | 每周一 9:00 | 生成周报 |
| 数据清理 | 每日 3:00 | 清理过期数据 |

---

## 🐛 遇到问题？

### 问题 1: SSH 连接失败

```bash
# 检查连接
ssh -v root@your-server

# 配置 SSH 密钥
ssh-copy-id root@your-server
```

### 问题 2: 权限不足

```bash
# 使用 root 用户
sudo su -
bash /opt/health-llm-driven/backend/scripts/production_setup.sh
```

### 问题 3: 部署失败

查看详细文档：
- `REMOTE_DEPLOY_NOW.md` - 远程部署详细指南
- `PRODUCTION_DEPLOYMENT.md` - 生产环境完整指南

---

## 📚 相关文档

| 文档 | 用途 |
|------|------|
| `START_HERE.md` | 👈 本文档 - 快速开始 |
| `REMOTE_DEPLOY_NOW.md` | 远程部署详细指南 |
| `PRODUCTION_DEPLOYMENT.md` | 生产环境完整指南 |
| `DEPLOY_TO_PRODUCTION.md` | 部署步骤说明 |

---

## 🎯 现在就开始

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
./deploy_to_server.sh
```

**就这么简单！** 🚀

---

## ⚠️ 重要提示

1. **保存数据库密码** - 部署过程会生成并显示
2. **备份数据** - 脚本会自动备份 SQLite
3. **记录日志** - 保存部署输出以备查询
4. **测试功能** - 部署后验证所有功能正常

---

> **立即执行**: `./deploy_to_server.sh`
