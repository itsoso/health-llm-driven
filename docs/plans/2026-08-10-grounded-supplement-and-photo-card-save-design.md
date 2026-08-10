# Grounded Supplement Writes and Photo Card Save Design

## Context

On 2026-08-10 a production turn asked to identify a supplement from an image and record it. The current turn contained no image and did not state a supplement name, but the answer model supplied `维生素D`; the runtime auto-created supplement definition `73` and verified supplement record `1073`. A later owner-bound meal photo confirmation failed twice before reaching `POST /api/v1/diet/records` because Mobile interpreted the food quantity `胡萝卜 约3片` as a medication marker.

Production evidence separates the failures:

- supplement definition `73` and record `1073` were successfully committed for user `52` at `2026-08-10 11:39:42 +08:00`;
- the corresponding client terminal event was a verified `health_record` receipt;
- the supplement turn had `has_image=false`;
- the two meal confirmation attempts emitted `card_action_failed`, while the backend received no diet write request;
- the persisted diet card carried a valid owner-bound `photo_draft_token`, but Mobile stripped that token before dispatch and rejected the phrase at its broad `片` heuristic.

## Decision

Use the release-safe, confirmation-first design approved by the user on 2026-08-10.

### Supplement boundary

1. A single-supplement write must be grounded in the current user turn.
2. If the current turn contains an attachment, `health_record(record_type=supplement)` cannot auto-create or tap a supplement. The tool returns a structured rejection asking the user to verify the recognized name in a new text message.
3. If the current turn has no attachment, the normalized supplement name supplied by the model must exactly equal one action-bound entity in the current user message. A canonical shared-lexicon alias may be used directly after deterministic dose removal. Any unknown new product name requires an explicit quote boundary (`「…」`, `“…”`, `"…"`, or `【…】`) after the record/intake action; unquoted unknown text never grants write authority. Structural separators, multiple canonical names, embedded dosage, generic category, image, pronoun, directive, conjunction, frequency forms, and concatenated names are rejected before any supplement lookup, definition creation, or tap request.
4. Direct canonical text such as `记录维生素D 1粒` remains an immediate write. A new product uses `记录「正官庄红参液」10mL`, preserving a concise but explicit confirmation workflow.
5. Group check-ins remain unchanged; this fix only covers `record_type=supplement`.

This release does not add a new supplement-image draft table or autonomous confidence threshold. A later feature may add an owner-bound supplement draft, but the smallest safe slice is to require the user to repeat the exact recognized name before writing.

### Contextual meal-photo confirmation

1. Mobile must preserve a valid `photo_draft_token` from a deterministic server card when posting `/diet/records`.
2. For an owner-bound photo draft, Mobile keeps the management-intent and health-metric checks and defers only an Arabic-number slice unit such as `胡萝卜 约3片`. It removes that one ambiguous unit and reruns medication/supplement detection; any remaining strong signal still fails before posting.
3. Backend authenticates the owner-bound token and applies its canonical diet intake guard. Backend and Mobile first normalize Unicode compatibility forms (NFKC), Unicode dash variants, case, and invisible/zero-width characters, then apply shared complete-name drug/supplement boundaries. Spaced/unspaced doses and numeric-ending names use dose lookahead, so `vitamin D1000IU`, `coq102粒`, `b122粒`, and `d32粒` remain supplement intake; compact multi-entity forms such as `vitaminDfishoil` and `d3-fish-oil` are rejected, while benign continuations such as `coq10environment` remain unmatched. A valid photo token cannot turn named medicine/supplement or mixed food-plus-nonfood payloads into diet data.
4. Text-only diet cards retain the existing client-side medication/supplement guard.
5. The exact production phrase containing `胡萝卜 约3片` becomes a regression test.
6. Card failures continue to fail visibly; known local validation and HTTP failures emit only a content-free stable error code.

## Data integrity correction

After code gates pass, authenticate as the owning user and read all owner-scoped records whose `supplement_id` is `73`. Continue only if the definition belongs to that same owner and the exact record-id set equals `{1073}`; any additional record or ownership mismatch aborts cleanup. Then remove definition `73` through the authenticated owner-scoped supplement API, whose existing cascade removes record `1073`. Verify both resources are absent using read-only owner-scoped queries. Do not mutate production tables directly.

## Safety and privacy

- No image, supplement name, meal text, URL, token, or record identifier is added to client telemetry.
- The supplement guard tightens write authority and cannot authorize a new write.
- The photo draft token is already an owner-scoped server capability with a bounded format, pending/consumed state, expiry, row locking, and user filtering.
- Backend diet validation remains authoritative. Mobile narrows only the numeric food-slice ambiguity and retains strong medication/supplement checks.
- Production cleanup is exact and user-authorized; no broad delete or direct SQL mutation is permitted.

## Acceptance criteria

1. A model-supplied supplement name absent from an explicit current-text entity span, an unknown name lacking explicit quotes, or generic/action/image text produces a structured rejection and zero downstream API calls.
2. Any current-turn attachment plus a supplement write produces a confirmation-required rejection and zero downstream API calls.
3. A canonical text-only supplement name, or an explicitly quoted unknown product name, still auto-creates and taps exactly once.
4. The production meal phrase with `胡萝卜 约3片` posts successfully when accompanied by a valid photo draft token.
5. The same phrase without a photo draft token remains subject to the existing client guard.
6. Known medicines and supplements, including Chinese/English names, fullwidth/Unicode-obfuscated forms, compact multiple names, spaced/unspaced doses, and mixed food-plus-drug payloads, remain rejected with or without a valid photo draft token; Backend creates no diet row and Mobile sends no request.
7. The photo draft token is sent to `/diet/records`, allowing the backend to bind the retained image and enforce idempotency.
8. Focused Backend and Mobile suites, typecheck, safety review, deploy health gates, and production smoke tests pass.
9. Cleanup first proves the exact owner-scoped record-id set `{1073}` for definition `73`, aborts on any mismatch, and only then removes definition `73`; both resources are absent afterward.

## Release impact

The backend supplement guard requires a backend deployment. The Mobile diet-card fix is JavaScript/TypeScript-only, but production OTA and App Review remain frozen until the release dossier's G3/G4 gates are green and the exact candidate strategy is re-evaluated. No App Store submission occurs as part of this fix.
