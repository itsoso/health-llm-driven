# Diet Card Single Projection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure one logical diet card is persisted and rendered after a diet record while preserving legitimate multi-card turns.

**Architecture:** Canonicalize server descriptors before persistence deduplication, treat existing intake cards and deterministic GenUI as authoritative occupancy signals, and reconcile Mobile streamed cards against the terminal turn snapshot. The backend owns durable composition; Mobile only uses local keyword cards when the server supplied no card at all.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React Native, TypeScript, Jest, React Native Testing Library.

---

### Task 1: Canonical persistence deduplication

**Files:**
- Modify: `backend/tests/test_agent_conversations_api.py`
- Modify: `backend/app/api/agent.py:229-261`

**Step 1: Write the failing test**

Add a test that gives `_persist_done_cards` one already-persisted `diet_draft` without `photo_url` and the same live descriptor with a signed `photo_url`. Assert that the stored `meta.cards` contains one descriptor after the call.

**Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_agent_conversations_api.py -k canonicalizes_before_dedupe -q
```

Expected: FAIL because two equal post-sanitization descriptors are persisted.

**Step 3: Implement canonical merge order**

In `_persist_done_cards`, canonicalize both inputs before merging:

```python
persisted_existing = cards_for_persistence(meta.get("cards") or [])
persisted_incoming = cards_for_persistence(cards)
meta["cards"] = _merge_card_descriptors(persisted_existing, persisted_incoming)
```

**Step 4: Run the focused test**

Run the command from Step 2. Expected: PASS.

### Task 2: Make existing intake cards occupy their card family

**Files:**
- Modify: `backend/tests/test_inline_cards_intake_dedup.py`
- Modify: `backend/app/services/inline_cards.py:1012-1060`
- Modify: `backend/app/api/agent.py:1705-1735`

**Step 1: Write failing tests**

Add parameterized tests for contextual `diet_draft` in both states:

```python
@pytest.mark.parametrize("data", [
    {"recorded": True, "record_id": 830},
    {"photo_draft_token": "draft-token"},
])
def test_contextual_diet_card_suppresses_legacy_query_draft(db, data):
    existing = [{"type": "diet_draft", "data": data}]
    suppress = represented_intake_kinds(existing)
    cards = build_cards(db, 1, "记录晚餐牛肉面 500 kcal", suppress_intake_kinds=suppress)
    assert suppress == {"diet"}
    assert not any(card["type"] == "diet_draft" for card in cards)
```

Also assert nested `cards_group` support and that unrelated diet records are not globally collapsed.

**Step 2: Run tests to verify they fail**

```bash
cd backend && .venv/bin/python -m pytest tests/test_inline_cards_intake_dedup.py -q
```

Expected: FAIL because draft descriptors do not currently contribute an intake kind.

**Step 3: Implement represented intake detection**

Add `represented_intake_kinds`, recurse through `cards_group`, map `record`, `record_quality`, and `_DRAFT_KIND_BY_CARD`, and use it in the API wrapper. Keep `recorded_intake_kinds` as a compatibility alias if existing callers/tests require it.

**Step 4: Run focused tests**

Run the command from Step 2. Expected: PASS.

### Task 3: Suppress legacy snapshots when deterministic GenUI owns the answer

**Files:**
- Modify: `backend/tests/test_agent_conversations_api.py`
- Modify: `backend/app/api/agent.py:155-183`

**Step 1: Write the failing test**

Pass `_answer_owns_its_visualization` a closed `reva-ui` fence whose parsed `type` is `diet_daily_summary`, with only `health_query` in `tools_used`. Assert true. Add controls for malformed JSON, unknown types, and plain text mentioning `diet_daily_summary`; all must remain false.

**Step 2: Verify red**

```bash
cd backend && .venv/bin/python -m pytest tests/test_agent_conversations_api.py -k reva_ui -q
```

Expected: FAIL for the valid deterministic fence.

**Step 3: Implement strict fence recognition**

Parse only closed `reva-ui` JSON fences and return true only when `type`/`component` is in the deterministic visualization allowlist. Reuse the existing boolean snapshot gate.

**Step 4: Verify green**

Run the command from Step 2. Expected: PASS.

### Task 4: Reconcile Mobile streamed and terminal cards

**Files:**
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`
- Modify: `mobile/hooks/useChatEngine.ts:1248-1548`

**Step 1: Write two failing tests**

First stream a diet `record_quality`, finish with completed `done` and no cards, mock `dispatchCard` to return local `record/diet`, and assert exactly one diet card plus zero fallback calls.

Second stream an old `record_quality`, finish with a non-empty authoritative `done.cards` version, and assert the current turn contains one card with the new summary.

**Step 2: Verify red**

```bash
cd mobile && npx jest --runInBand hooks/__tests__/useChatEngine.test.ts
```

Expected: the new cases fail with two current-turn card messages.

**Step 3: Implement terminal reconciliation**

Track whether a server card was streamed. On non-empty terminal cards, remove only card messages whose `sourceTurnId` equals the active turn and insert the rendered terminal snapshot once. If terminal cards are empty and a server card was streamed, retain it and do not call `dispatchCard`. Keep the local fallback only for turns with no server card source.

**Step 4: Verify green**

Run the command from Step 2. Expected: PASS.

### Task 5: Cross-layer verification and review

**Files:**
- Verify only

**Step 1: Run backend focused regression**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_agent_conversations_api.py \
  tests/test_inline_cards_intake_dedup.py \
  tests/test_dynamic_card_persistence.py \
  tests/test_agent_executor_completion_status.py -q
```

Expected: all pass.

**Step 2: Run Mobile regression and typecheck**

```bash
cd mobile && npx jest --runInBand hooks/__tests__/useChatEngine.test.ts services/__tests__/chatStream.test.ts
npx tsc --noEmit
```

Expected: all tests pass and TypeScript exits 0.

**Step 3: Check diff hygiene**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; unrelated user files remain unstaged and unchanged.

**Step 4: Independent review**

Have a fresh reviewer inspect the final diff for over-deduplication, cross-turn deletion, unsafe action-card retention, and missing persistence coverage. Resolve any blocking finding and rerun affected tests.

**Step 5: Commit and push**

Stage only the files listed in this plan, commit with `fix(cards): keep one authoritative diet card`, then push `main` after all gates pass.
