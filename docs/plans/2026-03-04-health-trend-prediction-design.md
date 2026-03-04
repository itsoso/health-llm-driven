# 健康趋势预测系统设计

日期：2026-03-04

## 概述

基于历史健康数据，通过 OpenClaw 多模型 LLM 分析，自动生成健康趋势报告和预测。覆盖体重/体脂、睡眠质量、运动表现、综合健康四个维度。支持 Dashboard 嵌入、每日推送、Chatbot 查询三种展示渠道。

## 方案选择

**方案A：纯 LLM 分析**（已选定）

每天定时聚合 7/14/30 天历史数据，通过 OpenClaw 多模型分析生成趋势报告。利用现有 `OpenClawAnalyzeClient` + `AIInsightsService` 的数据聚合能力。

选择理由：开发快，可解释性强，自然语言输出用户友好，充分复用现有基础设施。

## 数据聚合引擎

### 聚合维度

| 维度 | 数据来源 | 聚合周期 | 关键指标 |
|------|---------|---------|---------|
| 体重/体脂 | `WeightRecord` | 7/14/30天 | 体重变化量、变化率、BMI |
| 睡眠质量 | `GarminData` (sleep) | 7/14天 | 睡眠评分、深睡时长、规律性 |
| 运动表现 | `GarminData` (activity) | 7/14/30天 | 步数、跑步配速/距离、卡路里 |
| 综合健康 | `HealthScoreService` | 7/14/30天 | 各维度评分、整体趋势 |

### 分析流程

```
定时触发(22:00) → 聚合历史数据 → 构造 Prompt → OpenClaw 多模型分析 → 解析结果 → 存储到 HealthTrendReport → 推送通知(次日08:00)
```

### Prompt 设计

为每个维度构造结构化 prompt，包含：
- 原始数据序列（如最近30天的每日体重）
- 用户目标（如目标体重65kg）
- 要求输出：趋势判断（improving/declining/stable）、关键洞察（2-3条）、行动建议（2-3条）、风险提醒

## 数据模型

### 新增表：`health_trend_reports`

```python
class HealthTrendReport(Base):
    __tablename__ = "health_trend_reports"

    id: int (PK)
    user_id: int (FK → users)
    report_date: date          # 报告日期
    dimension: str             # "weight" | "sleep" | "exercise" | "overall"
    period: str                # "7d" | "14d" | "30d"

    # 趋势结果
    trend_direction: str       # "improving" | "declining" | "stable"
    raw_data_summary: JSON     # 原始数据摘要（图表用）
    insights: JSON             # LLM 生成的洞察列表
    suggestions: JSON          # LLM 生成的建议列表
    risk_alerts: JSON          # 风险提醒（可为空）
    full_report: text          # LLM 完整报告文本

    # OpenClaw 分析元数据
    openclaw_batch_id: str
    model_results: JSON

    created_at: datetime

    # 唯一约束
    UniqueConstraint(user_id, report_date, dimension, period)
```

### 存储策略
- 每日生成 4 维度 × 1 周期(7d) = 4 条记录
- 每周额外生成 14d/30d 报告
- 保留 90 天历史，超期自动清理

## API 端点

路由前缀：`/api/v1/health-trends`

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health-trends/latest` | GET | 获取最新一期各维度趋势概览 |
| `/health-trends/{dimension}` | GET | 指定维度详细报告，`?period=7d\|14d\|30d` |
| `/health-trends/history` | GET | 历史报告列表，支持分页 |
| `/health-trends/generate` | POST | 手动触发生成（调试用） |

## 展示渠道

### 1. Dashboard 嵌入

在首页仪表盘新增"健康趋势"卡片区域：
- 4 个维度的趋势方向图标（↑↓→）+ 一句话摘要
- 点击跳转 `/health-trends` 详情页

### 2. 每日推送

每天早上 08:00 推送昨日生成的趋势摘要通知：
- 包含最重要的 1-2 条洞察
- 如有风险提醒，优先展示

### 3. Chatbot 集成

- AI 助手支持查询趋势："我最近体重趋势怎么样"
- `chat_service.py` 系统 prompt 注入最新趋势数据
- AI 可引用趋势报告给出更精准建议

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/models/health_trend.py` | HealthTrendReport 模型 |
| `backend/app/services/health_trend_service.py` | 数据聚合 + OpenClaw 分析 + 结果解析 |
| `backend/app/api/health_trend.py` | 4 个 API 端点 |
| `backend/app/schemas/health_trend.py` | 请求/响应模型 |
| `backend/tests/test_health_trend.py` | 单元测试 |
| `frontend/src/app/health-trends/page.tsx` | 趋势详情页 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/models/__init__.py` | 注册新模型 |
| `backend/app/api/main.py` | 注册 router |
| `backend/app/celery_app.py` | 添加定时任务 beat schedule |
| `backend/app/tasks/notifications.py` | 新增趋势分析任务 + 早间推送 |
| `backend/app/services/chat_service.py` | 系统 prompt 注入趋势数据 |
| `frontend/src/app/dashboard/page.tsx` | 嵌入趋势卡片 |
| `frontend/src/services/api.ts` | 新增 `healthTrendApi` |

### 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| `daily_trend_analysis` | 每晚 22:00 | 聚合数据 + OpenClaw 分析 |
| `trend_morning_push` | 每早 08:00 | 推送趋势摘要通知 |
