# Grounded Supplement Writes and Photo Card Save Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent ungrounded supplement writes and make owner-bound contextual meal-photo cards save successfully without weakening the authoritative backend intake guard.

**Architecture:** Add a narrow server-side grounding choke point immediately before the existing supplement lookup/create/tap path. A model-provided name must exactly equal a concrete, action-bound entity extracted from the current text-only message after dosage removal; generic category, image, pronoun, and action terms fail closed. Preserve owner-bound photo draft identity in Mobile, but defer only an Arabic-number food-slice `片` signal; Mobile retains strong medication/supplement blocking and Backend reuses the canonical complete-drug lexicon.

**Tech Stack:** FastAPI/SQLAlchemy/Pytest, React Native/TypeScript/Jest, existing `AgentExecutor`, `photo_draft_token`, client terminal telemetry, controlled production deploy tooling.

---

### Task 1: Freeze the production regressions in tests

**Files:**
- Modify: `backend/tests/test_supplement_record_autocreate.py`
- Modify: `backend/tests/test_intake_intent_classifier.py`
- Modify: `backend/tests/test_diet.py`
- Modify: `mobile/services/__tests__/chatCardActions.test.ts`
- Modify: `mobile/utils/__tests__/dietIntakeGuard.test.ts`

**Step 1: Write the failing supplement grounding tests**

Add tests that set `_current_turn_user_message` and `_current_turn_has_attachment` explicitly:

```python
@pytest.mark.asyncio
async def test_model_inferred_supplement_name_is_rejected_before_dispatch(db):
    ex = _executor(db)
    ex._current_turn_user_message = "识别图中的补剂并且帮我打卡"
    ex._current_turn_has_attachment = False
    # Call _exec_health_record with supplement_name="维生素D".
    # Assert a structured supplement_name_not_user_grounded rejection and no API calls.

@pytest.mark.asyncio
async def test_attachment_supplement_write_requires_text_confirmation(db):
    ex = _executor(db)
    ex._current_turn_user_message = "识别并记录维生素D"
    ex._current_turn_has_attachment = True
    # Assert supplement_image_confirmation_required and no API calls.
```

Update the existing auto-create test so the current user message explicitly contains `正官庄红参液`.

Add zero-dispatch adversarial cases for model names such as `补剂`, `图`, `打卡`, `这个补剂`, and bare `维生素`. Add canonical Backend rejection cases for `阿司匹林 1片` and `阿奇霉素 1片`.

After the second independent review, add zero-dispatch cases for directive/generic superstrings (`维生素D并且帮我打卡`, `这个补剂维生素D`, `this supplement vitamin D`), conjunction/multi-entity input (`维生素D和鱼油`, `vitamin D and fish oil`), and residual frequency/dose input (`维生素D每天1片`). Add classifier and API no-row cases for Chinese/English drugs and supplements, spaced/unspaced doses, and mixed food-plus-drug payloads. The Mobile owner-bound-token matrix must prove the same inputs produce zero POSTs.

**Step 2: Write the failing contextual meal-photo test**

Use the production food phrase containing `胡萝卜 约3片`, a valid `photo_draft_token`, and the registered diet-card write policy. Assert that dispatch resolves, posts exactly once, and includes the same token.

```typescript
expect(mockApiPost).toHaveBeenCalledWith(
  '/diet/records',
  expect.objectContaining({
    food_items: expect.stringContaining('胡萝卜 约3片'),
    photo_draft_token: token,
  }),
  expect.anything(),
);
```

**Step 3: Run the focused tests and verify RED**

Run:

```bash
cd backend && ./venv/bin/pytest tests/test_supplement_record_autocreate.py -q
cd mobile && npm test -- --runInBand services/__tests__/chatCardActions.test.ts
```

Expected: the new Backend tests show the ungrounded calls still dispatch, and the Mobile test fails with `invalid_diet_food_items_non_diet`.

### Task 2: Enforce current-turn supplement grounding

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/skills/health-record/SKILL.md`
- Test: `backend/tests/test_supplement_record_autocreate.py`

**Step 1: Add a minimal normalization helper**

Normalize Unicode compatibility forms, lowercase ASCII, and remove whitespace/punctuation. Do not perform fuzzy matching or invent aliases.

```python
def _normalized_current_turn_entity_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())
```

**Step 2: Add the write guard before supplement lookup**

For `rtype == "supplement"`:

- reject current attachment turns with `supplement_image_confirmation_required`;
- extract only an entity following an explicit current-turn record/intake action, remove a leading/trailing quantity and dosage, and require exact normalized equality with the model-provided name;
- reject empty, one-character, generic category, image, pronoun, and action-only names with `supplement_name_not_user_grounded`;
- return through `local_write_rejection`, ensuring `dispatch_started=false`.

**Step 3: Update the runtime skill contract**

Replace the instruction that photo-derived new supplements auto-create immediately. State that image-derived names must be repeated by the user in a text-only confirmation turn; explicit text names keep the existing auto-create behavior.

**Step 4: Run the Backend focused tests and verify GREEN**

Run:

```bash
cd backend && ./venv/bin/pytest tests/test_supplement_record_autocreate.py tests/test_write_receipt_identity.py -q
```

Expected: all selected tests pass, and the existing text-only auto-create receipt remains verified.

### Task 3: Preserve the owner-bound photo draft and avoid the false positive

**Files:**
- Modify: `mobile/services/chatCardActions.ts`
- Modify: `mobile/utils/dietIntakeGuard.ts`
- Test: `mobile/services/__tests__/chatCardActions.test.ts`

**Step 1: Add a narrow photo-slice guard option**

Extend `assertDietFoodItemsAllowed` with an optional `ownerBoundPhotoDraft` flag. Always reject management and health-metric inputs. When the flag is true and the only non-diet signal is an Arabic-number slice unit such as `约3片`, remove only that unit and rerun the non-diet classifier. Any remaining medication or supplement signal still rejects before the request; the backend remains authoritative.

```typescript
export function assertDietFoodItemsAllowed(
  foodItems: string,
  options: { ownerBoundPhotoDraft?: boolean } = {},
): void {
  if (looksLikeDietManagementIntent(foodItems)) throw ...;
  if (looksLikeNonDietIntake(foodItems) && !onlyAmbiguousNumericPhotoSlice(foodItems, options)) throw ...;
  if (looksLikeHealthMetricIntent(foodItems)) throw ...;
}
```

**Step 2: Validate and preserve `photo_draft_token`**

Read the token before food-item validation. Accept only `^[A-Za-z0-9_-]{24,64}$`; reject malformed values. Pass the valid token to both the guard option and the request body.

**Step 3: Keep text-only defenses unchanged**

The existing medication/supplement rejection cases without a photo draft token must still fail before any API request. With a valid token, known medicines and supplements must also fail before posting. Backend must classify complete drug names from its canonical lexicon so owner-bound requests cannot bypass the authoritative guard.

**Step 4: Run the Mobile focused tests and verify GREEN**

Run:

```bash
cd mobile && npm test -- --runInBand services/__tests__/chatCardActions.test.ts services/__tests__/clientEvents.test.ts
```

Expected: production regression passes, text-only non-diet cases remain rejected, and telemetry tests stay green.

### Task 4: Run release gates and obtain the safety verdict

**Files:**
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Run changed Backend suites**

Run:

```bash
cd backend && ./venv/bin/pytest tests/test_supplement_record_autocreate.py tests/test_write_receipt_identity.py tests/test_agent_ops_registry.py -q
```

Expected: PASS with no skips caused by this change.

**Step 2: Run changed Mobile suites and typecheck**

Run:

```bash
cd mobile && npm test -- --runInBand services/__tests__/chatCardActions.test.ts components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx
cd mobile && npx tsc --noEmit
```

Expected: PASS.

**Step 3: Run repository drift and diff checks**

Run:

```bash
python3 scripts/check_doc_drift.py
git diff --check
```

Expected: PASS.

**Step 4: Commit the implementation**

Stage only the files listed in this plan and commit with:

```text
fix(agent): ground supplement writes and photo saves
```

**Step 5: Obtain an independent safety review**

The reviewer must inspect the committed diff for supplement write authority, owner isolation, photo draft ownership/expiry, diet guard preservation, receipt truthfulness, and privacy-safe telemetry. The first review returned BLOCK because arbitrary message substrings and whole-guard bypasses remained possible. The second review also returned BLOCK because directive/multi-entity superstrings remained groundable and owner-bound photo tokens still admitted English named medicines/supplements with dose text. Each BLOCK returns to implementation; a fresh independent reviewer must inspect the final committed tree, and only GO permits deploy.

### Task 5: Push, deploy, correct the bad record, and verify production

**Files:**
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Push the reviewed commit**

Push the exact current branch and verify the remote SHA.

**Step 2: Re-evaluate release delivery**

Deploy the backend only through `./deploy.sh -b`. Keep App Review frozen. Release the Mobile change only through the project-approved runtime/Store strategy after G3/G4 confirms that doing so does not violate the exact Build 256 submission contract.

**Step 3: Verify production health and revision**

Use the deploy health gate and read-only probes to confirm backend, PostgreSQL, Redis, Celery, exact SHA, and supplement rejection behavior.

**Step 4: Remove the exact erroneous resources through the owner-scoped API**

Authenticate as the owning review user without printing credentials or tokens. Resolve supplement definition `73`, then list every owner-scoped record with `supplement_id=73`. Assert the definition owner matches and the exact record-id set is `{1073}`; abort on any extra record or ownership mismatch. Only then call the existing authenticated delete endpoint for definition `73`. Do not use direct SQL mutation.

**Step 5: Verify cleanup**

Read back the owner-scoped supplement definition and record. Expected: neither resource exists and no unrelated supplement was changed.

**Step 6: Verify the two user flows**

- Ungrounded text `识别图中的补剂并且帮我打卡` with no current image: no write, explicit resend/type-name guidance.
- Owner-bound contextual meal card containing `胡萝卜 约3片`: one diet write, verified receipt, retained image, no generic save-failure toast.

**Step 7: Record Gate outcomes**

Update the dossier with exact commit, test counts, safety verdict, deployment health, cleanup proof, Mobile delivery status, and remaining App Review blockers. Do not mark G5/G6 complete unless every release requirement is actually satisfied.
