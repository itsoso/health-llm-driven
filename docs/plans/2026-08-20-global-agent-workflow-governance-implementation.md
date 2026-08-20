# Global Agent Workflow Governance Skill Implementation Plan

> Implement one Skill at a time with TDD. Do not create a global runtime Router in this slice.

**Goal:** Package the reusable governance semantics proven in Reva as one globally available, project-neutral Codex Skill without importing Reva routing or domain rules.

**Architecture:** A skills-only personal Plugin contains a concise governance Skill, a project Registry Schema, a standard-library validator and deterministic content lock. Projects opt in by creating their own Registry; their local Router remains authoritative.

**Tech stack:** Markdown, JSON Schema subset, Python standard library, pytest, Codex Plugin tooling.

---

### Task 1: Record the definition and Gate contract

**Files:**
- Create: `docs/plans/2026-08-20-global-agent-workflow-governance-design.md`
- Create: `docs/plans/2026-08-20-global-agent-workflow-governance-implementation.md`
- Create: `docs/dossiers/2026-08-20-global-agent-workflow-governance.md`

1. Record the user request, G1 admission and the no-second-Router Correct Course.
2. Freeze global versus project-local ownership, privacy and supply-chain boundaries.
3. Keep the original Reva governance G6 unchanged.

### Task 2: Capture RED before the Skill exists

**External Plugin files:**
- Create: `~/plugins/agent-workflow-governance/tests/test_governing_agent_workflows.py`

1. Scaffold only the Plugin manifest and empty `skills/` directory.
2. Add tests requiring exactly one Skill and the expected Plugin/Skill metadata.
3. Add synthetic Registry tests for missing Registry, two controllers, unknown enums, overlay ownership, project-root escape and symlink sources; project mode names have no global semantics.
4. Add content-lock tests for modified, missing and unexpected runtime files.
5. Add a provider-neutral leakage test rejecting project/domain IDs and platform-specific orchestration commands.
6. Run the tests and confirm RED because the Skill, validator and content lock do not exist.

### Task 3: Implement the one-Skill Plugin

**External Plugin files:**
- Create: `~/plugins/agent-workflow-governance/skills/governing-agent-workflows/SKILL.md`
- Create: `~/plugins/agent-workflow-governance/skills/governing-agent-workflows/agents/openai.yaml`
- Create: `~/plugins/agent-workflow-governance/skills/governing-agent-workflows/references/contract.md`
- Create: `~/plugins/agent-workflow-governance/skills/governing-agent-workflows/references/project-registry.schema.json`
- Create: `~/plugins/agent-workflow-governance/skills/governing-agent-workflows/scripts/validate_project_registry.py`
- Create: `~/plugins/agent-workflow-governance/scripts/content_lock.py`
- Create: `~/plugins/agent-workflow-governance/content.lock.json`

1. Keep `SKILL.md` trigger-focused and use progressive disclosure for the contract.
2. Make the validator standard-library-only and read only an explicit `--project-root` plus the fixed project-relative Registry path.
3. Return stable machine reason codes; unknown values and absent Registry fail closed without fallback.
4. Enforce source containment and reject symlinks.
5. Generate a deterministic lock over every Plugin runtime file except the lock itself and test/cache artifacts.
6. Require externally recorded previous version and root digest before regeneration; reject a missing/altered prior lock, same-version change, root mismatch or version downgrade.
7. Expose static `check` only; runtime route selection remains project-local.
8. Run the RED suite until GREEN, then run official Plugin and Skill validators.

### Task 4: Install and verify the global Plugin

**Personal marketplace files:**
- Create or update: `~/.agents/plugins/marketplace.json`

1. Add the validated Plugin to the personal marketplace only after tests are GREEN.
2. Use `/opt/homebrew/bin/codex`; record CLI version and verify each subcommand with `--help` before mutation.
3. Install `agent-workflow-governance@personal`.
4. Compare marketplace source and installed cache version, file set and root digest.
5. Start a fresh Codex task and verify discovery. Do not infer fresh discovery from the current process.

### Task 5: Forward-test project boundaries

1. In a synthetic project, verify valid analysis/quick-fix/feature/release registries and all failure injections.
2. In Reva, verify the project recommender remains authoritative and no second controller appears.
3. In `browser-llm-orchestrator`, verify a read-only forward smoke cannot resolve Health IDs or product-runtime Skills.
4. Verify ordinary coding requests do not trigger `governing-agent-workflows`; governance authoring requests do.
5. Request an independent fixed-diff review and close all BLOCKER/HIGH findings.

### Task 6: Commit and hand off

1. Commit only the three Reva documentation files in the clean worktree.
2. Initialize the personal Plugin source as its own local Git repository and commit its exact validated state; do not publish a remote without separate authorization.
3. Re-run tests, validators, digest verification and `git diff --check` from committed state.
4. Record G3/G4/G5 evidence and leave cross-project effectiveness G6 pending until prospective matched samples exist.
