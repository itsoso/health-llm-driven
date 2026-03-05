# Claude Code 项目说明

本文档为 Claude Code 提供项目部署和开发指南。

## 部署说明

### 服务器信息

#### 健康系统服务器 (阿里云 ECS)
- **服务器IP**: `root@39.98.206.178` (SSH 端口 22)
- **项目路径**: `/opt/health-app`
- **前端路径**: `/opt/health-app/frontend`
- **后端路径**: `/opt/health-app/backend`
- **域名**: `health.executor.life` (前端) / `health-api.executor.life` (API)

#### OpenClaw 服务器
- **服务器IP**: `root@47.237.191.17` (SSH 端口 22222)
- **Gateway 进程**: `openclaw-gateway` (端口 18789, 绑定 loopback)
- **域名**: `bot.executor.life` (Nginx SSL 代理 → 127.0.0.1:18789)
- **配置文件**: `/root/.openclaw/openclaw.json`
- **Nginx 配置**: `/etc/nginx/conf.d/openclaw.conf`

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
├── frontend/                          # Next.js 前端应用
│   ├── src/
│   │   ├── app/                      # 页面路由
│   │   │   ├── achievements/         # 成就徽章页
│   │   │   ├── ai-assistant/         # AI 助手（含语音指令）
│   │   │   ├── onboarding/           # 新手引导向导
│   │   │   └── ...
│   │   ├── components/               # 通用组件
│   │   │   ├── QuickActionButton.tsx  # 快捷操作悬浮按钮 (FAB)
│   │   │   ├── ProtectedRoute.tsx    # 路由守卫（含引导跳转）
│   │   │   └── ...
│   │   ├── contexts/                 # React Context
│   │   └── services/                 # API 服务
│   ├── package.json
│   └── next.config.js
├── backend/                          # FastAPI 后端应用
│   ├── app/
│   │   ├── api/                     # API 路由
│   │   │   ├── achievement.py       # 成就徽章 API
│   │   │   ├── onboarding.py        # 新手引导 API
│   │   │   └── ...
│   │   ├── models/                  # 数据库模型
│   │   │   ├── achievement.py       # BadgeDefinition + UserBadge
│   │   │   ├── anomaly_alert.py     # 健康异常预警
│   │   │   └── ...
│   │   ├── services/                # 业务逻辑
│   │   │   ├── achievement_service.py       # 成就计算与授予
│   │   │   ├── anomaly_detection_service.py # 异常检测引擎
│   │   │   ├── voice_command_service.py     # 语音指令解析
│   │   │   └── ...
│   │   ├── tasks/                   # Celery 异步任务
│   │   └── config.py               # 配置文件
│   ├── tests/                       # 单元测试（88+）
│   ├── requirements.txt
│   └── venv/                        # 虚拟环境
└── packages/                        # 小程序相关
    └── mini-program/                # Taro 小程序
```

## OpenClaw 集成架构

### OpenClaw Channel 代理模式 (2026-03-05)

系统作为 OpenClaw 的一个 Channel（类似飞书/钉钉集成），在 AI 助手页面新增独立的 OpenClaw tab。

**架构链路**:
```
前端 /ai-assistant (OpenClaw tab)
  → POST /api/v1/openclaw/stream (SSE)
    → FastAPI 后端 (39.98.206.178)
      → HTTPS POST bot.executor.life/v1/chat/completions
        → OpenClaw Gateway (47.237.191.17:18789, loopback)
          → Anthropic Claude Max
```

**配置项** (`.env-online`):
```
OPENCLAW_GATEWAY_URL=https://bot.executor.life
OPENCLAW_API_KEY=e89ad0759bb523b9cc56dbd52fb7993f86f545f19d6d4273
OPENCLAW_MODEL=openclaw:main
```

**API 端点**:
| 端点 | 方法 | 说明 |
|------|------|------|
| `/openclaw/stream` | POST | 流式对话 (SSE) |
| `/openclaw/conversations` | GET | 对话列表 |
| `/openclaw/conversations/{id}` | GET | 对话详情 + 消息 |
| `/openclaw/conversations/{id}` | DELETE | 删除对话 |

**关键文件**:
| 文件 | 说明 |
|------|------|
| `backend/app/models/openclaw.py` | OpenClawConversation + OpenClawMessage 模型 |
| `backend/app/services/openclaw_service.py` | Gateway 流式调用 + 会话管理 |
| `backend/app/api/openclaw.py` | 4 个 API 端点 |
| `frontend/src/app/ai-assistant/page.tsx` | OpenClaw tab UI + 独立 API 路由 |
| `frontend/src/services/api.ts` | openclawApi 服务对象 |

**与健康助理的区别**:
- 健康助理: 后端构建 12+ 健康上下文 → OpenClaw API → Action 解析执行
- OpenClaw Channel: 纯粹代理 → OpenClaw Gateway 全权处理 → Skills 自主调用 Health API

**诊断要点**:
- Gateway 连通性: `curl https://bot.executor.life/v1/chat/completions -H 'Authorization: Bearer {key}'`
- Gateway 进程: `ssh -p 22222 root@47.237.191.17 "ps aux | grep openclaw"`
- Gateway 端口: `ssh -p 22222 root@47.237.191.17 "ss -tlnp | grep 18789"`
- Nginx 配置: `ssh -p 22222 root@47.237.191.17 "cat /etc/nginx/conf.d/openclaw.conf"`
- 后端日志: `ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager | grep openclaw"`

---

## 最近更新

### 第一梯队 5 大新功能 (2026-03-03)

本次更新一次性新增 5 个核心功能，共 **88 个后端单元测试**全部通过。

#### 1. A2 — 健康异常检测与预警

**功能**：Garmin 同步后 + 每日定时自动分析健康指标，发现异常时推送预警通知。

**异常阈值**：
| 指标 | 条件 | 严重度 |
|------|------|--------|
| 静息心率 RHR | >15% 高于 7 天均值 | warning |
| HRV | >20% 低于 7 天均值 或 status="low" | warning |
| 睡眠评分 | <50 (critical) 或连续 3 天 <60 (warning) | warning/critical |
| 压力 | >75 连续 2+ 天 | warning |
| 血氧 SpO2 | <95% | critical |
| Body Battery | 晨起 <30 | info |

**新增文件**：
- `backend/app/models/anomaly_alert.py` — AnomalyAlert 模型（唯一约束 user_id+alert_type+date）
- `backend/app/services/anomaly_detection_service.py` — 6 个检查方法 + send_alerts（critical 绕过静默时段）
- `backend/tests/test_anomaly_detection.py` — 23 个测试

**修改文件**：
- `backend/app/models/__init__.py` — 注册新模型
- `backend/app/tasks/garmin_sync.py` — 同步完成后触发异常检测
- `backend/app/tasks/notifications.py` — 新增 `daily_anomaly_check` 每日任务
- `backend/app/celery_app.py` — beat schedule 每晚 23:00 执行

#### 2. B4 — 语音指令直接执行

**功能**：语音转文字后，先尝试匹配快捷指令（饮水、体重、血压、打卡），匹配成功直接执行动作，不走 AI 对话。

**支持指令**：
| 模式 | 示例 | 动作 |
|------|------|------|
| 饮水 | "喝了一杯水"、"喝水250" | 记录饮水 |
| 体重 | "体重72公斤"、"72.5kg" | 记录体重 |
| 血压 | "血压120/80" | 记录血压 |
| 打卡 | "跑步打卡"、"打卡俯卧撑" | 快速打卡 |

**新增文件**：
- `backend/app/services/voice_command_service.py` — 正则匹配 + DB 记录
- `backend/app/schemas/voice_command.py` — 请求/响应模型
- `backend/tests/test_voice_command.py` — 28 个测试

**修改文件**：
- `backend/app/api/chat.py` — 新增 `POST /chat/voice-command` 端点
- `frontend/src/app/ai-assistant/page.tsx` — 语音 onstop 先尝试快捷指令
- `frontend/src/services/api.ts` — 新增 `voiceCommand` 方法

#### 3. C4 — 快捷操作悬浮按钮 (FAB)

**功能**：全局悬浮按钮，点击展开快捷操作菜单。

**操作项**：💧喝水+250ml、✅打卡、🍽️记饮食、🤖AI助手

**新增文件**：
- `frontend/src/components/QuickActionButton.tsx` — FAB 组件

**修改文件**：
- `frontend/src/app/layout.tsx` — 集成 QuickActionButton

#### 4. C3 — 新用户引导流程

**功能**：新注册用户首次登录后，引导完成 3 步：基本信息 → 健康目标 → 选择打卡模板。

**API 端点**：
- `GET /onboarding/status` — 引导状态
- `POST /onboarding/step1` — 基本信息（身高/体重/性别/生日）
- `POST /onboarding/step2` — 健康目标（步数/睡眠/饮水/运动）
- `POST /onboarding/complete` — 完成引导（可选初始化打卡模板）
- `POST /onboarding/skip` — 跳过

**新增文件**：
- `backend/app/api/onboarding.py` — 5 个端点
- `backend/app/schemas/onboarding.py` — 请求/响应模型
- `frontend/src/app/onboarding/page.tsx` — 3 步向导页面
- `backend/tests/test_onboarding.py` — 18 个测试

**修改文件**：
- `backend/app/models/user.py` — User 增加 `onboarding_completed` 字段
- `backend/app/schemas/auth.py` — UserResponse 增加 `onboarding_completed`
- `backend/app/api/auth.py` — user_to_response 返回 onboarding_completed
- `frontend/src/contexts/AuthContext.tsx` — User interface 增加字段
- `frontend/src/components/ProtectedRoute.tsx` — 未完成引导时跳转 `/onboarding`
- `frontend/src/services/api.ts` — 新增 `onboardingApi`

#### 5. D1 — 成就徽章系统

**功能**：15 个预置成就徽章，自动检测解锁条件，展示进度和已解锁徽章。

**徽章分类**：
| 类别 | 徽章 | 条件 |
|------|------|------|
| 连续 streak | 三天坚持/一周不断/月度达人/百日不辍 | 连续打卡 3/7/30/100 天 |
| 活动 activity | 饮水新手/达人/王者 | 累计饮水 50/100/500 次 |
| 活动 activity | 迈出第一步/百公里/马拉松 | 累计跑步 10/100/500 km |
| 里程碑 milestone | 第一次打卡/AI初体验 | 首次操作 |
| 里程碑 milestone | 打卡百次/五百/饮食记录员 | 累计次数 |

**API 端点**：
- `GET /achievements/definitions` — 所有徽章定义（公开）
- `GET /achievements/me` — 用户成就 + 进度
- `POST /achievements/check` — 手动触发检查

**新增文件**：
- `backend/app/models/achievement.py` — BadgeDefinition + UserBadge + 15 种子数据
- `backend/app/services/achievement_service.py` — 进度计算 + 自动授予
- `backend/app/api/achievement.py` — 3 个端点
- `frontend/src/app/achievements/page.tsx` — 成就页面（分类 tab + 网格 + 进度条 + 详情弹窗）
- `backend/tests/test_achievement.py` — 19 个测试

**修改文件**：
- `backend/app/api/checkin.py` — 打卡成功后触发成就检查
- `backend/app/api/main.py` — 注册 achievement router
- `frontend/src/services/api.ts` — 新增 `achievementApi`

#### 测试验证

```bash
cd backend && python -m pytest tests/test_anomaly_detection.py tests/test_voice_command.py tests/test_onboarding.py tests/test_achievement.py -v
# 88 passed
```

#### 部署

```bash
./deploy.sh -a  # 部署前端和后端
```

---

### 健康顾问数据增强 (2026-02-12)

**新增功能**：
健康顾问现在可以基于用户的历史数据提供更精准的建议

**新增数据分析**：
1. **运动数据分析**
   - 最近 7 天：平均步数、总步数、平均消耗卡路里、平均活动时间
   - 最近 30 天：同上统计维度

2. **饮食数据分析**
   - 最近 3 天：每天详细营养摄入（卡路里、蛋白质、碳水、脂肪）+ 主要食物
   - 最近 7 天：平均每日营养摄入统计

3. **打卡数据分析**
   - 最近 7 天：按打卡模板分组，显示完成天数和平均值
   - 最近 30 天：同上统计维度

**技术实现**：
- 文件：`backend/app/services/chat_service.py`
- 从 GarminData、DietRecord、CheckinRecord 表中提取历史数据
- 数据自动注入到 AI 对话的系统提示中
- AI 可基于这些数据给出个性化的运动、饮食、打卡建议

**使用场景**：
用户可以在健康顾问页面询问：
- "根据我最近的运动情况，今天应该如何安排运动？"
- "我最近的饮食营养搭配怎么样？"
- "我的打卡完成情况如何？"

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

*最后更新：2026-03-05*
