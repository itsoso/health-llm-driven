# XiaoBa Agent Kernel Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace scattered keyword/tool-routing decisions with a unified Agent Kernel that turns every user input into a typed intent, gates every tool through a deterministic capability policy, and only lets XiaoBa claim actions that have verifiable receipts.

**Architecture:** Model the backend after Pi-style harness boundaries: user-facing `AgentMessage` is transformed into a stable `TurnSnapshot`, converted to provider messages only at the LLM boundary, and every tool call passes through `beforeToolCall`/`afterToolCall`-like hooks. Voice and realtime inputs follow a Pipecat-style pipeline, and intent selection can later adopt semantic-router style route embeddings, but no regex or prompt rule is allowed to be the final write boundary.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, existing LLM provider registry, existing `WriteIntent`/`SafetyGuardian`, Mobile/Mac/Web SSE clients, Watch summary/actions, optional future embedding router.

---

## Why This Is Needed

The recent "列出饮食记录" false write shows a structural problem: similar text can be routed by different code paths, and each path decides intent differently. Fixing one phrase in chat does not protect Telegram, recovered textual tool calls, proactive reminders, Watch actions, or future dynamic UI cards.

The new invariant:

```text
No tool executes because a model, prompt, tool schema, keyword, or UI label suggested it.
A tool executes only after CapabilityPolicy grants it for the current TurnSnapshot.
```

## Reference Implementations

- Pi Agent Harness separates agent messages, LLM messages, turn snapshots, hooks, tool execution and lifecycle events. The useful pattern for XiaoBa is not its coding-agent domain, but its boundary design: transform context before provider calls, gate tool calls with typed hooks, and save state only at explicit turn boundaries.
- Pi's security docs also matter by contrast: Pi does not provide a built-in sandbox, so it recommends container/VM-level isolation for stronger boundaries. For XiaoBa, the equivalent lesson is that trust labels, UI state and prompt rules are not runtime safety boundaries.
- Pipecat frames realtime agents as explicit voice/multimodal pipelines. XiaoBa's realtime dictation should be ASR -> turn assembler -> intent -> LLM/tool -> response, with cancellation and backpressure as state, not component booleans.
- Semantic Router demonstrates route objects, thresholds and abstention for semantic decisions. XiaoBa can use that shape later for action routing, but ambiguous routes must return "clarify/read-only", never write.

References:

- https://github.com/earendil-works/pi
- https://github.com/earendil-works/pi/blob/main/packages/agent/docs/agent-harness.md
- https://github.com/earendil-works/pi/blob/main/packages/agent/docs/hooks.md
- https://github.com/earendil-works/pi/blob/main/packages/agent/docs/observability.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/security.md
- https://github.com/pipecat-ai/pipecat
- https://docs.pipecat.ai/guides/learn/pipecat-flows
- https://github.com/aurelio-labs/semantic-router

## Current Risk Inventory

| Risk | Current Evidence | Target Control |
|---|---|---|
| Multiple intent sources | `agent_executor.py`, `telegram_inbound.py`, `intake_intent_classifier.py`, `tool_validator.py` all infer intent or record scope. | One `IntentFrame` module consumed by every entry surface. |
| Keyword write routing | Telegram treats any `_RECORD_HINTS` hit as `record`, including noun phrases with "记录". | Entry adapters can classify, but cannot grant writes. |
| Tool exposure as control | Fast/read turns remove tools from the schema, but textual tool-call recovery can resurrect tool calls. | ToolGateway policy applies after recovery and before execution. |
| Name-only read/write split | `health_manage` can be `list` or `update/delete`; `health_record` includes reminders and actions. | Capability policy evaluates tool name plus normalized args. |
| Monolithic executor | `agent_executor.py` owns prompt build, streaming, recovery, tool normalization, execution, cards and receipts. | Extract kernel modules behind stable APIs before deleting legacy branches. |
| Side-channel bypass | Telegram, Watch, Rokid, proactive reminders and card actions are not guaranteed to share chat's gates. | All surfaces submit `AgentEnvelope` or `ToolExecutionRequest`. |
| Time ambiguity | Current time is injected in some prompts/tools but not a first-class execution parameter everywhere. | `ExecutionContext` always carries current ISO time and timezone. |
| Receipt ambiguity | Some flows have `WriteIntent`, some use tool result strings, some rely on UI completion. | Every write returns `ToolExecutionResult.receipt` or fails closed. |
| Observability gaps | Logs exist, but there is no one causal trace from intent to capability to receipt. | Turn event stream mirrors Pi lifecycle spans. |
| Realtime state drift | ASR, hold-to-talk, live dictation and app background rules are split across clients and backend. | Voice pipeline state is explicit and feeds the same kernel. |

## Target Architecture

```text
Surface Adapter
  Mobile / Mac / Web / Watch / Telegram / Rokid / proactive
        |
        v
AgentEnvelope
  user_id, channel, text, media, source ids, client capabilities
        |
        v
ExecutionContext
  current_time_iso, timezone, user profile, health summary, safety tier
        |
        v
IntentFrame
  primary=read/write/mutate/advice/chat/unknown
  domain=diet/water/medication/supplement/metric/reminder/general
  operation=list/create/update/delete/analyze/ask
  confidence, evidence, ambiguity flags
        |
        v
TurnSnapshot
  immutable per provider request
        |
        +----> LLM context transform -> provider messages -> model output
        |
        v
ToolGateway
  parse/recover -> validate args -> CapabilityPolicy -> execute -> receipt -> SafetyGuardian
        |
        v
TurnEventBus + response/cards
```

## Kernel Contracts

```python
class AgentEnvelope:
    user_id: int
    channel: str
    text: str
    media: list[dict]
    source_message_id: str | None
    client_capabilities: dict

class ExecutionContext:
    current_time_iso: str
    timezone: str
    user_id: int
    channel: str
    safety_level: str
    autonomy_tier: str

class IntentFrame:
    primary: str
    domain: str
    operation: str
    confidence: float
    evidence: list[str]
    ambiguity: list[str]
    is_write: bool

class CapabilityDecision:
    action: str  # allow | block | require_confirm | ask_clarify | downgrade_to_read
    reason: str
    normalized_tool_name: str | None
    normalized_args: dict | None
    receipt_required: bool
```

## Execution Rules

- Entry adapters may enrich context, but cannot execute health tools directly.
- Tool schema subsetting improves model behavior, but never replaces capability policy.
- Textual tool-call recovery is a parser only. It never authorizes execution.
- `health_manage(list)` is read-only; `health_manage(update/delete)` is write.
- Ambiguous write/read collisions become read-only or clarification.
- Every prompt/tool receives the same `ExecutionContext.current_time_iso` and `timezone`.
- XiaoBa's final answer is checked against tool receipts before claiming completion.
- Watch/notification wording cannot claim device delivery without device/client receipt.

## Implementation Phases

### Phase 0: Audit Harness And Regression Corpus

**Goal:** Freeze known false-write cases and surface-local bypasses before changing runtime.

**Files:**
- Add: `backend/tests/test_agent_kernel_intent_corpus.py`
- Add: `backend/tests/fixtures/agent_intent_corpus.json`
- Modify: `backend/tests/test_utterance_intent_classifier.py`

**Steps:**

1. Add corpus rows for "今天我的饮食记录, 帮我列个表格出来", "不是记录, 是列出", "帮我记录午餐", "删除上一餐", "我记录里有哪些饮食".
2. Assert each row maps to expected `IntentFrame.primary/domain/operation/is_write`.
3. Include channel variants for chat, Telegram and voice transcript.
4. Run the focused tests and confirm they fail where current non-shared paths bypass the classifier.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_intent_corpus.py \
  backend/tests/test_utterance_intent_classifier.py \
  -q --no-cov
```

### Phase 1: Agent Kernel Types And Shared IntentFrame

**Goal:** Promote the current semantic classifier into a stable kernel API.

**Files:**
- Add: `backend/app/services/agent_kernel/__init__.py`
- Add: `backend/app/services/agent_kernel/types.py`
- Add: `backend/app/services/agent_kernel/intent_frame.py`
- Modify: `backend/app/services/utterance_intent_classifier.py`
- Test: `backend/tests/test_agent_kernel_intent_frame.py`

**Steps:**

1. Define `AgentEnvelope`, `ExecutionContext`, `IntentFrame`, `CapabilityDecision`, `ToolExecutionRequest` and `ToolExecutionResult`.
2. Wrap `classify_agent_utterance` with `build_intent_frame(envelope, context)`.
3. Preserve existing classifier behavior, but expose evidence and ambiguity flags.
4. Add tests proving no regular expression or keyword hit is sufficient to set `is_write=True` when read/list/table action dominates.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_intent_frame.py \
  backend/tests/test_utterance_intent_classifier.py \
  -q --no-cov
```

### Phase 2: CapabilityPolicy As The Only Write Gate

**Goal:** Decide allow/block/confirm/downgrade by snapshot, tool name and arguments.

**Files:**
- Add: `backend/app/services/agent_kernel/capability_policy.py`
- Test: `backend/tests/test_agent_kernel_capability_policy.py`

**Steps:**

1. Implement `decide_tool_capability(snapshot, request)`.
2. Block `health_record` when `IntentFrame.primary` is read/advice/chat/unknown.
3. Allow `health_manage(list)` for read/advice turns and block/demand confirmation for update/delete unless the intent is mutate.
4. Require receipts for `health_record`, `health_manage(update/delete)` and `intervention_cycle`.
5. Add a `policy_mode=shadow|enforce` setting so production can observe first.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_health_manage_date_normalize.py \
  backend/tests/test_force_record_tool_choice.py \
  -q --no-cov
```

### Phase 3: ToolGateway Wrapper

**Goal:** Put one preflight/postflight wrapper around structured and recovered textual tool calls.

**Files:**
- Add: `backend/app/services/agent_kernel/tool_gateway.py`
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_agent_kernel_tool_gateway.py`
- Test: `backend/tests/test_generic_tool_tag_leak.py`
- Test: `backend/tests/test_force_record_tool_choice.py`

**Steps:**

1. Create `ToolGateway.execute(request, snapshot, executor)` with parse, validation, policy, execution, receipt and post-safety hooks.
2. Keep existing `_exec_health_record`, `_exec_health_manage` and validators, but call them only from ToolGateway.
3. Route `_extract_inline_tool_call` and XML/bracket/bare recoveries into ToolGateway; recovery may produce a request, not a grant.
4. Emit `agent.tool_blocked` when a recovered textual tool call is blocked.
5. Ensure blocked calls are not appended as successful tool results.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_tool_gateway.py \
  backend/tests/test_generic_tool_tag_leak.py \
  backend/tests/test_force_record_tool_choice.py \
  backend/tests/test_agent_stream_no_false_record_claim.py \
  -q --no-cov
```

### Phase 4: Surface Adapter Migration

**Goal:** Remove surface-local write routing from Telegram and align Watch/Rokid/proactive actions with the same envelope/policy.

**Files:**
- Modify: `backend/app/services/telegram_inbound.py`
- Modify: `backend/app/services/voice_command_service.py`
- Modify: `backend/app/services/wearable_router.py`
- Modify: `backend/app/services/reminder_delivery_status.py`
- Test: `backend/tests/test_telegram_inbound_intent_gate.py`
- Test: `backend/tests/test_watch_summary.py`
- Test: `backend/tests/test_watch_actions.py`

**Steps:**

1. Replace Telegram `_RECORD_HINTS` routing with `AgentEnvelope` + `IntentFrame`.
2. For record-looking but ambiguous Telegram text, reply with clarification rather than calling `llm_extract_record`.
3. Ensure voice transcript and manual text use identical intent frames.
4. Ensure Watch actions accept only registered action IDs and never free-form health tools.
5. Keep delivery wording tied to `delivery_status` receipts.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_telegram_inbound_intent_gate.py \
  backend/tests/test_realtime_speech_transcription.py \
  backend/tests/test_watch_summary.py \
  backend/tests/test_watch_actions.py \
  backend/tests/test_health_manage_date_normalize.py \
  -q --no-cov
```

### Phase 5: TurnSnapshot And Event Bus

**Goal:** Make time, channel, user context and tool decisions immutable within a provider request, then trace every turn.

**Files:**
- Add: `backend/app/services/agent_kernel/context.py`
- Add: `backend/app/services/agent_kernel/events.py`
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_agent_kernel_turn_snapshot.py`
- Test: `backend/tests/test_agent_event_stream.py`

**Steps:**

1. Build `ExecutionContext` once per turn from server time and user timezone.
2. Inject `current_time_iso` and timezone into every time-sensitive prompt through one helper.
3. Emit lifecycle events: turn start, intent decision, capability decision, tool requested, tool result, receipt verified, turn end.
4. Persist or log events with `run_id`, `turn_id`, `user_id`, `channel` and `policy_mode`.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_turn_snapshot.py \
  backend/tests/test_agent_event_stream.py \
  backend/tests/test_agent_system_time_context.py \
  -q --no-cov
```

### Phase 6: Dynamic UI Action Policy

**Goal:** Treat action cards as capability-bound atomic abilities, not arbitrary frontend commands.

**Files:**
- Modify: `backend/app/services/inline_cards.py`
- Modify: `mobile/services/chatCardActions.ts`
- Modify: `mobile/components/chat/cards/*`
- Test: `backend/tests/test_inline_cards.py`
- Test: `mobile/__tests__/chatCardActions.test.ts`

**Steps:**

1. Add `capability_id`, `required_receipt`, `autonomy_tier` and `policy_reason` to backend card action payloads.
2. Make Mobile/Mac/Web dispatch card actions through registered backend endpoints only.
3. Keep closed atomic components, but require backend policy metadata for executable actions.
4. Remove duplicate or route-conflicting actions such as separate "看下一餐建议" and "问小巴下一餐" when they invoke the same dynamic flow.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_inline_cards.py -q --no-cov
cd mobile && npm test -- --runInBand chatCardActions
```

### Phase 7: Retire Legacy Gates

**Goal:** Delete or demote old regex/keyword gates after coverage proves every caller uses the kernel.

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/intake_intent_classifier.py`
- Modify: `backend/app/services/telegram_inbound.py`
- Test: `backend/tests/test_agent_ops_registry.py`

**Steps:**

1. Replace route gates that still depend on local `_RECORD_*`, `_QUERY_*`, `_DESTRUCTIVE_*` rules with kernel calls.
2. Keep domain entity parsing where needed, but prevent it from deciding write permission.
3. Add a static regression test that fails when any direct call to `_exec_health_record` or `_exec_health_manage` appears outside ToolGateway-approved files.
4. Remove obsolete tests that assert old regex details; replace them with intent-frame/policy expectations.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_ops_registry.py \
  backend/tests/test_agent_kernel_static_coverage.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  -q --no-cov
backend/venv/bin/python -m ruff check backend/app/services/agent_executor.py backend/app/services/agent_kernel
```

### Phase 8: Rollout, Metrics And Release Gate

**Goal:** Ship safely and prove the false-write class is closed.

**Files:**
- Modify: `docs/dossiers/2026-07-17-xiaoba-agent-kernel.md`
- Modify: release checklist docs if needed

**Steps:**

1. Run policy in shadow mode for one deploy and inspect disagreements.
2. Enable enforce mode for write tools only.
3. Run backend focused regressions, Mobile/Mac smoke and Watch tests.
4. Deploy backend.
5. OTA Mobile if card/action contracts changed.
6. Verify production health and sample traces.

**Verify:**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_agent_kernel_intent_frame.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_agent_kernel_tool_gateway.py \
  backend/tests/test_health_manage_date_normalize.py \
  backend/tests/test_force_record_tool_choice.py \
  backend/tests/test_telegram_inbound_intent_gate.py \
  -q --no-cov
backend/venv/bin/python -m ruff check backend/app/services/agent_kernel backend/app/services/agent_executor.py backend/app/services/telegram_inbound.py
git diff --check
./deploy.sh -b
```

## Acceptance Criteria

- All executable health tools pass through ToolGateway.
- All entry surfaces use `AgentEnvelope` and `IntentFrame`.
- Read/list/table/analysis turns cannot create or mutate health records.
- Textual tool-call recovery cannot bypass policy.
- Every write claim in final answer maps to a verified receipt.
- Current time and timezone are available in every time-sensitive prompt and tool normalization path.
- Watch delivery wording remains receipt-honest.
- Dynamic UI cards expose atomic actions with capability metadata.

## Rollback

- Keep `AGENT_KERNEL_POLICY_MODE=shadow` as a production fallback.
- If enforcement blocks valid writes, switch back to shadow while retaining event logs.
- ToolGateway extraction must be additive until Phase 7, so old executor methods remain callable internally during rollback.
