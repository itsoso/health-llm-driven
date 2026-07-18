# Claude Branch Integration Dossier

| 字段 | 值 |
|---|---|
| slug | `claude-branch-integration` |
| 创建日期 | 2026-07-18 |
| 当前阶段 | S5 CI 修复验证 |
| 状态 | pending_remote_ci |
| 负责 | Codex |
| 反馈环 | 本地测试 / main 集成 |

## S0 · 用户需求(逐字)

> 逐个合并，确保逻辑不要出问题，要做严格检验和测试

- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1):维护主干的研发者需要将已完成的 Claude 改造逐项纳入主干，并让每项改造具有可复核的测试与安全证据。

## S1 · Discovery(现状勘察)

Integrate the unmerged `claude/*` source branches into `main` individually. This is engineering maintenance that strengthens existing Health OS objects and contracts; it introduces no independently scoped product surface. Source changes that alter safety, privacy, health claims, notifications, or write paths retain their original safety obligations.

## Baseline

- Target: `main` at `014aded1e68376d735f84b124c16d8a488a72375`, matching `origin/main` before integration.
- Protected pre-existing user-owned untracked work was intentionally excluded from this integration commit.
- Source inventory and dependency order: [`2026-07-18-claude-branch-integration.md`](../plans/2026-07-18-claude-branch-integration.md).

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: SafetyGuardian, HealthAgendaItem, HealthTwin, ExecutionEvent, and existing Agent contracts.
- core_loop_step: Maintenance across existing safety gating, execution, agent response, and notification paths.
- target_surface / safety_level / autonomy_tier: Existing backend, mobile, and web surfaces; inherit the source change's existing risk and autonomy tier.
- spec_required(§8.1): No new product behavior is introduced by integration itself; source changes with safety, notification, or write-path behavior must pass G4 individually.
- smallest_end_to_end_slice: One source branch, source review, focused tests, then explicit inclusion or exclusion.
- stale_surface_to_remove: None.
- **裁决**: PASS — integration maintenance supports existing product objects without creating a separate product objective.
- 用户确认: User explicitly requested sequential integration with strict verification.

## G2 · 可行性 + 安全压测

- 评审方式: Source inventory, dependency ordering, direct diff review, and per-source safety/privacy review for sensitive changes.
- 硬阻断(已焊进规划): Do not merge duplicate branches; do not accept a source if its focused verification or safety review fails.
- **裁决**: PASS — proceed only branch-by-branch under the recorded stop conditions.

## G3 · 测试闸

- Accumulated backend safety / write-path regression: `347 passed`.
- Agent, dynamic-view, and timezone regression were split because combining the timezone suite with the Agent process can retain a test-session resource: `136 passed` + `14 passed`.
- Causal-memory / outcome / migration regression: `255 passed`.
- Safety evaluator: `8/8 pass`, no regression against the `main` baseline.
- Web: affected component and dashboard-flow suites `58 passed`; TypeScript check passed.
- Mobile: chat write-path, BP card, and guidance suites `34 passed`; TypeScript check passed.
- Mac: `MacP0FeatureTests` `53 passed`.
- API types were regenerated for Web and Mobile after the quick-record response contract change.
- Generated system-map was refreshed and `scripts/check_doc_drift.py` passed.
- `d9d24902d` 的远端 CI 在提交后暴露了四个集成回归：dossier 引用了未提交的用户本地文件；语义分析句中的“记录”名词被误判为写入；进程内血压读路径没有带齐 API 的展示/安全字段；工具决策轮复用了过长的 fast-answer prompt。
- 修复后，本地同名 Agent CI 分片重跑：`agent-a-h` `471 passed`，`agent-i-z` `147 passed`；失败用例聚合回归 `89 passed`。
- **裁决**: PENDING_REMOTE_CI — 本地 Gate 已通过，等待本修复提交的远端 CI 重跑。

## G4 · 安全闸

- Outcome / causal-memory chain received an independent GO review after checks for migration safety, clinician-confounding gates, and legacy-view boundaries.
- Blood-pressure / quick-record chain received an independent review. The first review blocked three missing client paths; the second review blocked persistence of incomplete streaming or failed assistant output. All findings were fixed, including the terminal-turn guard, then independently re-reviewed **GO**.
- Severe blood-pressure feedback is now server-canonical and preserved across typed BP records, quick-record responses, Mobile chat and direct record flows, Web dashboard and typed form flows, Mac Record Hub / Quick Capture / menu-bar flows.
- **裁决**: PASS

## G5 · 部署健康闸

- Deployment is not requested for this integration-only task.
- **裁决**: NOT_APPLICABLE

## G6 · 验证闸(人在环)

- Production validation is not requested because no deployment is included.
- **裁决**: NOT_APPLICABLE

## S4 · 研发任务分解

| Source branch | Scope | Status | Verification |
| --- | --- | --- | --- |
| `claude/nice-saha-fa4a3c` | Flaky DB rollback test | absorbed | Focused infrastructure test passed |
| `claude/bold-swartz-79c816` | Chinese timing category correction | absorbed | Focused timing regression passed |
| `claude/admiring-moore-1effbf` | Persistent critical-vital safety escalation | absorbed | Safety review GO; focused safety tests passed |
| `claude/vigilant-euclid-a78ade` | Delayed notification escalation | reimplemented on accumulated main | Safety review GO; focused notification tests passed |
| `claude/sweet-gould-b1c3c7`, `claude/modest-golick-e58f3f`, `claude/thirsty-chandrasekhar-784f37`, `claude/bold-dirac-9ac246`, `claude/genui-metric-table-safety`, `claude/vigorous-hertz-e9070a` | Duplicate or already-absorbed correctness / safety work | verified already absorbed | Cross-branch regression gate |
| `claude/competent-elbakyan-585f28`, `claude/recursing-ellis-bad3c5` | Competing privacy implementations | superseded | Stronger single-source implementation retained on main |
| `claude/agitated-cerf-5c3abb`, `claude/sweet-almeida-317556` | Transport / interruption work | replaced by stronger accumulated main implementation | Focused transport regressions passed |
| `claude/elastic-euler-d31f7b` | Diet correction behavior | not cherry-picked | Existing explicit correction path is stronger; targeted regression passed |
| `claude/quizzical-northcutt-8c66dc` | Clinical / founder policy decision | blocked by product ratification | Deliberately excluded; no engineering substitute made |
| `claude/recursing-mendeleev-5157cd`, `claude/causal-honesty-floor` | Causal-memory / outcome honesty | reimplemented on accumulated main | Outcome and migration regression passed |
| `claude/goofy-gagarin-d5f558` | Blood-pressure safety and cross-client quick record | integrated and strengthened | Safety evaluator, three-client regression, independent GO |

## S5 · 实现

- Accepted source behavior was integrated sequentially into the accumulated `main` state. Direct cherry-picks were used only where the branch remained mechanically compatible; otherwise the intended behavior was reimplemented against the current contracts and verified.
- Blood-pressure work converged on one backend classification / guidance contract. Clients render server-provided `category`, `category_color`, and `safety_guidance`; no client may independently reinterpret a severe reading.
- Strict-review fixes added during integration:
  - cached starter synthesis can only replace the lowest-priority non-source chip and never exceeds the display limit;
  - user-timezone timeline testing is clock-controlled rather than tied to the host date;
  - safety feedback is shown immediately after a verified write receipt, before noncritical cache invalidation;
  - assistant-message record saving is available only for completed, non-error turns.
- Intentionally excluded or superseded source branches remain excluded; no partial or unreviewed branch changes are staged.
