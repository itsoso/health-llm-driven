# Pre-App-Store Agent Reliability Closeout

> Status: executing
> Updated: 2026-07-28
> Related dossier: `docs/dossiers/2026-07-28-pre-appstore-agent-reliability-closeout.md`

## Goal

Close the remaining deterministic reliability and observability gaps in the
Mobile-first Agent conversation flow before App Store submission, without
changing health advice, write semantics, or the existing Runtime protocol.

## Work Order

1. Reuse the existing durable draft, stable `client_turn_id`, authoritative
   Turn recovery, and verified `WriteReceipt` paths instead of adding parallel
   state.
2. Add privacy-safe terminal telemetry for image attachment preparation and
   server acceptance.
3. Aggregate attachment acceptance and failure stages in the existing
   observability service with an actionable threshold.
4. Turn representative historical Agent failures into deterministic golden
   trajectories that block regressions in write honesty and idempotency.
5. Verify Mobile Run state, WriteReceipt presentation, TypeScript, backend
   event validation, aggregation, and the zero-cost Agent harness.
6. Run an independent safety review, then commit and push only the scoped
   files.
7. Deploy the backend and publish a production Mobile OTA only after all
   automated gates are green.
8. Keep App Store readiness open until TestFlight build 239 passes real-device
   image, background/resume, weak-network retry, and terminal receipt checks.

## Non-Goals

- No new medical inference or recommendation behavior.
- No image contents, prompts, responses, health text, file names, URLs, user
  IDs, Turn IDs, or record IDs in client telemetry.
- No Runtime framework migration or duplicate client state machine.
- No claim that simulator or unit tests replace real-device G6 verification.

## Verification

```bash
cd mobile
npm test -- --runInBand --runTestsByPath \
  hooks/__tests__/useChatEngine.test.ts \
  'app/(tabs)/__tests__/chat.test.tsx' \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  components/chat/__tests__/ChatTodayFocusCard.test.tsx
npx tsc --noEmit

cd ..
backend/venv/bin/python -m pytest \
  backend/tests/test_client_events.py \
  backend/tests/test_observability_client_events.py \
  backend/tests/test_observability_service.py \
  backend/tests/test_agent_trajectory_scorer.py \
  backend/tests/test_llm_synthesis_regression_gate.py
backend/venv/bin/python scripts/harness_llm_regression_gate.py --json
backend/venv/bin/python backend/scripts/check_dossier_consistency.py
backend/venv/bin/python scripts/check_doc_drift.py
git diff --check
```
