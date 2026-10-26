# Public phone registration and administrator creation

| 字段 | 值 |
|---|---|
| slug | `public-phone-registration` |
| 创建日期 | 2026-10-26 |
| 当前阶段 | S5 实现与本地验证 |
| 状态 | in_progress |

## G1 · Requirement admission

- 用户明确要求管理员可直接创建用户、取消邀请制并开放手机号注册。
- 按需访问能力，验证手机号后建立用户隔离身份；不放宽健康数据或 AI 同意。
- Spec: `docs/specs/active/2026-10-26-public-phone-registration.md`.
- **裁决：PASS。** 不代替 G4、CI 或生产验证。

- Request: remove invitation-only access; permit verified-phone signup and direct administrator account creation.
- Baseline: `cf080ee99` from freshly fetched origin/main.
- Workspace: isolated worktree to preserve the shared checkout's unrelated changes.
- Controller: health-harness-orchestrator; safety-gate overlay.
- Spec: `docs/specs/active/2026-10-26-public-phone-registration.md`.
- State: implementation and focused regression verification; not released.

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
- Release activation and related existing publisher suites: 270 passed before native systemctl-format follow-up; final follow-up verification required.

## Remaining gates

- Focused backend/Mobile/Web checks, PostgreSQL semantics, integration CI mode.
- Independent safety review of exact candidate.
- Authorized integration and exact main CI; trusted backend/Web/OTA delivery.
- Production policy/runtime readback and user-flow acceptance, without creating real accounts or sending SMS solely as a probe.
