# 🧬 AI 驱动的个人健康管理

> **Health LLM-Driven System** — 多模型协作的智能健康分析平台

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14+-black.svg)](https://nextjs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 🎯 项目愿景

**让每个人都拥有专属的 AI 健康顾问团队。**

我们相信，真正有价值的健康建议不应该来自单一算法，而应该是多个专业视角的综合研判。就像顶级医院的多学科会诊（MDT），本系统通过**多 LLM 协作决策**机制，为用户提供更全面、更可靠的个性化健康指导。

---

## 💡 核心理念

### 1. 多模型协作决策 (Multi-LLM Collaborative Decision)

```
┌─────────────────────────────────────────────────────────────────┐
│                      用户健康数据输入                             │
│  (Garmin 可穿戴设备 / 体检报告 PDF / 日常打卡 / 饮食记录)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     多 LLM 并行分析层                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   GPT-4o    │  │   Claude    │  │   Gemini    │   ...        │
│  │  (深度推理)  │  │  (综合分析)  │  │  (快速响应)  │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     智能仲裁层 (Arbitration)                     │
│  • 交叉验证各模型观点                                             │
│  • 识别共识与分歧点                                               │
│  • 综合权衡形成最终建议                                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     个性化健康建议输出                            │
│  (睡眠优化 / 运动处方 / 饮食调整 / 风险预警 / 就医建议)             │
└─────────────────────────────────────────────────────────────────┘
```

**为什么需要多 LLM？**

| 单一模型的局限 | 多模型协作的优势 |
|--------------|----------------|
| 存在模型特定的偏见和盲区 | 多视角交叉验证，减少误判 |
| 对某些领域知识覆盖不足 | 不同模型擅长不同领域，互补增强 |
| 输出可能过于自信或保守 | 通过分歧检测识别不确定性 |
| 单点故障风险 | 冗余设计，提高系统可靠性 |

### 2. 数据驱动的个性化 (Data-Driven Personalization)

- **全维度数据整合**：体检报告 + 可穿戴设备 + 日常记录 = 完整健康画像
- **时间序列分析**：追踪趋势变化，而非孤立的单点数据
- **个人基线建立**：了解"你的正常"，而非泛化的参考范围

### 3. 规则引擎 + AI 双轨制 (Hybrid Intelligence)

```
智能分析 = 规则引擎（确定性逻辑） + LLM（模糊推理）
         │                      │
         ├─ 血糖超标判定        ├─ 综合症状关联分析
         ├─ 心率异常预警        ├─ 个性化原因推断
         └─ 睡眠目标达成        └─ 生活方式建议生成
```

- **规则引擎**：处理有明确标准的判断（如血压分级、BMI 评估）
- **LLM 增强**：处理需要综合推理的复杂场景（如多指标关联分析）
- **两者协同**：规则保证基础准确性，AI 提供深度洞察

---

## 🏗️ 系统架构

```
health-llm-driven/
├── backend/                    # 后端服务 (FastAPI + Python)
│   ├── app/
│   │   ├── api/               # RESTful API 接口
│   │   ├── models/            # SQLAlchemy 数据模型
│   │   ├── schemas/           # Pydantic 数据校验
│   │   └── services/          # 业务逻辑 & AI 分析服务
│   │       ├── daily_recommendation.py   # 规则引擎 + AI 建议
│   │       ├── health_analysis.py        # 多 LLM 健康分析
│   │       ├── llm_health_analyzer.py    # LLM 调用封装
│   │       ├── exam_packages.py          # 体检套餐标准化
│   │       └── pdf_parser.py             # 体检报告 PDF 解析
│   ├── scripts/               # 数据同步与维护脚本
│   └── tests/                 # 测试套件
│
├── frontend/                   # 前端应用 (Next.js + TypeScript)
│   └── src/
│       ├── app/               # 页面路由
│       │   ├── daily-insights/    # 每日智能分析
│       │   ├── medical-exams/     # 体检报告管理
│       │   ├── garmin/            # Garmin 数据同步
│       │   ├── goals/             # 目标管理
│       │   └── ...
│       ├── components/        # 可复用组件
│       └── services/          # API 调用封装
│
└── docs/                       # 项目文档
```

---

## ✨ 核心功能

### 📊 数据采集与整合

| 数据来源 | 采集方式 | 数据类型 |
|---------|---------|---------|
| **Garmin 可穿戴设备** | API 自动同步 | 心率、HRV、睡眠、步数、压力、身体电量 |
| **体检报告** | PDF 智能解析 | 血常规、肝肾功能、血脂、肿瘤标志物、甲状腺功能等 |
| **日常记录** | 手动打卡 | 饮食、饮水、补剂、运动、户外时间 |
| **体重血压** | 手动录入 | 体重趋势、血压监测 |

### 🤖 AI 智能分析

- **每日健康洞察**：基于昨日数据的综合分析和今日建议
- **趋势预警**：识别指标异常变化趋势
- **关联分析**：发现不同健康指标间的潜在关联
- **个性化建议**：基于个人数据的定制化改善方案

### 🎯 目标管理

- **多维度目标**：饮食、运动、睡眠、体重等
- **分级规划**：年度 → 月度 → 周度 → 每日
- **进度追踪**：可视化完成情况
- **智能提醒**：基于习惯的个性化督促

### 🧪 体检套餐支持

系统内置丰富的体检项目模板，支持快速录入：

- 肝肾脂糖电解质测定（生化全套）
- 糖化血红蛋白测定（HbA1c）
- 心肌酶谱常规检查
- 甲状腺功能全套（TT3/TT4/TSH/FT3/FT4/TPOAb/TgAb）
- 肿瘤标志物套餐（男/女）
- 免疫功能 T 细胞亚型分析（10CD）
- 25羟维生素D 测定
- 更多...

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- SQLite（开发）/ PostgreSQL（生产）

### 一键部署（生产环境）

详细部署指南请参考 [部署文档](./docs/DEPLOY.md)。

```bash
# 克隆代码
git clone https://github.com/itsoso/health-llm-driven.git
cd health-llm-driven

# 后端设置
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 初始化数据库
sqlite3 health.db < ../scripts/init_database.sql

# 创建管理员用户
python scripts/create_user.py --email admin@example.com --password yourpassword --admin

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 等配置

# 启动后端
./start-server.sh

# 前端设置（新终端）
cd ../frontend
npm install
npm run build
npm start
```

### 本地开发

```bash
# 后端（热重载）
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 前端（热重载）
cd frontend
npm run dev
```

### 配置 LLM

在 `backend/.env` 中配置：

```bash
# 数据库
DATABASE_URL=sqlite:///./health.db

# JWT 密钥（生产环境请更换）
SECRET_KEY=your-super-secret-key-change-in-production

# OpenAI API（用于 AI 健康分析）
OPENAI_API_KEY=sk-xxxxx

# 可选：OpenAI 代理（中国大陆用户可能需要）
# OPENAI_BASE_URL=https://api.openai-proxy.com/v1

# 可选：Garmin 凭证加密密钥
# GARMIN_ENCRYPTION_KEY=your-fernet-key

# 可选：配置多个 LLM 提供商
# ANTHROPIC_API_KEY=sk-ant-xxxxx
# GOOGLE_API_KEY=xxxxx
```

### 数据库迁移

如果从旧版本升级，需要执行数据库迁移：

```bash
# 查看可用迁移
ls scripts/migrations/

# 执行迁移（以添加运动训练表为例）
sqlite3 backend/health.db < scripts/migrations/20260107_02_create_workout_records.sql
```

---

## 📖 文档索引

| 文档 | 说明 |
|-----|------|
| [架构设计](./ARCHITECTURE.md) | 系统整体架构与模块设计 |
| [运行指南](./RUN.md) | 详细部署与运行说明 |
| [Garmin 同步](./backend/GARMIN_SYNC_GUIDE.md) | 可穿戴设备数据同步 |
| [目标管理](./backend/GOAL_MANAGEMENT_GUIDE.md) | 健康目标设置与追踪 |
| [测试说明](./backend/tests/README.md) | 测试运行与覆盖率 |

---

## 🔮 未来规划

- [ ] **更多 LLM 集成**：支持 Claude、Gemini、本地模型等
- [ ] **多模型投票机制**：实现真正的多 LLM 共识决策
- [ ] **Apple Health 集成**：支持 iOS 生态数据源
- [ ] **家庭健康管理**：支持多用户家庭账户
- [ ] **医疗机构对接**：与医院/体检中心数据互通
- [ ] **移动端 App**：React Native 跨平台应用

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

[MIT License](LICENSE) - 自由使用，但请保留原作者信息。

---

<div align="center">

**让 AI 成为你的健康守护者** 🏥💪

</div>
