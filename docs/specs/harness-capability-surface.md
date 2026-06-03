# Harness Capability Surface — 跨端契约 v1

> 状态：v1（Phase 3 产物）· 2026-06-03
> 关联：`docs/prd/agent-harness-refactor-prd.md` §5
> 用途：定义后端 Agent Harness 对外暴露的**能力**（模式 / SSE 事件 / 证据 / 可解释性 / 延迟预算）。**三端（mac / web / mobile）与跨端统一设计语言（Claude Design）以此为唯一契约**，不各自猜测后端行为。
> 实现锚点：`backend/app/services/agent_executor.py`（`agent/stream` SSE）。
> 版本约定：契约变更 bump 版本号；新增字段向后兼容（端侧未知字段忽略）。

---

## 1. 入口与请求

- 端点：`POST /api/v1/agent/stream`（SSE）。
- 请求体（关键）：`message`、`conversation_id?`、`images?`/`file_base64?`、`extra_context?`（JSON 字符串）。
- `extra_context` 携带能力面控制位：
  | 字段 | 含义 |
  |---|---|
  | `model_id` | 手动指定单模型（registry id，如 `qwen3.7-max`） |
  | `multi_model: true` | 多模型综合档（商用三强；忽略 `model_id`） |
  | `web_search_requested: true` | 联网检索 |
  | `client` / `response_format` | 来源/输出格式（source-aware） |
  | `context_items` | 已选上下文（如某指标趋势） |

---

## 2. 模式 / 档位（Mode/Tier）

端侧用「模型/模式选择器」暴露：

| 档位 | 触发 | 行为 | 延迟/成本 | UI 含义 |
|---|---|---|---|---|
| `fast_record` | 记录意图（正则命中） | 便宜模型工具直写 + 回执 | 最低 | 极简回执卡，不展开分析 |
| `single` | 默认 | 单模型（取数+分析一体或便宜取数+单分析） | 中 | 普通流式回答 |
| `multi_model` | 用户选「多模型综合(商用三强)」 | Gather(便宜取数一次)→ 三强并发分析 → 强模型综合 | 高（几十秒） | panel 阶段进度 + 结构化综合报告 |

> 档位在 `done.mode` 回传；端侧据此切换渲染（如 `multi_model` 显示「共识/各模型/分歧」分区）。

---

## 3. SSE 事件契约

每条 SSE：`{"event": <type>, "data": {...}}`。当前事件类型：

### 3.1 `agent_start`
```json
{"event":"agent_start","data":{"message":"Agent 正在分析...","conversation_id":123}}
```
UI：建立占位/会话 ID（断线可按此 ID 拉回后台落库结果）。

### 3.2 `token`
```json
{"event":"token","data":{"content":"增量文本"}}
```
UI：主回答区流式追加（Markdown）。

### 3.3 `tool_call`
```json
{"event":"tool_call","data":{"tool":"health_query","args":"{...}","round":1}}
```
UI：工具活动 chip「正在查询…」。

### 3.4 `tool_result`
```json
{"event":"tool_result","data":{"tool":"health_record","success":true,
  "preview":"已记录…","result":"完整文本",
  "record_type":"diet","record_data":{...}}}
```
- `record_type`/`record_data` 仅 `health_record` 有 → UI 渲染**记录回执卡**。
- 多模型档复用此事件做**阶段进度**（`tool`=「多模型·主分析/多方/综合」）。

### 3.5 `done`
```json
{"event":"done","data":{
  "conversation_id":123,"message_id":456,
  "elapsed_ms":1234,"llm_ms":900,"llm_rounds":2,
  "model":"Qwen3.7 Max",            // 单模型名 或「Claude+GPT+Gemini(综合)」
  "sources_used":["健康数据查询","系统知识库"],
  "mode":"agent",                    // 或 "multi_model"
  "cards":[ /* 证据/动态卡 */ ],
  "finish_reason":"stop","completion_status":"completed",
  "record_intent_no_tool":false
}}
```
UI：收尾 footer（耗时/模型/来源）、证据卡区、记录-意图无写入的告警态。

### 3.6 `error`
```json
{"event":"error","data":{"message":"..."}}
```
UI：错误态 + 重试入口。

---

## 4. 证据与可解释性

| 来源 | 字段 | UI |
|---|---|---|
| 来源归因 | `done.sources_used`（中文标签：Garmin/化验/补剂 · 系统知识库 · 化验单 …） | 「AI 用了哪些数据」标签条 |
| 证据卡 | `done.cards`（system-KB evidence + inline cards + query 派生卡） | 可展开证据/卡片区 |
| 决策反查 | audit（`route`/`tier`/specialist trace）经 `/safety/{id}` `/specialist/{id}` | 「为什么这么说」展开面（不二次调 LLM） |
| 多模型结构 | 综合报告含「共识 / 各模型补充 / 分歧」 | 结构化分区折叠 |

---

## 5. 延迟预算（Source-aware）

| 来源 | 预算 | 策略 |
|---|---|---|
| Siri / 快速记录 | < 2s | fast path，骨架最少 |
| Web / Mac 分析 | 流式秒级首 token | 进度态 + 流式 |
| 多模型综合 | 几十秒 | 阶段进度（Gather→Analyze→Synthesize）必显，避免「卡死」错觉 |
| Push / 后台 | 异步 | 落库后拉取（按 `conversation_id`） |

---

## 6. 跨端设计语言要渲染的核心组件（给 Claude Design 的输入）

1. **模型/模式选择器** — 单模型(默认 Qwen3.7 Max) / 多模型综合(商用三强)；显示当前实际用的模型。
2. **流式回答区** — Markdown，问/答同字号；标题层级；表格；编号行动列表。
3. **阶段进度条** — Gather→Analyze→Synthesize（多模型档必显）。
4. **工具活动 chip / 记录回执卡** — `tool_call`/`tool_result` 渲染。
5. **证据/来源区** — `sources_used` 标签 + `cards` 展开。
6. **可解释性展开面** — route/tier/specialist trace。
7. **多模型综合报告分区** — 共识 / 各模型观点 / 分歧。
8. **空态起始建议** — starter prompts（仅空对话）。
9. **历史/上下文面板** — 分页历史 + 已选上下文。

> 以上 9 组件需在 mac / web / mobile 三端共享同一设计语言（颜色语义、字号体系、间距、动效、组件语义一致），各端按平台适配交互。
