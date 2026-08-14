# Feature Spec: Agent 多药合并确认与可信写入

> Status: blocked · G4 feature review passed historically; current release G4/G5 BLOCK
> Owner: Codex
> Updated: 2026-07-21
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` R4, R15, R16
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/medication_intake_batch.py`, `backend/app/services/write_intent_service.py`, Mobile/Web/Mac chat clients
>
> **Current release override (2026-08-12):** all repo-contained automatic remote/vendor release
> entrypoints, local signing/install/automatic-provisioning entrypoints and OTA/rollback channels
> are frozen. Manual Gate means BLOCK/STOP; local checks cannot authorize deployment. Do not use
> mobile device build/sign/install helpers. Production network observation and release
> plan/validate are also frozen. Only Metro/iOS Simulator/tests, offline evidence, public
> unauthenticated HTTPS and
> `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` offline IPA metadata/report are allowed;
> that command creates no install manifest, install QR, or installability claim.

## 1. Decision

修复 Agent 把“等待用药确认”错误覆盖成缺字段追问的回归；对于能确定性拆出的一个或多个用药事实，服务端冻结一份 owner-bound `WriteIntent`，一次人工确认后原子、幂等地写入全部 `MedicationLog`，不再信任模型自报 `confirmed=true`。

## 2. Problem

当前用户说“记录服用两种胃药：伊托必利 替普瑞酮 各一粒”时，用药工具已经进入 `NEEDS_CONFIRMATION`，但回合末把“没有写回执”误当成“没有调用写工具”，最终显示与事实无关的通用缺参话术。与此同时，现有跨轮确认依赖模型再次提交 `confirmed=true`，没有服务端持有的待确认计划；复合用药还会被解析成一个大药名，且实际服量没有进入日志。

如果不修，用户会在最短、最高频的健康记录动作上失去信任；若只恢复文案而继续让模型重放写工具，则可能发生确认越权、参数漂移、部分写入和重复记录。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复 Agent 用药记录退化，并支持多药一次确认、可信落库
  classification: bugfix + product_change
  first_user_fit: 通过聊天记录一个或多个已发生用药事实的用户
  core_loop_step: user statement -> WriteIntent -> manual confirm -> MedicationLog receipts -> safety review
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: [Backend Agent, Mobile Chat, Web Chat, Mac Chat]
  source_of_truth: PostgreSQL WriteIntent and MedicationLog
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 当前用户原话 + 服务端冻结计划 + 用户显式确认
  claim_hedging: 只陈述记录事实，不声称药物、组合或剂量正确或安全
  verification_window: 确认响应内返回批次及逐项可验证回执
  success_metric: 精确回归句首轮显示两项合并确认，确认后恰有两条各 1粒日志，重试不重复
  added_user_burden: 一次确认
  burden_justification: 用药属于医疗级写入，确认同时防止模型参数漂移
  non_goals: [开药或调药, 判断两药能否同服, 推断处方剂量和频次, 任意自由文本药名识别]
  smallest_end_to_end_slice: 明确已服用句 -> 冻结批次 -> 一次确认 -> 原子 MedicationLog -> 回执
  stale_surface_to_remove_or_archive: 模型 confirmed=true 直接放行 medication health_record
  spec_required: yes
```

## 4. Non-Goals

- 不给出“可以一起吃”“剂量正确”等医疗结论。
- 不从“一粒”反推药品规格、处方剂量、每日频次或提醒计划。
- 不把模糊的“两个胃药”、否定、更正、疑问或无法唯一识别的药名强行写入。
- 不在本切片迁移补剂、疾病等其他确认流。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | 新增 `medication_intake_batch` kind，绑定用户、会话来源消息和冻结计划；以持久化 `decision_status` 保存逻辑终态；永不自治执行 |
| `ExecutionEvent` | 确认后以批次结果和逐项 `MedicationLog` `write_receipts` 表达实际副作用 |

## 6. User Flow

```text
明确记录一个或多个已服用药物
  -> 确定性解析药名与本次实际服量
  -> owner + conversation + source message 绑定的 WriteIntent(pending)
  -> 对话正文和卡片展示同一冻结计划
  -> 用户点击“确认记录”/“取消”或在同一会话紧接着回复“确认”/“取消”
  -> 服务端以条件更新一次性裁决 WriteIntent；confirm/dismiss 竞态以数据库胜者为准
  -> confirmed: 同事务解析/创建最小药物条目并写入全部 MedicationLog
     -> 返回 status + decision_status + 逐项 write_receipts
     -> 写后 SafetyGuardian；筛查失败不回滚真实记录，但明确提示未完成
  -> dismissed/expired: 关闭授权，零 MedicationLog、零 write_receipts
```

超过 30 分钟的未决授权会物理终结为 `status=dismissed`，同时持久化逻辑终态 `decision_status=expired`；即使终结提交后响应中断，重试也只重放 expired，不重新授权、不调用 LLM。

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | 解析、冻结、授权、原子执行和回执真源 | 不信任模型 `confirmed`; owner-scoped; 同一 source message 至多一个批次；持久化并返回权威逻辑终态 |
| Mobile / Web / Mac Chat | 展示计划并触发人工确认/取消 | 动作只提交服务端签发的 WriteIntent id，不回传或修改 items；按 `decision_status` 和完整 `write_receipts` 收敛 confirm/dismiss 竞态，不用本地点击动作覆盖服务端胜者 |

服务端终态通过 `medication_batch_decision` 命名空间携带批次自己的精确回执与安全提示；客户端只在旧消息缺少嵌套字段时回退顶层兼容数组。文字确认回合即使 `done.cards=[]`，三端也必须按 intent id 立即终结上一轮 pending 卡片并清除动作，不能等历史重载。

## 8. Data Contract

```yaml
apis:
  - POST /write-intents/{id}/confirm 保持兼容，medication batch 返回 status/decision_status/write_receipts/safety_alerts
  - POST /write-intents/{id}/dismiss 返回同一组权威终态字段；若并发 confirm 已胜出，返回 executed 和完整 write_receipts
events:
  - Agent done.turn_outcome=confirmation_required for pending plans
models:
  - existing WriteIntent with kind=medication_intake_batch and nullable decision_status
  - existing Medication and MedicationLog
fields:
  - payload.schema_version/conversation_id/source_message_id/plan_hash/timezone/taken_date/taken_time/items
  - WriteIntent.decision_status=executed|dismissed|expired
  - assistant.meta.medication_batch_decision={intent_id,status,write_receipts,safety_alerts}
enums:
  - WriteIntent.kind += medication_intake_batch
backward_compatibility:
  - 既有 write-intent kinds 和客户端单回执保持可用
migration:
  - 为 WriteIntent 增加 nullable decision_status
  - 为 medication_intake_batch 的 user + source_message 建立条件唯一索引
```

计划中的 `items` 是确认时唯一可执行参数；确认请求不接受 items。API 的 `status` 保存物理状态，`decision_status` 保存逻辑裁决：正常确认是 `executed/executed`，主动取消是 `dismissed/dismissed`，过期是 `dismissed/expired`。Agent 把该批次的完整逻辑结果写入 namespaced `assistant.meta.medication_batch_decision.status`，顶层 `write_receipts`/`safety_alerts` 仅作与同回合其他能力合并后的兼容投影。药名与剂量只存在 owner-scoped 健康存储及鉴权后的聊天卡片。标题、日志和指标只记录批次 id、项目数和状态。

## 9. Safety, Privacy, And Medical Boundary

- 用药事实属于 L3 健康数据；所有查询与确认都强制 `user_id`，隐式文字确认还必须匹配同一会话的上一条 assistant 消息。
- `medication_intake_batch` 加入自治永久拒绝集合。模型传 `confirmed=true`、修改 items 或直接重放工具都不能授权写入。
- 必要的新药物条目只承载用户已陈述的事实，不填处方剂量、频次、用途或诊断；确认文案明确说明会加入清单。
- 核心批次写入同一事务；第二项失败时零条新日志、零个半成品药物条目。
- 同药、同本地日期和同冻结时点已有相同事实可作为幂等回执；实际服量冲突必须 fail loud，不静默覆盖。
- confirm/dismiss 互相竞争时只允许一个条件更新胜出；失败方必须读取并返回数据库中的权威终态，不能显示与真实写入相反的成功提示。
- 过期终结将授权物理关闭并持久化 `decision_status=expired`；提交后崩溃或网络中断的恢复路径不得重新执行、不得降回 pending。
- 写后执行确定性 SafetyGuardian。安全筛查失败时说“记录已保存但筛查暂不可用”，不能把失败解释为安全，也不能建议自行停换药。
- 锁屏推送、日志、metrics 和非鉴权任务标题不得出现具体药名或剂量。

## 10. AI Behavior

- LLM 可以识别用户意图和解释失败，但不能签发确认、改变冻结 items、决定原子性或生成成功回执。
- 明确多药句在 LLM 前走确定性解析；解析不确定时回到澄清，不猜药名、数量或单位。
- 任何用药写入只有服务端返回 `decision_status=executed`，且 `write_receipts` 数量、类型和 intent 前缀与冻结计划完全一致后，才能显示“已记录”。
- confirm/dismiss、过期和提交后崩溃统一由服务端终态渲染器解释；LLM 和客户端本地动作都不能改写权威裁决。
- 旧 `health_record(medication, confirmed=true)` 一律不能作为授权源。

## 11. Acceptance Criteria

```gherkin
Given 用户说“记录服用两种胃药：伊托必利 替普瑞酮 各一粒”
When Agent 处理首轮
Then 不写 MedicationLog，显示包含两药和各 1粒 的一次确认，不显示通用缺参话术，outcome 为 confirmation_required

Given 上述批次仍 pending
When 用户点击确认或在同一会话紧接着回复“确认”
Then 同一事务写入两条 taken MedicationLog，actual_dosage 均为 1粒，并返回两个 verified write_receipts

Given 同一确认被双击、超时重试或跨分钟重放
When 服务端再次收到同一 intent id
Then 返回同一执行结果且数据库仍只有两条日志

Given 模型在首轮或无 pending 的回合提交 confirmed=true
When health_record 尝试执行 medication 写入
Then 零写入且不能显示成功

Given 计划属于另一用户、另一会话、已撤销或已过期
When 用户以隐式文本尝试确认
Then 不执行任何 MedicationLog 写入

Given confirm 和 dismiss 并发提交同一 intent
When 任一动作先完成条件更新
Then 两个请求最终都返回同一权威 decision_status；confirm 胜出时均带完整 write_receipts，dismiss 胜出时均为零写入

Given 一个未决计划已超过确认窗口
When 服务端持久化 dismissed/expired 后在返回响应前崩溃
Then 重试只恢复 expired 终态，零写入、零 LLM 调用，也不会提示用户改为确认

Given 批次第二项写入失败或同槽存在不同实际服量
When 确认事务执行
Then 整个批次回滚，状态不伪装 executed，并向用户返回可重试或需核对的明确错误
```

## 12. Verification Plan

```bash
# TEST_DATABASE_URL points to an isolated PostgreSQL database.
TEST_DATABASE_URL="$TEST_DATABASE_URL" backend/.venv/bin/python -m pytest \
  backend/tests/test_agent_medication_batch_flow.py \
  backend/tests/test_medication_intake_batch.py \
  backend/tests/test_medication_record_autocreate.py \
  backend/tests/test_write_intents_api.py \
  backend/tests/test_write_intent_medication_batch_schema.py \
  backend/tests/test_originator_drugs.py \
  backend/tests/test_medication_safety_precheck.py \
  backend/tests/test_medication_intake_batch_postgres.py -q --no-cov

DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/.venv/bin/python -m pytest \
  backend/tests/test_agent_conversations_api.py \
  backend/tests/test_agent_executor_completion_status.py \
  backend/tests/test_agent_stream_no_false_record_claim.py \
  backend/tests/test_health_record_amount_regression.py \
  backend/tests/test_inline_cards_intake_dedup.py \
  backend/tests/test_medication_record_autocreate.py \
  backend/tests/test_medication_safety_precheck.py \
  backend/tests/test_medication_timing.py \
  backend/tests/test_originator_drugs.py \
  backend/tests/test_r4_probes_observe_only.py \
  backend/tests/test_starter_pregen.py \
  backend/tests/test_write_autonomy.py \
  backend/tests/test_agent_medication_batch_flow.py \
  backend/tests/test_medication_intake_batch.py \
  backend/tests/test_medication_intake_batch_postgres.py \
  backend/tests/test_write_intent_medication_batch_schema.py \
  backend/tests/test_write_intents_api.py -q --no-cov

cd frontend && npm test && npx tsc --noEmit && npm run build
cd mobile && npx jest --runTestsByPath services/__tests__/chatCardActions.test.ts services/__tests__/chatStream.test.ts hooks/__tests__/useChatEngine.test.ts components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx components/chat/cards/__tests__/MedicationDraftCard.test.tsx components/chat/cards/__tests__/registry.test.tsx services/__tests__/conversationContinuity.test.ts --runInBand
cd mobile && npx tsc --noEmit && npm run design:check && npm run lint
swift test --package-path apps/mac --filter MedicationBatchConfirmationTests
swift test --package-path apps/mac --filter HealthAgentMacCoreTests

backend/.venv/bin/python scripts/check_doc_drift.py
git diff --check
```

## 13. Rollout And Rollback

- P0 状态修复不改数据库，可独立回滚。
- P1 复用已有 WriteIntent/MedicationLog，新增索引迁移幂等执行；旧客户端仍能提交通用 `write_intent.confirm`。
- 回滚代码后保留已执行的真实用药记录；未决 `medication_intake_batch` 不会被旧代码执行，必要时标记 dismissed。
- `decision_status` 为 nullable，旧 kind/旧响应兼容；回滚应用代码时保留列和条件唯一索引，不把 `dismissed/expired` 恢复成可执行授权。
- 发布后用精确原句做单账号真实会话验证；在两个逐项回执齐全前不宣告 G6 完成。

## 14. Open Questions

- 后续是否把单药、补剂和药物更正统一迁入同一 server-owned confirmation plan；不阻塞本切片。
- 是否为非处方的一次性历史用药增加独立 `MedicationExposure` 对象；本切片继续复用 Medication + MedicationLog。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-21 | Initial draft | 修复确认态覆盖并建立可信多药批次写入 |
| 2026-07-21 | Implementation contract closeout | 同步 `write_receipts`、持久化逻辑终态、namespaced 批次结果、双向竞态和过期崩溃恢复 |
