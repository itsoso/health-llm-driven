# Agent Native Health OS 架构记录

**日期**: 2026-05-15  
**状态**: Phase 0 已落地, Phase 1 规划中  
**目标**: 个人健康操作系统, Mobile First, Agent Native, 先聚焦体重与代谢健康。

---

## 1. 产品北极星

本项目的长期形态是每个人的身体智能体: 以基因作为先天底图, 融合体检、可穿戴、饮食、运动、睡眠、情绪和环境数据, 持续理解身体状态, 并把医学、营养、运动和行为科学转化为每天能执行的行动。

第一阶段聚焦体重与代谢健康:

- 体重、腰围、BMI、血压、血脂、血糖、睡眠、训练表现。
- 每天产出可执行计划: 吃什么、怎么练、怎么睡、补什么、什么时候需要咨询医生。
- 不替代医生, 而是做日常健康管理入口、医生决策前后的数据助手和长期执行系统。

核心度量沿用 WSCLA: Weekly Safe Closed-Loop Actions, 即每周用户完成“建议 -> 执行 -> 反馈 -> 下次调整”的安全闭环次数。

---

## 2. 已落地代码边界

### Backend

| 模块 | 文件 | 职责 |
|---|---|---|
| 腰围记录 | `backend/app/models/waist.py` | `WaistRecord` 存储用户腰围、日期、来源、备注 |
| 腰围 API | `backend/app/api/waist.py` | `/api/v1/waist/records*` 当前用户 CRUD + latest + stats |
| Daily Operating Plan | `backend/app/models/daily_operating_plan.py` | 保存每日操作计划快照 |
| 计划生成服务 | `backend/app/services/daily_operating_plan.py` | 从 Twin 生成代谢健康行动清单 |
| 计划 API | `backend/app/api/daily_plan.py` | `GET /api/v1/daily-plan/me` |
| Twin 扩展 | `backend/app/twin/schema.py`, `_collectors.py`, `builder.py` | `body_composition` 加腰围、腰高比、中心性肥胖标记 |
| Agent bugfix | `backend/app/services/agent_executor.py` | `extra_context` 流程前置初始化 `sources_used` |
| 迁移 | `backend/migrations/create_waist_and_daily_operating_plans.sql` | PostgreSQL 建表和索引 |

### Mobile

| 模块 | 文件 | 职责 |
|---|---|---|
| Daily Plan service | `mobile/services/dailyPlan.ts` | 拉取 `/daily-plan/me`, 归一化 actions |
| Today Plan UI | `mobile/components/dashboard/TodayPlanPanel.tsx` | 首页展示今日优先行动、腰围/BP 状态提示 |
| 首页接入 | `mobile/app/(tabs)/index.tsx` | React Query 拉计划, 刷新联动, action 路由分发 |
| Service test | `mobile/services/__tests__/dailyPlan.test.ts` | 覆盖 API 调用与 top actions 选择 |

### Tests

| 文件 | 覆盖 |
|---|---|
| `backend/tests/test_waist_and_daily_plan.py` | 腰围 create/list/upsert、Twin 腰围字段、Daily Plan API |
| `backend/tests/test_health_record_amount_regression.py` | `extra_context` 入口不会在首个 SSE event 前崩溃 |
| `mobile/services/__tests__/dailyPlan.test.ts` | Daily Plan mobile service |

---

## 3. 当前架构图

```mermaid
flowchart TB
  subgraph Mobile["Mobile First App"]
    Home["app/(tabs)/index.tsx"]
    TodayPlan["TodayPlanPanel"]
    DailyPlanSvc["services/dailyPlan.ts"]
    Record["record / diet / movement / sleep pages"]
    Chat["Agent chat / voice-chat"]
  end

  subgraph API["FastAPI API"]
    WaistAPI["api/waist.py<br/>/waist/records"]
    PlanAPI["api/daily_plan.py<br/>/daily-plan/me"]
    AgentAPI["api/agent.py<br/>/agent/stream"]
  end

  subgraph Core["Agent Native Core"]
    TwinBuilder["twin/builder.py"]
    WaistCollector["twin/_collectors.fetch_waist_latest"]
    PlanBuilder["services/daily_operating_plan.py"]
    AgentExecutor["services/agent_executor.py"]
  end

  subgraph Store["PostgreSQL"]
    WaistRecord["waist_records"]
    DailyPlan["daily_operating_plans"]
    HealthTables["weight / BP / sleep / Garmin / labs"]
  end

  Home --> TodayPlan
  TodayPlan --> DailyPlanSvc
  DailyPlanSvc --> PlanAPI
  PlanAPI --> PlanBuilder
  PlanBuilder --> TwinBuilder
  TwinBuilder --> WaistCollector
  WaistCollector --> WaistRecord
  TwinBuilder --> HealthTables
  PlanBuilder --> DailyPlan
  Record --> WaistAPI
  WaistAPI --> WaistRecord
  Chat --> AgentAPI
  AgentAPI --> AgentExecutor
  AgentExecutor --> TwinBuilder
```

---

## 4. Daily Operating Plan 数据流

```mermaid
sequenceDiagram
  participant App as Mobile Home
  participant API as GET /api/v1/daily-plan/me
  participant Plan as build_daily_operating_plan
  participant Twin as build_twin
  participant DB as Postgres

  App->>API: JWT Bearer
  API->>Plan: current_user.id
  Plan->>Twin: force_refresh=True
  Twin->>DB: latest weight, waist, BP, sleep, training
  Twin-->>Plan: HealthTwin snapshot
  Plan->>Plan: deterministic metabolic action policy
  Plan->>DB: upsert daily_operating_plans(user_id, plan_date)
  Plan-->>API: plan dict
  API-->>App: state_summary + actions + targets
  App->>App: show top 3 actions on TodayPlanPanel
```

设计约束:

- `DailyOperatingPlan` 是当天计划快照, 当前版本是确定性规则生成, 后续可在同一数据契约内接 LLM 裁决。
- `build_daily_operating_plan` 每次请求都会 fresh build Twin, 避免首页显示旧状态。
- 腰围属于代谢健康的核心客观指标, 写入后会调用 `invalidate_twin_cache(user_id)`。
- 所有 API 均使用 `get_current_user_required`, 查询必须带 `user_id`。

---

## 5. 移动端功能地图

```mermaid
flowchart LR
  Home["首页 / app/(tabs)/index.tsx"]
  Plan["今日操作计划<br/>TodayPlanPanel"]
  Chat["Agent 对话"]
  Record["记录"]
  Diet["饮食计划"]
  Movement["运动计划"]
  Sleep["睡眠"]
  Card["Action Card"]

  Home --> Plan
  Plan -->|"nutrition"| Diet
  Plan -->|"movement"| Movement
  Plan -->|"sleep"| Sleep
  Plan -->|"measurement"| Record
  Plan -->|"source_card_id"| Card
  Plan -->|"fallback"| Chat
```

首页现在不是“纯 dashboard”, 而是把每日可执行计划放到第一屏:

1. `EnvironmentCard` 给当天外部约束。
2. `TodayPlanPanel` 给代谢健康的 1-3 个优先动作。
3. Chat 流承接解释、调整、追问。

---

## 6. 下一阶段缺口

| 阶段 | 缺口 | 推荐实现 |
|---|---|---|
| Phase 1 | 饮食/睡眠/运动/体检/Twin 页面进入 Agent 时仍有入口缺少结构化 context | 抽 `mobile/utils/agentContext.ts`, 每个入口序列化当前页态并传 `extra_context` |
| Phase 1 | Daily Plan 只读, 用户尚不能确认、调整、完成行动 | 加 action outcome 写回, 复用 ActionCard outcome 或新增 plan action event |
| Phase 1 | 腰围移动端录入入口还未显式上首页/record tab | 在 record tab 加 waist quick input, 对接 `/waist/records` |
| Phase 2 | L2 一键下单尚未接入 | `MenuShareCard` 增 order_suggestions + OTA-friendly URL scheme |
| Phase 3 | WSCLA 闭环缺分享/下单/执行漏斗 | 统一 `intervention_event`, Celery 回看 diet/exercise/checkin 命中 |
| 医生协作 | 医生视图和导出摘要尚未形成稳定契约 | Web/doctor-loop 只读汇总, 不进入治疗建议自动化 |

---

## 7. 给后续编程模型的定位规则

- 改每日行动生成: 先读 `backend/app/services/daily_operating_plan.py`, 再读 `backend/app/twin/schema.py`。
- 改首页行动展示: 先读 `mobile/components/dashboard/TodayPlanPanel.tsx`, 再读 `mobile/app/(tabs)/index.tsx`。
- 改腰围能力: 先读 `backend/app/api/waist.py`, `backend/app/models/waist.py`, `backend/app/twin/_collectors.py`。
- 改 Agent context: 先读 `backend/app/api/agent.py`, `backend/app/services/agent_executor.py`, `mobile/services/chat.ts`, `mobile/hooks/useChatEngine.ts`。
- 新增健康记录类型必须同时补: model/schema/api/service 或 collector、测试、迁移、`docs/ARCHITECTURE.md`、`mobile/PRODUCT_MAP.md`。

