# health-llm-driven 架构文档

**维护**: 每次 PR 涉及本文档列出的任一模块都应在**同一 PR** 里同步更新本文件。最后一次全量重写: 2026-05-08。

---

## 一、一页概览

```
                        ┌───────────────────────────────────────────┐
                        │  iPhone App (健康助理 / 生产)             │
 Voice ⇄ Siri ──▶       │   Expo SDK 55 + RN 0.83 + expo-router     │──────┐
                        │   mobile/app/*.tsx (44 路由)              │      │
                        └───────────────────────────────────────────┘      │
                                                                           │ HTTPS (JWT Bearer)
                        ┌───────────────────────────────────────────┐      │
                        │  Web (health.executor.life)               │      │
                        │   Next.js 14 App Router + RSC             │──────┤
                        │   frontend/src/app/*/page.tsx (68 页)     │      │
                        └───────────────────────────────────────────┘      │
                                                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              Backend: FastAPI (Python 3.12)                          │
│                  health-api.executor.life · 117 API 路由 · 140 services              │
│  ┌───────────┐  ┌──────────┐  ┌─────────────────┐  ┌────────────────────┐            │
│  │ Auth+JWT  │  │ Router   │  │ Orchestrator    │  │ Agent Executor     │            │
│  │           │  │ dispatch │  │ (10 specialist) │  │ (tool-calling LLM) │            │
│  └───────────┘  └──────────┘  └────────┬────────┘  └──────────┬─────────┘            │
│                                        │                      │                      │
│                                        ▼                      ▼                      │
│                              ┌─────────────────────────────────────────┐              │
│                              │  Digital Health Twin (13 分区语义视图)  │              │
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
  │ (多表)   │ │ (cache + │  │ (41 任务)   │    │ openai-proxy /   │  │ Garmin API  │
  │          │ │  pubsub) │  │ worker+beat │    │ tokenplan (qwen/ │  │ qweather    │
  │          │ │          │  │             │    │ glm/deepseek/    │  │ APNs        │
  │          │ │          │  │             │    │ minimax) / kimi  │  │ Telegram    │
  │          │ │          │  │             │    │ / openclaw       │  │ WeChat MP   │
  └──────────┘ └──────────┘  └─────────────┘    └──────────────────┘  └─────────────┘
```

**简述**:
- 单租户 AI 健康管理平台(目前)。iPhone App 是**主要入口**, Web 是辅助(计划重定位为家庭/医生视图, 见 FUTURE_ROADMAP.md)。
- 核心是**Agent-Native**: 一个 Agent Executor (tool-calling LLM) 统一处理对话, 背后是一套 Orchestrator 调度 10 个 Specialist + Safety Guardian (8 类 51 条规则) + Digital Twin (13 分区状态视图).
- 数据源: Garmin 腕表为主, 加 Withings / CGM / 化验 / 基因 / 环境 / 补剂 / 药物 / Telegram 语音入口.

---

## 二、技术栈

| 端 | Stack | 位置 | 规模 |
|---|---|---|---|
| **Backend** | FastAPI + SQLAlchemy + Celery + Redis + Postgres + pytest | `backend/` | 117 API 路由, 140 services, 69 models, 41 Celery 任务 |
| **Mobile** | Expo SDK 55 + RN 0.83 + expo-router + React Query + expo-audio + react-native-maps + @react-native-voice/voice | `mobile/` | 42 路由 |
| **Web** | Next.js 14 App Router + React 18 + Tailwind + Vitest | `frontend/` | 68 页 |
| **WeChat 小程序** | uni-app (pnpm workspace) | `packages/mini-program/` | 独立发布 |
| **MCP Server** | Python (独立) | `mcp-server/` | 第三方 OpenClaw 宿主用 |
| **OpenClaw Skills** | Markdown | `backend/skills/` (22 个, 随后端部署) + `openclaw-skills/` (独立分发) | 22 + 12 |

**Monorepo**: pnpm workspace (仅 `packages/*`) + 独立 npm/pip 根目录 (`backend/`, `frontend/`, `mobile/`, `mcp-server/`).

---

## 三、架构分层

项目按"可变性 × 责任"分四层(改 Layer 1/2 需 review, 改 Layer 3 自由迭代):

### Layer 1 — 不可变核心(Frozen Core)

| 文件 | 职责 |
|------|------|
| `backend/app/database.py` | 数据库连接、`get_db` 依赖 |
| `backend/app/config.py` | Pydantic Settings, 所有 env 定义 |
| `backend/app/models/*.py` | 69 个 SQLAlchemy ORM 模型 |
| `backend/app/twin/schema.py` | HealthTwin 13 分区 Pydantic schema |
| `backend/main.py` 中间件 | 安全头 / CORS / 限流 / request context |
| `backend/tests/conftest.py` | 测试基础设施 |
| `deploy.sh` | 部署流程(备份+回滚) |

### Layer 2 — Agent 层(Agent Fleet)

确定性规则 + 结构化裁决, 详见 §四.

| 目录 | 职责 |
|------|------|
| `backend/app/twin/` | Digital Health Twin 构建、缓存、格式化 |
| `backend/app/agents/safety_guardian/` | 51 条安全规则引擎(不依赖 LLM) |
| `backend/app/agents/recovery_coach/` | Readiness 评分 (Garmin training_readiness 优先, 否则自算 5 维) |
| `backend/app/agents/movement_coach/` | ACWR + 训练处方 (Garmin training_status 映射优先) |
| `backend/app/agents/fuel_strategist/` | TDEE-缺口 + 基因驱动饮食 |
| `backend/app/agents/mental_health_companion/` | 危机检测 + 非药物支持 |
| `backend/app/agents/chronic_specialists/` | 鼻炎/高血压/代谢 专科 |
| `backend/app/agents/knowledge_librarian/` | 得到 wiki RAG (ChromaDB) |
| `backend/app/agents/longitudinal_analyst/` | 6 月趋势 + 因果叙事 |
| `backend/app/orchestrator/` | 意图路由 + specialist 调度 + LLM 合成 |
| `backend/app/agents/audit.py` | Agent 审计日志 |

### Layer 3 — 可变业务(Mutable Business)

| 目录 | 职责 |
|------|------|
| `backend/app/api/*.py` | 117 条 API 路由 |
| `backend/app/services/*.py` | 140 个服务(含 `cgm/` / `data_collection/` / `notification/` / `environment/` / `llm/`) |
| `backend/app/tasks/*.py` | 41 Celery 异步任务 |
| `frontend/src/app/*/page.tsx` | 68 Web 页 |
| `frontend/src/components/*.tsx` | Web 组件 |
| `mobile/app/` | 44 RN 路由 + Tab 导航 |
| `mobile/components/` | RN 组件(按领域) |
| `mobile/services/` + `mobile/hooks/` | RN API + React Query hooks |

### Layer 4 — 指令层(Instructions)

| 文件 | 职责 |
|------|------|
| `CLAUDE.md` | Claude Code 工作指南 |
| `AGENTS.md` | AI Agent 开发规范(安全/日志/测试权威来源, 992 行) |
| `docs/ARCHITECTURE.md` | **本文件** — 架构说明 |
| `docs/HARNESS.md` | LLM Harness 设计方法论 |
| `docs/FUTURE_ROADMAP.md` | 战略盘点 + 决策追踪 |
| `backend/skills/*/SKILL.md` | OpenClaw Skill 定义(随后端部署) |
| `openclaw-skills/` | 独立可分发的 OpenClaw Skill 包 |

---

## 四、核心架构: Agent-Native

```
用户对话框 (App / Web / Siri / Telegram)
        ↓
┌────────────────────────────────────┐
│  Agent Executor (agent_executor.py)│  ← 统一入口
│  /api/v1/agent/stream  (SSE)       │
│  - 循环: LLM call → tool → 再 LLM  │
│  - 工具: health_record, health_query│
│          health_advice, image_vision│
└───────────────┬────────────────────┘
                │ ("我这周恢复得怎么样" / "血压降了说明啥")
                ▼
┌────────────────────────────────────┐
│  Orchestrator (orchestrator.py)    │  ← 深度分析路径
│  - intent.py 关键字分类            │
│  - specialists.py 注册表顺序调度   │
│  - LLM 合成 + 失败回退 OpenClaw    │
│  - Streaming SSE (stream_orchestrator)│
└───────────────┬────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────────────┐
│  10 Specialists                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SafetyGuardian  — 51 条确定性规则, 不调 LLM             │   │
│  │   vitals.py (12) labs.py (7) ddi.py (7) dsi.py (7)     │   │
│  │   pgx.py (9) training_load.py (3) cgm.py (6)           │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ RecoveryCoach  · MovementCoach  · FuelStrategist        │   │
│  │ MentalHealthCompanion · KnowledgeLibrarian              │   │
│  │ LongitudinalAnalyst                                     │   │
│  │ HypertensionSpecialist · MetabolicSpecialist            │   │
│  │ RhinitisSpecialist                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│  共享 context: recovery.readiness_zone → movement_coach         │
└───────────────┬────────────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────┐
│  Digital Health Twin (13 分区)     │  ← 状态视图
│  schema.py + builder.py (并行 fill)│
│  - Redis 5min 缓存                 │
│  - 降级: 失败 filler 不影响其它    │
└───────────────┬────────────────────┘
                │
                ▼
┌────────────────────────────────────┐
│  Collectors + Services             │
│  Garmin / Withings / CGM / 化验   │
│  基因 / 环境 / 补剂 / 药物         │
└────────────────────────────────────┘
```

### HealthTwin 13 分区

`backend/app/twin/schema.py`:

1. **PhysiologicalState** — HRV/心率/睡眠/血氧/压力/VO2max + 夜间呼吸(OSAHS)+ Garmin Training Readiness
2. **BodyCompositionState** — 体重/BMI/体脂 + Garmin Training Status/Load Ratio/Acute Load
3. **LabsContext** — 血脂/血糖/血压/肝肾功能
4. **CgmContext** — CGM 连续血糖(占位,用户无 CGM 时默认)
5. **MedicationState** — 当前用药 + 依从性
6. **SupplementState** — 补剂清单
7. **GeneticContext** — 基因 variants + 分类(nutrition/pgx/cognition)
8. **EnvironmentalState** — 天气/AQI/UV
9. **BehavioralState** — 饮水/饮食/训练/鼻炎打卡
10. **MentalState** — 心情/日记主题
11. **ChronicConditionState** — 慢性病档案
12. **GoalsContext** — 用户目标

辅助: **DataFreshness** 标记每个分区新鲜度(>X 小时视为过期, LLM prompt 里附提示)。

### Safety Guardian 规则分类(51 条)

`backend/app/agents/safety_guardian/rules/` (8 文件):

- `vitals.py` (12): BP/HR/SpO2/stress/sleep 急性阈值
- `labs.py` (7): 肝酶三联/LDL/HbA1c/eGFR/WBC 模式识别
- `ddi.py` (7): 药-药相互作用(GLP-1×磺脲, SSRI×MAOI 等)
- `dsi.py` (7): 药-补剂相互作用(鱼油×抗凝, 钙×铁)
- `pgx.py` (9): CYP2D6/CYP2C19/SLCO1B1/G6PD/HLA-B*5701/DPYD/ALDH2/MTHFR
- `training_load.py` (3): ACWR 过载/欠训练/零运动
- `cgm.py` (6): 低血糖/高血糖/TIR/CV/GLP-1 联动

加一 `__init__.py` 自动注册 = 8 文件。数字由 `scripts/check_doc_drift.py` 校验, 规则增删时同步更新本表 + CLAUDE.md + 该脚本。

---

## 五、数据流 — 一次对话的生命周期

### 5.1 用户在 App 输入"今天吃了一个鸡蛋和一个苹果"

```
Mobile useChatEngine
    │
    │ POST /api/v1/agent/stream  (SSE)
    ▼
api/agent.py::agent_stream
    │
    │ AgentExecutor.run_stream(user_id, message, conv_id)
    ▼
_build_system_prompt
    │ - 注入 lite health context (昨夜 readiness / 睡眠 / AQI)
    │ - 注入 user memory (relevant facts)
    │ - 注入 active model 标识
    │
    ▼
_call_llm → LLM 返 tool_call: health_record(type=diet, data={food_items:"鸡蛋,苹果"})
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
    │   └─ PostRunAnalyzeService.openclaw.analyze → WorkoutAnalysisResult
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

116 条, 主要分 10 域:

| 域 | 路由前缀 | 关键端点 |
|---|---|---|
| **Auth** | `/auth` | `/login` `/register` `/refresh` |
| **Agent/Chat** | `/agent` `/openclaw` `/orchestrator` | `/agent/stream` (主对话入口) `/openclaw/conversations` (历史) `/orchestrator/chat/stream` (深度分析) |
| **Twin/Safety** | `/twin` `/safety` | `/twin/me` `/safety/me` `/safety/audit` `/safety/explain` |
| **Records** | `/diet` `/water` `/weight` `/blood-pressure` `/exercise` `/checkin` `/medication` `/supplements` `/illness` | RESTful CRUD, `/records/me/date/{YYYY-MM-DD}` |
| **Devices** | `/data-collection/garmin/me/*` `/cgm` | Garmin 同步 `/sync?days=N`, CGM batch |
| **Environment** | `/environment` | `/weather` `/air-quality` `/advice` `/exercise-suitability` |
| **Analytics** | `/garmin-analysis` `/daily-health` `/spo2` `/health-analysis` `/personal-outcome` `/monthly-reports` | 聚合 + 趋势 |
| **Reminders/Notifications** | `/notification` `/smart-reminder` | `/bind/ios` `/bind/wechat` `/logs` |
| **Voice/Briefing** | `/tts` `/briefing` `/pre-workout` `/clarification` | `/tts/synthesize` (CosyVoice 代理), briefing voice script |
| **Admin** | `/admin` `/admin/llm` `/admin/observability` | `/admin/llm/models` `/admin/llm/select-model` `/admin/llm/benchmark/{id}` |

路由全量表见 `backend/app/api/main.py` 的 `include_router` 列表。

---

## 七、Mobile 架构

### 导航与主屏

```
app/_layout.tsx (root)
├── (tabs)/  — 4 tab
│   ├── index.tsx     — 首页 (对话 + dashboard)
│   ├── record.tsx    — 健康记录 (VitalsGrid + ActivityRings + Sparklines + ...)
│   ├── alerts.tsx    — 安全告警 + 推理回放
│   └── chat.tsx      — (deprecated, merged into index)
│
└── modal / stack pages — 40+
    ├── voice-chat.tsx (带 ?conversation_id=X 历史恢复)
    ├── workout-detail.tsx · sleep.tsx · sleep-spo2-analysis.tsx
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

68 页, 主要分域(和 Mobile 有**显著 parity 缺口** — 详见 `docs/FUTURE_ROADMAP.md`):

- **Daily** (有 mobile 对应): `/ai-assistant` `/checkin` `/diet` `/sleep` `/goals` `/workout` `/reminders` `/notifications` `/settings`
- **Deep Analytics**: `/digital-twin` `/personal-outcome` `/health-report` `/health-trends`
- **Admin/Ops** (web 独占): `/admin` `/admin/performance` `/admin/architecture` `/skills` `/review`
- **Authoring/Onboarding** (web 独占): `/register` `/onboarding` `/knowledge`
- **Low-frequency refs**: `/medical-exams` `/supplement-products` `/family/*`

**规则**:
- 新 feature 涉及 iPhone/iPad **先写 mobile RN 版本**(CLAUDE.md §决策)
- Web 保留 PC 浏览器场景;新近趋势是 Web 重定位为"家庭/医生视图"(FUTURE_ROADMAP.md §盲点 2)

---

## 九、Celery 调度(41 个任务)

`backend/app/celery_app.py` (北京时区 `Asia/Shanghai`, Redis broker):

| 时间 | 任务 | 职责 |
|---|---|---|
| 每分钟 | `notifications.scan_medication_reminders` | 扫 `medications` 的 `reminder_times` 匹配当前 `HH:MM`, 推送用药提醒 |
| 每小时 | `garmin_sync.sync_all_users` | 所有用户 Garmin 数据拉新 + 触发异常检测/Safety/workout 分析 |
| 03:00 | `cleanup.cleanup_old_logs` | 清 old notification logs / expired tokens |
| 06:00 | `daily_health_plan.generate_for_all` | 生成每日健康计划 |
| 07:30 | `morning_briefing.send_for_all` | 晨间语音简报推送 |
| 08:00 | `reminders.send_plan_reminder` | 计划执行提醒 |
| 08:30 | `trend_push.send_for_all` | 趋势推送 |
| 20:30 | `evening_insight.send_for_all` | 夜间洞察 |
| 23:00 | `anomaly_check.run_for_all` | 异常检测夜间通扫 |
| 周一 09:00 | `weekly_report.generate_for_all` | 周报 |
| 周日 20:00 | `weekly_voice_invite.send_for_all` | 周聊语音邀请 |
| 其他 | 各服务自定义 | 见 `celery_app.py` `beat_schedule` |

**幂等与 dedup**: 每个推送调用 `PushService.send_notification(data={"rule_id": X})`, `dedup_window_hours` 内相同 rule 不重推。

---

## 十、LLM Harness

设计文档见 `docs/HARNESS.md`。核心机制:

### 10.1 多 Provider / 多模型

`backend/app/services/llm/`:
- `factory.py` — `get_llm_provider()` 单例, 读 `settings.llm_provider` 或 `model_registry.get_active_model_id()` (admin 切换)
- `model_registry.py` — **单一真相源**, 9 个模型 entry (speed_tier fast/balanced/reasoning + requires_env 验证)
- `providers/openai_provider.py` — 兼容 OpenAI 协议 (用于 gpt/qwen/glm/moonshot/zhipu, 都走 OpenAI 兼容)
- `providers/ollama_provider.py` — 本地
- `providers/openclaw_provider.py` — 内部 OpenClaw 网关
- `usage_tracker.py` — wrap provider, 记录 token 用量

可选模型 (当前 `.env-online`):
- **OpenAI proxy**: gpt-4o-mini (fast), gpt-4o (balanced)
- **TokenPlan (阿里百炼套餐)**: qwen3.6-plus (reasoning), deepseek-v3.2, glm-5, MiniMax-M2.5
- **Moonshot (需独立 key)**: kimi-k2
- **OpenClaw**: openclaw-main

切换: `POST /admin/llm/select-model {model_id}` (admin, 进程内, 重启失效; 永久改 `.env-online`)。

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
3. **OpenClaw skill 调用**: memory skill 给外部 agent 用
4. **Tier**: tier="user_profile"/"episodic"/"emotional"/"goal", confidence 0-1

### 10.4 Streaming per-sentence TTS

Mobile `useVoiceConversation`: LLM stream token → 累到真标点 → `stripMarkdownForTTS` → 加入 `ttsQueueRef` → `flushTTS` 顺序合成 + 播放。**并发优化**: 当前句播时预合成队列下一句 (`preSynthRef`), 消除句间 network gap。

### 10.5 Provider failover

`agent_executor._call_llm` 失败时 fallback 到 openclaw provider (低质量兜底)。

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
2. quiet_hours 窗口检查 (默认 22:00-08:30, 可 per-user 配)
3. rule_id dedup (JSONB `data::jsonb ->> 'rule_id' = :rid`)
4. 并行发 3 channel, 收集每个状态
5. 最后写 **1 条** NotificationLog, `channels` JSON 列存各 channel 状态
6. 任一 channel sent → 整条 status=sent

Mobile `notification-history.tsx` 直读 `channels` 字段, 每条显示 emoji 行 (📱 ✈️ 💬) + 状态。

### 11.3 推送 deep link

APNs payload `data.deep_link` → mobile `useNotifications` 接收 → `router.push(deep_link)`. 覆盖 `/workout-detail?id=X` / `/trace/{id}` / `/voice-chat?intent=clarify&alert_id=X` 等。

---

## 十二、部署流水线

### 12.1 Backend (deploy.sh)

```
./deploy.sh -b
    │
    ├─ git push (GitHub + kuaishou GitLab 双推)
    ├─ DB 备份 (保留最近 10 份)
    ├─ 同步 .env-online (scp)
    ├─ ssh 服务器 → git pull + pip install
    ├─ 重启 systemd (health-backend) + Celery worker/beat
    ├─ Skills manifest 同步 + 验证 (22 个 SKILL.md)
    └─ 健康度检查 (scripts/system_health_score.py)
         - score >= 35 (skip_tests) → PASS
         - 否则自动回滚到上一版本
```

健康度维度(总分 60 skip_tests 模式):
- `health_check` (0-30): `/api/v1/health` HTTP 状态 + 延迟
- `api_latency` (0-20): P95 延迟 (`/health`, `/admin/observability/health`)
- `error_rate` (0-10): journalctl 近 200 行 `[ERROR]`/`[CRITICAL]` 占比

阈值调参: `scripts/system_health_score.py::FAIL_THRESHOLD` + 各 score 函数内部分段。

### 12.2 Frontend (`-f`)

```
./deploy.sh -f → npm run build → PM2 restart health-frontend
```

### 12.3 Mobile

**双通道并行**(2026-05-06 新姿势, `feedback_mobile_dual_channel_parallel.md`):

| 通道 | 适合 | 命令 |
|---|---|---|
| **本机 Simulator** | 日常 JS 迭代 (90%) | `cd mobile && npx expo start --dev-client` (Metro) + `npx expo run:ios --no-bundler` |
| **OTA production** | JS-only 推已装 TestFlight | `./scripts/mobile-ota.sh production "msg"` (~30s) |
| **EAS build production** | 有 native 改动 / 发版 | `eas build -p ios --profile production --auto-submit --non-interactive` (~20min) |
| **EAS build development** | 真机 dev-client (热重载) | `eas build -p ios --profile development` (首次交互式配凭证) |

**规矩**:
- 有意义 commit 后默认并发启 production + development 两个 EAS build, 不等
- Metro **必须独立长驻**, `expo run:ios --no-bundler` (否则 run:ios 退出带死 Metro)
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
- 3 个 AppIntent: `HealthCommandIntent` (不开 App, 语音记录), `HealthAnalysisIntent` (不开 App, 分析), `HealthAnalysisOpenIntent` (开 App 到 voice-chat)
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
- `client_events` 表: mobile 埋点 (voice_opened, chip_clicked, record_logged 等)
- Perf: `metric: llm_call ...` 日志行可 grep 聚合
- Sentry: 生产 enabled (`SENTRY_DSN`), dev 可 `SENTRY_DISABLE_AUTO_UPLOAD=true` 禁用 source map 上传

---

## 十四、配置与秘钥

### 14.1 核心 env (.env-online)

```
SECRET_KEY=<32+ chars>
DEVICE_ENCRYPTION_KEY=<Fernet key>
GARMIN_ENCRYPTION_KEY=<Fernet key>
DATABASE_URL=postgresql://health_user:***@localhost:5432/health_db
REDIS_URL=redis://localhost:6379/0

# LLM
LLM_PROVIDER=openai  # openai|tokenplan|openclaw|ollama
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

- `pytest tests/` — in-memory SQLite (`conftest.py` 提供 fixture), Redis lazy
- 关键文件:
  - `test_twin_builder.py` — schema 默认值, builder 空/部分, formatter
  - `test_safety_guardian.py` — 规则正反例 + 严重度排序
  - `test_orchestrator.py` — intent 分类 + specialist 注册表 + e2e
  - `test_specialists.py` — 5 个 specialist 单测 (Recovery/Fuel/Movement/Mental/Chronic 宏观覆盖)
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
| Twin schema 新字段 | §四 HealthTwin 13 分区, §五 数据流 |
| Mobile 新路由 / 移除路由 | §七 Mobile 架构 |
| Celery 新任务 | §九 Celery 调度 |
| 新 LLM provider / model | §十 LLM Harness |
| 通知通道改动 | §十一 通知系统 |
| 部署脚本 / 健康度逻辑改动 | §十二 部署流水线 |
| 新 env 字段 | §十四 配置与秘钥 |

**自动校验**: `backend/scripts/check_doc_drift.py` (CI 执行) 校验关键数字, 不一致 fail CI。**新加专属计数指标时同步更新此脚本的 `EXPECTED` 常量**。

### 16.2 文档分工

| 文档 | 职责 | 何时读 |
|---|---|---|
| `docs/ARCHITECTURE.md` (本文) | 系统骨架, 长期稳定 | 新成员 onboarding / 回顾系统设计 |
| `CLAUDE.md` | Claude Code 工作规范 | Claude session 启动必读 |
| `AGENTS.md` | 安全/日志/测试规范(权威) | 改 API / 日志 / 测试前 |
| `docs/HARNESS.md` | LLM Harness 方法论 | 做 LLM 相关任务前 |
| `docs/FUTURE_ROADMAP.md` | 战略决策 + 盲点追踪 | 每周五 review |
| `~/work/personal/PRACTICES/` | 跨项目经验沉淀 | 做移动端 / Expo native module 前 |
| `backend/skills/*/SKILL.md` | OpenClaw Skill 定义 | 改对话能力边界时 |

### 16.3 演进 log

每次本文件重写都在此记一行:

| 日期 | 更新者 | 摘要 |
|---|---|---|
| 2026-05-08 | Claude Opus 4.7 | 首次全量重写; 覆盖 Agent-Native 四层架构 / 116 API / 44 mobile 路由 / 68 web 页 / 41 Celery 任务 / 13 Twin 分区 / 51 Safety 规则 / 3 push 通道 / 双通道 mobile 部署 / 9 LLM 模型注册表 |
| 2026-05-08 | Claude Opus 4.7 | feat: SymptomEntry 通用症状录入 (Home + Record tab + voice); fix: 莫米松 checkin 字段不存在 → 改走 medication_logs; fix: 计划提醒推送前按今日实际天气校对 title (修"雨天力量维护日"但今天没下雨 badcase). 数字: API 116→117, models 68→69, mobile 42→43 |

---

*此文档是**骨架不是全景**。具体实现细节去读代码, 有歧义时**以代码为准, 更新本文件**而不是反过来。*
