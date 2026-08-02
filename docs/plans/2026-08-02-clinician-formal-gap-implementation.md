# Clinician Formal Gap Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close all non-letter/number Unicode basis gaps and preserve opaque raw content inside verified doctor-feedback writes.

**Architecture:** Keep the clause-local raw-offset canonical view, but make its retained alphabet an explicit Unicode `L*`/`N*` whitelist after boundary handling. Pass valid explicit-feedback content spans as exclusions only to the general obfuscation detector; leave the exact envelope and compound-action parser unchanged.

**Tech Stack:** Python 3.12, Unicode `unicodedata`, pytest, FastAPI agent kernel/runtime tests.

---

### Task 1: Prove the Unicode bypass and content false rejection

**Files:**
- Modify: `backend/tests/fixtures/clinician_provenance_guard_safety_cases.json`
- Modify: `backend/tests/test_clinician_provenance_guard.py`
- Modify: `backend/tests/test_agent_kernel_capability_policy.py`
- Modify: `backend/tests/test_agent_write_adapter_rejections.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`

1. Add the five Cc/Co/Cn destructive basis examples across guard, classifier,
   capability, schema, direct dispatch, and end-to-end stream paths.
2. Add ordinary Unicode negative controls.
3. Change the duplicated provider/root/object content fixtures to explicit
   typed writes and add provider/advice/mutation content gap examples.
4. Add verified-receipt cases that assert a single row and raw content.
5. Run the focused selections and confirm failures are caused by the two
   current production behaviors.

### Task 2: Implement the minimal production correction

**Files:**
- Modify: `backend/app/services/clinician_provenance_guard.py`

1. In `_canonical_clauses`, flush boundaries first and retain only Unicode
   categories whose first character is `L` or `N`.
2. Give `_has_obfuscated_clinician_action` an opaque-span parameter and pass it
   to `_canonical_clauses` as exclusions.
3. Pass only valid explicit-feedback content spans from
   `classify_clinician_turn`.
4. Remove the narrower basis-only exception made redundant by full validated
   content opacity.
5. Re-run the focused tests until green.

### Task 3: Verify and submit

**Files:**
- Verify all files above; do not stage concurrent Dossier or Spec edits.

1. Run the full relevant regression without output-truncating pipes.
2. Run Ruff, py_compile, JSON validation, `git diff --check`, and pre-commit
   under the backend virtualenv.
3. Request independent review focused on false negatives, explicit-envelope
   authority, and raw receipt integrity; resolve all Critical/Important items.
4. Stage only owned files, commit, and report the commit SHA and fresh evidence.
