# Claude Code 项目说明

本文档为 Claude Code 提供项目部署和开发指南。

## 部署说明

### 服务器信息
- **服务器IP**: `root@39.98.206.178`
- **项目路径**: `/opt/health-app`
- **前端路径**: `/opt/health-app/frontend`
- **后端路径**: `/opt/health-app/backend`

### 部署脚本使用

项目提供自动化部署脚本 `deploy.sh`，配置文件为 `.env-online`。

#### 常用部署命令

```bash
# 部署前端（最常用）
./deploy.sh -f

# 部署后端
./deploy.sh -b

# 部署前端和后端
./deploy.sh -a

# 仅重启服务（不拉取代码）
./deploy.sh -r

# 查看服务状态
./deploy.sh -s

# 查看日志
./deploy.sh -l
```

#### 服务管理

**前端服务**使用 PM2 管理，**后端服务**使用 systemd 管理：

```bash
# 前端服务 (PM2)
pm2 list
pm2 restart health-frontend
pm2 stop health-frontend
pm2 start health-frontend
pm2 logs health-frontend

# 后端服务 (systemd)
systemctl status health-backend
systemctl restart health-backend
systemctl stop health-backend
systemctl start health-backend
```

### 手动部署流程

如果部署脚本不可用，可以手动部署：

#### 前端部署

```bash
ssh root@39.98.206.178
cd /opt/health-app/frontend
git pull
npm install
npm run build
pm2 restart health-frontend
```

#### 后端部署

```bash
ssh root@39.98.206.178
cd /opt/health-app/backend
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart health-backend
```

## 项目结构

```
health-llm-driven/
├── frontend/              # Next.js 前端应用
│   ├── src/
│   │   ├── app/          # 页面路由
│   │   ├── components/   # 通用组件
│   │   └── services/     # API 服务
│   ├── package.json
│   └── next.config.js
├── backend/              # FastAPI 后端应用
│   ├── app/
│   │   ├── api/         # API 路由
│   │   ├── models/      # 数据库模型
│   │   ├── services/    # 业务逻辑
│   │   └── config.py    # 配置文件
│   ├── requirements.txt
│   └── venv/            # 虚拟环境
└── packages/            # 小程序相关
    └── mini-program/    # Taro 小程序
```

## 最近修复

### 导航栏遮挡问题修复 (2026-02-12)

**问题描述**：
- AI 助手页面（`/ai-assistant`）顶部的"历史"和"新建"按钮被固定导航栏遮挡

**根本原因**：
- 导航栏使用 `fixed` 定位，高度为 `h-16` (64px)
- 主内容区域通过 `mt-16` (64px) 推开，为导航栏留出空间
- AI 助手页面使用 `min-h-[calc(100vh-4rem)]` 计算高度，但 `min-h` 允许内容溢出，导致布局计算不精确

**解决方案**：
将 AI 助手页面的容器高度从 `min-h-[calc(100vh-4rem)]` 改为 `h-[calc(100vh-4rem)]`，确保页面精确填充视口减去导航栏的空间。

**修改文件**：
- `frontend/src/app/ai-assistant/page.tsx` (第 172 行)

**部署记录**：
```bash
git commit -m "fix: 修复AI助手页面导航遮挡问题"
git push
./deploy.sh -f  # 部署前端
```

## 开发规范

### Git 提交规范

使用约定式提交（Conventional Commits）：

```
feat: 新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式调整（不影响功能）
refactor: 重构
perf: 性能优化
test: 测试相关
chore: 构建/工具链相关
```

### 代码风格

- 前端：遵循 Next.js 和 React 最佳实践，使用 TypeScript
- 后端：遵循 FastAPI 和 Python PEP 8 规范
- CSS：使用 Tailwind CSS 实用类

## 常见问题

### 1. SSH 连接失败

如果遇到 SSH 连接被关闭的问题：
- 检查是否使用了正确的服务器 IP (`39.98.206.178`)
- 确认 SSH 密钥配置正确
- 检查服务器防火墙设置

### 2. 前端构建失败

常见原因：
- 依赖包版本冲突：删除 `node_modules` 和 `package-lock.json`，重新 `npm install`
- 内存不足：检查服务器内存使用情况
- 环境变量缺失：确保 `.env.local` 配置正确

### 3. 后端服务启动失败

常见原因：
- Python 虚拟环境未激活
- 依赖包未安装：`pip install -r requirements.txt`
- 数据库连接失败：检查数据库服务状态和配置
- 环境变量缺失：确保 `.env` 配置正确

## 环境变量配置

### 前端环境变量 (.env.local)

```env
NEXT_PUBLIC_API_URL=https://health-api.executor.life
```

### 后端环境变量 (.env)

重要环境变量在 `.env-online` 中管理（不提交到 Git），通过部署脚本同步到服务器。

主要包括：
- 数据库连接配置
- API 密钥（OpenAI, Garmin, 高德地图等）
- JWT 密钥
- 和风天气配置

## 监控和日志

### 查看实时日志

```bash
# 前端日志
journalctl -u health-frontend -f

# 后端日志
journalctl -u health-backend -f

# 最近 50 条日志
journalctl -u health-frontend -n 50
journalctl -u health-backend -n 50
```

### PM2 监控（如果使用）

```bash
pm2 list
pm2 logs
pm2 monit
```

## 注意事项

1. **部署前务必提交代码**：部署脚本会自动推送到 GitHub
2. **环境变量安全**：`.env-online` 不应提交到版本控制
3. **数据库备份**：重要更新前备份数据库
4. **测试验证**：部署后访问网站验证功能正常

---

*最后更新：2026-02-12*
