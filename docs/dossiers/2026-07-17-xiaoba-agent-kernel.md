# Dossier: XiaoBa Agent Kernel 重构

| 字段 | 值 |
|---|---|
| slug | `xiaoba-agent-kernel` |
| 创建日期 | 2026-07-17 |
| 当前阶段 | S4 研发 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | backend pytest / ruff / Mobile-Mac-Web smoke / Watch XCTest / deploy health |

## S0 · 用户需求

> 思考系统里是否还有类似的风险点，或者设计不合理的地方。给出你的规划，做系统的重新设计和优化。要参考下开源的 pi 的实现。

上下文：刚修复过“列出饮食记录”被误判为记录/写入的问题。用户要求不再用简单正则或关键词口令解决，而是用更智能的语义和意图分析，并从系统设计上消灭同类风险。

## S1 · Discovery

- 已有可复用：
  - `backend/app/services/utterance_intent_classifier.py` 已提供不依赖正则的语义帧分类入口。
  - `backend/app/services/write_intent_service.py`、`write_autonomy.py`、`llm/tool_validator.py`、`SafetyGuardian` 相关测试已有写入确认、参数校验和安全复盘基础。
  - `docs/plans/2026-07-09-mobile-agent-reliability-kernel-design.md` 已定义 `AgentTurnState`、`WriteReceipt`、`ComposerState` 方向。
  - `docs/plans/2026-07-17-watch-reminder-delivery.md` 已定义 Watch delivery wording 和 receipt honesty。
- 缺口：
  - `backend/app/services/telegram_inbound.py` 仍用 `_RECORD_HINTS` 等关键词路由，并可直接调用 `_exec_health_record`。
  - `backend/app/services/agent_executor.py` 同时处理 prompt、工具子集、文本工具恢复、归一、执行、卡片和回执，边界过厚。
  - `health_record` / `health_manage` 的执行授权散落在工具列表、prompt、validator、normalizer 和 post-processing 中。
  - 文本工具调用恢复是 parser，但当前容易被误认为授权层；所有恢复后的工具调用必须再过统一策略。
  - 时间、渠道、客户端能力、用户时区没有统一成为每一轮执行的不可变参数。
- Pi 借鉴：
  - 区分 Agent message 与 LLM message。
  - 每轮使用 snapshot，结构性变更只在安全点生效。
  - `beforeToolCall`/`afterToolCall` 形式的工具钩子把授权和结果加工从模型输出中拆出来。
  - 统一生命周期事件和观测。
  - 安全边界不能依赖框架信任提示，必须有运行时隔离/策略。

## G1 · 准入

- first_class_objects：`WriteIntent`、`ExecutionEvent`、`SafetyGuardian`、`HealthAgendaItem`
- core_loop_step：用户输入/语音/动态 UI action -> 语义意图 -> 工具策略 -> 执行回执 -> 小巴解释
- target_surface：Backend Agent、Mobile、Mac、Web、Watch、Telegram/Rokid
- safety_level：L3 健康数据与写入边界
- autonomy_tier：默认 manual_confirm；模糊意图 read-only/clarify
- smallest_slice：Chat 和 Telegram 在任何 `health_record` / `health_manage` 前共享 `IntentFrame` + `CapabilityPolicy`
- stale_surface_to_remove：每个 surface 自己判断关键词写入；把 tool schema 子集当安全边界
- **裁决：PASS**。该工作直接降低误写健康记录、错误设备交付宣称和跨端行为漂移风险。

## S2 · Spec

- Feature Spec：[`docs/specs/active/2026-07-17-xiaoba-agent-kernel.md`](../specs/active/2026-07-17-xiaoba-agent-kernel.md)
- 关键不变量：
  - 任何工具执行前必须通过 `CapabilityPolicy`。
  - prompt、工具描述、UI 文案、关键词和模型输出都不是写入授权。
  - ambiguous intent 默认只读或澄清。
  - 写入宣称必须有 deterministic receipt。
  - 时间和时区来自统一 `ExecutionContext`。

## S3 · 规划

- Implementation Plan：[`docs/plans/2026-07-17-xiaoba-agent-kernel-redesign.md`](../plans/2026-07-17-xiaoba-agent-kernel-redesign.md)
- Phase 顺序：
  - P0 审计语料与回归测试。
  - P1 Agent Kernel 类型与共享 `IntentFrame`。
  - P2 `CapabilityPolicy` 成为唯一写入授权。
  - P3 `ToolGateway` 包住结构化和文本恢复工具调用。
  - P4 迁移 Telegram、Voice、Watch/Rokid/proactive adapters。
  - P5 `TurnSnapshot` + EventBus + 时间上下文。
  - P6 动态 UI action capability metadata。
  - P7 删除遗留正则/关键词安全门。
  - P8 shadow -> enforce -> deploy/OTA。

## G2 · 可行性与安全压测

- 现有代码已经有 classifier、validator、write receipt、安全复盘，可做 additive migration。
- 最大风险是 `agent_executor.py` 巨大，必须先包一层 ToolGateway，再逐步抽离，避免一次性重写。
- Enforcement 先以 `shadow` 观察，确认没有误挡正常写入后再 fail-closed。
- **裁决：PASS，带约束**：第一轮只做 P0-P3，不删除 legacy；删除旧门只允许在 P7 静态覆盖测试通过后执行。

## S4 · 研发任务

- [x] T0 intent corpus 回归语料。
- [x] T1 `agent_kernel/types.py` 与 `intent_frame.py`。
- [x] T2 `capability_policy.py` 和写/读/澄清矩阵。
- [x] T3 `tool_gateway.py` 包住 AgentExecutor 工具执行。
- [x] T4 Telegram 移除关键词写路由。
- [x] T5 统一时间/时区 `ExecutionContext`。
- [x] T6 dynamic UI action capability metadata。
- [ ] T7 legacy gates 清理和静态覆盖测试。
- [ ] T8 shadow/enforce 发布与线上验证。

进展：

- 已新增 `backend/app/services/agent_kernel/*` 的基础类型、共享 `IntentFrame` 包装和 `CapabilityPolicy`。
- 已新增 `backend/app/services/agent_kernel/tool_gateway.py`，并接入 `AgentExecutor._execute_tool` 底层 choke point。
- 明确 `read/advice/chat` 意图下的 `health_record` 与 `health_manage(update/delete)` 会在执行前被 block；`unknown` 先兼容放行，避免误杀历史隐式记录句式，后续靠语料和澄清策略收紧。
- 已新增 `backend/tests/fixtures/agent_intent_corpus.json`，覆盖 "记录" 名词查询、对比纠正、明确记录和明确删除。
- 已把 `backend/app/services/telegram_inbound.py` 的 record/query 分流接到共享语义帧；`记录` 关键词不再单独决定写入路由。
- 已把 Telegram `execute_health_record` 从直接调用 `_exec_health_record` 改为调用 `_execute_tool("health_record", ...)`，并传入原始 source text / telegram channel，让 validator、ToolGateway、read-only guard 和 receipt 逻辑统一覆盖。
- 2026-07-18 P0/P1 复核：Mobile 已移除从 Agent 回复正文推断健康写入的遗留入口；排队埋点 `chat_turn_queued` 已纳入后端白名单并使用严格、无正文的 surface/channel/queue-depth 合约。剩余重点是 T7 遗留门静态清理与 T8 发布/线上验证，不能以客户端隐藏入口代替统一 ToolGateway 授权。

## G3 · 测试

- 第一组最小回归已执行：

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_intent_corpus.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_telegram_inbound_intent_gate.py \
  backend/tests/test_utterance_intent_classifier.py \
  -q --no-cov
```

- 结果：`24 passed, 6 warnings`。
- 现有写入/只读护栏回归：

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_health_manage_date_normalize.py \
  backend/tests/test_force_record_tool_choice.py \
  -q --no-cov
```

- 结果：`47 passed, 6 warnings`。
- T3 ToolGateway 与直接执行回归：

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_intent_corpus.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_agent_kernel_tool_gateway.py \
  backend/tests/test_telegram_inbound_intent_gate.py \
  backend/tests/test_utterance_intent_classifier.py \
  backend/tests/test_health_manage_date_normalize.py \
  backend/tests/test_force_record_tool_choice.py \
  -q --no-cov
```

- 结果：`75 passed, 6 warnings`。
- T4 Telegram 执行绕行回归：

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_telegram_inbound_intent_gate.py \
  backend/tests/test_agent_kernel_tool_gateway.py \
  -q --no-cov
```

- 结果：`8 passed, 6 warnings`。
- T4 叠加 kernel 回归：

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_intent_corpus.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_agent_kernel_tool_gateway.py \
  backend/tests/test_telegram_inbound_intent_gate.py \
  backend/tests/test_utterance_intent_classifier.py \
  backend/tests/test_health_manage_date_normalize.py \
  backend/tests/test_force_record_tool_choice.py \
  -q --no-cov
```

- 结果：`76 passed, 6 warnings`。
- 直接 `_execute_tool` 历史回归：

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_health_record_amount_regression.py \
  backend/tests/test_health_record_date_guard.py \
  backend/tests/test_agent_health_manage.py \
  backend/tests/test_watch_voice_record_failclosed.py \
  backend/tests/test_starter_pregen.py \
  -q --no-cov
```

- 结果：`85 passed, 7 warnings`。
- 静态检查：`ruff check` 覆盖新增 kernel、Telegram、classifier 和新增测试，PASS。
- `git diff --check`：PASS。

## G4 · 安全

- 待执行。重点审查：
  - `health_record`、`health_manage(update/delete)`、`intervention_cycle` 不存在绕 ToolGateway 路径。
  - LLM textual tool recovery 只解析，不授权。
  - Watch/推送文案不越权宣称已送达。
  - user_id 隔离和写回执仍由现有确定性 API 保障。

## S6/G5 · 部署

- 后端提交：`a924fa925 feat(agent): add Xiaoba agent kernel policy foundation`
- 部署方式：`./deploy.sh -b`
- 结果：部署完成，后端健康度 `60/60 PASS`，skills manifest 本地/线上 `22/22`。
- 本轮无 Mobile/Mac/Web/Watch 客户端改动，无需 OTA 或 TestFlight。
- **裁决：PASS**。

T3 ToolGateway 部署：

- 后端提交：`866ab4dce feat(agent): gate tool dispatch through kernel policy`
- 部署方式：`./deploy.sh -b`
- 结果：部署完成，后端健康度 `60/60 PASS`，skills manifest 本地/线上 `22/22`。
- 本轮仅后端工具执行策略变化，无客户端改动。
- **裁决：PASS**。

T4 Telegram 执行入口部署：

- 后端提交：`34b3a61cc fix(agent): route Telegram records through tool gateway`
- 部署方式：`./deploy.sh -b`
- 结果：部署完成，后端健康度 `60/60 PASS`，skills manifest 本地/线上 `22/22`。
- 本轮仅后端 Telegram inbound 路由变化，无客户端改动。
- **裁决：PASS**。

## G6 · 上线验证

- 待执行。需要至少覆盖：
  - Mobile/Mac/Web 同一句读请求不写库。
  - Telegram 同一句读请求不写库。
  - 明确记录饮食仍能写入并返回 receipt。
  - 明确删除/修改仍先查候选或确认，不编造 ID。
  - Watch reminder wording 与 delivery receipt 一致。

## S8 · 沉淀

- 待完成。若 P7 删除旧门成功，将把“语义意图 + 能力策略 + 工具网关”沉淀为本项目研发 skill 或 backend agent harness 指南。
