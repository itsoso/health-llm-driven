# LifeNav Mobile UI release — 2026-10-14

| 字段 | 值 |
| --- | --- |
| 状态 | shipping |
| 当前阶段 | S6 verification and release preparation |

## G1 Scope admission

裁决: PASS

The user explicitly requested shipping the already implemented compact Mobile UI. This candidate preserves existing product scope and storage contracts; new backend-dependent modules are excluded and that boundary has been communicated. No new clinical behavior, source permissions or native capabilities are introduced.

## Scope and authorization

User explicitly requested deployment to the phone after local LifeNav UI improvements. This release extracts only the backward-compatible presentation changes from the existing LifeNav worktree onto origin/main e9ca5c218bb230f78a7e6a20e1fb2352ec49a0c4. The original worktree remains untouched.

Included: compact typography, less header text, combined date/status/save toolbar, selected tabs, collapsible task editors and composers, finished-task folding, local current-day search, and preserving draft input while filtering or collapsing. Existing weekly task links open the corresponding editor.

Excluded: unshipped morning ingestion, goal schema expansion, new calendar APIs, managed migrations, external source credentials, native configuration, dependency changes and Web deployment. Existing API/model/save/account isolation contracts remain byte-for-byte unchanged. The new modules remain in the original worktree for separate backend readiness.

## Verification

- Local TypeScript passed; focused UI lint has zero errors and eight pre-existing test/import/hook warnings.
- Adapted page integration tests: 22 passed, including explicit saving, conflict retention, background/account invalidation, search/editor retention, finished task links and collapsed input drafts.
- The first full CI-mode Mobile run had one obsolete weekly-navigation assertion failing, 3609 passing and one skipped; that assertion was updated to the released weekly-table controls and the page suite passed. Final full run pending.
- Source and mobile changes are JS/TS-only; no API types, service, runtime version, native plugins, package locks, backend or database changes included.
- Secret scan passed for existing tracked files; staged source scan and exact SHA CI remain required.
- Production was read-only verified at e9ca5c218; GitHub relay enabled/active. Explicit existing known_hosts file restores strict host verification for the configured production target; no keys or host trust were changed.

## Delivery state

Candidate preparation in progress. Commit, exact main CI, reviewed production authorization, same-SHA backend deployment and trusted OTA validate/publish must each be recorded independently. No device-application claim without device evidence. No backups, recovery copies or restore drills per repository standing instruction.
