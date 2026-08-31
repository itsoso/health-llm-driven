# Feature Spec: 饮食记录渐进式响应与确定性快路径

> Status: approved
> Owner: Codex
> Updated: 2026-08-29
> Related PRD/PDD: `docs/dossiers/2026-08-29-diet-progressive-response-ttft.md`
> Related code: `backend/app/services/agent_executor.py`, `mobile/services/chat.ts`, `mobile/hooks/useChatEngine.ts`

## 1. Decision

为饮食记录提供可验证的阶段进度、内容安全的端到端时延埋点，并让明确的纯文字记餐跳过首次 LLM 工具决策，继续复用现有校验、写入、回执和卡片链路。

## 2. Problem

Mobile 已能立刻显示通用“正在理解”占位，但用户在真正收到餐食处理结果前仍会等待很久：最近 72 小时的 34 个生产样本中，总耗时 P50 为 33078ms、P90 为 73714ms，文本 TTFT P50 为 29823ms、P90 为 53222ms。多轮回合是主要长尾，而明确文字记餐仍需先等待一次 LLM 工具决策。

现有埋点没有饮食意图标签，也没有“本地反馈、首个有用进度、写入验证”里程碑，因此只能证明通用 Agent 慢，不能持续量化饮食记录的用户感知时延。若不处理，用户会把等待理解为卡死、重复提交，并增加重复健康记录风险。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 降低每次回复的用户感知等待，优先优化饮食记录
  classification: existing_core_loop_performance_and_reliability
  first_user_fit: yes
  core_loop_step: capture -> interpret -> persist -> verify
  first_class_objects: [WriteIntent, ExecutionEvent, HealthTwin]
  target_surface: [Mobile, Backend]
  source_of_truth: verified health_record write receipt
  safety_level: privacy_sensitive_health_write
  prescription_or_causal_verdict: no
  autonomy_tier: unchanged
  evidence_provenance: production content-free latency metrics and verified write receipts
  claim_hedging: nutrition remains an estimate
  verification_window: same turn plus 72-hour production percentile review
  success_metric: first useful feedback and verified-write latency percentiles
  added_user_burden: none
  burden_justification: not_applicable
  non_goals: [raw_chain_of_thought, relaxed_write_validation, automatic_low_confidence_photo_write]
  smallest_end_to_end_slice: clear text meal -> semantic progress -> normal validated write -> verified receipt -> result card
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- 不向用户展示模型原始思维链，只显示系统能够证明的阶段摘要。
- 不改变医学建议、营养估算免责声明或 App Review 引用策略。
- 不降低图片记餐置信度阈值，不绕过低置信度图片确认。
- 不让含附件、疑问、否定、复合指令或语义不明确的输入进入确定性快路径。
- 不改变数据库结构，不新增自动化写入权限。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | 继续只在已验证饮食记录写入后更新。 |
| `ExecutionEvent` | 增加内容安全的阶段与耗时里程碑。 |
| `WriteIntent` | 明确文字记餐可由确定性目标编译器生成，但仍通过既有验证和写入网关。 |

## 6. User Flow

```text
用户发送明确文字餐食
  -> Mobile 立即显示单一处理中卡片
  -> Backend 持久化请求并确认确定性饮食目标
  -> 依次发送“已识别 / 估算营养 / 正在写入”安全阶段
  -> 既有 validator + ToolGateway + write checkpoint 执行一次写入
  -> 仅在 verified receipt 后发送“已写入”及饮食结果卡
  -> Mobile 在同一处理中卡片内更新阶段，最终收口为结果
```

图片记餐继续走结构化视觉识别；低置信度结果停在待确认草稿，不进入正式饮食记录。

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 即时反馈、单卡片阶段展示、客户端里程碑 | 不展示原始思维链；不得提前显示“已记录”。 |
| Backend | 目标判定、营养估算、正常写入链、进度事件和服务端里程碑 | 只有 verified receipt 可触发成功阶段和成功文案。 |

## 8. Data Contract

```yaml
apis:
  - existing SSE chat endpoint; additive event fields only
events:
  - status.stage: diet_parsed | diet_estimating | diet_writing | diet_verified
  - status.stage: diet_photo_saved | diet_photo_recognizing | diet_photo_review
  - client event: agent_turn_milestone
models: none
fields:
  - perf.request_persisted_ms
  - perf.first_progress_ms
  - perf.first_useful_ms
  - perf.first_card_ms
  - perf.write_verified_ms
  - perf.action_type
  - perf.decision_route
  - perf.nutrition_estimate_ms
  - perf.nutrition_estimate_calls
  - perf.nutrition_estimate_timed_out
  - perf.nutrition_estimate_model
  - perf.nutrition_estimate_caller
  - perf.tool_decision_llm_rounds
  - perf.model_wait_ms
  - perf.model_call_count
enums:
  - agent_turn_milestone.phase: local_feedback | server_accepted | first_useful | write_verified
  - agent_turn_milestone.action_type: generic | diet_record | diet_photo
backward_compatibility: old clients ignore additive status stages and perf fields
migration: none
```

客户端事件只允许阶段、耗时、动作类别和是否带图；禁止携带消息、食物名、模型输出、用户标识或健康记录标识。

## 9. Safety, Privacy, And Medical Boundary

- 本功能接触饮食健康数据，继续使用现有 owner scope、目标守卫、参数验证、ToolGateway、写入检查点和回执校验。
- 营养数值仍标记为估算，不能声称诊断、处方或确定因果。
- 成功状态、成功文案和结果卡必须以本轮已验证写入回执为前提；不得用进度事件伪造写入结果。
- 埋点保持内容无关，不记录用户输入、图片、识别出的食物或健康数值。
- 图片记餐的草稿、确认、幂等和所有权边界保持不变。

## 10. AI Behavior

- 明确、单一、无附件的文字记餐由现有确定性目标编译器判断是否符合快路径。
- 快路径只跳过首次 LLM 工具决策；营养估算仍是一次单独模型调用，必须被记入模型调用次数和等待时间。
- 营养快估硬超时为 3 秒，超时需取消供应商协程并回退到现有模型恢复流程；不得让用户继续等待后台线程。
- 快路径估算或验证失败时，不得静默成功；回退期间仍继续发送可验证的饮食写入阶段。
- 其他对话、建议、复杂修改、删除以及图片确认继续走现有 Agent 编排。
- 用户只看到可审计的执行阶段摘要，不显示私有推理或隐藏提示词。

## 11. Acceptance Criteria

```gherkin
Given 用户输入一个明确且单一的文字餐食
When 系统识别为 simple_health_record/diet/create
Then 首轮不调用工具决策 LLM，并通过既有营养估算和写入链只写入一次
And 依次发送 diet_parsed、diet_estimating、diet_writing、diet_verified
And diet_verified 只在 verified receipt 后出现
And 同一 client_turn_id 重试不再次估算或写入

Given 营养快估超过 3 秒
When 确定性快路径执行
Then 取消营养模型协程并回退模型修复链
And 模型调用次数、等待时间和超时状态被如实记录

Given 用户输入含图片、问题、否定、复合要求或不明确餐食
When 系统编译目标
Then 不使用确定性文字记餐快路径，并保持现有 Agent 或图片确认流程

Given 图片记餐置信度不足
When 结构化视觉识别完成
Then 只保留 owner-scoped DietPhotoDraft 和确认卡，不写入正式 DietRecord

Given Mobile 正在接收饮食阶段事件
When 新阶段到达
Then 在同一个处理中面板更新当前阶段并保留已完成阶段，不新增多条永久助手消息

Given 任意客户端里程碑被上报
When 后端验证事件
Then 只接受允许的阶段、动作类别、整数耗时和布尔图片标记，拒绝未知或含内容字段的数据
```

初始 SLO：本地反馈 P95 ≤ 100ms；首个语义进度 P90 ≤ 1s；明确文字记餐首个有用结果 P90 ≤ 2s；写入验证 P50 ≤ 5s、P90 ≤ 10s；伪成功为 0。

## 12. Verification Plan

```bash
# Backend focused behavior and contracts
python3.12 -m pytest backend/tests/test_agent_simple_record_goal_guard.py
python3.12 -m pytest backend/tests/test_agent_executor_progress_events.py
python3.12 -m pytest backend/tests/test_client_events.py

# Mobile contracts and single-panel behavior
cd mobile && npm test -- --runInBand services/__tests__/chatStream.test.ts
cd mobile && npm test -- --runInBand services/__tests__/clientEvents.test.ts
cd mobile && npm test -- --runInBand hooks/__tests__/useChatEngine.test.ts

# Architecture and hygiene
./scripts/system-map-check.sh
git diff --check
```

发布前还需运行受影响面回归、项目集成闸、主干 CI、后端健康检查与 Mobile OTA 验证。

## 13. Rollout And Rollback

- 后端改动随正常部署发布；Mobile 的纯 JS/TS 改动通过 production OTA 发布。
- 协议是加法变更，旧客户端继续显示通用状态。
- 回滚后端可恢复 LLM 首轮决策；已写入记录不迁移、不重写。
- 回滚 Mobile 只影响阶段文案和客户端埋点，不影响数据完整性。

## 14. Open Questions

- 生产按意图分桶后的样本量达到 30 个后，是否需要按文字/图片分别收紧 SLO。
- 后续是否为其他高频、低风险的明确写入目标复用同一确定性路由框架；不属于本切片。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-29 | Initial approved spec | 用户确认按建议实施。 |
