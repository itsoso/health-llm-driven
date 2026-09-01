# Diet Progressive Response TTFT Implementation Plan

> Execution contract: follow the repository Gate sequence and record exact evidence in the related Dossier.

**Goal:** 让明确文字记餐在不削弱回执验证和图片确认边界的前提下更快，并让 Mobile 用户立即看到可验证的阶段进度。

**Architecture:** 复用现有确定性目标编译器生成首轮饮食工具计划，注入既有 Agent 执行管线；Backend 通过 SSE 发送加法阶段事件并记录内容无关里程碑；Mobile 在既有单一思考面板内更新阶段并上报白名单指标。所有成功文案继续由 verified write receipt 驱动。

**Tech Stack:** Python 3.12, FastAPI/SSE, pytest, React Native/Expo, TypeScript, Jest.

> 交互展示、终态、去重与回放发布门禁的后续统一治理见
> `docs/plans/2026-08-31-agent-interaction-quality-reliability.md`。

---

### Task 1: Freeze contracts and RED tests

**Files:**
- Modify: `backend/tests/test_agent_executor_progress_events.py`
- Modify: `backend/tests/test_agent_simple_record_goal_guard.py`
- Modify: `backend/tests/test_client_events.py`
- Modify: `mobile/services/__tests__/chatStream.test.ts`
- Modify: `mobile/services/__tests__/clientEvents.test.ts`
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`

1. Add failing tests for the new stage labels and strict client-event schema.
2. Add a failing run-stream test proving a clear text meal bypasses `_call_llm_stream`, writes once, and emits success only after a verified receipt.
3. Add failing Mobile hook tests proving dietary stages share one progress panel and milestone events emit once.
4. Run focused tests and confirm failures are caused by missing behavior, not broken fixtures.

### Task 2: Backend deterministic text-meal route

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/ai/food_recognition.py`

1. Build an eligible first-round plan only for `simple_health_record/diet/create` without attachments or an existing receipt.
2. Feed that plan through the same normalization, enrichment, validation, gateway, checkpoint, receipt, card, and deterministic completion path used today.
3. If estimation or validation fails, keep the ordinary recovery path available and surface failures honestly.
4. Cancel the nutrition provider coroutine at the 3-second budget, then fall back to the ordinary repair path.
5. Track tool-decision rounds separately from nutrition-model calls and total model wait.

### Task 3: Backend progressive stages and telemetry contract

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/api/client_events.py`
- Test: `backend/tests/test_agent_executor_progress_events.py`
- Test: `backend/tests/test_client_events.py`

1. Emit diet text stages: parsed, estimating, writing, verified.
2. Emit diet photo stages: saved, recognizing, review; preserve confirmation-required terminal behavior.
3. Add request-persisted, first-progress, first-useful, first-card and write-verified milliseconds to content-free perf data.
4. Add a strict `agent_turn_milestone` allowlist/schema; reject content-bearing or unknown fields.

### Task 4: Mobile single-panel progressive UX and milestones

**Files:**
- Modify: `mobile/services/chat.ts`
- Modify: `mobile/hooks/useChatEngine.ts`
- Modify: `mobile/services/clientEvents.ts`
- Test: `mobile/services/__tests__/chatStream.test.ts`
- Test: `mobile/services/__tests__/clientEvents.test.ts`
- Test: `mobile/hooks/__tests__/useChatEngine.test.ts`

1. Map additive diet stages to concise Chinese user-facing summaries.
2. Append prior dietary stages to the existing safe thinking-step list while keeping only one assistant progress panel.
3. Emit each client milestone at most once per turn; never include message text, food details, IDs or health values.
4. Treat first semantic dietary status/card/token as first useful feedback and verified receipt as write verified.

### Task 5: Regression, architecture, review, release

**Files:**
- Modify: `docs/dossiers/2026-08-29-diet-progressive-response-ttft.md`
- Regenerate only if required: `docs/_generated/system-map.json` and derivatives

1. Run all focused Backend and Mobile tests, then the repository's affected integration gates.
2. Run `./scripts/system-map-check.sh`, lint/type checks and `git diff --check`; regenerate the system map only if the structure contract requires it.
3. Review the complete diff for false-success, duplicate-write, owner-scope, image-confirmation and content-telemetry regressions.
4. Update Dossier gates with exact evidence.
5. Commit only changed files, push, fast-forward `main` if it has not moved, deploy Backend, publish Mobile production OTA, and verify production SHA/health plus a safe real Mobile flow.
