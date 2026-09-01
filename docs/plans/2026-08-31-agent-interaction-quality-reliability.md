# Agent Interaction Quality and Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除健康 Agent 对话中的正文污染、重复执行、状态误报和长尾时延，让每一轮回答都可渲染、可验证、可恢复，并在健康安全边界内提供足够的信息密度。

**Architecture:** Backend 是回合状态、工具结果和 verified receipt 的唯一真源；Mobile 只消费规范化正文和权威终态。所有回答入口复用一条内容清洗管线，所有写操作按动作拆分并逐项返回结果。只读问题使用基于请求指纹的数据复用和快速路由，复杂报告使用明确的模型调用和输出预算。

**Tech Stack:** Python 3.12, FastAPI/SSE, SQLAlchemy/PostgreSQL, pytest, React Native/Expo, TypeScript, Jest.

---

## Production baseline (sanitized)

The latest 20 production interactions for the audited account were reviewed on 2026-09-01 server time. Raw health text, user identifiers, image payloads, and credentials are intentionally excluded from this plan.

- 20 user turns contained 17 distinct input strings; the same meal-photo request was submitted four times.
- Run-level outcomes were 15 `succeeded`, 4 `waiting_for_user`, and 1 `failed`.
- 18 assistant messages were marked `complete`, including turns whose run was waiting, blocked, or failed; this is a terminal-state contract mismatch.
- Average total latency was 42.2s, P50 26.3s, and P95 99.4s. Median first useful feedback was 15.9s.
- The sample recorded 11 blocked tool decisions and 13 tool failures.
- Two replies contained hundreds of literal `<br>` fragments; one contained hundreds of isolated `.` lines.
- The longest report took about 213s, used four model calls, and persisted roughly 213k characters.
- The screenshot failure-recovery turn matches the audited sample and has no verified write receipt for the claimed follow-up action.

### Facts, inferences, and unknowns

- **Facts:** malformed fragments are persisted in assistant content; the same image request can produce confirmation, success, and failure outcomes; run and assistant terminal states disagree; ordinary questions frequently use two model calls.
- **Likely causes:** no canonical HTML/placeholder normalizer, no semantic duplicate suppression, overly expensive routing for simple/no-data turns, and a missing output-size/quality gate before persistence.
- **Unknowns to resolve during implementation:** whether the malformed fragments originate in the provider response, an intermediate stream adapter, or a retry/placeholder path; whether repeated image submissions are user retries or client auto-resubmits.

## Scope and non-goals

In scope:

- Assistant content normalization and malformed-output rejection.
- Consistent run/completion/receipt semantics across Backend, SSE, and Mobile.
- Semantic turn dedupe, in-flight coalescing, and image-task dedupe.
- Fast paths and output budgets for simple, no-data, clarification, and image-confirmation turns.
- Evidence-rich processing summaries and health-safety guard coverage.

Non-goals:

- No database migration unless the existing idempotency contract cannot express the required key.
- No change to medical diagnosis, medication dosage, or clinical thresholds.
- No automatic execution of a write without the existing authorization and receipt contract.
- No storage of raw production conversations or health payloads in tests or documentation.

### Task 1: Freeze malformed-output fixtures and terminal-state contracts

**Files:**
- Create: `mobile/utils/__tests__/assistantContentNormalizer.test.ts`
- Modify: `mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx`
- Modify: `mobile/components/reva/__tests__/RevaAgentView.test.tsx`
- Modify: `mobile/services/__tests__/chatStream.test.ts`
- Modify: `backend/tests/test_agent_turn_outcome.py`
- Modify: `backend/tests/test_agent_executor_completion_status.py`

**Step 1: Write failing content tests**

Add redacted fixtures for:

- repeated `<br>`, `<br/>`, and `<br />`;
- repeated isolated punctuation lines;
- malformed/unsupported `reva-ui` fences;
- an oversized answer;
- a valid Markdown answer that must remain unchanged.

Assert that no literal HTML break, punctuation flood, raw protocol JSON, or empty answer reaches the rendered surface.

**Step 2: Write failing state tests**

Assert that:

- `waiting_for_user` is not rendered as `complete`;
- `tool_blocked`, `tool_failed`, and `model_refusal` retain their reason codes;
- a write without a verified receipt cannot be shown as executed;
- partial multi-action writes expose per-action status;
- an uncertain write is not automatically retryable.

**Step 3: Run focused tests and verify RED**

```bash
cd mobile && npm test -- --runInBand utils/__tests__/assistantContentNormalizer.test.ts services/__tests__/chatStream.test.ts
cd ../backend && venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_turn_outcome.py tests/test_agent_executor_completion_status.py
```

Expected: failures identify the missing normalizer and state mapping, not fixture or environment errors.

### Task 2: Implement one canonical assistant-content pipeline

**Files:**
- Create: `mobile/utils/assistantContentNormalizer.ts`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/components/reva/RevaAgentView.tsx`
- Modify: `mobile/utils/revaUiBlocks.ts`
- Modify: `mobile/utils/safeMarkdown.ts`
- Test: `mobile/utils/__tests__/assistantContentNormalizer.test.ts`
- Test: `mobile/components/reva/__tests__/RevaAgentView.test.tsx`

**Step 1: Implement the smallest normalizer**

The normalizer must:

1. Convert `<br\s*/?>` to a newline.
2. Normalize repeated blank lines without deleting meaningful paragraph breaks.
3. Remove only lines consisting solely of a repeated placeholder token after a bounded threshold; ordinary punctuation remains valid.
4. Extract supported `reva-ui` blocks through the existing descriptor parser.
5. Replace malformed protocol blocks with a readable fallback, never raw JSON.
6. Enforce a bounded display length and return a quality flag for telemetry.

**Step 2: Integrate every assistant surface**

`ChatBubble`, `RevaAgentView`, history reload, streaming `done`, copy/share/TTS, and accessibility labels must use the same normalized text. Do not maintain a second Reva-only parser.

**Step 3: Run the focused tests and verify GREEN**

```bash
cd mobile && npm test -- --runInBand utils/__tests__/assistantContentNormalizer.test.ts components/chat/__tests__/ChatBubbleStreaming.test.tsx components/reva/__tests__/RevaAgentView.test.tsx
```

### Task 3: Make run and assistant terminal states authoritative

**Files:**
- Modify: `backend/app/services/agent_turn_outcome.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/api/agent.py`
- Modify: `mobile/services/chat.ts`
- Modify: `mobile/utils/agentTurnState.ts`
- Modify: `mobile/hooks/useChatEngine.ts`
- Test: `backend/tests/test_agent_turn_outcome.py`
- Test: `backend/tests/test_agent_executor_completion_status.py`
- Test: `mobile/utils/__tests__/agentTurnState.test.ts`
- Test: `mobile/hooks/__tests__/useChatEngine.test.ts`

**Step 1: Define an additive outcome envelope**

Use explicit values such as `complete`, `waiting_for_user`, `blocked`, `failed`, `refused`, and `reconciliation_required`. Include `reason_code`, `retryable`, `dispatch_started`, and `verified_receipt_count` without exposing internal stack traces.

**Step 2: Enforce write truthfulness**

- `complete` for a write requires a verified receipt for every claimed action.
- A blocked or failed write cannot be described as executed.
- Multi-action turns return an action list with independent status and recovery guidance.
- Missing receipt is fail-closed and not safe for blind resubmission.

**Step 3: Make Mobile consume the envelope**

The reducer waits for authoritative `done`/runtime state, preserves intermediate tool evidence, and only renders retry when `retryable=true` and the server provides a safe retry mode.

**Step 4: Run focused tests and verify GREEN**

```bash
cd backend && venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_turn_outcome.py tests/test_agent_executor_completion_status.py
cd ../mobile && npm test -- --runInBand utils/__tests__/agentTurnState.test.ts hooks/__tests__/useChatEngine.test.ts services/__tests__/chatStream.test.ts
```

### Task 4: Add semantic turn and image-request idempotency

**Files:**
- Modify: `backend/app/api/agent.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/agent_turn_retry.py`
- Modify: `mobile/services/chat.ts`
- Modify: `mobile/hooks/useChatEngine.ts`
- Test: `backend/tests/test_agent_runtime_idempotency.py`
- Test: `backend/tests/test_agent_turn_retry.py`
- Test: `mobile/hooks/__tests__/useChatEngine.test.ts`

**Step 1: Write failing dedupe tests**

Cover:

- same user, conversation, normalized request, and data version within a short window returns the existing result;
- an in-flight duplicate attaches to the existing run instead of creating a second model call;
- a different request or changed data version creates a new run;
- the same image hash and intent does not run recognition twice;
- a prior uncertain write is never silently replayed.

**Step 2: Implement the smallest key contract**

Use the existing `client_turn_id` for exact idempotency and add a bounded semantic fingerprint for read-only requests. Image dedupe must include owner scope, conversation scope, image hash, and intent. Do not dedupe across users or unrelated conversations.

**Step 3: Run focused tests and verify GREEN**

```bash
cd backend && venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_runtime_idempotency.py tests/test_agent_turn_retry.py
cd ../mobile && npm test -- --runInBand hooks/__tests__/useChatEngine.test.ts
```

### Task 5: Introduce fast lanes and explicit output budgets

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/agent_turn_outcome.py`
- Modify: `backend/app/api/agent.py`
- Modify: `backend/app/config.py`
- Modify: `mobile/hooks/useChatEngine.ts`
- Test: `backend/tests/test_agent_executor_latency_routing.py`
- Test: `backend/tests/test_agent_output_quality_gate.py`
- Test: `mobile/hooks/__tests__/useChatEngine.test.ts`

**Step 1: Write failing routing/budget tests**

Assert that:

- incomplete one-character input asks for clarification without loading health context;
- a no-data read produces a short deterministic answer without a second synthesis call;
- image recognition failure produces a confirmation-safe recovery path;
- simple numeric/time queries use the fast model and bounded output;
- complex reports have a hard output budget and section-level truncation.

**Step 2: Implement fast paths and budgets**

- Route clarification, empty-result, and confirmation turns before deep synthesis.
- Escalate to the heavy model only for an admitted complex/high-stakes task.
- Bound model output and reject a response that exceeds the persistence budget.
- Keep first-progress telemetry separate from first-useful answer telemetry.

**Step 3: Add quality telemetry**

Record content-free fields for route, model-call count, dedupe hit, output quality flags, first progress, first useful, and total time. Never include raw health text, image data, or secrets.

**Step 4: Run focused tests and verify GREEN**

```bash
cd backend && venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_executor_latency_routing.py tests/test_agent_output_quality_gate.py
```

### Task 6: Improve evidence density and health-safety boundaries

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/guidance_validator.py`
- Modify: `backend/app/orchestrator/orchestrator.py`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/components/reva/RevaAgentView.tsx`
- Test: `backend/tests/test_guidance_validator.py`
- Test: `backend/tests/test_agent_safety_routing.py`
- Test: `mobile/components/chat/__tests__/ChatBubble.test.tsx`

**Step 1: Replace generic processing labels**

Processing summaries must report source, time range, row count/availability, failure reason, and next action. A phase label alone is not sufficient evidence.

**Step 2: Add clarification guards**

An incomplete utterance must not inherit a prior health intent automatically. Natural-language facts such as caffeine intake and sleep onset should become a structured, user-confirmable draft rather than a generic write failure.

**Step 3: Tighten medical-boundary output**

Medication, supplement, ulcer, examination, and follow-up advice must distinguish user-provided facts, retrieved evidence, model inference, and clinician-confirmed instructions. Do not generate a new dose or claim a medication action was scheduled without an authorized write receipt.

**Step 4: Run focused safety tests and verify GREEN**

```bash
cd backend && venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_guidance_validator.py tests/test_agent_safety_routing.py
cd ../mobile && npm test -- --runInBand components/chat/__tests__/ChatBubble.test.tsx components/reva/__tests__/RevaAgentView.test.tsx
```

### Task 7: Replay the sanitized 20-turn corpus and release with gates

**Files:**
- Create: `backend/tests/fixtures/agent_interaction_quality/README.md`
- Create: `scripts/replay_agent_interaction_quality.py`
- Modify: `docs/dossiers/2026-08-31-complex-latency-recovery-safety-routing.md`
- Modify: `docs/plans/2026-08-29-diet-progressive-response-ttft.md` (cross-link only, if needed)

**Step 1: Build a sanitized replay corpus**

Use only intent labels, output-shape markers, timing buckets, and synthetic health values. Do not commit production text, images, user IDs, tokens, or database dumps.

**Step 2: Define acceptance thresholds**

- Literal `<br>` and placeholder floods: 0/100 replayed assistant surfaces.
- Raw protocol leakage: 0/100.
- Run/assistant terminal mismatch: 0.
- Write claim without verified receipt: 0.
- Duplicate read/image execution inside the dedupe window: <1%.
- Simple read P95 TTFT: ≤5s target.
- Routine health answer P95 TTFT: ≤10s target.
- Complex report P95 total: ≤30s target, with a bounded and readable answer.
- Safety regression: no unreviewed medication/dosage execution path.

**Step 3: Run repository verification**

```bash
./scripts/system-map-check.sh
git diff --check
cd backend && venv/bin/python -m pytest -q --no-cov -p no:cacheprovider
cd ../mobile && npm test -- --runInBand
npm run typecheck
```

Run the project CI-mode integration gate and verify the target `main` revision is green before any deployment.

**Step 4: Release in separated layers**

1. Commit only the implementation/test/documentation files for this plan.
2. Push and verify the remote revision.
3. Deploy Backend and verify health plus production response metadata.
4. Publish Mobile OTA only if Mobile files changed and runtime/native boundaries remain unchanged.
5. Replay the three representative paths: simple read, image confirmation, and high-stakes health question.

**Step 5: Rollback conditions**

Immediately disable the affected feature flag and stop rollout if any of these occurs:

- a literal protocol/placeholder reaches the user surface;
- a write is claimed without a receipt;
- duplicate execution is observed;
- high-stakes advice becomes less conservative;
- P95 latency or answer quality regresses beyond the baseline.

## Related plans

- `docs/plans/2026-08-29-diet-progressive-response-ttft.md` — dietary progressive feedback and TTFT.
- `docs/plans/2026-07-28-agent-write-recovery.md` — write recovery and retry authority.
- `docs/plans/2026-07-31-record-write-outcome-reliability.md` — authoritative write outcome contract.
- `docs/dossiers/2026-08-31-complex-latency-recovery-safety-routing.md` — existing recovery-data routing and latency evidence.
