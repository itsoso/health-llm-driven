# Local main reconciliation

| 字段 | 值 |
|---|---|
| slug | `local-main-integration` |
| 创建日期 | 2026-10-29 |
| 当前阶段 | S5 实现 |
| 状态 | building |
| 负责 | Codex |

## Scope

Reconcile proven product changes from the shared dirty checkout onto the current
canonical `main` without resetting, cleaning, or committing unrelated historical
release evidence. The integration baseline is
`158dc5a0ce5ce5ec787de7a498772f7f2fb6db64`. The final integration was rebased
without conflicts onto `ee7cbfda15378b3e1eac11d0581cf5cd10898d74` after canonical
`main` advanced concurrently. The reviewed non-dossier patch digest remained
`75d16d42b8799a6f4a1c5209db838f6bb8d4d4367d4ae6b8ae4277cd905c9cef`.

## G1 · Admission and boundaries

- **裁决**: PASS
- G2 scope is fixed to four independent, already implemented slices: chat header
  actions, retryable chat images, diet record/share actions, and an offline food
  vision transport benchmark.
- The older supplement manual-entry patch was excluded. Current `main` already
  contains a more complete fail-closed implementation and its safety evidence;
  applying the older checkout copy would have weakened that state.
- `codex/account-deletion-cache-scope` and
  `codex/voice-client-lifecycle-fix` require no merge because their behavior is
  already integrated or superseded on `main`.
- Draft PR #280 (`codex/neo-wechat-health-bridge`) remains outside this delivery:
  its cross-family, activation, recovery, and production lifecycle gates are not
  complete.
- Historical dossiers, receipts, and other source-unknown files in the shared
  checkout remain untouched. This clean integration checkout contains only the
  task-owned changes listed below.

## Candidate commits

- `288bd8ff1` — unify chat header actions.
- `8099cb846` — add retryable chat image fallback.
- `7a490274c` — refine diet record and share actions.
- `66db62c0c` — compare asynchronous vision transport.
- `5f3800168` — preserve 44×44 header touch
  targets around the 40×40 visual controls.
- `2144420ae` — bind community sharing to the
  exact recorded meal.

## Verification

- Focused Mobile Jest: 6 suites, 291 tests passed.
- Mobile TypeScript: `tsc --noEmit` passed.
- Changed-file ESLint: zero errors; ten pre-existing warnings in the registry test.
- Design-token drift: raw hex usage decreased from 599 to 596; font-family count
  remained 67.
- Vision benchmark regression: 51 passed. The benchmark uses synthetic inputs and
  is diagnostic only; it does not read personal images or health records.
- Final Mobile regression: 381 suites, 4,051 passed and one existing skip.
- Final focused header and card regression after repairs: 371 passed; TypeScript
  remained clean.
- System Map, tracked-secret scan, dossier consistency, diff hygiene, and changed-file
  ESLint passed. ESLint retained ten existing warnings in the registry test and no
  errors.
- The final local release-invariants run reached 2,427 passed / 11 skipped before
  failing a macOS-only fixture assumption that `/etc` is not a symlink. The exact
  failing test also fails on the untouched `158dc5a0` baseline because macOS maps
  `/etc` to `private/etc`; this run is preserved as a failure and is not publication
  evidence. The exact candidate Linux CI remains the release gate.

## G4 · Independent safety review

- The first review BLOCKED a peer-share route that could target another record owned
  by the same user.
- The repair accepts only the exact canonical route, requires positive safe-integer
  route and card IDs to match, and removes invalid candidates before they can fall
  through to the generic action bar. Negative tests cover mismatched, trailing,
  non-numeric, unsafe, missing, zero, and unrecorded cases.
- The independent fixed-range re-review at `2144420ae`
  ran 121 Mobile tests plus TypeScript and diff checks.
- **裁决**: GO

## Gate state

- G3: IN PROGRESS pending the exact candidate Linux CI. Local product behavior is
  green; the platform-specific release-invariants failure is recorded above.
- G4: GO for the exact code candidate through `2144420ae`.
- G5/G6: NOT STARTED. No push, deployment, OTA publication, or App Store mutation
  is claimed by this document.
