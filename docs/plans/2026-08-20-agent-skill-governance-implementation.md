# Reva Agent Skill Governance Implementation Plan

> **For coding agents:** Implement with one writer, read-only reviewers, TDD, narrow staging, and fresh verification. Do not touch unrelated Health Day or KBase worktree changes.

**Goal:** Make Reva's recommended development Skill set machine-governed, route every task through at most one controller, and separate Codex adapters from Claude adapters.

**Architecture:** A JSON registry and agent-neutral governance contract define lifecycle, routing and overlays. A deterministic checker validates the registry, returns recommendations, and rejects platform leakage. Thin platform adapters consume the same contract; repository gates run the checker.

**Tech Stack:** Python 3.12, JSON/JSON Schema, Markdown Skill adapters, pytest, pre-commit, GitHub Actions.

---

### Task 1: Lock the RED contracts

**Files:**
- Modify: `backend/tests/test_reva_health_harness_plugin_package.py`
- Create: `backend/tests/test_agent_skill_governance.py`

1. Add tests requiring a registry, one-controller routing, lifecycle metadata, privacy-minimal run events and a `reva-workflow-router` adapter.
2. Add tests rejecting Claude-only tokens in the Codex plugin and remove the byte-identical-copy expectation for platform-specific adapters.
3. Run:

   ```bash
   cd backend
   python3.12 -m pytest tests/test_agent_skill_governance.py tests/test_reva_health_harness_plugin_package.py -q
   ```

4. Confirm RED because the registry, checker and Router do not exist and Codex adapters still contain Claude-only instructions.

### Task 2: Implement the registry and deterministic checker

**Files:**
- Create: `docs/governance/agent-skill-registry.json`
- Create: `docs/governance/agent-skill-run-event.schema.json`
- Create: `scripts/check_agent_skill_governance.py`
- Modify: `backend/tests/test_agent_skill_governance.py`

1. Define project-managed skills separately from external recommendations.
2. Require standard skills to declare owner, version, layer, kind, platform, trigger family, review date and evidence.
3. Define task modes `analysis`, `quick_fix`, `feature`, `implementation`, `incident`, and `release`; machine routing must yield zero or one controller and a deduplicated overlay set.
4. Make `using-superpowers` and direct `executing-plans` deprecated for this project; keep TDD, debugging and verification as capabilities, not controllers.
5. Implement `check` and `recommend` commands using only the standard library. Fail closed on aliases, missing files, invalid lifecycle transitions, conflicting controllers, unknown overlays and sensitive event fields.
6. Run the focused tests until GREEN.

### Task 3: Add the Router and platform-native adapters

**Files:**
- Create: `.claude/skills/reva-workflow-router/SKILL.md`
- Create: `plugins/reva-health-harness/skills/reva-workflow-router/SKILL.md`
- Create: `plugins/reva-health-harness/skills/reva-workflow-router/agents/openai.yaml`
- Modify: `plugins/reva-health-harness/skills/product-pipeline/SKILL.md`
- Modify: `plugins/reva-health-harness/skills/health-harness-orchestrator/SKILL.md`
- Modify: `plugins/reva-health-harness/.codex-plugin/plugin.json`
- Modify: `plugins/reva-health-harness/README.md`

1. Use the official Skill initializer for the new Codex Router folder, then replace generated placeholders.
2. Keep Router metadata concise and trigger-focused. Require it to run the deterministic recommendation before loading workflow skills.
3. Make Claude and Codex Router adapters semantically equivalent while allowing tool-specific instructions.
4. Rewrite the two Codex workflow adapters as thin consumers of the neutral contract; remove `TeamCreate`, `TaskCreate`, `SendMessage`, hard-coded Opus and Claude co-author text.
5. Validate each changed Skill and run its focused tests before moving to the next adapter.

### Task 4: Wire governance into the project

**Files:**
- Modify: `docs/agent-skill-binding.md`
- Modify: `AGENTS.md`
- Modify: `scripts/validate.py`
- Modify: `.pre-commit-config.yaml`
- Modify: `.github/workflows/ci.yml`
- Modify: `backend/tests/test_harness_gate_wiring.py`
- Modify: `backend/tests/test_reva_health_harness_plugin_package.py`
- Modify: `docs/plans/2026-08-20-agent-skill-governance-design.md`

1. Make Router + registry the first project Skill decision point; keep product runtime skills explicitly out of scope.
2. Add the governance checker as a blocking local validation, pre-commit and docs-quality CI step.
3. Update plugin tests to verify semantic contracts and native-platform boundaries rather than byte equality.
4. Remove the design document's Markdown trailing whitespace.
5. Run focused tests and `python3.12 scripts/check_agent_skill_governance.py check`.

### Task 5: Forward-test and verify

**Files:**
- Modify only files above when a demonstrated failure requires it.

1. Run the original cross-end and quick-fix pressure scenarios with the Router, using fresh read-only agents and no expected answer leakage.
2. Verify that each scenario selects at most one controller, keeps overlays non-owning, and avoids unnecessary planning for quick fixes.
3. Run:

   ```bash
   cd backend
   python3.12 -m pytest \
     tests/test_agent_skill_governance.py \
     tests/test_reva_health_harness_plugin_package.py \
     tests/test_harness_gate_wiring.py -q
   cd ..
   python3.12 scripts/check_agent_skill_governance.py check
   python3.12 scripts/validate.py -v
   git diff --check
   ```

4. Request independent code/contract review on a fixed diff.
5. Stage only the listed governance files, commit, re-run the focused gate from committed state, then push only if the local branch is not behind `origin/main` and no unrelated commit would be published.
