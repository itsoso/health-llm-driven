---
doc: architecture
last-reviewed: 2026-08-11
generated-source: docs/_generated/system-map.json
capability-map: docs/system-map/product-map.md
---

# health-llm-driven 架构文档

**维护**: 每次 PR 涉及本文档列出的任一模块都应在**同一 PR** 里同步更新本文件。代码派生的计数与 roster 只引用 [`docs/_generated/system-map.json`](_generated/system-map.json)，不在叙事中手写。

---

## 一、一页概览

```
                        ┌───────────────────────────────────────────┐
                        │  iPhone App (小巴 / 生产)                 │
 Voice ⇄ Siri ──▶       │   Expo SDK 55 + RN 0.83 + expo-router     │──────┐
                        │   mobile/app/*.tsx (计数见 system-map)   │      │
                        └───────────────────────────────────────────┘      │
                                                                           │ HTTPS (JWT Bearer)
                        ┌───────────────────────────────────────────┐      │
                        │  Web (health.executor.life)               │      │
                        │   Next.js 14 App Router + RSC             │──────┤
                        │   frontend/src/app/*/page.tsx             │      │
                        └───────────────────────────────────────────┘      │
                                                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              Backend: FastAPI (Python 3.12)                          │
│                  health-api.executor.life · 规模见生成的 system-map               │
│  ┌───────────┐  ┌──────────┐  ┌─────────────────┐  ┌────────────────────┐            │
│  │ Auth+JWT  │  │ Router   │  │ Orchestrator    │  │ Agent Executor     │            │
│  │           │  │ dispatch │  │ specialists     │  │ (tool-calling LLM) │            │
│  └───────────┘  └──────────┘  └────────┬────────┘  └──────────┬─────────┘            │
│                                        │                      │                      │
│                                        ▼                      ▼                      │
│                              ┌─────────────────────────────────────────┐              │
│                              │  Digital Health Twin (分区语义视图)     │              │
│                              │  app/twin/schema.py + builder.py         │              │
│                              └────────────────┬────────────────────────┘              │
│                                               │ (Redis 5min cache)                    │
│                                               ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐        │
│  │  Collectors / Services                                                   │        │
│  │  Garmin · Withings · CGM · 化验 · 基因 · 环境 · 补剂 · 药物 · Telegram  │        │
│  └──────────────────────────────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────────────────────────────┘
         │           │                │                    │                  │
         ▼           ▼                ▼                    ▼                  ▼
  ┌──────────┐ ┌──────────┐  ┌─────────────┐    ┌──────────────────┐  ┌─────────────┐
  │ Postgres │ │  Redis   │  │  Celery     │    │  LLM Providers   │  │  3rd-party  │
  │ (多表)   │ │ (cache + │  │ worker+beat │    │ openai-proxy /   │  │ Garmin API  │
  │          │ │  pubsub) │  │ worker+beat │    │ tokenplan (qwen/ │  │ qweather    │
  │          │ │          │  │             │    │ glm/deepseek/    │  │ APNs        │
  │          │ │          │  │             │    │ minimax) / kimi  │  │ Telegram    │
  │          │ │          │  │             │    │ / local dev      │  │ WeChat MP   │
  └──────────┘ └──────────┘  └─────────────┘    └──────────────────┘  └─────────────┘
```

**简述**:
- 单租户 AI 健康管理平台(目前)。iPhone App 是**口袋执行入口**, Mac App 是**桌面执行与导入工作台**, Web 是辅助(计划重定位为家庭/医生视图, 见 FUTURE_ROADMAP.md)。
- 核心是**Agent-Native**: 一个 Agent Executor (tool-calling LLM) 统一处理对话, 背后由 Orchestrator、Specialists、Safety Guardian 和 Digital Twin 共同执行。所有可漂移计数以 [`docs/_generated/system-map.json`](_generated/system-map.json) 为准。
- 数据源: Garmin 腕表为主, 加 Withings / CGM / 化验 / 基因 / 环境 / 补剂 / 药物 / Telegram 语音入口.
- Swift 原生 Mac P0 方案见 `docs/plans/2026-05-23-swift-native-mac-health-agent.md`; Mac 只做原生 UX、文件导入、任务和 trace 查看, 后端仍是唯一健康推理与数据源。

### 当前功能架构（2026-08-11 代码核验）

```mermaid
flowchart TB
    subgraph CLIENTS["交互与执行端"]
        MOBILE["Mobile<br/>今日 · 小巴 · 记录 · 我"]
        DESKTOP["Mac / Web<br/>工作台 · 报告 · 管理"]
        EDGE["Watch / 小程序 / Rokid<br/>低摩擦与免手执行"]
        CHANNELS["Siri / Telegram / MCP<br/>外部受控入口"]
    end

    API["FastAPI /api/v1<br/>认证 · 用户隔离 · 限流 · 审计"]
    DOMAIN_API["领域 API<br/>记录 · 计划 · 报告 · 设备 · 协作 · 运维"]
    STREAM["Agent Stream<br/>SSE 对话 · 语音 · 动态卡片"]
    SEMANTICS["Agent Kernel 语义层<br/>speech act · entity · time · target"]
    POLICY["确定性能力闸<br/>GoalSpec · CapabilityPolicy · Validator"]
    TOOLS["Tool Gateway<br/>query / batch / record / manage / analysis / AIGC draft"]
    ORCH["深度分析路径<br/>Evidence Runtime · Orchestrator · Specialists"]
    SERVICES["Health OS 服务层"]

    subgraph CAPABILITIES["当前能力域（完整清单见 system-map/product-map.md）"]
        RECORDS["健康记录与管理<br/>饮食 · 体征 · 睡眠 · 运动 · 症状/病症 · 用药/补剂"]
        EXECUTION["日常执行闭环<br/>Today · Agenda · Timeline · Calendar · Goal · Reminder"]
        INTELLIGENCE["健康智能<br/>Twin · Safety · 趋势 · 轨迹 · 评分 · 报告 · 个体结果"]
        KNOWLEDGE["知识与记忆<br/>System KB · Evidence · Conversation / Fact / Episode Memory"]
        COLLAB["协作与生成<br/>家庭/医生 · 社区 · 私有 AIGC · 分享"]
        DATA["数据接入<br/>Garmin · Withings · HealthKit · CGM · 化验 · 基因 · 环境"]
    end

    RUNTIME["PostgreSQL · Redis · Celery"]
    EXTERNAL["LLM / Wan · APNs · TTS · Garmin · Weather · WeChat / Telegram"]

    MOBILE --> API
    DESKTOP --> API
    EDGE --> API
    CHANNELS --> API
    API --> DOMAIN_API
    API --> STREAM
    STREAM --> SEMANTICS --> POLICY --> TOOLS
    TOOLS --> ORCH
    DOMAIN_API --> SERVICES
    TOOLS --> SERVICES
    ORCH --> SERVICES
    SERVICES --> RECORDS
    SERVICES --> EXECUTION
    SERVICES --> INTELLIGENCE
    SERVICES --> KNOWLEDGE
    SERVICES --> COLLAB
    SERVICES --> DATA
    RECORDS --> RUNTIME
    EXECUTION --> RUNTIME
    INTELLIGENCE --> RUNTIME
    KNOWLEDGE --> RUNTIME
    COLLAB --> EXTERNAL
    DATA --> EXTERNAL
```

图中“当前能力域”的用户可见功能、代码锚点和主要 surface 以 [`docs/system-map/product-map.md`](system-map/product-map.md#3-当前功能清单代码核验) 为叙事真源；规模以生成的 system-map 为真源。

---

## 二、技术栈

| 端 | Stack | 位置 | 规模 |
|---|---|---|---|
| **Backend** | FastAPI + SQLAlchemy + Celery + Redis + Postgres + pytest | `backend/` | 代码派生规模见 [`system-map.json`](_generated/system-map.json) |
| **Mobile** | Expo SDK 55 + RN 0.83 + expo-router + React Query + expo-audio + react-native-maps + @react-native-voice/voice | `mobile/` | 路由计数见 [`system-map.json`](_generated/system-map.json)，roster 见 `mobile/app/` |
| **Mac Desktop** | Swift 6 + SwiftUI + URLSession async/await + Keychain + MenuBarExtra | `apps/mac/` | 桌面工作台:Agent / Today / Schedule / Record / Import / Jobs / Trace |
| **Web** | Next.js 14 App Router + React 18 + Tailwind + Vitest | `frontend/` | 页面计数见 [`system-map.json`](_generated/system-map.json)，roster 见 `frontend/src/app/` |
| **WeChat 小程序** | Taro 4.1.10 (pnpm workspace) | `packages/mini-program/` | 微信内轻量入口 |
| **Watch** | watchOS + SwiftUI | `apps/watch/` | 今日状态、推送、快速记录、complication |
| **Rokid** | Android + Kotlin + Compose | `apps/rokid-pushup-glasses/` | CXR-L 眼镜免手俯卧撑教练 |
| **MCP Server** | Python (独立) | `mcp-server/` | 受控外部工具入口 |
| **Agent Skills** | Markdown | `backend/skills/` (随后端部署) | 第一方 Agent 运行时技能 |

**Monorepo**: pnpm workspace (仅 `packages/*`) + 独立 npm/pip 根目录 (`backend/`, `frontend/`, `mobile/`, `mcp-server/`).

---

## 三、架构分层

项目按"可变性 × 责任"分四层(改 Layer 1/2 需 review, 改 Layer 3 自由迭代):

### Layer 1 — 不可变核心(Frozen Core)

| 文件 | 职责 |
|------|------|
| `backend/app/database.py` | 数据库连接、`get_db` 依赖 |
| `backend/app/config.py` | Pydantic Settings, 所有 env 定义 |
| `backend/app/models/*.py` | SQLAlchemy ORM 模型；数量见生成的 system-map |
| `backend/app/models/app_release_policy.py` | 按 platform/channel 保存版本化发布策略；只控制更新路由，不控制医疗规则 |
| `backend/app/models/agent_capacity.py` | 跨 worker Agent 容量租约；只存身份/时效元数据，不存对话内容 |
| `backend/app/twin/schema.py` | HealthTwin 分区 Pydantic schema |
| `backend/main.py` 中间件 | 安全头 / CORS / 限流 / request context |
| `backend/tests/conftest.py` | 测试基础设施 |
| `deploy.sh` | 部署流程(备份+回滚) |

### Layer 2 — Agent 层(Agent Fleet)

确定性规则 + 结构化裁决, 详见 §四.

| 目录 | 职责 |
|------|------|
| `backend/app/twin/` | Digital Health Twin 构建、缓存、格式化 |
| `backend/app/agents/safety_guardian/` | 安全规则引擎(不依赖 LLM；规则数见生成的 system-map) |
| `backend/app/agents/recovery_coach/` | Readiness 评分 (Garmin training_readiness 优先, 否则自算 5 维) |
| `backend/app/agents/movement_coach/` | ACWR + 训练处方 (Garmin training_status 映射优先) |
| `backend/app/agents/fuel_strategist/` | TDEE-缺口 + 基因驱动饮食 |
| `backend/app/agents/mental_health_companion/` | 危机检测 + 非药物支持 |
| `backend/app/agents/chronic_specialists/` | 鼻炎/高血压/代谢 专科 |
| `backend/app/agents/knowledge_librarian/` | reviewed System KB V2 检索；legacy Chroma/RAG 仅显式开关调试 |
| `backend/app/agents/longitudinal_analyst/` | 6 月趋势 + 因果叙事 |
| `backend/app/agents/longevity_specialist/` | PhenoAge(Levine 2018)解读 + 委托四件套(抗衰 MVP) |
| `backend/app/orchestrator/` | 意图路由 + specialist 调度 + LLM 合成 |
| `backend/app/agents/audit.py` | Agent 审计日志 |

### Layer 3 — 可变业务(Mutable Business)

| 目录 | 职责 |
|------|------|
| `backend/app/api/*.py` | API 路由；计数见生成的 system-map，roster 见 `app/api/main.py` |
| `backend/app/services/*.py` | 业务服务(含 `cgm/` / `data_collection/` / `notification/` / `environment/` / `llm/` / `genui/`;多源去重见 `device_source_priority` + `garmin_daily_merged`) |
| `backend/app/tasks/*.py` | Celery 异步任务；计数见生成的 system-map，beat roster 见 `app/celery_app.py` |
| `frontend/src/app/*/page.tsx` | Web 页面；计数见生成的 system-map，roster 见文件树 |
| `frontend/src/components/*.tsx` | Web 组件 |
| `mobile/app/` | RN 路由 + Agent Native 导航；计数见生成的 system-map，roster 见文件树 |
| `mobile/components/` | RN 组件(按领域) |
| `mobile/services/` + `mobile/hooks/` | RN API + React Query hooks |

### Layer 4 — 指令层(Instructions)

| 文件 | 职责 |
|------|------|
| `CLAUDE.md` | Claude Code 工作指南 |
| `AGENTS.md` | AI Agent 开发规范(安全/日志/测试权威来源) |
| `docs/ARCHITECTURE.md` | **本文件** — 架构说明 |
| `docs/HARNESS.md` | LLM Harness 设计方法论 |
| `docs/FUTURE_ROADMAP.md` | 战略盘点 + 决策追踪 |
| `backend/skills/*/SKILL.md` | 第一方 Agent Skill 定义(随后端部署) |

---

## 四、核心架构: Agent-Native

```
用户对话框 (App / Web / Siri / Telegram)
        ↓
┌──────────────────────────────────────────┐
│ Agent Executor /api/v1/agent/stream SSE │  ← 统一入口
│ LLM call → tool proposal → result → LLM │
└────────────────────┬─────────────────────┘
                     ▼
┌──────────────────────────────────────────┐
│ Agent Kernel 确定性语义与授权层          │
│ health_semantics / write_intent_scope    │
│ GoalSpec → CapabilityPolicy → Validator  │
│ - 区分读、写、管理、分析与取消           │
│ - 绑定 owner / entity / time / target    │
│ - 未知维度和不充分语义 fail loud         │
└────────────────────┬─────────────────────┘
                     ▼
┌──────────────────────────────────────────┐
│ Tool Gateway                             │
│ health_query / health_query_batch        │
│ health_record / health_manage            │
│ health_analysis / knowledge / AIGC draft │
└──────────────┬─────────────────┬─────────┘
               │                 │ 深度分析
               │                 ▼
               │    ┌──────────────────────────────────────┐
               │    │ Evidence Runtime + Orchestrator      │
               │    │ Specialists + SafetyGuardian        │
               │    │ roster/计数见生成的 system-map      │
               │    └──────────────────┬───────────────────┘
               ▼                       ▼
┌──────────────────────────────────────────────────────────┐
│ Health OS 服务层                                         │
│ owner-scoped readers/writers · Plans · Reports · Memory  │
│ Digital Health Twin (roster 见生成的 system-map)         │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│ PostgreSQL / Redis / Celery + Collectors / Integrations  │
│ Garmin / Withings / HealthKit / CGM / 化验 / 基因 / 环境│
└──────────────────────────────────────────────────────────┘
```

病症查询是这条链路的当前代表性读路径：`health_semantics.py` 保留“上一次、最近一段时间、分别有哪些”等实体与时间语义，`health_query(dimension=illness)` 编译到 owner-scoped canonical reader；未知维度不再降级成综合可穿戴数据。写入则必须由 `write_intent_scope.py` 编译出直接、肯定、当前且目标一致的授权集合，模型提案本身不构成写权限。

### Health Evidence Runtime（跨端健康建议真源）

Mobile、Mac、Web 和外部 channel 不各自实现医疗推理。健康建议在
`AgentExecutor` 内进入同一个服务端 choke point：

```text
query + frozen HealthTwin
  → typed health intent / risk / mandatory discriminators
  → query-specific personal evidence + explicit gaps
  → internal runtime-only System KB retrieval
  → authority tier + locator + applicability + immutable artifact check
  → sufficiency (sufficient / clarify / safe_fallback)
  → strong model may select approved claim IDs only
  → deterministic verifier and canonical evidence envelope
  → Mobile / Mac / Web render the same clinical semantics
```

低背痛包继续被 `CLINICAL_RELEASE_HOLD_DOCUMENT_IDS` 排除在通用搜索、claim
详情和 legacy knowledge tool 之外；受控 health-evidence runtime 通过另一份精确
allowlist 只读取经 product owner 确认、T1 官方来源验证的 runtime-only claim，
不主张独立临床签署，并在每次生成和读取时重新验证 artifact 与适用性。Entity/eval
文档不作为用户回答证据。Dedao 只用于离线主题发现和解释结构，raw 内容或付费文本
不能进入 runtime。

持久化答案不因 synthesis feature flag 关闭而跳过撤销校验。历史、重复回放、模型
上下文、compaction、Desktop trace、cloud facade、pregen 和公开 agent share
统一经过 paired user→assistant projection；claim 被移出 allowlist 或 artifact
变化时，旧正文降级为确定性安全提示。读取时由 `source_query` 可重建的风险作为
下界：sealed manifest 可以记录 frozen Twin/SafetyGuardian 带来的更高风险，但绝不
允许低于问题文本本身已明确的风险。

Mobile/Web 的对话节选分享只提交 authenticated conversation ID 与 durable message
IDs。后端自行读取配对问题和最小 verification proof，公开页每次访问重新投影；客户端
不能提交 answer、manifest 或 proof。所有节选分享使用服务端中性标题，读取旧链接时
也不复用可能含症状的原会话标题。`/shared/create-text` 仅用于用户自拟的普通文本。

低背痛时序规则按每次症状提及分别解析既往、已缓解、持续/复发、否定和当前状态，
并遵循“当前变化优先”：只有明确的既往稳定/已停止且没有后续当前变化的泌尿症状
可从新发马尾风险判断中排除；任何当前尿潴留、失禁、鞍区/会阴感觉变化或明确的
新发/持续/复发/加重对比都会覆盖既往描述并进入急症分流。

### HealthTwin 分区（roster 见生成的 system-map）

`backend/app/twin/schema.py`:

1. **PhysiologicalState** — HRV/心率/睡眠/血氧/压力/VO2max + 夜间呼吸(OSAHS)+ Garmin Training Readiness
2. **BodyCompositionState** — 体重/BMI/体脂/腰围/腰高比/中心性肥胖标记 + Garmin Training Status/Load Ratio/Acute Load
3. **LabsContext** — 血脂/血糖/血压/肝肾功能
4. **CgmContext** — CGM 连续血糖(占位,用户无 CGM 时默认)
5. **MedicationState** — 当前用药 + 依从性
6. **SupplementState** — 补剂清单
7. **GeneticContext** — 基因 variants + 分类(nutrition/pgx/cognition)
8. **EpigeneticState** — 表观遗传 / 生活方式驱动的甲基化年龄反馈
9. **EnvironmentalState** — 天气/AQI/UV
10. **BehavioralState** — 饮水/饮食/训练/鼻炎打卡
11. **AcuteState** — 急性事件 / 急性阈值触发
12. **MentalState** — 心情/日记主题
13. **ChronicConditionState** — 慢性病档案
14. **GoalsContext** — 用户目标

辅助: **DataFreshness** 标记每个分区新鲜度(>X 小时视为过期, LLM prompt 里附提示)。

### Safety Guardian 规则分类

精确计数只引用 `docs/_generated/system-map.json`，不在手写文档中复制。

`backend/app/agents/safety_guardian/rules/`:

- `vitals.py`: BP/HR/SpO2/stress/sleep 急性阈值
- `labs.py`: 肝酶三联/LDL/HbA1c/eGFR/WBC 模式识别 + 高尿酸血症 + 红细胞系整体偏高(HGB+HCT 同向超上限才触发, MEDIUM, 非诊断)
- `ddi.py`: 药-药相互作用(GLP-1×磺脲, SSRI×MAOI 等)
- `dsi.py`: 药-补剂相互作用(鱼油×抗凝, 钙×铁)
- `pgx.py`: 手写规则 + CPIC Level-A 表驱动规则, 表数据在 `pgx_cpic_table.py`(纯数据, 无 @register): TPMT/NUDT15/UGT1A1/HLA-B*15:02/HLA-A*31:01/HLA-B*58:01/CYP2C19/CYP2D6/CYP2C9/CYP3A5/CYP2B6/RYR1/CACNA1S
- `training_load.py`: ACWR 过载/欠训练/零运动
- `cgm.py`: 低血糖/高血糖/TIR/CV/GLP-1 联动
- `symptoms.py`/`cardiac.py`/`problem_red_lines.py`: 症状急症（含腰痛严重神经压迫/马尾警示分流）+ ECG 房颤 + 数据驱动红线
- `guidance_red_lines.py`: R4 越界拦截——扫描 AI 生成的指导/总结文本里的量化/命令式饮食处方(CRITICAL)与命令式体态/训练指令(HIGH);读 `twin.acute.pending_guidance_texts`(仅 guidance 校验路径临时塞入, builder 永不填充), 与 `services/guidance_validator.py` 共享正则

规则增删后运行 `scripts/dump_system_map.py` 与
`scripts/check_doc_drift.py`；手写文档不复制架构计数。

### 抗衰 / Longevity 子系统(横切 L1-L4 + 闭环 + 群体)

复用四层架构、加抗衰特有几块,构成「生物年龄 测量→主动监测→干预→验证→群体学习」闭环。详见 `docs/longevity-os-architecture.md`。

- **算子**: `services/phenoage.py` — PhenoAge(Levine 2018)纯函数 + `phenoage_from_labs` 单一单位映射源(builder/评分/聚合三处复用)
- **L2 信号(3 路, 分级)**: `labs.phenotypic_age`(血检, validated)· `physiological.vo2max_fitness_age`(心肺, validated)· `epigenetic.*`(DNAm 第三方, experimental)。builder `_fill_phenoage`/`_fill_vo2max` 填充; `epigenetic_reports` API + `epigenetic_report_service` 摄入第三方时钟
- **L3 专家**: `agents/longevity_specialist/` — 解读 3 路信号 + `_compose_protocol` 真实编排四件套(Recovery/Fuel/Movement/Mental) + 提 12 周 N-of-1 ProposedCard
- **闭环**: ProposedCard → ActionCard → `tasks/metrics` `fetch_phenotypic_age`/`vo2max` 取值 → `outcome_grader` 评分(越低越好)
- **主动(Celery 周日 10:10)**: `tasks/longevity_watch` + `services/longevity_watch` 跨 `twin_snapshots` 比对生物年龄变化 → 推送(守打扰预算)+ `audit.log_longevity_trigger` 埋点
- **群体(去标识)**: `services/longevity_cohort_service` 聚合已评分 ActionCard → `/admin/longevity/cohort`(observational, 小样本抑制)
- **展示**: `mobile` `BiologicalAgeCard` + `twinHelpers`/`myProgress`(身体年龄卡 + 信任时刻对比)
- 诚实纪律: evidence_tier 三档 + claim_boundary 随展示; 伪科学红线
- 未落地(仅设计/规划): 无感硬件(W5, 依赖商务)、Concierge/商业化(P3-1/2, 依赖运营)、eval 看板(P3-4)、数据飞轮(下一步推荐方向)

---

## 五、数据流 — 一次对话的生命周期

### 5.1 用户在 App 输入"今天吃了一个鸡蛋和一个苹果"

```
Mobile useChatEngine
    │
    │ POST /api/v1/agent/stream  (SSE)
    ▼
api/agent.py::agent_stream
    │ 先校验附件真实格式，再申请 PostgreSQL AgentCapacityLease
    │ - 全局默认最多 100 个活跃回合、单用户默认 2 个
    │ - 租约过期自动回收；正常/异常/断流路径 finally 释放
    │
    │ AgentExecutor.run_stream(user_id, message, conv_id)
    ▼
保存 user message + 创建/复用 conversation
    │
    │ SSE agent_start: {conversation_id}
    │ - 新会话在 done 前切走时, mobile 也已持有 conversationId
    │ - 回到 chat tab/App active 时按 conversationId 拉 `/agent/conversations/{id}`
    │ - 若极早切走还没收到 start, fallback 按真实最近对话拉取, 不优先旧"每日健康简报"
    ▼
_build_system_prompt
    │ - 注入 lite health context (昨夜 readiness / 睡眠 / AQI)
    │ - 注入 user memory (relevant facts)
    │ - 注入 active model 标识
    │
    ▼
_call_llm → LLM 返 tool_call: health_record(type=diet, data={food_items:"鸡蛋,苹果"})
    │ 每一轮调用前统一检查用户/月 token、TokenPlan Credits 与日调用配额
    │
    │ tool_validator 校验: record_date 幻觉 2023? → 修成今天
    │
    ▼
_exec_health_record → POST /diet/records (内部调自身, JWT 带过)
    │
    │ SSE token 流: AI 接着说 "已记录早餐..."
    │
    │ 并发副作用 (clarification/memory extraction, 后台 fire-and-forget):
    │   - memory_service 抽 fact 写 memory_facts
    │   - clinical_journal 追加 SOAP 记录
    │   - outcome_grader 观察窗口登记
    │
    ▼
前端接收 SSE 流 → 气泡追加 token
```

### 5.2 用户问"最近恢复得怎么样"(深度分析路径)

```
Agent Executor
    │ LLM 判定需要复杂分析 → tool_call: health_advice(question="最近恢复得怎么样")
    ▼
orchestrator.py::run_orchestrator
    │
    │ intent.py 分类 → "recovery"
    │ specialists.py registry → [SafetyGuardian, RecoveryCoach, MovementCoach, LongitudinalAnalyst]
    │ Twin.build_twin() (带 5min Redis 缓存)
    │
    ▼
并行 evaluate specialists
    │   each: applies_to(intent, twin) → run(twin, context)
    │   RecoveryCoach.compute_readiness() → Garmin score 71 / 自算 fallback
    │   MovementCoach 基于 training_status 映射 "overload"
    ▼
LLM 合成(synthesis prompt 拼所有 findings + Twin blob + memory)
    ▼
SSE token 流 → 前端气泡
```

### 5.3 后台被动流 — Garmin 夜间同步 → 异常推送

```
Celery beat (每小时) → garmin_sync.sync_user_garmin_data(user_id)
    │ 调 garmin_connect SDK (cookies 来自 browser sync pipeline)
    │
    ▼
写 9 张表: daily_health, hrv_readings, spo2_samples, sleep_level_intervals,
          respiration_samples, workout_records, ...
    │
    ├─ trigger auto_analyze_workout (Celery task, 若有新 workout)
    │   └─ PostRunAnalyzeService.analyzer.analyze → WorkoutAnalysisResult
    │       └─ PushService.send_notification (workout_analysis)
    │
    ├─ AnomalyDetectionService.detect_anomalies → [AnomalyAlert]
    │   └─ PushService.send_notification (dedup rule_id, quiet_hours respect)
    │
    └─ Safety Guardian evaluate → critical alerts
        └─ PushService.send_notification (同上)
```

---

## 六、API 路由(按域分组)

以下按稳定职责域索引；全量注册表见 `backend/app/api/main.py` 的 `include_router`，实时计数见生成的 system-map：

| 域 | 路由前缀 | 关键端点 |
|---|---|---|
| **Auth** | `/auth` | `/login` `/register` `/refresh` |
| **Agent/Chat** | `/agent` `/orchestrator` `/speech` `/dynamic-views` | `/agent/stream` (主对话入口) `/agent/conversations` (历史) `/orchestrator/chat/stream` (深度分析) |
| **Twin/Safety** | `/twin` `/safety` | `/twin/me` `/safety/me` `/safety/audit` `/safety/explain` |
| **Records** | `/diet` `/water` `/weight` `/waist` `/blood-pressure` `/sleep-record` `/workout` `/symptoms` `/medication` `/supplements` `/illness` | owner-scoped CRUD；病症支持生命周期写入和“上一次/时间窗/分别有哪些”的语义读取 |
| **Devices** | `/devices` `/data-collection/garmin/me/*` `/withings` `/cgm` | HealthKit/Garmin/Withings/CGM 接入、同步和设备授权 |
| **Environment** | `/environment` | `/weather` `/air-quality` `/advice` `/exercise-suitability` |
| **Analytics** | `/garmin-analysis` `/daily-health` `/spo2` `/health-analysis` `/personal-outcome` `/monthly-reports` | 聚合 + 趋势 |
| **Trajectory** | `/trajectory` | `/trajectory/me` 疾病上游健康轨迹快照: 基因底图、甲基化缺口、临床锚点、实时状态、可干预变量; risk 携带 `evidence_tier/confidence/claim_boundary` |
| **Operating Plan** | `/daily-plan` | `/daily-plan/me` 当前用户每日代谢健康操作计划; action 携带 `evidence_tier/confidence/claim_boundary` |
| **Schedule/Goals** | `/agenda` `/timeline` `/calendar` `/schedule` `/goals` `/smart-reminder` | 今日执行、日程、目标、提醒及完成回执 |
| **Fitness (P2)** | `/fitness` | `/fitness/weekly-plan` (T2 周健身计划:系统起草→确认排程) `/fitness/exercise-guide` (动作图文指导,确定性数据集) |
| **Reorder/Commerce (P5/D2)** | `/reorder-intents` | 财务一等对象 `ReorderIntent`(复购下单,**SCAFFOLD 不真下单**):`POST /reorder-intents` (propose) `GET` (list) `/{id}/confirm` (T3 逐笔强确认→调快手电商 skill;**skill 契约未就绪→501**,意图停 user_confirmed,绝不 order_placed/扣款) `/{id}/cancel`。skill 网关 `services/kuaishou_skill_gateway.py::place_order` 恒抛 NotImplementedError(财务硬门可证惰性) |
| **Write 层/External Action (P5)** | `/write-intents` | 写意图账本(系统起草→用户确认才执行,全 `trust_tier=manual_confirm` 不自治):`GET` (list,顺带跑各生成器含 `generate_doctor_booking_drafts`) `POST` (propose 外部动作,服务端 kind 白名单 alarm_set/food_order/doctor_booking,未知→422)`/{id}/confirm` `/{id}/dismiss`。external-action kinds:`alarm_set`(确认→建 SmartReminder,设备到点触发,后端只记录)、`doctor_booking`(扫 `ReviewSchedule` due 行→草稿,确认→「去 X 科预约复查」提醒,**不真挂号**)、`food_order`(**DRAFT ONLY**,确认惰性 acknowledged,**不下单/不付款/不存支付凭据**;摘要过 `guidance_validator` R4 守门)。inert 网关 `services/food_order_skill_gateway.py::place_order` 恒抛 NotImplementedError(财务路径可证惰性);全 R15 P1,绝不 P0 |
| **Reminders/Notifications** | `/notification` `/smart-reminder` | `/bind/ios` `/bind/wechat` `/logs` |
| **Voice/Briefing** | `/tts` `/briefing` `/pre-workout` `/clarification` | `/tts/synthesize` (CosyVoice 代理), briefing voice script |
| **Knowledge/Memory** | `/system-knowledge` `/knowledge` `/memory-facts` `/conversation-memory` `/health-kg` | 受控知识、证据、事实与会话记忆、健康知识图谱 |
| **Collaboration/Generation** | `/family` `/doctor-report` `/community` `/aigc/media` `/shared` | 家庭/医生协作、匿名同行支持、私有 AIGC、受控分享 |
| **Admin** | `/admin` `/admin/llm` `/admin/observability` | `/admin/llm/models` `/admin/llm/select-model` `/admin/llm/benchmark/{id}` |

用户可见能力的完整分组和跨端入口见 [`docs/system-map/product-map.md`](system-map/product-map.md#3-当前功能清单代码核验)。

---

## 七、Mobile 架构

### 导航与主屏

```
app/_layout.tsx (root)
├── (tabs)/  — 可见主导航
│   ├── index.tsx     — 今日 dashboard
│   ├── chat.tsx      — 小巴健康参谋;历史/语音/新建/删除会话
│   ├── record.tsx    — 健康记录 (VitalsGrid + ActivityRings + Sparklines + ...)
│   └── me.tsx        — 个人档案、设置和数据入口
│
└── modal / stack pages
    ├── voice-chat.tsx (带 ?conversation_id=X 历史恢复)
    ├── workout-detail.tsx · sleep.tsx · sleep-spo2-analysis.tsx
    ├── body-measurements.tsx  — 体重 + 腰围一屏录入; Daily Plan measurement action 直达
    ├── trace/index.tsx · trace/[id].tsx  — 推理回放
    ├── medical-exams.tsx · consultations.tsx · consultations/[id].tsx
    ├── settings.tsx · location.tsx · notification-settings.tsx
    ├── admin-llm.tsx  — Admin 切换 LLM 模型 + benchmark
    ├── ...
```

### 关键 hook / service

- `hooks/useAuth.tsx` — JWT 存 expo-secure-store
- `hooks/useChatEngine.ts` — 首页聊天状态 + `streamChat` SSE 消费
- `hooks/useVoiceConversation.ts` — 语音对话 (录音 → Voice SDK → streamChat → TTS 队列 + 预合成下一句)
- `hooks/useNotifications.ts` — 注册 APNs token + bundle, deep-link 路由处理
- `hooks/useBiometricLock.ts` — Face ID 锁
- `hooks/useTheme.ts` — 主题系统(`c`/`isDark`, dark mode 切换)
- `services/api.ts` — Axios 实例 + JWT 拦截器, `EXPO_PUBLIC_API_URL`
- `services/cloudTts.ts` — CosyVoice HTTP 代理
- `services/chat.ts` — `streamChat` SSE + `getConversations`/`getConversationMessages`
- `services/dailyPlan.ts` — 首页 Daily Operating Plan 拉取与 action 归一化
- `services/bodyMeasurements.ts` — `/weight/records` + `/waist/records` 一屏录入封装; 后续承接 HealthKit / Health Connect 同步
- `services/trajectory.ts` — 首页 Personal Health Trajectory Snapshot 拉取与 risk 排序
- `components/dashboard/TodayPlanPanel.tsx` — Mobile First 的今日操作计划入口, 显示代谢健康优先动作
- `components/dashboard/TrajectorySnapshotPanel.tsx` — 疾病上游轨迹摘要, 连接基因/甲基化/临床锚点/可穿戴/行动缺口

### Native modules

- `modules/shared-keychain/` — 手写 local module, JWT 给 Siri 扩展用。**必须有 `.podspec`** 否则 autolinking 跳过(踩坑文档 `~/work/personal/PRACTICES/expo-local-module-podspec.md`)

### Variant bundle 机制 (2026-05-06)

`app.config.ts` 按 `APP_VARIANT` env 切:
- `production` → `life.executor.health` + "健康助理"
- `development` → `life.executor.health.dev` + "健康助理 Dev" (dev-client 并装)
- `preview` → `life.executor.health.preview`

APNs topic 用 `ios_bundle_id` per-device (绑定 token 时上报), 防 `DeviceTokenNotForTopic`。

---

## 八、Web (Next.js 14)

页面实时计数见生成的 system-map；主要分域如下(和 Mobile 有**显著 parity 缺口** — 详见 `docs/FUTURE_ROADMAP.md`):

- **Daily** (有 mobile 对应): `/ai-assistant` `/checkin` `/diet` `/sleep` `/goals` `/workout` `/reminders` `/notifications` `/settings`
- **Deep Analytics**: `/digital-twin` `/personal-outcome` `/health-report` `/health-trends`
- **Admin/Ops** (web 独占): `/admin` `/admin/performance` `/admin/architecture` `/skills` `/review`
- **Authoring/Onboarding** (web 独占): `/register` `/onboarding` `/knowledge`
- **Low-frequency refs**: `/medical-exams` `/supplement-products` `/family/*`

**规则**:
- 新 feature 涉及 iPhone/iPad **先写 mobile RN 版本**(CLAUDE.md §决策)
- Web 保留 PC 浏览器场景;新近趋势是 Web 重定位为"家庭/医生视图"(FUTURE_ROADMAP.md §盲点 2)

---

## 九、Celery 调度

任务实时计数见生成的 system-map；beat roster 以 `backend/app/celery_app.py` 为准(北京时区 `Asia/Shanghai`, Redis broker):

| 时间 | 任务 | 职责 |
|---|---|---|
| 每分钟 | `notifications.scan_medication_reminders` | 扫 `medications` 的 `reminder_times` 匹配当前 `HH:MM`, 推送用药提醒 |
| 每分钟 | `event_reminders.scan_event_reminders` | 事件前提醒(P1-B): 排程/会议项开始前按类提前量(会议-10/服药-15/补剂-15/锻炼-20)推一次, `SentEventReminder` 去重 + `proactive_coordinator` 稀缺门 |
| 09:10 | `reorder_scan.scan_reorder_nudges` | 复购检测(P3-D1): 补剂按依从消耗 + 库存估剩余天数 ≤7 → 提议补货 `reorder_nudge` write_intent + 稀缺门推送(**不下单**, 财务面是 P5/D2) |
| 每小时 | `garmin_sync.sync_all_users` | 所有用户 Garmin 数据拉新 + 触发异常检测/Safety/workout 分析 |
| 03:00 | `cleanup.cleanup_old_logs` | 清 old notification logs / expired tokens |
| 03:05 | `maintenance.purge_expired_meal_raw_media` | 餐食监控原始帧图像 +7d TTL 到期物理删除(L3 隐私; finished-but-unconfirmed / abandoned session 的唯一归零路径, fail-loud) |
| 06:00 | `daily_health_plan.generate_for_all` | 生成每日健康计划 |
| 06:10 | `course_review_materialize.materialize_course_reviews` | 物化「用药疗程结束 → 复查」日历: 扫在用药 `end_date` 在未来 ~45 天内的用户, 逐人调 `medication_course_service.ensure_review_schedules`(幂等), 让议程的药程复查投影有 `ReviewSchedule` 行可显(**提示性, 不诊断/不改药/不写依从**) |
| 07:30 | `morning_briefing.send_for_all` | 晨间语音简报推送 |
| 08:00 | `reminders.send_plan_reminder` | 计划执行提醒 |
| 08:30 | `trend_push.send_for_all` | 趋势推送 |
| 20:30 | `evening_insight.send_for_all` | 夜间洞察 |
| 23:00 | `anomaly_check.run_for_all` | 异常检测夜间通扫 |
| 周一 09:00 | `weekly_report.generate_for_all` | 周报 |
| 周日 20:00 | `weekly_voice_invite.send_for_all` | 周聊语音邀请 |
| 周日 10:50 | `protocol_learning.protocol_learning_watch` | P6 学习闭环: 聚合每用户协议 14d 完成/跳过/逾期 → 人体工学调参建议(时间窗/冷却/曝光面/节奏)落审计(`protocol_learning_watch`), **SUGGEST-ONLY 不推送/不改协议/不调药量**; 节流由 `event_reminders` 按需读 |
| 其他 | 各服务自定义 | 见 `celery_app.py` `beat_schedule` |

**幂等与 dedup**: 每个推送调用 `PushService.send_notification(data={"rule_id": X})`, `dedup_window_hours` 内相同 rule 不重推。

---

## 十、LLM Harness

设计文档见 `docs/HARNESS.md`。核心机制:

### 10.1 多 Provider / 多模型

`backend/app/services/llm/`:
- `factory.py` — `get_llm_provider()` 单例, 读 `settings.llm_provider` 或 `model_registry.get_active_model_id()` (admin 切换)
- `model_registry.py` — **单一真相源**, model entry 携带 speed_tier 与 requires_env 验证
- `providers/openai_provider.py` — 兼容 OpenAI 协议 (用于 gpt/qwen/glm/moonshot/zhipu, 都走 OpenAI 兼容)
- `providers/ollama_provider.py` — 本地
- `usage_tracker.py` — wrap provider, 记录 token 用量

可选模型 (当前 `.env`):
- **OpenAI proxy**: gpt-4o-mini (fast), gpt-4o (balanced)
- **TokenPlan (阿里百炼套餐)**: qwen3.6-plus (reasoning), deepseek-v3.2, glm-5, MiniMax-M2.5
- **Moonshot (需独立 key)**: kimi-k2

切换: `POST /admin/llm/select-model {model_id}` (admin, 进程内, 重启失效; 永久改 `.env`)。

Admin UI: `mobile/app/admin-llm.tsx` 含 benchmark 按钮 (`/admin/llm/benchmark/{id}?runs=3`), 显示 3 次延迟 + 平均。

Perf 打点: 每次 LLM 调用写 `metric: llm_call provider=<host> model=<m> latency_ms=<n> status=<n> attempt=<n>`, 可日志聚合。

### 10.2 Source-aware fast path + tool schema 加厚

- `source=siri` 走 orchestrator fast 路径, 跳 specialist + 仲裁(3-5s 返回)
- `tool_validator.py` 对 LLM 输出的 dimension/type 做校验 + 强制 coerce (如 `dimension=workout` → `comprehensive`, `record_date=2023-09-23` → 今天)
- `verification-before-write`: weight/blood_pressure/illness 写库前强制要 `confirmed=true` (L8 pattern)

### 10.3 Memory 4-stage

`services/memory_service.py` / `conversation_memory_service.py`:
1. **Prompt 前取**: `get_relevant_memories(user_id, limit=5)` 语义匹配放 system prompt
2. **对话后抽**: `extract_facts_from_dialog` 异步抽, 写 `memory_facts`
3. **Agent skill 调用**: 第一方 Agent runtime 读取必要记忆
4. **Tier**: tier="user_profile"/"episodic"/"emotional"/"goal", confidence 0-1

### 10.4 Streaming per-sentence TTS

Mobile `useVoiceConversation`: LLM stream token → 累到真标点 → `stripMarkdownForTTS` → 加入 `ttsQueueRef` → `flushTTS` 顺序合成 + 播放。**并发优化**: 当前句播时预合成队列下一句 (`preSynthRef`), 消除句间 network gap。

### 10.5 Provider failover

`agent_executor._call_llm` 失败时走模型注册表内的可用 provider failover, 不再依赖外部网关。

---

## 十一、通知系统

`backend/app/services/notification/` + `backend/app/models/notification.py`:

### 11.1 三通道

- **iOS APNs** (`ios_push.py`): JWT .p8 → HTTP/2 推送. topic = `ios_bundle_id` per-device (2026-05-07 per-device)
- **微信 MP 订阅消息** (`wechat.py`): 模板消息 (openid 绑定)
- **Telegram** (`telegram.py`): bot fallback 渠道

### 11.2 一次 send, 一条 log (2026-05-07 重构)

`push_service.send_notification(...)`:
1. 读 `UserNotificationSetting` → 决定启用哪些 channel
2. 健康建议类 push 先进入 `AdviceGuard` / `advice_ledger`: 同一用户当天已有“降低强度/休跑”建议时, “运动不足/提高强度”push 会被拦截并留审计记录
3. dedup 先于 quiet_hours: 同一 `rule_id` 或 title 在窗口内已 sent/failed/delayed/pending 时不再排队
4. quiet_hours 窗口检查 (默认 22:00-08:30, 可 per-user 配); delayed flush 会再次折叠历史重复队列
5. 并行发 3 channel, 收集每个状态
6. 最后写 **1 条** NotificationLog, `channels` JSON 列存各 channel 状态
7. 任一 channel sent → 整条 status=sent

趋势类 push 必须过 Agent 一致性 gate: exercise 维度的“运动不足/体能下降”风险, 如果 Agent / Daily Plan / AdviceLedger 显示恢复优先, push 不再催用户增加跑步强度。

Mobile `notification-history.tsx` 直读 `channels` 字段, 每条显示 emoji 行 (📱 ✈️ 💬) + 状态。

### 11.3 推送 deep link

APNs payload `data.deep_link` → mobile `useNotifications` 接收 → `router.push(deep_link)`. 覆盖 `/workout-detail?id=X` / `/trace/{id}` / `/voice-chat?intent=clarify&alert_id=X` 等。

---

## 十二、部署流水线

### 12.1 Backend (deploy.sh)

```
./deploy.sh -b
    │
    ├─ 获取本地 + 远端 release lease，冻结 exact expected SHA
    ├─ 备份/恢复演练/站外归档预检，保存健康回滚点
    ├─ 将候选 backend env 暂存在 root-only release stage
    ├─ 停 socket/backend/Celery → 撤销 runtime 授权并 fsync
    ├─ 原子安装规范 flag=false env → 重启并逐 cgroup PID 证明 false
    ├─ exact SHA checkout（Git bundle 是 fetch 超时回退）+ locked 依赖 + migration
    ├─ guard 健康/revision/通用 hold contract 通过后才导入 System KB
    ├─ staged runtime-only KB contract + health score + skills manifest
    └─ 成功时线上仍为 flag=false；医学运行时另走 ./deploy.sh -H
```

健康度维度(总分 60 skip_tests 模式):
- `health_check` (0-30): `/api/v1/health` HTTP 状态 + 延迟
- `api_latency` (0-20): P95 延迟 (`/health`, `/admin/observability/health`)
- `error_rate` (0-10): journalctl 近 200 行 `[ERROR]`/`[CRITICAL]` 占比

阈值调参: `scripts/system_health_score.py::FAIL_THRESHOLD` + 各 score 函数内部分段。

`HEALTH_EVIDENCE_RUNTIME_ENABLED=true` 不能通过通用 env/restart 路径上线。受控
`./deploy.sh -H` 先验证 exact revision、staged KB contract 和 systemd deadman
能力，再用 `/run` drop-in 做 canary；所有健康、认证、score、语义 contract 通过后，
才原子提交包含 commit 与 guard hash 的 durable authorization。去掉 canary 并重启
后，还要证明 backend、Celery worker pool 与 beat 的全部 cgroup PID 都是唯一
`flag=true`。任何失败必须自动恢复并证明 `flag=false`，否则隔离服务并保留远端
lease/stage 供人工处置。

通用 deploy/env/restart/rollback 在改代码、配置或知识前都先撤销 durable/runtime
authorization。SSH/HUP/INT/TERM 导致远端结果不明确时，发布端保留 lease 与 stage，
禁止启动猜测性的并发 rollback；只有远端命令终止且 schema/auth/quarantine/逐 PID
终态都已证明，rollback 才报告成功。

### 12.2 Frontend (`-f`)

```
./deploy.sh -f
  → 证明服务器 checkout 是 expected SHA 且 clean
  → npm ci → build → PM2 restart health-frontend
  → 再证明 exact SHA/clean/revision
```

frontend-only 不 checkout 共享仓库、不重启 backend/Celery、不更改 health-evidence
授权。要部署包含新前端 commit 的版本，必须先走 `--all`/backend 建立同 SHA 后端
回滚地板。

### 12.3 Mobile

**双通道并行**(2026-05-06 新姿势, `feedback_mobile_dual_channel_parallel.md`):

| 通道 | 适合 | 命令 |
|---|---|---|
| **本机 Simulator** | 日常 JS 迭代 (90%) | `cd mobile && npx expo start --dev-client` (Metro) + `npx expo run:ios --no-bundler` |
| **OTA production** | JS-only 推已装 TestFlight | `./scripts/mobile-ota.sh production "msg"` (~30s) |
| **EAS build production** | 有 native 改动 / 发版 | `eas build -p ios --profile production --auto-submit --non-interactive` (~20min) |
| **EAS build development** | 真机 dev-client (热重载) | `eas build -p ios --profile development` (首次交互式配凭证) |
| **TestFlight public QR** | 外部用户扫码安装 | `TESTFLIGHT_PUBLIC_LINK=https://testflight.apple.com/join/... node scripts/testflight-public-link.mjs` |

**规矩**:
- 有意义 commit 后默认并发启 production + development 两个 EAS build, 不等
- Metro **必须独立长驻**, `expo run:ios --no-bundler` (否则 run:ios 退出带死 Metro)
- App Store Connect API 可用时, `node scripts/testflight-public-link.mjs` 会尝试开启/读取 External Testing public link; 否则用 `TESTFLIGHT_PUBLIC_LINK` 生成 `artifacts/testflight/index.html` 扫码页
- 细节见 `~/work/personal/PRACTICES/mobile-expo-dev-workflow.md`

---

## 十三、运行时特性

### 13.1 Auth

- JWT Bearer token, 秘钥 `SECRET_KEY` (32+ 字符)
- Mobile 存 `expo-secure-store` key `auth_token`
- Web 存 `localStorage` key `auth_token`
- API 路由全部 `get_current_user_required` 依赖; admin-only 用 `get_admin_user`

### 13.2 Siri 集成

- `modules/shared-keychain/` — 共享 keychain group 让 Siri AppIntent 拿 JWT
- `plugins/withIntentsExtension.js` — Expo config plugin 生成 Siri Intents target
- AppIntent roster: `HealthCommandIntent` (不开 App, 语音记录), `HealthAnalysisIntent` (不开 App, 分析), `HealthAnalysisOpenIntent` (开 App 到 voice-chat)
- 后端 `?source=siri` 走 fast path

### 13.3 语音对话 (voice-chat)

- 入口参数: `?autoStart=1` / `?intent=briefing|clarify|weekly|preworkout|journal` / `?conversation_id=X`(历史 review) / `?prompt=...`
- 录音: `@react-native-voice/voice` → partial + final
- 静默 1.2s 自动发送 (silence timer) 或用户再点一次立即发
- TTS: CosyVoice v3.5-plus 阿里云 (voice_id `cosyvoice-v3.5-plus-bailian-0ecf848a...`) 代理走 `/api/v1/tts/synthesize`
- 段落衔接: 只用真标点切句, 当前句播时预合成下句 (prefetch)

### 13.4 GPS 精确定位

- `expo-location` 取 lat/lon → `POST /v1/profile/me/gps-location`
- 后端 qweather GeoAPI `/geo/v2/city/lookup?location=lon,lat` 反查到区(`海淀`)
- 存 `detected_city` + `detected_region` (市)
- 天气查询用 `_resolve_weather_city` (剥"市"后缀到市级), 避免 qweather 查不到区级

### 13.5 Observability

- 后端日志: systemd journal (`journalctl -u health-backend`)
- `agent_audit_log` 表: 每次 Safety/Orchestrator 评估写一条 (旁路, 失败不影响业务)
- `client_events` 表: mobile 埋点 (voice_opened, chip_clicked, record_logged、app_update 生命周期等)
- `app_release_policies` 表: Admin 版本化 Remote Config；客户端读取失败降级到安全默认，策略变更写 AgentAuditLog
- Perf: `metric: llm_call ...` 日志行可 grep 聚合
- Sentry: 生产 enabled (`SENTRY_DSN`), dev 可 `SENTRY_DISABLE_AUTO_UPLOAD=true` 禁用 source map 上传

---

## 十四、配置与秘钥

### 14.1 核心 env (.env)

```
SECRET_KEY=<32+ chars>
DEVICE_ENCRYPTION_KEY=<Fernet key>
GARMIN_ENCRYPTION_KEY=<Fernet key>
DATABASE_URL=postgresql://health_app_runtime:***@localhost:5432/health_db
REDIS_URL=redis://localhost:6379/0

# LLM
LLM_PROVIDER=tokenplan  # openai|tokenplan|ollama
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai-proxy.com/v1
OPENAI_MODEL=gpt-4o-mini
TOKENPLAN_API_KEY=sk-sp-...
TOKENPLAN_BASE_URL=https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
TOKENPLAN_MODEL=qwen3.6-plus
MOONSHOT_API_KEY=<optional>  # Kimi
ZHIPU_API_KEY=<optional>      # GLM 官方, 不是 TokenPlan 里的 GLM-5
LLM_VISION_API_KEY=... LLM_VISION_BASE_URL=... LLM_VISION_MODEL=qwen-vl-max

# Push
APNS_TEAM_ID=... APNS_KEY_ID=... APNS_KEY_PATH=/opt/health-app/backend/keys/AuthKey_XXX.p8
APNS_BUNDLE_ID=life.executor.health
APNS_ENV=production
TELEGRAM_BOT_TOKEN=...

# Third party
QWEATHER_API_KEY=... QWEATHER_API_TYPE=premium QWEATHER_API_HOST=<customer>.re.qweatherapi.com
AQICN_API_TOKEN=...
SENTRY_DSN=...

# Garmin (admin, 非 user-facing)
GARMIN_EMAIL=... GARMIN_PASSWORD=...
```

生产 API/Worker 的 `DATABASE_URL` 必须使用非 superuser、非 `BYPASSRLS`、非
`CREATEDB/CREATEROLE` 的运行账号。`MIGRATION_DATABASE_URL` 不进入应用 `.env`，只存于
服务器 root 可读的 `/etc/health-app/migration.env`，部署迁移阶段临时加载；迁移账号与运行
账号相同会直接阻断部署。初次拆分账号使用
`backend/scripts/provision_database_roles.sql`，真实密码通过 psql variables 注入，禁止写入仓库。

### 14.2 Test env 最小集

```
SECRET_KEY=test-secret-key-32-chars-minimum!!
GARMIN_ENCRYPTION_KEY=mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=
```

### 14.3 Mobile

- `EXPO_PUBLIC_API_URL` (默认 `https://health.executor.life/api`)
- `app.config.ts` 读 `APP_VARIANT` env 切 bundle (production/development/preview)

---

## 十五、测试

### 15.1 Backend

- `pytest tests/` — 默认 in-memory SQLite 跑快速单测；设置 `TEST_DATABASE_URL=postgresql://...test...` 时使用真实 PostgreSQL 测试库（库名必须包含 `test`, fixture 会 drop/create schema）
- 关键文件:
  - `test_twin_builder.py` — schema 默认值, builder 空/部分, formatter
  - `test_safety_guardian.py` — 规则正反例 + 严重度排序
  - `test_orchestrator.py` — intent 分类 + specialist 注册表 + e2e
  - `test_specialists.py` — specialist 单测 (Recovery/Fuel/Movement/Mental/Chronic 宏观覆盖)
  - `test_smoke.py` — fixture-free `from main import app` 自检

- **盲区**: Movement/Fuel/Longitudinal/Mental/Knowledge/ChronicSpecialists 缺 prompt 回归测试 (见 FUTURE_ROADMAP.md §盲点 3)

### 15.2 Mobile

- `jest` 配置在, 覆盖率低: 主要 services + ErrorFallback/NetworkBanner
- 零页面测试(voice-chat / workout-detail 关键路径未覆盖)

### 15.3 CI

`.github/workflows/ci.yml`:
- Backend pytest (`DATABASE_URL=sqlite:///:memory:`) + `check_doc_drift.py`
- Frontend `npm run build` + `npm run lint`
- Mobile `npx tsc --noEmit` (typecheck only)

---

## 十六、维护规范

### 16.1 何时更新本文件

**强制同步**(以下改动**必须**在同一 PR 里更新本文件对应章节):

| 改动 | 更新章节 |
|---|---|
| 新增/删除 Specialist | §四, §四 Safety Guardian 规则分类 |
| 新增/删除 API 路由 | §六 API 路由 |
| Twin schema 新字段 | §四 HealthTwin 分区, §五 数据流 |
| Mobile 新路由 / 移除路由 | §七 Mobile 架构 |
| Celery 新任务 | §九 Celery 调度 |
| 新 LLM provider / model | §十 LLM Harness |
| 通知通道改动 | §十一 通知系统 |
| 部署脚本 / 健康度逻辑改动 | §十二 部署流水线 |
| 新 env 字段 | §十四 配置与秘钥 |

**自动校验**: `scripts/check_doc_drift.py` (CI 执行) 比较代码与 `docs/_generated/system-map.json`，并拒绝把可变架构计数写回活跃叙事。新增代码派生结构时，在 `scripts/dump_system_map.py::build_map` 增加字段并重新生成快照。

### 16.2 文档分工

| 文档 | 职责 | 何时读 |
|---|---|---|
| `docs/ARCHITECTURE.md` (本文) | 系统骨架, 长期稳定 | 新成员 onboarding / 回顾系统设计 |
| `CLAUDE.md` | Claude Code 工作规范 | Claude session 启动必读 |
| `AGENTS.md` | 安全/日志/测试规范(权威) | 改 API / 日志 / 测试前 |
| `docs/HARNESS.md` | LLM Harness 方法论 | 做 LLM 相关任务前 |
| `docs/FUTURE_ROADMAP.md` | 战略决策 + 盲点追踪 | 每周五 review |
| `~/work/personal/PRACTICES/` | 跨项目经验沉淀 | 做移动端 / Expo native module 前 |
| `backend/skills/*/SKILL.md` | 第一方 Agent Skill 定义 | 改对话能力边界时 |

### 16.3 演进 log

每次本文件重写都在此记一行:

| 日期 | 更新者 | 摘要 |
|---|---|---|
| 2026-08-11 | Codex GPT-5 | 依据当前代码补齐多端功能架构、Agent Kernel 确定性语义/能力闸、功能清单入口；移除活跃叙事中的手写动态计数并加漂移回归检查。 |
| 2026-05-08 | Claude Opus 4.7 | 首次全量重写; 覆盖 Agent-Native 四层架构 / API / Mobile / Web / Celery / 13 Twin 分区 / 51 Safety 规则 / 3 push 通道 / 双通道 mobile 部署 / 9 LLM 模型注册表 (历史 116/44/68/41) |
| 2026-05-08 | Claude Opus 4.7 | feat: SymptomEntry 通用症状录入 (Home + Record tab + voice); fix: 莫米松 checkin 字段不存在 → 改走 medication_logs; fix: 计划提醒推送前按今日实际天气校对 title (修"雨天力量维护日"但今天没下雨 badcase). 数字: API 116→117, models 68→69, mobile 42→43 |
| 2026-05-09 | Claude Opus 4.6 | feat: Agent-Native v3 Episode 闭环 — Run Recovery Coach 落地 (Increment 1-3): backend/protocols/ YAML registry, services/episode/ planner+lifecycle, ActionGraph + 详情页 + Home OpenEpisodeCard, Garmin sync hook 推 episode_created 推送, Celery beat episode_scheduler 每分钟扫 due reminder + auto-expire + auto-close, 11 单测 + 4 scheduler 单测全绿. 数字: API 117→118, mobile 44→45, Celery 41→42, services 140→147 |
| 2026-05-09 | Claude Opus 4.6 | feat: Agent-Native v3 Increment 4 §1 — Episode Reflection Worker. Celery beat 每天 09:43 北京 (Garmin 同步后) 对 48h 内关闭的 Episode 拉次日 HRV/Sleep, 写 EpisodeOutcome.metrics_delta + 中文模板 summary (无 LLM 成本). API GET /episodes/{id} 现回 outcome 字段 (mobile 可渲染反馈). 5 单测覆盖正路径/数据缺失/幂等/48h 边界/baseline fallback. Celery 42→43 |
| 2026-05-15 | Codex GPT-5 | feat: Agent Native Health OS Phase 0 — 腰围记录、Twin 腰围/腰高比/中心性肥胖标记、每日操作计划 `/daily-plan/me`、Mobile 首页 TodayPlanPanel、架构记录 `docs/AGENT_NATIVE_HEALTH_OS_ARCHITECTURE.md` 和移动端功能地图同步。 |
| 2026-05-15 | Codex GPT-5 | feat: Personal Health Trajectory Agent 骨架 — 新增 `/trajectory/me` 和 Mobile `TrajectorySnapshotPanel`, 将基因底图、甲基化长期反馈缺口、临床锚点、可穿戴状态、可干预变量和 next actions 统一成疾病上游轨迹快照。 |
| 2026-05-15 | Codex GPT-5 | feat: Evidence boundary contract — `/trajectory/me` risks 和 `/daily-plan/me` actions 增加 `evidence_tier/confidence/claim_boundary`, 将甲基化限制为 `experimental/low` 长期代理指标。 |
| 2026-05-15 | Codex GPT-5 | feat: Body measurement intake — Daily Plan 中体重/腰围 action 直达 Mobile `/body-measurements`, 一屏保存体重与腰围, 并记录 HealthKit / Health Connect 优先的自动化路线。 |

---

*此文档是**骨架不是全景**。具体实现细节去读代码, 有歧义时**以代码为准, 更新本文件**而不是反过来。*
