# Public phone registration and administrator creation

| 字段 | 值 |
|---|---|
| slug | `public-phone-registration` |
| 创建日期 | 2026-10-26 |
| 当前阶段 | S6 部署；后端与 Web 完成，OTA 收尾中 |
| 状态 | in_progress |

## G1 · Requirement admission

- 用户明确要求管理员可直接创建用户、取消邀请制并开放手机号注册。
- 按需访问能力，验证手机号后建立用户隔离身份；不放宽健康数据或 AI 同意。
- Spec: `docs/specs/active/2026-10-26-public-phone-registration.md`.
- **裁决：PASS。** 不代替 G4、CI 或生产验证。

- Request: remove invitation-only access; permit verified-phone signup and direct administrator account creation.
- Initial baseline: `cf080ee99`; rebased onto `184d2205f` to retain the concurrent native UUID fix.
- Workspace: isolated worktree to preserve the shared checkout's unrelated changes.
- Controller: health-harness-orchestrator; safety-gate overlay.
- Spec: `docs/specs/active/2026-10-26-public-phone-registration.md`.
- State: backend, Web and registration policy released; App OTA remains incomplete.

## Evidence and checkpoints

- Existing production policy rejected phone-code and administrator create requests with 403.
- First regression run: administrator-admission and public-default tests failed on the baseline (8 failures, 21 passes).
- Mobile error-parser regression failed with expected business code versus actual Axios ERR_BAD_REQUEST (1 failure, 68 passes).
- Baseline System Map verification passed. Focused auth.py selector is not indexed; source and adjacent tests are authoritative.
- Production publishers enforce invitation flags; a reviewed, dedicated transition is needed before release. No production settings changed by diagnosis.

## Local verification

- Backend authentication, admission, abuse limits, merge, config, invitation compatibility and Web-session regression: 150 passed, 1 PostgreSQL-only case skipped in SQLite run.
- Real PostgreSQL dedicated test database: 16 passed, including concurrent registration and administrator admission.
- Mobile auth service, login UI and auth hook: 148 passed; TypeScript passed.
- Web phone registration, cookie session, admin and navigation: 23 passed; TypeScript and focused ESLint passed.
- Backend integration plus self-registration/WeChat compatibility: 30 passed.
- System Map drift gate passed after changes.
- Release activation and publisher regression run: 268 passed; dedicated activation suite: 45 passed, including the actual multi-line systemctl EnvironmentFiles format.
- Web full suite: 609 passed, 1 skipped; production Next build passed.
- Independent G4: GO on `4ee08597a433d009a7ee0ee4ff4f9ce8730441ba`; follow-up stale invitation restoration fix requires incremental review.
- Production auto-approval env has no override; deployed source default is true. Recheck effective value after activation.

## Production delivery and OTA blocker

- `c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf`: full CI `40274525250` succeeded; independent final G4 GO. Supplemental production-to-candidate checks passed: PostgreSQL 213 passed/6 inapplicable combinations skipped; integration 316 passed/8 skipped; Mobile 3963 passed/1 skipped; real-model regression and path-sensitive gate passed using synthetic data only.
- Backend workflow `40277848266` succeeded, with server `SUCCEEDED` receipt and health 60/60.
- Registration activation reached `CONFIGURATION_SUCCEEDED`. All three service processes read the new policy; effective settings confirm self-registration and auto-approval enabled, both invitation flags disabled. Immediate post-restart checks paused; only the original journal was resumed after stable process readback. No SMS or user creation was performed.
- Web operation `15bcb6ab52274668a37451b8625bfed6` reached `FRONTEND_SUCCEEDED`, without backups. Anonymous `/register` returns 200 with phone/verification-code fields and no invitation field. Empty phone-code payload returns the backend's 422 validation response; unauthenticated admin create remains 401.
- OTA validation `40280824500` passed. Publication `40281092624` failed at `claim-ota`, with only the original intent and lease saved and no `claimed.json`. The bound publisher invokes the vendor only after a successful claim; this run did not publish an update.
- Read-only execution of the original local compatibility proof returned `COMPATIBLE`, but was observed still running after 271 seconds, beyond its 240-second validity window. Repeated native-recovery verification inside each identity-chain edge is the identified hot path. The repair validates that recovery once per chain traversal, repeats it on every separate proof, and retains all per-edge checks and the original deadline.
- The failed OTA requires its own fixed, byte-bound unpublished-claim closure before a new candidate can publish. Original evidence and failure semantics remain intact; no retry of the consumed SHA.

## Remaining gates

- Independent safety review and exact main CI for the publisher repair and fixed closure profile.
- Verified closure of the original unpublished OTA, followed by new candidate backend and OTA receipts.
- Real phone delivery/registration and administrator-create acceptance remain unverified; do not infer them from read-only probes or create real accounts solely as a probe.
