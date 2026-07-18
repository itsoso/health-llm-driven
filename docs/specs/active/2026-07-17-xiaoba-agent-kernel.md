# Feature Spec: XiaoBa Agent Kernel

> Status: draft
> Owner: Codex
> Updated: 2026-07-17
> Related PRD/PDD: `docs/plans/2026-07-17-xiaoba-agent-kernel-redesign.md`
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/utterance_intent_classifier.py`

## 1. Decision

Build a unified XiaoBa Agent Kernel so every surface routes user language through the same semantic intent, capability policy, tool execution and receipt boundary.

## 2. Problem

Recent failures show the same root problem: user text can be interpreted by several independent gates. Chat has a semantic classifier, but Telegram still uses keyword routing, `agent_executor.py` still owns text tool-call recovery and tool subsets, and validators only check tool arguments after a tool has already been chosen.

If we only patch each phrase, read-only requests such as "列出今天的饮食记录" can still become writes on another surface, in textual tool recovery, or through a future proactive/Watch entry point.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "审计类似误判风险, 参考开源 Pi, 重新设计和优化 Agent 系统"
  classification: product_infrastructure
  first_user_fit: high
  core_loop_step: Chat/Mobile/Mac/Watch/Telegram input -> intent -> tool/action -> receipt -> explanation
  first_class_objects:
    - WriteIntent
    - ExecutionEvent
    - SafetyGuardian
    - HealthAgendaItem
  target_surface:
    - Backend Agent
    - Mobile Chat
    - Mac Chat
    - Web Chat
    - Watch
    - Telegram/Rokid adapters
  source_of_truth: backend Agent Kernel
  safety_level: L3 health data, write boundary
  prescription_or_causal_verdict: no
  autonomy_tier: manual_confirm by default; read-only for ambiguous intent
  evidence_provenance: deterministic context snapshot + tool receipts
  claim_hedging: every write claim requires verified receipt
  verification_window: before deployment, then shadow-mode production metrics
  success_metric: zero false write for read/list/table/analysis utterances in regression corpus
  added_user_burden: none for clear intents; clarification only for ambiguous writes
  burden_justification: clarification protects health record integrity
  non_goals:
    - automatic diagnosis or prescription
    - direct Watch APNs delivery claims without receipt
    - replacing all health tools in one migration
  smallest_end_to_end_slice: one central IntentFrame and CapabilityPolicy gate used by chat and Telegram before any health_record/health_manage call
  stale_surface_to_remove_or_archive: surface-local keyword routing and name-only tool allowlists as safety boundaries
  spec_required: yes
```

## 4. Non-Goals

- Do not let an LLM freely create new tool names, UI actions or write paths.
- Do not use prompt text, tool descriptions, route names or UI labels as the safety boundary.
- Do not remove existing `WriteIntent`, `SafetyGuardian`, tool validators or receipts; the kernel composes them.
- Do not make ambiguous user text write by default.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthAgendaItem` | Receives actions only after capability policy grants the surface/channel. |
| `LeverageAction` | Becomes an executable action with an explicit capability decision. |
| `SafetyGuardian` | Runs after any verified write and can block/annotate risky outputs. |
| `ExecutionEvent` | Stores intent, tool request, policy decision, receipt and final outcome. |
| `WriteIntent` | Remains the manual confirmation object for create/update/delete. |

## 6. User Flow

```text
user text / voice / card action
  -> AgentEnvelope(channel, user, media, client caps)
  -> ExecutionContext(current time, timezone, user profile, source)
  -> IntentFrame(primary intent, domain, operation, confidence)
  -> CapabilityPolicy(allow / block / require_confirm / ask_clarify)
  -> ToolGateway(validate args, execute, receipt, safety)
  -> response + dynamic UI + audit events
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Watch | Execute known agenda/reminder actions only. | No free-form write tool execution; every completion posts a receipt. |
| Mobile | Primary chat and dynamic UI. | Never infers write completion from text; relies on backend receipts. |
| Mac | Same chat semantics as Mobile. | Same SSE event grammar and capability decisions. |
| Web | Render dynamic cards and admin/debug traces. | Cannot bypass backend policy through card actions. |
| Backend | Sole authority for intent, capability, tool execution and receipts. | All tools run through ToolGateway. |
| External agents | Adapt inbound messages. | Must submit `AgentEnvelope`; no local keyword write routing. |

## 8. Data Contract

```yaml
apis:
  - no breaking public API in first slice
events:
  - agent.turn_start
  - agent.intent_decided
  - agent.capability_decided
  - agent.tool_requested
  - agent.tool_allowed
  - agent.tool_blocked
  - agent.tool_result
  - agent.write_receipt_verified
  - agent.turn_end
models:
  - AgentEnvelope
  - ExecutionContext
  - TurnSnapshot
  - IntentFrame
  - CapabilityDecision
  - ToolExecutionRequest
  - ToolExecutionResult
fields:
  - current_time_iso
  - timezone
  - channel
  - client_capabilities
  - autonomy_tier
  - policy_reason
enums:
  - primary_intent: read | write | mutate | advice | chat | unknown
  - capability_action: allow | block | require_confirm | ask_clarify | downgrade_to_read
backward_compatibility:
  - existing tool schemas remain stable
migration:
  - wrap existing AgentExecutor paths first, then extract modules
```

## 9. Safety, Privacy, And Medical Boundary

This feature touches health records, reminders, medications, supplements, labs and user context. It must preserve user ownership checks and L3 health privacy.

- Ambiguous intent defaults to read-only or clarification, not write.
- `health_manage(list)` is read-only; `health_manage(update/delete)` is write.
- Every create/update/delete must have a deterministic receipt before XiaoBa says it completed.
- Push/watch language must not claim delivery without client or device receipt.
- All current-time dependent prompts/tools receive `ExecutionContext.current_time_iso` and `timezone`.

## 10. AI Behavior

The LLM may explain, synthesize and propose actions. It must not be the final authority for write permission.

Deterministic checks:

- Before LLM/tool: build `IntentFrame` and `TurnSnapshot`.
- Before tool execution: run `CapabilityPolicy`.
- After tool execution: validate receipt and run SafetyGuardian where applicable.
- Before final response: ensure claimed actions match verified receipts.

Failures degrade to clarification or read-only explanation.

## 11. Acceptance Criteria

```gherkin
Given a user says "今天我的饮食记录, 帮我列个表格出来"
When any surface submits the turn
Then no health_record create is allowed and any health_manage call is list-only

Given a model emits textual "health_record(...)" during a read-only turn
When ToolGateway receives the recovered call
Then the policy blocks it before execution and records the block reason

Given a Telegram message contains "记录" as a noun
When it is processed
Then Telegram uses the shared IntentFrame instead of local keyword routing

Given a reminder is created for Watch
When no Watch visibility receipt exists
Then XiaoBa says it was created and can appear after refresh, not that it was delivered to Watch

Given a write succeeds
When the final answer is generated
Then the answer can cite only the verified resource IDs or executed refs from the receipt
```

## 12. Verification Plan

```bash
# Backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_utterance_intent_classifier.py \
  backend/tests/test_health_manage_date_normalize.py \
  backend/tests/test_force_record_tool_choice.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_agent_kernel_tool_gateway.py \
  backend/tests/test_telegram_inbound_intent_gate.py \
  -q --no-cov

# Static
backend/venv/bin/python -m ruff check backend/app/services/agent_kernel backend/app/services/telegram_inbound.py backend/app/services/agent_executor.py
git diff --check
```

## 13. Rollout And Rollback

- Phase 1 ships in shadow mode: log policy decisions while preserving existing behavior for low-risk reads.
- Phase 2 enables fail-closed blocking for write tools on Chat and Telegram.
- Phase 3 migrates Watch/Rokid/proactive adapters.
- Rollback flag: disable new gateway enforcement and fall back to existing tool execution, keeping logging enabled.

## 14. Open Questions

- Whether semantic routing should use local embeddings immediately or start with the current semantic frame plus LLM adjudication for ambiguous cases.
- Whether all `ExecutionEvent` rows need durable database storage in the first slice or can begin as structured logs.
- Whether Mac/Web should expose policy traces in developer mode only or also in a collapsed user-facing "依据与过程".

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-17 | Initial draft | User requested system-level redesign after intent false-write risk. |
