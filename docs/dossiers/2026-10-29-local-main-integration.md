# Local main reconciliation

| 字段 | 值 |
|---|---|
| slug | `local-main-integration` |
| 创建日期 | 2026-10-29 |
| 当前阶段 | G4 OTA 领取冲突收口审查 |
| 状态 | recovery implementation verified locally |
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

- G3: PASS for canonical main `1c30cfa94a689f5b99f6c638a27c622a87a35d35`;
  exact Linux CI run `40847684852` is green across all 32 jobs.
- G4: GO for the integrated product changes. The preclaim recovery extension is
  limited to fixed release evidence and requires its own review before use.
- G5: backend PASS; OTA validate PASS; OTA publish BLOCKED for 1c30 at the
  preclaim boundary. The original failed operation is preserved and cannot be
  replayed.
- G6: backend production path verified; Mobile device installation and real-data
  acceptance remain unverified.

## Main integration and production evidence

- The reconciled Mobile changes, build-286 OTA baseline, dietary reasoning fixes,
  and provider fallback repair were integrated at
  `1c30cfa94a689f5b99f6c638a27c622a87a35d35` and remain in the ancestry of the
  current successor main revision. Production remains on 1c30 until its failed
  preclaim is closed and the successor completes its own backend release.
- Exact CI run `40847684852` completed successfully with all 32 jobs green.
- Trusted Release validation `40849267386` passed. Backend release run
  `40850051454` completed successfully; production source and completed receipt
  both bind 1c30, all backend/worker services are active, public health returns
  200 healthy, and anonymous `/api/v1/auth/me` returns 401.
- OTA validation run `40850818571` passed for the same revision and build-286
  runtime cohort.

## OTA preclaim incident and recovery

- The only OTA publish run, `40851087780`, failed at `claim-ota`. Its official
  artifact `12887890387` has ZIP SHA256
  `304d625462b5577c3c2a166ab7a5edc164f652f35474f51aec6f03b9b73e1476`
  and contains exactly `ota-claim.json`, `ota-preflight.json`, and the sanitized
  `command_failed` diagnostic. There is no vendor or completion receipt.
- Read-only server evidence shows `/var/lib/reva-release/ota/1c30…` contains only
  `intent.json` and `lease.json`; `claimed.json`, `verified.json`, and
  `completed.json` are absent. The original business lease remains present with
  its recorded device/inode identity. The vendor publish call was never reached.
- G5 is **BLOCKED** for 1c30 and that SHA must never be republished. A fixed,
  byte-bound preclaim-closure profile is being added in the next reviewed main
  revision. It accepts only this exact failed workflow/job/artifact and original
  publisher source hashes, and requires a fresh exact-CI-green closing SHA plus
  unchanged server evidence. After closure, the successor SHA must complete its
  own backend and OTA validate/publish sequence.
- TestFlight, App Review, phone operation, and real health-data acceptance remain
  outside this recovery and were not changed.

## 53f successor delivery and pre-intent-failure incident

- Successor `53f9c6aee3eb30d8937a4582e206cce47de80157` closed the 1c30 unpublished
  preclaim, passed exact CI run `40854228341` (32/32), and deployed its backend
  through run `40859955295`. Production source and the durable backend receipt
  bind 53f; public health is 200/healthy and anonymous auth is 401.
- OTA validate `40860774134` passed. The single publish run `40861067214`
  failed at `claim-ota` before server OTA intent creation and before the vendor
  call. Official artifact `12890544500` has ZIP SHA256
  `261128bc5c7ba573a6df56fb6a33255610ce877d2009e6018131fdc8180fde50`
  and contains only claim, preflight, and sanitized failure diagnostics.
- The overlapping no-backup Web operation
  `dbbb6a5caeb94991ab079a39b7a1275d` is now durably
  `FRONTEND_SUCCEEDED` for 53f, with the fixed frontend tree and artifact digest;
  the business lease is absent. No `ota/53f…` server directory exists.
- The frontend operation's durable files begin after the GitHub failure timestamp,
  so the closure does not claim that its lease caused the failure. It binds the
  completed overlapping operation only to prove that no related publication or
  lease remains unfinished.
- A dedicated pre-intent-failure closure operator now binds the official failed workflow,
  exact publisher bytes, completed frontend receipt, absent OTA state, absent
  lease, backend terminal, and health readback. It writes one durable closure and
  makes a future 53f claim fail closed. It never creates an OTA intent, calls the
  vendor, or grants retry authority.
- Focused recovery/history verification currently passes 438 tests with two
  existing skips. Independent G4 and exact successor CI are still required before
  the operator may be staged or executed. The failed 53f publish will not be
  replayed.
