# Clinician Unicode Gap And Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close Unicode Mark/Symbol and clinician-basis alias mutation bypasses while preserving narrowly proven read-only analysis and explicit typed clinician-feedback saves.

**Architecture:** Extend the existing clause-local canonical view, preserving raw offsets and hard/question boundaries, so Unicode punctuation, marks, and symbols may be ignored only within a clause. Keep clinician-basis vocabulary in the shared lexicon. Release basis mutations as advice only through two constrained epistemic shapes: risk/side-effect analysis and genuinely quoted meaning analysis, both with no extra deny-only actions.

**Tech Stack:** Python 3.12, pytest, FastAPI service policy/runtime tests, Ruff.

---

## Design constraints

- Ignore Unicode `M*` and `S*` categories in the canonical view, including variation selectors, combining grapheme joiners, emoji, and decorative symbols.
- Never canonicalize across `。`, newline, or question punctuation.
- Recognize `醫囑`, `遵嘱`, and `依嘱` as clinician-basis aliases from the shared lexicon.
- A risk/side-effect turn may be advice when it is one semantic segment, contains the expected one mutation (or exactly two for comparison), and contains no additional deny-only action.
- A meaning/definition turn may be advice only when the basis-to-mutation range is fully contained in one matched quote span and no action exists outside that span.
- A bare trailing question mark is never sufficient to release a mutation.
- Explicit feedback content remains raw and may contain a single clinician-basis update; the typed gateway must still emit a verified receipt.

### Task 1: Add failing Unicode and alias safety tests

**Files:**

- Modify: `backend/tests/fixtures/clinician_provenance_guard_safety_cases.json`
- Modify: `backend/tests/test_clinician_provenance_guard.py`
- Modify: `backend/tests/test_agent_kernel_capability_policy.py`
- Modify: `backend/tests/test_agent_write_adapter_rejections.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`

**Steps:**

1. Add the four exact Mark/Symbol bypasses and the three aliases to the safety fixture.
2. Add classifier/capability/zero-schema/direct-dispatch/stream assertions that they fail closed.
3. Add hard-boundary negatives plus normal emoji, unit, and ordinary-tool controls.
4. Run the focused selection and record the expected failures before production changes.

### Task 2: Add failing epistemic analysis tests

**Files:**

- Modify: `backend/tests/fixtures/clinician_provenance_guard_safety_cases.json`
- Modify: `backend/tests/test_agent_kernel_capability_policy.py`
- Modify: `backend/tests/test_agent_write_adapter_rejections.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`

**Steps:**

1. Add the four exact positive analysis forms and Unicode-obfuscated risk/quoted-meaning controls.
2. Assert `clinician_advice/analyze`, read capability, and no write receipt.
3. Add appended read/write/reminder/media/plan counterexamples and a generic action question.
4. Run the focused selection and confirm positive forms fail for missing behavior while negative forms remain closed.

### Task 3: Implement the minimal guard changes

**Files:**

- Modify: `backend/app/services/utterance_intent_lexicon.py`
- Modify: `backend/app/services/clinician_provenance_guard.py`

**Steps:**

1. Add the three aliases to `CLINICIAN_BASIS_TERMS`.
2. Ignore Unicode `M*` and `S*` categories in `_canonical_clauses` without changing its flush conditions.
3. Generalize `_basis_analysis_reason` only to the approved epistemic shapes while retaining segment, quote-containment, mutation-count, and extra-action constraints.
4. Run the focused tests to GREEN.

### Task 4: Verify and commit

**Files:** All files above plus this plan.

**Steps:**

1. Run guard/classifier, capability, adapter, stream, Health Evidence, routing, runtime-operation, and turn-outcome suites.
2. Run Ruff, `py_compile`, JSON validation, `git diff --check`, doc drift, and pre-commit on exact owned files.
3. Request a focused code review and resolve all Critical/Important findings.
4. Stage exact owned files only; leave the parent-owned Dossier unstaged.
5. Commit with the repository message format and report the SHA plus RED/GREEN evidence.
