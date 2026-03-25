# AI 驱动的个人健康管理平台

> **Health LLM-Driven** — 多模型协作的智能健康分析与管理系统

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14+-black.svg)](https://nextjs.org)
[![Capacitor](https://img.shields.io/badge/Capacitor-8-blue.svg)](https://capacitorjs.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 项目愿景

**让每个人都拥有专属的 AI 健康顾问团队。**

通过**多 LLM 协作决策**机制，类似顶级医院的多学科会诊（MDT），为用户提供全面、可靠的个性化健康指导。系统整合可穿戴设备、体检报告、日常记录等多维度数据，结合规则引擎与 AI 深度分析，实现从数据采集到健康洞察的全链路智能化。

---

## 重要说明

**本项目目前处于活跃开发阶段，请注意以下事项：**

- **设备支持**：目前主要支持 **Garmin** 和 **Withings** 可穿戴设备，华为和 Apple Watch 的支持仍在开发中
- **开发方式**：本项目主要通过 **Vibe Coding**（AI 辅助编程）开发，代码质量和稳定性持续改进中
- **使用建议**：本项目可作为 Demo 体验，**不建议直接部署到生产环境**
- **风险提示**：如要使用，请自行承担风险，建议在测试环境中充分验证

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.12+, FastAPI, SQLAlchemy, Pydantic, Celery |
| **前端** | Next.js 14, React 18, TypeScript, Tailwind CSS |
| **移动端** | Capacitor 8 (iOS 原生 App) |
| **数据库** | PostgreSQL (生产) / SQLite (开发测试) |
| **缓存/队列** | Redis, Celery Beat |
| **AI/LLM** | OpenAI GPT-4o, Claude, Gemini, Ollama, OpenClaw |
| **向量数据库** | ChromaDB (知识库 RAG) |
| **部署** | PM2 (前端), systemd (后端), Nginx |

---

## 系统架构

```
                        ┌──────────────────┐
                        │   iOS App        │
                        │   (Capacitor)    │
                        └────────┬─────────┘
                                 │
┌──────────────┐        ┌────────▼─────────┐        ┌──────────────────────┐
│   浏览器     │───────▶│   Next.js 前端   │───────▶│   FastAPI 后端       │
│   Web        │        │   50+ 页面       │ /api/* │   80+ API 路由       │
└──────────────┘        │   TypeScript     │        │   66+ 服务模块       │
                        └──────────────────┘        └────────┬─────────────┘
                                                             │
                        ┌────────────────────────────────────┼────────────────┐
                        │                                    │                │
               ┌────────▼────────┐              ┌───────────▼──────┐  ┌──────▼───────┐
               │  多 LLM 分析层  │              │   数据采集层     │  │  异步任务    │
               │  GPT-4o         │              │   Garmin API     │  │  Celery      │
               │  Claude         │              │   Withings API   │  │  定时同步    │
               │  Gemini         │              │   体检报告 PDF   │  │  异常检测    │
               │  OpenClaw       │              │   NFC 快速记录   │  │  推送通知    │
               └─────────────────┘              └──────────────────┘  └──────────────┘
                        │                                    │
               ┌────────▼────────┐              ┌───────────▼──────┐
               │  智能仲裁层     │              │   PostgreSQL     │
               │  交叉验证       │              │   120+ 数据模型  │
               │  共识决策       │              │   Redis 缓存     │
               └─────────────────┘              └──────────────────┘
```

### 请求链路

```
浏览器 → Next.js (localhost:3000)
  → rewrites /api/* → FastAPI (localhost:8000) /api/v1/*

iOS App → 直接访问 https://health-api.executor.life/api/v1/*
```

---

## 核心功能

### 数据采集与整合

| 数据来源 | 采集方式 | 数据类型 |
|---------|---------|---------|
| **Garmin 设备** | OAuth + 凭证自动同步 | 心率、HRV、睡眠、步数、压力、血氧、身体电量 |
| **Withings 设备** | OAuth API 同步 | 体重、体脂、血压 |
| **体检报告** | PDF 智能解析 | 血常规、肝肾功能、血脂、肿瘤标志物、甲状腺功能等 |
| **NFC 碰触** | NFC 标签快速记录 | 饮水、排泄、用药、打卡等快捷操作 |
| **手动录入** | 日常打卡 | 饮食、饮水、体重、血压、情绪、补剂、运动 |

### AI 智能分析

- **多 LLM 协作决策**：GPT-4o / Claude / Gemini 并行分析，智能仲裁层交叉验证形成共识
- **每日健康洞察**：基于前日数据的综合分析与当日建议
- **健康异常预警**：自动检测心率、HRV、睡眠、血氧等指标异常，支持 6 类预警规则
- **健康趋势预测**：时间序列分析，追踪指标变化趋势
- **个性化饮食推荐**：基于健康目标和饮食记录的营养方案
- **食物图像识别**：拍照自动识别食物并估算营养成分
- **健康评分**：多维度量化健康状态
- **健康报告**：定期生成综合健康分析报告

### 健康数据管理

- **体重与体成分**：BMI 计算、体脂率、趋势图表
- **血压监测**：收缩压/舒张压记录与分级
- **睡眠分析**：睡眠质量评分、深浅睡比例
- **心率与 HRV**：静息心率趋势、心率变异性分析
- **运动记录**：步数、距离、卡路里消耗、运动训练
- **排泄追踪**：排泄规律分析、异常提醒
- **情绪记录**：心情日记与情绪趋势
- **用药管理**：药物与补剂的服用记录与提醒
- **疾病追踪**：慢性病管理与多阶段进展追踪

### OpenClaw AI 助手

系统集成 [OpenClaw](https://github.com/nicepkg/openclaw) 智能体平台，提供两种 AI 交互模式：

- **健康助理**：后端构建 12+ 维度健康上下文 → LLM 分析 → Action 解析执行
- **OpenClaw Channel**：纯代理模式，OpenClaw Gateway 全权调度 Skills 自主调用 Health API

**Skills 系统** (`backend/skills/`)：
| Skill | 功能 |
|-------|------|
| health-record | 饮水、体重、血压、打卡、饮食、补剂记录 |
| health-analysis | AI 健康分析、趋势分析、健康评分 |
| health-query | 查询步数、心率、睡眠、体重、血压等指标 |
| multi-model-analyze | 多模型健康数据分析 |
| rhinitis-tracker | 过敏性鼻炎追踪 |

### 社交与激励

- **成就徽章系统**：15 个预置成就，自动检测解锁条件（连续打卡、累计记录等）
- **好友系统**：添加好友、查看健康动态
- **私信与群聊**：健康话题交流
- **PK 挑战**：与好友进行健康指标 PK

### 更多功能

- **语音指令**：语音快捷记录饮水、体重、血压、打卡
- **智能提醒**：基于习惯的个性化健康督促
- **新用户引导**：3 步引导流程（基本信息 → 健康目标 → 打卡模板）
- **快捷操作按钮 (FAB)**：全局悬浮按钮，一键喝水/打卡/记饮食/AI 助手
- **目标管理**：多维度健康目标设定与进度追踪
- **数据导出**：健康数据批量导出
- **知识库 RAG**：基于 ChromaDB 的健康知识检索增强生成
- **环境上下文**：天气、空气质量数据集成（和风天气、AQICN）
- **微信小程序登录**：OAuth 授权登录与账户合并
- **儿童模式**：儿童健康管理 + 主题切换

---

## 项目结构

```
health-llm-driven/
├── backend/                          # FastAPI 后端
│   ├── main.py                       # 入口文件
│   ├── app/
│   │   ├── api/                      # 80+ API 路由模块
│   │   │   ├── main.py               # 路由注册中心
│   │   │   ├── auth.py               # 认证 (JWT)
│   │   │   ├── chat.py               # AI 对话 + 语音指令
│   │   │   ├── openclaw.py           # OpenClaw 代理
│   │   │   ├── health_analysis.py    # 多 LLM 健康分析
│   │   │   ├── nfc.py                # NFC 快速记录
│   │   │   └── ...
│   │   ├── models/                   # 120+ SQLAlchemy 数据模型
│   │   ├── schemas/                  # Pydantic 请求/响应模型
│   │   ├── services/                 # 66+ 业务逻辑模块
│   │   │   ├── chat_service.py       # AI 对话核心服务
│   │   │   ├── health_analysis.py    # 多 LLM 协作分析
│   │   │   ├── anomaly_detection_service.py  # 异常检测引擎
│   │   │   ├── ai/                   # AI 子服务 (食物识别等)
│   │   │   ├── knowledge/            # RAG 知识库
│   │   │   ├── environment/          # 天气/空气质量
│   │   │   └── device_adapters/      # 设备适配器
│   │   ├── tasks/                    # Celery 异步任务
│   │   └── config.py                 # 配置 (Pydantic Settings)
│   ├── skills/                       # OpenClaw Skills 定义
│   ├── tests/                        # pytest 测试套件
│   └── requirements.txt
│
├── frontend/                         # Next.js 14 前端
│   ├── src/
│   │   ├── app/                      # 50+ 页面路由 (App Router)
│   │   │   ├── dashboard/            # 健康仪表盘
│   │   │   ├── ai-assistant/         # AI 助手 (健康助理 + OpenClaw)
│   │   │   ├── analysis/             # 健康分析
│   │   │   ├── diet/                 # 饮食记录
│   │   │   ├── checkin/              # 日常打卡
│   │   │   ├── achievements/         # 成就徽章
│   │   │   ├── friends/              # 社交
│   │   │   ├── onboarding/           # 新手引导
│   │   │   └── ...
│   │   ├── components/               # 通用组件
│   │   ├── contexts/                 # React Context (Auth, Toast, KidsTheme)
│   │   └── services/api.ts           # Axios HTTP 客户端 + JWT 拦截器
│   ├── ios/                          # Capacitor iOS 项目
│   ├── capacitor.config.ts           # Capacitor 配置
│   └── next.config.js                # Next.js 配置 (API 代理)
│
├── docs/                             # 项目文档
├── deploy.sh                         # 自动化部署脚本
└── CLAUDE.md                         # Claude Code 开发指南
```

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- PostgreSQL (生产) / SQLite (开发)
- Redis (可选，用于 Celery 异步任务)

### 后端

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入必要配置 (DATABASE_URL, SECRET_KEY, OPENAI_API_KEY 等)

# 启动开发服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev    # 开发服务器 http://localhost:3000
```

### iOS App

```bash
cd frontend
npm run build:ios    # BUILD_TARGET=native next build && cap copy ios
npm run sync:ios     # cap sync ios
npm run open:ios     # 在 Xcode 中打开
```

### 运行测试

```bash
cd backend
source venv/bin/activate
pytest                                    # 运行全部测试
pytest tests/test_users.py -v             # 运行单个测试文件
pytest --cov=app --cov-report=term-missing  # 测试覆盖率
```

---

## 环境变量

在 `backend/.env` 中配置：

```bash
# 数据库
DATABASE_URL=sqlite:///./health.db          # 开发环境
# DATABASE_URL=postgresql://user:pass@localhost/health  # 生产环境

# JWT
SECRET_KEY=your-secret-key

# LLM 提供商
OPENAI_API_KEY=sk-xxxxx
# ANTHROPIC_API_KEY=sk-ant-xxxxx          # 可选
# GOOGLE_API_KEY=xxxxx                    # 可选

# OpenClaw (可选)
# OPENCLAW_GATEWAY_URL=https://bot.executor.life
# OPENCLAW_API_KEY=your-key
# OPENCLAW_MODEL=openclaw:main

# 设备集成 (可选)
# GARMIN_ENCRYPTION_KEY=your-fernet-key
# WITHINGS_CLIENT_ID=xxx
# WITHINGS_CLIENT_SECRET=xxx

# 外部服务 (可选)
# QWEATHER_API_KEY=xxx                    # 和风天气
# AQICN_API_KEY=xxx                       # 空气质量
# REDIS_URL=redis://localhost:6379/0      # Celery
```

---

## 部署

项目提供自动化部署脚本：

```bash
./deploy.sh -f   # 部署前端
./deploy.sh -b   # 部署后端
./deploy.sh -a   # 部署全部
./deploy.sh -s   # 查看服务状态
./deploy.sh -l   # 查看日志
```

**生产环境架构**：
- 前端：PM2 管理 Next.js 进程 → `health.executor.life`
- 后端：systemd 管理 FastAPI 服务 → `health-api.executor.life`
- 数据库：PostgreSQL
- 反向代理：Nginx + SSL

---

## API 概览

所有 API 路由前缀：`/api/v1`，使用 JWT Bearer Token 认证。

| 模块 | 路由前缀 | 说明 |
|------|---------|------|
| 认证 | `/auth` | 注册、登录、JWT 令牌 |
| 用户 | `/users` | 个人资料、设置 |
| 体重 | `/weight` | 体重记录与趋势 |
| 血压 | `/blood-pressure` | 血压记录与分级 |
| 饮水 | `/water` | 饮水量记录 |
| 饮食 | `/diet` | 饮食记录与营养分析 |
| 打卡 | `/checkin` | 日常健康打卡 |
| 睡眠 | `/sleep` | 睡眠数据记录 |
| 运动 | `/workout` | 运动训练记录 |
| 排泄 | `/excretion` | 排泄记录与规律分析 |
| 情绪 | `/mood` | 情绪记录 |
| 用药 | `/medication` | 药物管理 |
| 补剂 | `/supplements` | 营养补剂记录 |
| 体检 | `/medical-exams` | 体检报告管理 |
| 设备 | `/devices` | Garmin/Withings 设备绑定与同步 |
| NFC | `/nfc` | NFC 快速记录 |
| AI 对话 | `/chat` | AI 健康助理 + 语音指令 |
| OpenClaw | `/openclaw` | OpenClaw 流式对话 |
| 健康分析 | `/health-analysis` | 多 LLM 健康分析 |
| 健康评分 | `/health-score` | 健康评分计算 |
| 健康趋势 | `/health-trend` | 趋势预测 |
| 健康报告 | `/health-report` | 综合健康报告 |
| 异常预警 | `/anomaly` | 健康异常检测 |
| 饮食推荐 | `/diet-recommendation` | AI 饮食方案 |
| 目标 | `/goals` | 健康目标管理 |
| 成就 | `/achievements` | 徽章系统 |
| 好友 | `/friendship` | 好友关系 |
| 私信 | `/direct-message` | 私信 |
| 群聊 | `/group-chat` | 群组聊天 |
| PK | `/pk-challenge` | 健康 PK 挑战 |
| 通知 | `/notification` | 消息推送 |
| 引导 | `/onboarding` | 新手引导 |
| 数据导出 | `/data-export` | 数据导出 |

---

## 文档索引

| 文档 | 说明 |
|-----|------|
| [QUICKSTART.md](./QUICKSTART.md) | 快速上手指南 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 系统架构设计 |
| [TESTING.md](./TESTING.md) | 测试说明 |
| [CLAUDE.md](./CLAUDE.md) | Claude Code 开发指南 |
| [docs/DEPLOY.md](./docs/DEPLOY.md) | 部署文档 |
| [docs/SECURITY.md](./docs/SECURITY.md) | 安全说明 |
| [docs/TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md) | 问题排查 |

---

## 未来规划

- [ ] Apple Watch 数据集成
- [ ] 华为健康 Kit 完整支持
- [ ] 家庭健康管理（多用户关联）
- [ ] 医疗机构数据互通
- [ ] Android App (Capacitor)
- [ ] 更多 OpenClaw Skills 扩展

---

## 贡献

欢迎提交 Issue 和 Pull Request!

---

## 许可证

[MIT License](LICENSE)

---

<div align="center">

**让 AI 成为你的健康守护者**

</div>
