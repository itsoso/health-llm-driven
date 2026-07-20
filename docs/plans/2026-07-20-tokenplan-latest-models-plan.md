# TokenPlan Latest Models Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the TokenPlan registry exactly match the owner-approved 2026-07-20 model whitelist while safely exposing Qwen3.8 and cataloging HappyHorse video models.

**Architecture:** Keep `model_registry.py` as the single source of truth. Add only registry metadata and regression assertions; preserve the existing user preference → admin active model → settings default routing chain. Non-chat media models stay discoverable through `include_non_chat=True` but are excluded from chat and tool routing.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, OpenAI-compatible TokenPlan API.

---

### Task 1: Lock the approved model contract in failing tests

**Files:**
- Modify: `backend/tests/test_model_registry_latest.py`

**Step 1: Write the failing tests**

Add Qwen3.8, HappyHorse, and GLM reasoning capabilities to `EXPECTED_MODELS`, then assert the TokenPlan provider model set matches the source snapshot exactly:

```python
EXPECTED_TOKENPLAN_IDS = set(EXPECTED_MODELS)


def test_tokenplan_registry_exactly_matches_owner_whitelist():
    actual = {m.id for m in reg.MODELS if m.provider == "tokenplan"}
    assert actual == EXPECTED_TOKENPLAN_IDS
```

Add separate image/video non-chat sets and a Qwen3.8 safety-profile assertion:

```python
def test_qwen38_preview_uses_probe_verified_conservative_flags():
    entry = reg.get_model("qwen3.8-max-preview")
    assert entry is not None
    assert entry.reliable_tool_calling is True
    assert entry.supports_thinking_budget is False
    assert entry.supports_forced_tool_choice is False
    assert entry.supports_explicit_cache is False
```

**Step 2: Run the focused test and verify RED**

Run:

```bash
cd backend
venv/bin/python -m pytest tests/test_model_registry_latest.py -q --no-cov
```

Expected: FAIL because Qwen3.8 and HappyHorse are not registered and GLM lacks `reasoning`.

**Step 3: Keep the failing test changes unstaged until the implementation passes**

Review only `backend/tests/test_model_registry_latest.py` and confirm the failure is caused by missing registry behavior rather than syntax or fixture errors.

### Task 2: Implement the minimal registry refresh

**Files:**
- Modify: `backend/app/services/llm/model_registry.py`
- Test: `backend/tests/test_model_registry_latest.py`

**Step 1: Add Qwen3.8 Preview**

Add a TokenPlan `ModelEntry` with exact `id` and `model` value `qwen3.8-max-preview`, `speed_tier="reasoning"`, capabilities `text_generation`, `reasoning`, and `vision_understanding`, and note the Preview / limited-time 10x capacity status. Keep `reliable_tool_calling=True` based on the fresh automatic tool-call probe. Do not enable thinking-budget, forced-tool-choice, or explicit-cache flags.

**Step 2: Add HappyHorse media-only entries**

Add `happyhorse-1.1-i2v`, `happyhorse-1.1-t2v`, and `happyhorse-1.1-r2v` with `capabilities=("video_generation",)`, `chat_selectable=False`, and `reliable_tool_calling=False`.

**Step 3: Correct GLM capability metadata**

Add `reasoning` to GLM 5.2, 5.1, and 5 while retaining their conservative `reliable_tool_calling=False` flags.

**Step 4: Verify GREEN**

Run:

```bash
cd backend
venv/bin/python -m pytest tests/test_model_registry_latest.py -q --no-cov
```

Expected: all tests pass.

### Task 3: Verify routing compatibility and finish

**Files:**
- Verify: `backend/app/services/llm/model_registry.py`
- Verify: `backend/app/api/user_llm_preference.py`
- Verify: `backend/app/api/admin_llm.py`
- Verify: `backend/tests/test_model_registry_latest.py`

**Step 1: Run the required focused regression suite**

```bash
cd backend
venv/bin/python -m pytest tests/test_model_registry_latest.py tests/test_agent_executor_tool_gating.py tests/test_task_routing.py tests/test_llm_factory.py tests/test_agent_executor_model_override.py -q --no-cov
```

Expected: all tests pass with no failures.

**Step 2: Compile the affected Python surfaces**

```bash
cd backend
venv/bin/python -m compileall -q app/services/llm/model_registry.py app/api/user_llm_preference.py app/api/admin_llm.py tests/test_model_registry_latest.py
```

Expected: exit code 0 and no output.

**Step 3: Validate repository hygiene**

```bash
cd ..
git diff --check
git status --short
```

Expected: no whitespace errors; unrelated owner files remain unstaged and untouched.

**Step 4: Commit and push only task files**

```bash
git add backend/app/services/llm/model_registry.py backend/tests/test_model_registry_latest.py docs/plans/2026-07-20-tokenplan-latest-models-plan.md
git commit -m "feat(llm): add latest TokenPlan models"
git push origin main
```
