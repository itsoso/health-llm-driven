# 全局架构与模块说明 (Architecture & Modules)

本文档旨在详细描述健康管理系统的全局架构设计、核心模块功能以及数据交互流程。

## 1. 全局架构 (Global Architecture)

本系统采用经典的 **客户端-服务器 (Client-Server)** 架构，并集成了 **大语言模型 (LLM)** 作为核心智能分析引擎。

### 1.1 技术栈
- **前端 (Frontend)**: Next.js (App Router), React, TypeScript, Tailwind CSS, Recharts (数据可视化)。
- **后端 (Backend)**: FastAPI (Python), SQLAlchemy (ORM), Pydantic (数据校验)。
- **数据库 (Database)**: SQLite (开发环境持久化存储)。
- **AI 引擎 (AI Engine)**: OpenAI GPT-4o-mini (通过官方 API 集成)。
- **数据源 (Data Source)**: Garmin Connect (通过 `garminconnect` 社区库)。

### 1.2 数据流向 (Data Flow)
1. **数据采集**: 用户通过脚本或 API 触发 Garmin 数据同步 -> 后端调用 `garminconnect` 库获取数据 -> 解析并存入 SQLite。
2. **规则分析**: 后端业务层根据预设的健康规则（如步数目标、睡眠时长阈值）对原始数据进行初步处理。
3. **AI 智能分析**: 规则分析结果 + 原始数据 + 用户基本信息 -> 组合成 Prompt 发送给 OpenAI -> 接收 JSON 格式的深度见解。
4. **前端展示**: 前端通过 RESTful API 获取处理后的数据和 AI 建议 -> 使用 Recharts 绘制趋势图 -> 展示个性化健康面板。

---

## 2. 模块说明 (Module Descriptions)

### 2.1 后端模块 (Backend: `backend/app/`)

| 目录/文件 | 功能描述 |
| :--- | :--- |
| `api/` | **接口层**: 定义 RESTful API 路由。|
| `api/daily_recommendation.py` | 核心入口，提供结合规则和 AI 的每日健康建议接口。 |
| `api/garmin_connect.py` | 处理 Garmin 登录和手动同步请求。 |
| `models/` | **实体层**: SQLAlchemy 数据库模型，定义表结构。 |
| `schemas/` | **校验层**: Pydantic 模型，定义 API 输入输出的数据格式。 |
| `services/` | **业务层**: 处理核心逻辑。 |
| `services/llm_health_analyzer.py` | **AI 核心**: 负责构建 Prompt、调用 OpenAI 并解析返回的健康见解。 |
| `services/daily_recommendation.py` | **规则引擎**: 负责基于指标阈值的硬规则分析（如步数是否达标）。 |
| `services/data_collection/` | **采集核心**: 包含 Garmin 数据的深度解析逻辑，适配复杂的 API 结构。 |
| `scheduler.py` | **后台任务**: 每隔 2 小时自动同步最近 3 天的 Garmin 数据。 |

### 2.2 前端模块 (Frontend: `frontend/src/`)

| 目录/文件 | 功能描述 |
| :--- | :--- |
| `app/` | **页面路由 (Next.js App Router)**。 |
| `app/garmin/` | 展示 Garmin 原始数据趋势、详细列表（支持分页）和多维度分析图表。 |
| `app/daily-insights/` | **智能面板**: 展示 AI 生成的每日总结、关键洞察、针对性建议及今日目标。 |
| `services/api.ts` | **API 客户端**: 基于 Axios 封装的后端通信模块。 |

### 2.3 脚本与工具 (Scripts: `backend/scripts/`)

| 文件 | 功能描述 |
| :--- | :--- |
| `sync_garmin_full.py` | **全量同步**: 支持同步过去两年的历史数据，带进度显示。 |
| `test_garmin_api.py` | **调试工具**: 用于测试 Garmin 接口连通性并查看原始数据结构。 |
| `create_user.py` | **快速上手**: 快速初始化系统用户及基本身体数据。 |

---

## 3. 核心设计亮点

1. **双重分析架构**: 
   - **硬规则**: 确保基础达标（如：步数 < 5000 必报预警）。
   - **软智能 (LLM)**: 识别潜在联系（如：压力大导致深度睡眠减少，建议通过某种运动缓解）。
2. **数据持久化**: 放弃内存数据库，使用 `sqlite` 文件存储，确保用户同步的多年健康数据在服务重启后依然存在。
3. **防御性解析**: Garmin 接口返回的数据结构极不稳定，系统实现了 `safe_get_nested` 和多重路径匹配逻辑，确保解析过程不会因某个字段缺失而崩溃。

---

## 4. 后续扩展计划
- **离线模型支持**: 增加 Local LLM (如 Ollama) 的支持，保护隐私。
- **体检报告 OCR**: 增加对 PDF/图片格式体检单的自动识别。
- **多设备支持**: 扩展到 Apple Health 和华为健康。

