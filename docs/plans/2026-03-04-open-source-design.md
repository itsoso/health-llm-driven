# 健康管理系统开源设计文档

> **目标**：将现有健康管理系统开源，让每个用户都能拥有自己的智能健康管理助理。

**日期**：2026-03-04

---

## 1. 项目概览

### 1.1 愿景

类似 OpenClaw 的开源模式，提供一套完整的 AI 驱动健康管理系统，用户可以自部署或使用托管版本。

### 1.2 目标用户

- **开发者**：自部署、自定义、贡献代码
- **普通用户**：通过托管版或 Docker 一键部署快速使用

### 1.3 核心决策

| 决策项 | 选择 |
|--------|------|
| 方案 | 渐进式重构（在现有代码基础上逐步抽象） |
| LLM 后端 | 多 LLM 适配层（OpenAI/Claude/Ollama/本地模型） |
| 部署方式 | Docker Compose 一键启动 |
| 设备集成 | 插件化适配器（Garmin + Apple Health + Google Fit） |
| 商业模式 | 开源核心 + 云服务增值（类 Supabase/GitLab） |
| 开源协议 | MIT 或 Apache 2.0 |

---

## 2. 项目结构

```
open-health/
├── docker-compose.yml          # 一键启动
├── docker-compose.dev.yml      # 开发环境
├── .env.example                # 环境变量模板（完整注释）
├── Dockerfile.backend          # 后端镜像
├── Dockerfile.frontend         # 前端镜像
├── LICENSE                     # MIT / Apache 2.0
├── README.md                   # 项目介绍 + 快速开始
├── docs/
│   ├── quickstart.md           # 5 分钟上手
│   ├── configuration.md        # 完整配置指南
│   ├── llm-providers.md        # LLM 提供商配置
│   ├── device-providers.md     # 设备适配器开发指南
│   └── api-reference.md        # API 文档
├── backend/                    # FastAPI 后端
│   └── app/
│       └── services/
│           ├── llm/            # LLM 适配层（新）
│           │   ├── base.py
│           │   └── providers/
│           │       ├── openai_provider.py
│           │       ├── ollama_provider.py
│           │       └── openclaw_provider.py
│           └── devices/        # 设备适配器（新）
│               ├── base.py
│               └── providers/
│                   ├── garmin_provider.py
│                   ├── apple_health_provider.py
│                   └── google_fit_provider.py
├── frontend/                   # Next.js 前端
└── plugins/                    # 社区插件目录（Phase 2）
```

---

## 3. LLM 适配层

### 3.1 现状分析

当前系统有 10+ 个服务通过两种模式调用 AI：

| 调用模式 | 使用服务 | 方式 |
|---------|---------|------|
| OpenClaw Chat | chat_service, smart_plan, ai_insights, period_goal | HTTP POST `/chat/completions` |
| OpenAI SDK | health_analysis, food_recognition, vision, workout_analysis, llm_health_analyzer | `openai.ChatCompletion.create()` |
| OpenClaw Analyze | post_run_analyze, health_trend | HTTP POST + 轮询（多模型） |

### 3.2 统一 Provider 接口

```python
# backend/app/services/llm/base.py
class LLMProvider(ABC):
    """所有 LLM 提供商的基类"""

    @abstractmethod
    async def chat(self, messages, model=None, temperature=0.7,
                   max_tokens=2000, stream=False) -> str | AsyncIterator:
        """单轮/多轮对话"""

    @abstractmethod
    async def chat_with_vision(self, messages, images: list[str],
                               model=None) -> str:
        """视觉理解（食物识别、图片分析）"""

    @abstractmethod
    async def multi_model_analyze(self, prompt, models=None) -> dict:
        """多模型并行分析（可选，非所有 Provider 支持）"""
```

### 3.3 内置 Provider

- **OpenAIProvider**：支持 OpenAI / DeepSeek / vLLM / LM Studio 等任何 OpenAI 兼容 API
- **OllamaProvider**：本地 Ollama 模型
- **OpenClawProvider**：保留现有 OpenClaw 高级功能（多模型分析）

### 3.4 配置方式

```env
LLM_PROVIDER=openai          # openai | ollama | openclaw
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_VISION_MODEL=gpt-4o
MULTI_MODEL_ENABLED=false
```

### 3.5 迁移策略

所有现有服务改为注入 `LLMProvider`，不再直接调用 OpenAI SDK 或 OpenClaw HTTP。`multi_model_analyze` 设为可选，Provider 不支持时 fallback 为单模型。

---

## 4. 设备集成插件系统

### 4.1 标准化数据格式

```python
@dataclass
class HealthDataPoint:
    metric: str              # "steps", "heart_rate", "sleep_score", "workout"
    value: float
    unit: str                # "steps", "bpm", "score", "minutes"
    timestamp: datetime
    source: str              # "garmin", "apple-health"
    raw_data: dict | None    # 原始设备数据（可选）
```

### 4.2 DeviceProvider 接口

```python
class DeviceProvider(ABC):
    name: str
    display_name: str
    supported_metrics: list
    auth_type: str           # "oauth2", "api_key", "webhook", "local_import"

    @abstractmethod
    async def authorize(self, user_id, callback_url) -> str:

    @abstractmethod
    async def handle_callback(self, user_id, auth_code) -> bool:

    @abstractmethod
    async def sync_data(self, user_id, start_date, end_date) -> list[HealthDataPoint]:

    @abstractmethod
    async def get_sync_status(self, user_id) -> dict:
```

### 4.3 设备注册

```env
ENABLED_DEVICES=garmin,manual
GARMIN_CONSUMER_KEY=xxx
GARMIN_CONSUMER_SECRET=xxx
```

### 4.4 路线图

- **Phase 1**：GarminProvider（迁移现有）+ ManualProvider
- **Phase 2**：AppleHealthProvider + GoogleFitProvider
- **社区扩展**：Fitbit、Samsung Health 等

---

## 5. Docker Compose 部署

### 5.1 服务架构

```yaml
services:
  frontend:     # Next.js (port 3000)
  backend:      # FastAPI (port 8000)
  db:           # PostgreSQL 16
  redis:        # Redis 7
  celery-worker: # Celery Worker
  celery-beat:   # Celery Beat（定时任务）
```

### 5.2 一键启动

```bash
git clone https://github.com/xxx/open-health.git
cd open-health
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY
docker compose up -d
# 打开 http://localhost:3000
```

### 5.3 数据库初始化

- 首次启动自动执行 `alembic upgrade head`
- 内置种子数据（成就徽章定义、默认打卡模板）

---

## 6. 敏感信息清理

需要移除的硬编码：

| 文件 | 内容 | 处理 |
|------|------|------|
| `openclaw_analyze.py` | `oc-kuaishou-2026` API Key | → 环境变量 |
| `openclaw_analyze.py` | `baokun` User ID | → 环境变量 |
| `openclaw_analyze.py` | `base.executor.life` URL | → 环境变量 |
| `config.py` | `bot.executor.life` URL | → 已是环境变量，改默认值 |
| 各服务 | 硬编码模型名 `gpt-4o-mini` | → 走 LLM Provider |

---

## 7. 功能精简（v0.1 Alpha）

### 保留核心模块

- 用户认证（注册/登录/微信）
- 健康打卡系统（2.0）
- 饮食记录（含拍照识别）
- 运动追踪（Garmin 同步 + 手动）
- 体重/血压/饮水记录
- AI 健康对话（流式）
- 健康趋势预测
- 每日推荐
- 成就徽章
- 新手引导

### 可选模块（通过环境变量启用/禁用）

- 社交功能（好友/PK/私信/群聊）
- 情绪追踪
- 用药管理
- 女性健康
- 数字孪生

### 移除/隐藏（过于定制化）

- 安全资产布局（security_life）
- 单词本（vocabulary）
- 儿童计划（kids_plan）
- 儿童狗狗空间（kids_pet）

---

## 8. 发布路线图

| 阶段 | 版本 | 内容 |
|------|------|------|
| Phase 1 | v0.1 Alpha | Docker Compose + LLM 适配层 + 核心功能 + 敏感信息清理 |
| Phase 2 | v0.5 Beta | 设备插件系统 + 文档完善 + CI/CD + 模块启用/禁用 |
| Phase 3 | v1.0 正式版 | 托管版 SaaS + 社区贡献指南 + 多语言 i18n |

---

## 9. 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Next.js 14 + React + TypeScript + Tailwind CSS |
| 后端 | FastAPI + SQLAlchemy + Pydantic v2 |
| 数据库 | PostgreSQL 16（生产）/ SQLite（开发可选） |
| 缓存 | Redis 7 |
| 异步任务 | Celery + Redis |
| AI | 多 LLM Provider（OpenAI/Ollama/OpenClaw） |
| 部署 | Docker Compose |
| CI/CD | GitHub Actions（待建） |
