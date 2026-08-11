<!-- 产品地图(facet 6)。计数引用 docs/_generated/system-map.json,绝不手打 live 数字。
     端 roster / surface 名 / 流程 = 叙事,改了 bump 下方 last-reviewed。 -->
---
doc: system-map/product-map
last-reviewed: 2026-08-11
generated-source: docs/_generated/system-map.json
authoritative-surface-doc: docs/specs/active/2026-06-26-surface-ownership-inventory.md
---

# 产品地图 — 多端 × UI × 业务流 × 系统流

> 计数(mobile/web 路由等)以 [`docs/_generated/system-map.json`](../_generated/system-map.json) 为准;本文给**端 roster、surface 名、业务流、系统流**(叙事,带 last-reviewed)。surface 级 disposition(Keep/Converge/Archive)见 [surface-ownership-inventory](../specs/active/2026-06-26-surface-ownership-inventory.md)。

## 1. 多端

| 端 | 栈 | 入口 | 角色 |
|---|---|---|---|
| **backend** | FastAPI + SQLAlchemy + Celery (py3.12) | `backend/main.py`;`app/api/main.py` | 产品真源(Twin/Safety Gate/Agenda/Router/Write 自治),无 UI |
| **mobile** | Expo SDK 55 + expo-router + RN 0.83 | `mobile/app/` 文件路由 | **主日常产品**(iPhone/iPad 唯一原生 App) |
| **frontend** | Next.js 14 App Router | `frontend/src/app/` | Web(PC);收敛向 admin/history/doctor/family |
| **mac** | Swift 6 / SwiftUI / SPM | `apps/mac/Sources/HealthAgentMac/HealthAgentMacApp.swift` | 工作台(文件/化验导入、长 agent 流、trace) |
| **mini-program** | WeChat + **Taro 4.1.10** | `packages/mini-program/src/app.config.ts` | `weixin` 客户端 |
| **watch** | 原生 watchOS / SwiftUI | `apps/watch/WatchApp/RevaWatchApp.swift` | Apple Watch 低摩擦执行 |
| **rokid-pushup-glasses** | 原生 Android(Kotlin + Compose) | `apps/rokid-pushup-glasses/app/` | Rokid CXR-L 眼镜免手执行 |
| **mcp-server** | Python + FastMCP | `mcp-server/server.py` | 受控扩展(stdio + SSE) |

> 跨端角色与主要 surface 以本表和下节为准；可变规模不在叙事中复制，只读 `_generated`。

## 2. 每端 UI surface(roster;计数见 `_generated`)

- **mobile**(`mobile/app/`):可见 tab 为今日 `index.tsx` · 小巴 `chat.tsx` · 记录 `record.tsx` · 我 `me.tsx`(隐藏:`alerts.tsx`/`journal/`)。日常非 tab:`reva.tsx`/`agenda.tsx`/`timeline.tsx`/`day-schedule.tsx`/`diet.tsx`/`symptom-record.tsx`/`medications.tsx`/`goals.tsx`/`reminders.tsx`/`voice-chat.tsx`;同行支持从已验证饮食卡的服务端 `route.open` 动态进入 `community.tsx`，因此静态导航抽取器不会生成入边。
- **frontend**(`frontend/src/app/`):dashboard/digital-twin/health-trends/health-report/personal-outcome/admin/review/onboarding/family/… (全量计数 `_generated`)。
- **mac**(`SidebarDestination.swift`):today/agenda/timeline/calendar/agent/record/data/dataSources/prescriptions/liver/healthExtras/genetics/knowledge/workouts/goals/jobs/trace/settings。
- **watch**(`apps/watch/WatchApp/`):`TodayStatusView` · `PushListView` · `QuickRecordView` + complication `RevaComplication.swift`。(对话/记录扩展见 watch §13 实施规划)
- **mini-program**(`src/pages/`):index/dashboard/checkin/settings(tabBar)+ diet/workout/heart-rate/medication/… 全量见 `app.config.ts`。
- **mcp-server**(`server.py`):工具全量与分类以 `mcp-server/server.py` 注册表为准。
- **rokid-pushup-glasses**:单一用途(眼镜俯卧撑教练),非多屏导航。

## 3. 当前功能清单（代码核验）

本清单由 `backend/app/api/main.py`、`backend/app/services/tool_schema_registry.py`、各端路由/导航注册表和 Celery task 目录交叉核验。它列稳定能力域与代码锚点，不复制会漂移的数量。

| 能力域 | 当前功能 | 后端/契约锚点 | 主要 surface |
|---|---|---|---|
| **账号与身份** | 注册/登录/刷新、微信身份、邀请与 onboarding、用户合并、档案/API key/LLM 偏好、数据导出 | `api/auth.py` · `api/wechat.py` · `api/invitation.py` · `api/onboarding.py` · `api/user_profile.py` · `api/data_export.py` | Mobile 我/设置 · Web 注册/onboarding/admin |
| **小巴 Agent** | SSE 文字对话、语音/TTS、会话历史、澄清、动态卡片与 action card、推理 trace、受控分享、实时/知识检索 | `api/agent.py` · `services/agent_executor.py` · `services/tool_schema_registry.py` · `api/dynamic_views.py` · `api/speech.py` · `api/shared_conversation.py` | Mobile 小巴/voice-chat · Mac Agent/Trace · Web AI Assistant |
| **确定性语义与权限** | 读/写/管理/分析 speech-act 分类，实体/时间/目标绑定，Tool Gateway 调度；模型只能提议，CapabilityPolicy 决定能否执行 | `services/agent_kernel/health_semantics.py` · `services/write_intent_scope.py` · `services/agent_kernel/goal_spec.py` · `services/agent_kernel/capability_policy.py` · `services/agent_kernel/tool_gateway.py` | 所有 Agent 对话入口共享 |
| **健康记录与生命周期** | 饮食/饮水、体重/腰围/血压/心率/血氧、睡眠/排泄/情绪、运动/鼻炎/症状/病症、用药/补剂、体检/处方、基因、女性健康；支持查询、补录、修改、删除及病症痊愈状态 | `services/tool_schema_registry.py` 的 `health_record`/`health_manage` · `api/diet.py` · `api/basic_health.py` · `api/illness.py` · `api/medical_exams.py` · `api/genetic_data.py` | Mobile 记录与各详情页 · Mac Record/Import · Web records/pages |
| **语义健康读取** | 当前值、滚动时间窗、批量指标、聚合/对比、病症关键词与“上一次/分别有哪些”；owner-scoped canonical reader，未知维度 fail loud | `health_query`/`health_query_batch` · `services/health_read.py` · `services/health_query_batch.py` · `services/health_query_dimensions.py` | 小巴 Agent 各端共享 |
| **计划与执行闭环** | Today/Daily Plan、Agenda、Timeline、Calendar/Schedule、目标、提醒、健康计划/协议、健身计划、复查与用药疗程、完成回执 | `api/daily_plan.py` · `api/agenda.py` · `api/timeline.py` · `api/calendar.py` · `api/goals.py` · `api/smart_reminder.py` · `api/health_program.py` | Mobile 今日/议程/日历 · Mac Today/Schedule · Watch Today/Quick Record |
| **设备与数据接入** | Garmin、Withings、HealthKit、CGM、家居/卧室环境、化验/基因/文件导入、NFC、Rokid 与设备观测 | `api/devices.py` · `api/data_collection.py` · `api/withings.py` · `api/cgm.py` · `api/upload.py` · `api/genetic_data.py` · `api/rokid.py` · `api/device_observation.py` | Mobile 数据连接 · Mac Data Sources/Import · Watch/Rokid |
| **健康智能与安全** | Digital Twin、确定性 Safety Guardian、深度分析、趋势/评分/异常、健康轨迹、慢病风险、生物标志物、个体模型/结果、干预周期/交叉实验、月报/医生报告 | `twin/` · `agents/safety_guardian/` · `api/health_analysis.py` · `api/trajectory.py` · `api/chronic_risk.py` · `api/personal_outcome.py` · `api/intervention_cycles.py` · `api/doctor_report.py` | Mobile 今日/告警/报告 · Mac Insights · Web analytics/family/doctor |
| **知识、证据与记忆** | reviewed System KB、Health Evidence Runtime、知识/实时搜索、事实/会话/事件记忆、健康知识图谱、临床日记、用户指令 | `api/system_knowledge.py` · `api/knowledge.py` · `api/memory_facts.py` · `api/conversation_memory.py` · `api/health_kg.py` · `api/clinical_journal.py` · `api/user_directive.py` | Agent 回答 · Mac Knowledge · Web Knowledge/Review |
| **通知、协作与生成** | 早晚/周/月简报、提醒与安全推送、Siri/Telegram/微信/MCP、家庭与医生协作、匿名同行支持、私有 AIGC 媒体、对话节选分享 | `api/notification.py` · `api/briefing.py` · `api/siri.py` · `api/telegram_webhook.py` · `api/family.py` · `api/community.py` · `api/aigc_media.py` · `mcp-server/server.py` | Mobile/Mac/Web · Watch · 小程序 · 外部 channel |
| **后台自动化** | 设备同步、计划/简报/提醒生成、安全扫描、知识生命周期、记忆/梦周期、结局评分、数据完整性与维护 | `backend/app/tasks/` · `backend/app/celery_app.py` | 后台 worker/beat，无直接 UI |
| **管理与治理** | Admin、模型选择与用量、监控/SLO/性能、数据健康、review/audit、发布策略、桌面与客户端观测 | `api/admin*.py` · `api/monitoring.py` · `api/performance.py` · `api/data_health.py` · `api/review.py` · `api/app_release_policy.py` · `api/client_events.py` | Web/Mobile admin · Mac Jobs/Trace/Settings |

## 4. 业务流(用户视角 · client→backend→DB · file:symbol 锚点)

> ⚠️ CLAUDE.md 的「AI Chat Routing」前端 `needsSkill` 分流图**已部分过时** —— 现状是 mobile+web 统一打 `/agent/stream`,**服务端 tool-calling 路由**;`_needs_skill` 仅是弱模型(无 tool 支持)的兜底。

1. **AI 对话(统一 agent chat,主流)**:mobile `mobile/services/chat.ts` `POST /agent/stream` · web `frontend/src/services/api/ai.ts` `agentApi.streamMessage` → `backend/app/api/agent.py` `POST /agent/stream` → `agent_executor.py:AgentExecutor.run_stream`(暴露 query/batch/record/manage/analysis/knowledge/AIGC 等工具；AIGC 工具只能创建确认草稿，真正外部调用由用户卡片点击消费一次性确认记录)。
2. **病症语义读取**:用户问“上一次某病症是什么时候/最近一段时间分别有哪些” → `health_semantics.py`/`utterance_intent_classifier.py` 判定只读 speech act → `CapabilityPolicy` 只授权 typed `health_query(dimension=illness, keyword=…, days=…)` → `health_read.py` owner-scoped 读取；没给窗口时保留全历史“上一次”语义，未知维度直接报错，不再静默变成综合可穿戴查询。
3. **云端记录饮食**:`mobile/app/diet.tsx` → `backend/app/api/diet.py`:`POST /diet/records`(确认写)· `POST /diet/voice/parse`(**只产草稿不写库**,R4)· `POST /diet/recognize[-and-save]`(照片)。Mobile 仅支持云端账号会话；未认证或会话未知时 egress fail-closed，不生成本地替代回复。
4. **完成议程闭环**:`mobile/app/agenda.tsx` `POST /agenda/complete` + `POST /timeline/events/{id}/complete` → 单核 `timeline_agenda_service.py:complete_agenda_event`(DB 原子认领防虚高依从 → `agenda_service.complete_item` 写真实领域行,确定性 taken_time;失败回滚不翻态)。
5. **安全告警**:`mobile/app/(tabs)/alerts.tsx` / web `SafetyPanel.tsx` → `backend/app/api/safety.py` `GET /safety/me` → `guardian.py:evaluate_safety(twin)` → `evaluate_rules` 跑 `rules/` 下 `@register`(计数见 `_generated`);确定性、无 LLM、按 severity 排序、带 `failed_rule_count` fail-loud。
6. **HealthKit 同步(iOS)**:`mobile/services/appleHealth.ts` `fetchDailyRecords` → `toApiRecord`(生成 schema 标注)→ `POST /devices/healthkit/import` → `device_adapters/healthkit.py`。(自动同步规划见 reva mobile/watch/healthkit experience plan)
7. **私有 AIGC 媒体任务**:Mobile/Web/Mac 在既有对话中上传素材 → Agent Kernel 的 `draft_aigc_media` 创建加密 `AIGCMediaConfirmation` → 用户卡片点击 `POST /aigc/media/confirmations/{id}/confirm`(仅 opaque ID) → `AIGCMediaJob` → owner-scoped `GET/cancel /aigc/media/jobs` → `aigc_media_confirmation.v1`/`aigc_media_job.v1` 动态卡片。仅向确认过的百炼 Wan 请求传出绑定的提示词与当回合图像；输出拷贝到用户私有存储，卡片按需换取短期结果链接。
8. **饮食价值回执与同行支持**:Agent/饮食 API 的已验证 `DietRecord` 写入 → `post_record_quality.py` 在原有单卡中加入 owner-scoped 目标距离与近 7 日记录反馈 → 用户手动点击 `route.open /community?composeRecordId=…` → `POST /community/posts` 再次校验记录所有权并生成无原图、体重、病史、药物、位置和备注的匿名快照 → 支持/同行/有启发三种反应。社区发布失败不回滚或重试私人饮食写入，反应数不进入 Agent 健康建议排序。

## 5. 系统流(内部架构)

- **Agent 请求主链**:`AgentExecutor.run_stream` 冻结 turn snapshot → `health_semantics`/`write_intent_scope` 编译 speech act 与授权目标 → `CapabilityPolicy`/validator 决定工具能力 → `ToolGateway` 调 owner-scoped reader/writer；模型提案不能绕过确定性闸。
- **多 agent 深度分析**(L4→L3→L2→L1):`health_analysis` → `backend/app/orchestrator/orchestrator.py` `run_orchestrator`/`stream_orchestrator` → `build_twin`(Redis 5min)→ `classify_intent` → `_select_specialists`(trivial 短路 lite)→ `_run_specialists`(并行 ThreadPool 12s 超时,recovery→movement readiness 传递)→ 交叉评审+仲裁 → LLM 合成。详图见 [`ARCHITECTURE.md`](../ARCHITECTURE.md) §四 + CLAUDE.md §Multi-Agent。
- **请求流(Web)**:Browser → Next.js rewrites `/api/*` → backend `/api/v1/*`。
- **Write 自治承重墙**:见 `backend/app/services/write_autonomy.py`(只 `measurement_prompt` 自治,NEVER 集封顶 manual_confirm)。

## 6. 视觉验证(怎么看每端真实页面 · 可重生成方法,不钉静态图)

> 静态截图是最易漂的工件,与 system-map「代码生成真源」原则相悖 → 本节给**重生成方法/命令**,不在库里钉死截图(按需现生成)。`captured-as-of` = 方法本身,非快照。

| 端 | 怎么生成视觉 | 状态(2026-06-27 实测) |
|---|---|---|
| **mac**(原生 macOS) | 组件级渲染:`cd apps/mac && swift test --filter HealthAgentMacTests`(snapshot 套件 → `Tests/HealthAgentMacTests/__Snapshots__/` 下 RefreshPanel/WearablePanel/PriorityActionHero/BriefingCard/SpO2WeekCard 等 PNG)。整屏:`swift run HealthAgentMac` 起 app(需登录后端)。 | ✅ `swift build` 绿;snapshot PNG 已 committed,可重录 |
| **mobile**(iOS) | **`./scripts/sim-build.sh ["iPhone 17 Pro"]`**(Rokid 排除 build+install+launch)→ `xcrun simctl io <sim> screenshot`。 | ✅ **已解决** —— Rokid `RGCxrClient.framework` 只有 device 切片,直接 `npx expo run:ios <sim>` 必 exit 65。`sim-build.sh` 用 `ROKID_IOS_SDK_ENABLED=0`(不注入 RGCxrClient → canImport 假 → Rokid 代码全排除)+ `LC_ALL=en_US.UTF-8`(绕 ruby unicode 崩)+ `SENTRY_DISABLE_AUTO_UPLOAD=true` + 删 Podfile.lock 强制重装。**实测 build 绿、app 在模拟器渲染首页**。device/真机 Rokid 功能零影响(EAS device build 仍 ENABLED=1)。见 [[project_ios_simulator_blocked_by_rokid_framework]]。 |
| **watch** | 同 mobile(原生 watchOS target,真机;sim 同受 Rokid/签名限制)。 | ⚠️ 真机 |
| **frontend**(Web) | `cd frontend && npm run dev` → 浏览器/Playwright 截。 | ✅ 可本地起 |
| **mini-program** | 微信开发者工具预览。 | ✅ 工具内 |
| **rokid-pushup-glasses** | 眼镜真机(CXR-L)。 | ⚠️ 真机 |

**结论**:mac 用 snapshot 套件渲染真实组件视觉;**mobile 模拟器路径已打通**(`sim-build.sh` 排除 device-only Rokid 框架 → 模拟器 build+run 成功,首页实测渲染)。两端视觉都可在 macOS 上现生成。

## 维护

- 端 roster / surface 名 / 流程改了 → 改本文 + bump `last-reviewed`(product-pipeline S8)。
- 任何计数 → 改代码后跑 `python scripts/dump_system_map.py`,**别手打进本文**。
- 新端 / 新主流 → 同时更新本文 + surface-ownership-inventory。
