# Safe HTML table rendering — Mobile and Mac

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 implementation / G3 |
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
- G3 GREEN: initial Mobile full `CI=1 npm test -- --runInBand`: 317 suites, 3,116 passed / one existing skipped, exit 0 (`/tmp/reva-html-mobile-full.log`). Additional real native renderer tests and parser tests: 22 passed. Final candidate rerun pending. Typecheck and focused ESLint passed. Mac core initial 528 tests, one skipped, zero failures; final parser alignment / WK verification pending.
- Mac final G3: Core + real WK suite, 530 tests, one existing Keychain opt-in skipped, zero failures, exit 0 (`/tmp/mac-html-table-final-green.log`). WK DOM assertions cover exact cell order/empty text, literal encoded tags, no injected scripts/images/iframes/action nodes, horizontal overflow and exact disclosed source. Synthetic screenshot `/tmp/mac-safe-html-table-smoke.png` inspected by writer and root; this is real WebKit using the current transcript shell, not whole-app manual acceptance.
- G4: pending fixed local candidate review.
- G5/G6: not started; no deployment claimed.

## Verification gaps

UI acceptance and complete release integration verification pending. No live health data queried or modified for this task. System Map wrapper passed after using the repository Python 3.12 in PATH; map generation is unchanged by this display-only slice. Dossier checker accepts this dossier but remains red for the pre-existing medication-clarification dossier metadata; that unrelated dirty file is not modified or staged by this task. LLM change-path gate passes without a live model requirement; no prompt/provider change.

Mobile UI evidence is React Native component/real Markdown rendering and interaction tests, not an installed simulator build. No iOS simulator visual acceptance or production OTA claimed. Mac evidence is scoped to the real transcript shell; installed application update not performed. Full release CI remains separate and blocked by the previously reported branch/release scope.
