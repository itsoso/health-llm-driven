# Safe HTML table rendering — Mobile and Mac

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 verified / G4 GO; release pending alignment |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 — Scope

裁决: PASS

- Run: `bc8519389ba3`; controller: Health Harness; overlays: safety; system-map on-demand.
- Request: render the screenshot's assistant HTML sleep table on Mobile and Mac.
- Scope: bounded display-only projection + source disclosure. No backend prompts, user data writes or arbitrary HTML execution.
- Spec: `docs/specs/active/2026-09-29-safe-html-table-rendering.md`.
- Baseline: Mobile disables Markdown HTML; Mac escapes it. Both lack a safe HTML table path. Mac read-only baseline: 65 tests passed, no HTML coverage.
- Worktree has unrelated GPS/privacy/dossier edits. Preserve them; do not stage them. Previous prompt publication remains paused due upstream auth/registration release scope.
- Ownership: root Mobile/spec/verification; scope_investigation Mac parser/render/tests only. Independent safety review on fixed local candidate before any release.

## Gates / evidence

- G1/G2: admitted as maintenance; bounded cross-client contract established.
- G3 RED: Mobile parser tests initially fail (module missing); actual ChatBubble preview test fails; normalization test then reproduces loss of `<br>` and legacy-looking literal cell data (`/tmp/reva-html-normalization-red.log`). Mac real render regression fails 5 preview assertions, `/tmp/mac-html-table-red.log`; real ViewModel exposed closing-fence cleanup and prose-command extraction needing correction.
- G3 GREEN: initial Mobile full `CI=1 npm test -- --runInBand`: 317 suites, 3,116 passed / one existing skipped, exit 0 (`/tmp/reva-html-mobile-full.log`). Additional real native renderer tests and parser tests: 22 passed. Typecheck and focused ESLint passed. Mac core initial 528 tests, one skipped, zero failures. These intermediate results are superseded by the final correction evidence below.
- Mac final G3: Core + real WK suite, 530 tests, one existing Keychain opt-in skipped, zero failures, exit 0 (`/tmp/mac-html-table-final-green.log`). WK DOM assertions cover exact cell order/empty text, literal encoded tags, no injected scripts/images/iframes/action nodes, horizontal overflow and exact disclosed source. Synthetic screenshot `/tmp/mac-safe-html-table-smoke.png` inspected by writer and root; this is real WebKit using the current transcript shell, not whole-app manual acceptance.
- Initial G4 on `f8346d6b3c34884e354380793a5afa19ff7a0ee1`: **NO-GO**. Reviewer reproduced separate reva-ui action fences alongside an HTML table becoming actionable Mobile cards; Mac likewise still produced GenUI placeholders. No candidate published.
- Correction: whole HTML-bearing messages keep all prose protocol fences literal; only independently structured API card fields remain active. Added RED/GREEN for before/after fences, menu_share, legacy protocol prefix, and indented code not being promoted by cleanup. Mac final correction: 532 tests, one existing opt-in skip, zero failures, exit 0 (`/tmp/mac-html-protocol-final-green.log`). Mobile final full rerun: 318 suites, 3,122 passed / one existing skipped, exit 0 (`/tmp/reva-html-mobile-final2.log`); focused correction 129 passed. Final typecheck, focused ESLint, map/governance/secret/diff checks passed. Fixed candidate `a6c305eead02cef7524a063bc3820f7aeb6a7f6b`; new independent G4 pending.
- G5/G6: not started; no deployment claimed.

Second G4 on `a6c305eead02cef7524a063bc3820f7aeb6a7f6b`: **NO-GO**. Prefix removal still consumed the whitespace that distinguishes indented code from a raw table. Added the composed prefix + indented-table counterexamples first (RED), then changed cleanup to remove only protocol bytes and keep the remainder's exact whitespace. Added Mobile emoji-prefixed protocol-boundary recognition to prevent a closing fence from consuming the next table; these blocks remain inert. New focused regression and final full rerun/re-review recorded below when complete. No Mac production code changes after its 532-test correction run.

## Final G3 / G4

裁决: GO

Code candidate: `46837f7376e08d1b9f7f7518d373cbcd713fd757`.

- Final Mobile `CI=1 npm test -- --runInBand`: **318 suites, 3,123 passed, one existing skipped**, exit 0 (`/tmp/reva-html-mobile-final3.log`). Focused cross-path regression 137 passed; typecheck/focused ESLint passed.
- Independent read-only G4: **GO**, 118 focused tests independently passed; all composed prefix/indent and sibling protocol counterexamples closed. No new script/native bridge/network/prose-action path found. Mac production blobs unchanged from the 532-test / zero-failure / one existing skip verification above.
- Final Mobile native fixture was re-bundled from this exact code candidate and reinstalled only as `life.executor.health.htmlaudit`; CUA confirmed emoji-prefixed menu source stays inert, the following table previews, and the displayed prose-card count is zero. Source fixture removed afterward; `bundle-final.log` retained with local artifacts. This does not replace production-package release acceptance.
- No database/API/model prompt/dependency changes. Local secret scan, diff checks, System Map and skill governance passed. No unknown worktree changes staged.
- Code-safety GO is not a release verdict. Candidate has not been pushed or deployed; exact remote CI and release integration remain unfulfilled, and main reconciliation is still blocked as described below.

## Verification gaps

Complete production-app UI acceptance and release integration verification remain pending. No live health data queried or modified for this task. System Map wrapper passed after using the repository Python 3.12 in PATH; map generation is unchanged by this display-only slice. Dossier checker accepts this dossier but remains red for the pre-existing medication-clarification dossier metadata; that unrelated dirty file is not modified or staged by this task. LLM change-path gate passes without a live model requirement; no prompt/provider change.

Read-only release check after implementation: `git ls-remote origin refs/heads/main` returned `d55e189cdf74e5cb61a645e761ab6d4018efd077`. Local candidate is not that SHA; unrelated historical CI successes are not release evidence. No remote Git writes, reconciliation, OTA, TestFlight or production desktop deployment performed.

Mobile UI evidence now includes native iPhone 17 Pro / iOS 26.5 simulator inspection: an isolated offline `life.executor.health.htmlaudit` app reused the installed audit native shell, with updates disabled and a newly bundled synthetic entry importing the actual SafeTableMarkdown component. CUA verified the six-column table, horizontal scroll through the final column, preserved empty cell, literal encoded script text, and source open/close. No account/network/data hooks imported. Temporary entry was removed after bundling; artifacts remain under `/tmp/reva-html-simulator.yeY6m6`. This is a native component acceptance fixture, not full production-app end-to-end or OTA evidence. The G4 follow-up changes affect protocol opacity, not the inspected layout. Mac evidence is scoped to the real transcript shell; installed production application update not performed. Full release CI remains separate and blocked by the previously reported branch/release scope.
