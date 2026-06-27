<!-- 产品地图(facet 6)。计数引用 docs/_generated/system-map.json,绝不手打 live 数字。
     端 roster / surface 名 / 流程 = 叙事,改了 bump 下方 last-reviewed。 -->
---
doc: system-map/product-map
last-reviewed: 2026-06-27
generated-sources:
  - docs/_generated/system-map.json
  - docs/_generated/mobile-access-map.json
authoritative-surface-doc: docs/specs/active/2026-06-26-surface-ownership-inventory.md
---

# 产品地图 — 多端 × UI × 业务流 × 系统流

> 计数(mobile/web 路由等)以 [`docs/_generated/system-map.json`](../_generated/system-map.json) 为准;Mobile 页面节点、导航边、用户旅程和 IA 评估以 [`docs/_generated/mobile-access-map.json`](../_generated/mobile-access-map.json) 为准。本文给**端 roster、surface 名、业务流、系统流**(叙事,带 last-reviewed)。surface 级 disposition(Keep/Converge/Archive)见 [surface-ownership-inventory](../specs/active/2026-06-26-surface-ownership-inventory.md)。

## 1. 多端(8 端)

| 端 | 栈 | 入口 | 角色 |
|---|---|---|---|
| **backend** | FastAPI + SQLAlchemy + Celery (py3.12) | `backend/main.py`;`app/api/main.py` 挂载 router(计数见 `_generated`) | 产品真源(Twin/Safety Gate/Agenda/Router/Write 自治),无 UI |
| **mobile** | Expo SDK 55 + expo-router + RN 0.83 | `mobile/app/` 文件路由 | **主日常产品**(iPhone/iPad 唯一原生 App) |
| **frontend** | Next.js 14 App Router | `frontend/src/app/` | Web(PC);收敛向 admin/history/doctor/family |
| **mac** | Swift 6 / SwiftUI / SPM | `apps/mac/Sources/HealthAgentMac/HealthAgentMacApp.swift` | 工作台(文件/化验导入、长 agent 流、trace) |
| **mini-program** | WeChat + **Taro 4.1.10** | `packages/mini-program/src/app.config.ts` | `weixin` 客户端 |
| **watch** | 原生 watchOS / SwiftUI | `apps/watch/WatchApp/RevaWatchApp.swift` | Apple Watch 低摩擦执行 |
| **rokid-pushup-glasses** | 原生 Android(Kotlin + Compose) | `apps/rokid-pushup-glasses/app/` | Rokid CXR-L 眼镜免手执行 |
| **mcp-server** | Python + FastMCP | `mcp-server/server.py` | 受控扩展(stdio + SSE) |

> **本地图已修正的旧文档漂移**(CLAUDE.md 待同步):① Rokid 是第 8 端(CLAUDE.md Monorepo 表缺)② mini-program 是 Taro 4.1.10 非 uni-app ③ mobile 是 SDK 55/RN 0.83 非 54/0.81 ④ mobile 路由计数以 `_generated` 为准,非 CLAUDE.md「~15」。

## 2. 每端 UI surface(roster;计数见 `_generated`)

- **mobile**(`mobile/app/`,4 可见 tab):今日 `index.tsx` · 私教 `chat.tsx` · 记录 `record.tsx` · 我 `me.tsx`(隐藏:`alerts.tsx`/`journal/`)。日常非 tab:`reva.tsx`/`agenda.tsx`/`timeline.tsx`/`day-schedule.tsx`/`diet.tsx`/`symptom-record.tsx`/`medications.tsx`/`goals.tsx`/`reminders.tsx`/`voice-chat.tsx`;透明化入口:`system-map.tsx`。全量页面/边/旅程/低曝光评估见 [`mobile-access-map.md`](mobile-access-map.md) 与 `_generated/mobile-access-map.json`。
- **frontend**(`frontend/src/app/`):dashboard/digital-twin/health-trends/health-report/personal-outcome/admin/review/onboarding/family/… (全量计数 `_generated`)。
- **mac**(`SidebarDestination.swift` 18 dest):today/agenda/timeline/calendar/agent/record/data/dataSources/prescriptions/liver/healthExtras/genetics/knowledge/workouts/goals/jobs/trace/settings。
- **watch**(`apps/watch/WatchApp/`,3 屏):`TodayStatusView` · `PushListView` · `QuickRecordView` + complication `RevaComplication.swift`。(对话/记录扩展见 watch §13 实施规划)
- **mini-program**(`src/pages/`):index/dashboard/checkin/settings(tabBar)+ diet/workout/heart-rate/medication/… 全量见 `app.config.ts`。
- **mcp-server**(`server.py`,18 tool):10 query + 5 record + 3 analysis。
- **rokid-pushup-glasses**:单一用途(眼镜俯卧撑教练),非多屏导航。

## 3. 业务流(用户视角 · client→backend→DB · file:symbol 锚点)

> ⚠️ CLAUDE.md 的「AI Chat Routing」前端 `needsSkill` 分流图**已部分过时** —— 现状是 mobile+web 统一打 `/agent/stream`,**服务端 tool-calling 路由**;`_needs_skill` 仅是弱模型(无 tool 支持)的兜底。

1. **AI 对话(统一 agent chat,主流)**:mobile `mobile/services/chat.ts` `POST /agent/stream` · web `frontend/src/services/api/ai.ts` `agentApi.streamMessage` → `backend/app/api/agent.py` `POST /agent/stream` → `agent_executor.py:AgentExecutor.run_stream`(暴露 `health_record`/`health_query`/`health_analysis`,LLM tool-call;写前 `_confirm_or_describe` 注 `[NEEDS_CONFIRMATION]` 守 R4)。
2. **记录饮食**:`mobile/app/diet.tsx` → `backend/app/api/diet.py`:`POST /diet/records`(确认写)· `POST /diet/voice/parse`(**只产草稿不写库**,R4)· `POST /diet/recognize[-and-save]`(照片)。
3. **完成议程闭环**:`mobile/app/agenda.tsx` `POST /agenda/complete` + `POST /timeline/events/{id}/complete` → 单核 `timeline_agenda_service.py:complete_agenda_event`(DB 原子认领防虚高依从 → `agenda_service.complete_item` 写真实领域行,确定性 taken_time;失败回滚不翻态)。
4. **安全告警**:`mobile/app/(tabs)/alerts.tsx` / web `SafetyPanel.tsx` → `backend/app/api/safety.py` `GET /safety/me` → `guardian.py:evaluate_safety(twin)` → `evaluate_rules` 跑 `rules/` 下 `@register`(计数见 `_generated`);确定性、无 LLM、按 severity 排序、带 `failed_rule_count` fail-loud。
5. **HealthKit 同步(iOS)**:`mobile/services/appleHealth.ts` `fetchDailyRecords` → `toApiRecord`(生成 schema 标注)→ `POST /devices/healthkit/import` → `device_adapters/healthkit.py`。(自动同步规划见 reva mobile/watch/healthkit experience plan)

## 4. 系统流(内部架构)

- **多 agent**(L4→L3→L2→L1):`backend/app/orchestrator/orchestrator.py` `run_orchestrator`/`stream_orchestrator` → `build_twin`(Redis 5min)→ `classify_intent` → `_select_specialists`(trivial 短路 lite)→ `_run_specialists`(并行 ThreadPool 12s 超时,recovery→movement readiness 传递)→ 交叉评审+仲裁 → LLM 合成。详图见 [`ARCHITECTURE.md`](../ARCHITECTURE.md) §5 + CLAUDE.md §Multi-Agent。
- **请求流(Web)**:Browser → Next.js rewrites `/api/*` → backend `/api/v1/*`。
- **Write 自治承重墙**:见 `backend/app/services/write_autonomy.py`(只 `measurement_prompt` 自治,NEVER 集封顶 manual_confirm)。

## 维护

- 端 roster / surface 名 / 流程改了 → 改本文 + bump `last-reviewed`(product-pipeline S8)。
- 任何计数 → 改代码后跑 `python scripts/dump_system_map.py`,**别手打进本文**。
- Mobile 路由、Tab、设置行、静态跳转或用户 journey 改了 → 跑 `python scripts/dump_mobile_access_map.py`,并让 `check_doc_drift.py` 通过。
- 新端 / 新主流 → 同时更新本文 + surface-ownership-inventory。
