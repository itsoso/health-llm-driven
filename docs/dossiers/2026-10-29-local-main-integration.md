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
`158dc5a0ce5ce5ec787de7a498772f7f2fb6db64`.

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

- `891680fa8ca5c110a7a75885b4383cff430a7da1` — unify chat header actions.
- `193a5c833bdfd87e79735dc26e33af68dc57b996` — add retryable chat image fallback.
- `2d914f715b3e38ee0288ccd89f50f9934aef5cbd` — refine diet record and share actions.
- `44caf537663e947efe0678650b61a63a4b8c4709` — compare asynchronous vision transport.

## Verification

- Focused Mobile Jest: 6 suites, 291 tests passed.
- Mobile TypeScript: `tsc --noEmit` passed.
- Changed-file ESLint: zero errors; ten pre-existing warnings in the registry test.
- Design-token drift: raw hex usage decreased from 599 to 596; font-family count
  remained 67.
- Vision benchmark regression: 51 passed. The benchmark uses synthetic inputs and
  is diagnostic only; it does not read personal images or health records.
- Full Mobile regression, release-invariants, independent G4, exact remote CI,
  publication, and production acceptance are recorded only after they complete.

## Gate state

- G3: IN PROGRESS pending full Mobile and release-invariants checks.
- G4: IN PROGRESS under independent safety review of the exact candidate range.
- G5/G6: NOT STARTED. No push, deployment, OTA publication, or App Store mutation
  is claimed by this document.
