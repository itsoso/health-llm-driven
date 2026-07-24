# Agent Goal Contract Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hard-coded Agent goal extension points with immutable registries while preserving current diet behavior and fail-closed verification.

**Architecture:** Add registry primitives in Agent Kernel, then make the existing goal compiler, prompt formatter, and postcondition verifier delegate to static registry instances. Keep all public APIs and client/runtime contracts unchanged.

**Tech Stack:** Python 3, dataclasses, typing protocols, pytest.

---

### Task 1: Define registry behavior with tests

**Files:**
- Create: `backend/tests/test_agent_goal_registry.py`
- Modify: `backend/tests/test_agent_goal_spec.py`
- Modify: `backend/tests/test_agent_goal_postconditions.py`

**Steps:**
1. Add tests for deterministic compiler selection.
2. Add tests that duplicate compiler names and duplicate goal kinds are rejected.
3. Add facade inspection tests for the diet compiler, prompt renderer, and verifier.
4. Add a fail-closed test for an unregistered verified goal.
5. Run the focused tests and confirm they fail because registry APIs do not exist.

### Task 2: Implement immutable registry primitives

**Files:**
- Create: `backend/app/services/agent_kernel/goal_registry.py`

**Steps:**
1. Add typed specs for compilers, prompt renderers, and verifiers.
2. Add immutable registries with construction-time duplicate validation.
3. Add deterministic dispatch and read-only name/kind inspection.
4. Run registry unit tests.

### Task 3: Migrate existing diet goal behavior

**Files:**
- Modify: `backend/app/services/agent_kernel/goal_spec.py`
- Modify: `backend/app/services/agent_kernel/postconditions.py`

**Steps:**
1. Extract specialized diet compilation from the generic fallback.
2. Register the diet compiler and contract prompt renderer.
3. Extract the diet postcondition verifier and register it.
4. Preserve `unsupported_goal_verifier` for unregistered verified goals.
5. Run all focused goal and postcondition tests.

### Task 4: Run regression gates and record evidence

**Files:**
- Modify: `docs/dossiers/2026-07-24-agent-trajectory-intelligence.md`

**Steps:**
1. Run Agent Kernel focused tests.
2. Run stateful trajectory and offline Agent regression gates.
3. Run system-map/doc drift checks if architecture metadata changes.
4. Record exact test evidence and remaining next step in the dossier.
5. Commit only files from this change, push to `main`, deploy the backend, and verify public health plus deployed SHA.
