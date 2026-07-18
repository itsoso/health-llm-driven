# XiaoBa AIGC Media Dossier

| 字段 | 值 |
| --- | --- |
| 标识 | `xiaoba-aigc-media` |
| 创建日期 | 2026-07-17 |
| 当前阶段 | S5 验证 |
| 状态 | production_deployed_pending_manual_e2e |
| 负责人 | product-engineering |
| 发布策略 | Backend deploy after independent Model Studio credential and HTTPS source URL are configured; JS clients can follow with OTA |

## S0 Intake

User request (verbatim):

> 帮我查询一下阿里云的 Token Plan 的 API。应该有 AIGC 的调 wan 相关的 API。查一下百炼的那个 API 接口，帮我继续集成，更新到最新。然后这样我就可以上传自己的图片。并且能够做 AIGC 相关的一些事情。让本 APP、本 Agent 让小巴可以支持 AIGC 的一些能力，短视频的 AIGC。

The user wants Xiaoba to accept a user's image in chat, create AIGC images and
short videos, and expose the work as an Agent capability rather than a fixed
dashboard.

## S1 Discovery

- Existing chat already accepts up to nine image attachments, compresses them on
  device, and persists them as owner-scoped private files:
  `mobile/hooks/useMediaPicker.ts`, `mobile/utils/imageUpload.ts`,
  `backend/app/services/agent_executor.py`, and `backend/app/services/chat_utils.py`.
- Those signed private URLs cannot be supplied to an external model provider.
  The media integration must read the owner-scoped file server-side and pass
  bytes/data only during the explicitly confirmed provider call.
- Existing Token Plan routing is OpenAI-compatible text generation only:
  `backend/app/services/llm/model_registry.py` and
  `backend/app/services/llm/factory.py`.
- The current Agent Kernel provides a single tool-policy choke point and dynamic
  AtomicCapability contract. New media creation must enter there instead of
  bypassing it.
- Model Studio's current documentation states that Token Plan Team Edition is
  text-only and disallows custom application backends. Wan AIGC therefore needs
  a separate Model Studio pay-as-you-go API key and a matching regional endpoint.
- Wan 2.7 image calls are synchronous; Wan 2.7 text/image-to-video calls are
  asynchronous and must be persisted/polled. Provider task data is retained for
  a limited time, so results must be copied into the product's private storage
  before expiry.

## G1 Requirement Admission

**裁决**: PASS

| Field | Decision |
| --- | --- |
| First-class objects | `AIGCMediaConfirmation`, `AIGCMediaJob`, `AgentAuditLog` |
| Core-loop step | Makes a planned action easier to understand, execute, or share; never changes health decisions |
| Safety level | L3 health data plus user media privacy |
| Autonomy | `manual_confirm`; the Agent creates an encrypted draft, and only a physical card click consumes it and creates a billable job |
| Smallest E2E slice | One uploaded chat image -> one image-to-video request -> a truthful job card -> private result playback/download |
| Stale surface | None; this is an additive chat capability, not a new dashboard |
| Spec required | Yes: new user-visible behavior, external media transfer, persistent job, cross-surface API, and new write path |

The product is deliberately not a general-purpose media studio. V1 supports
health-action, healthy-recipe, exercise, recovery, and shareable wellness-story
media only. It must not produce diagnosis, treatment, medication, or before/after
health claims.

## S2 PRD

- [PRD](../prd/2026-07-17-xiaoba-aigc-media.md)
- [Feature spec](../specs/active/2026-07-17-xiaoba-aigc-media.md)

## S3 Plan

- [Implementation plan](../plans/2026-07-17-xiaoba-aigc-media.md)

## G2 Feasibility And Privacy Pressure Test

**裁决**: PASS

- Do not use `TOKENPLAN_API_KEY` for AIGC. Require an explicit
  `DASHSCOPE_AIGC_API_KEY` and workspace/region base URL.
- Do not expose the DashScope key, private source URLs, raw base64, or provider
  request payloads to clients, audit events, or logs.
- Do not let an LLM or client-provided boolean start a paid generation. The
  Agent creates a server-bound encrypted draft; an owner card click consumes a
  one-time confirmation ID bound to user, source, prompt fingerprint, model,
  and expiry.
- Short-video generation is asynchronous. The UI must present `queued`,
  `running`, `succeeded`, `failed`, or `cancelled`, never a fabricated completed
  state.
- The first cut accepts only a source image from the active chat turn. This
  removes ambiguous historic-media ownership and makes consent unambiguous.

## S4 Task Breakdown

1. Add media job model, paired managed migrations, configuration, and a
   DashScope Wan provider adapter.
2. Add an encrypted confirmation ledger plus owner-scoped get/cancel/poll job
   endpoints. Creation is not a public route; a client can only consume a
   server-issued one-time draft.
3. Register an Agent draft tool and two AtomicCapability cards: an explicit
   external-provider confirmation card and a private job projection card.
4. Add mobile chat card rendering and polling. Existing picker stays the source
   image attachment path.
5. Run backend, mobile, API-type, security, and deploy verification gates.

## G3 Tests

**裁决**: PARTIAL - feature gates pass; full Mac release suite has an unrelated snapshot baseline failure.

- Backend AIGC/Agent Kernel/migration/AtomicCapability suite: `141 passed, 1
  skipped` under in-memory SQLite. Multi-model stream and send-observability
  regression suite: `19 passed`. The focused AIGC hardening suite passes with
  `44` tests; `ruff` passes for all changed backend modules.
- Mobile confirmation-card regressions: `76 passed`; TypeScript type check
  passes. Web inline-card suite (`27` tests) and production build pass. Mac
  Core transcript/card verification passes (`405` tests, `1` skipped).
- The full Mac suite is currently red: `432` tests with `14` snapshot
  mismatches in pre-existing SpO2, Wearable, and related presentation snapshot
  suites. Those source/snapshot files are outside this feature diff; snapshots
  were not re-recorded. This is a release-level baseline issue and blocks a
  full client-release gate until it is triaged separately.

## G4 Security Review

**裁决**: PASS

The first review found six release blockers: model-controlled confirmation,
Token Plan credential reuse, instructional-only medical restrictions,
cancel/complete races, permanent failure on transient polling errors, and
unbounded result buffering. The first remediation re-review then found four
dispatch-specific blockers: Unicode/clinical-policy bypasses, cross-process
duplicate billing, incomplete 2xx provider receipts, and non-atomic polling.

The final independent review passes after: invisible Unicode normalization and
clinical/medication/dose backstops; a post-lock fingerprint recheck plus
database uniqueness; `submission_unknown` for indeterminate successful
responses; and task/account-level durable poll leases. The reviewer directly
verified the original bypass prompts and ran `67` targeted tests with no
release-blocking finding.

## G5 Deployment Health

**裁决**: PASS

Local deployment configuration now binds `DASHSCOPE_AIGC_API_KEY` to the
existing independent DashScope vision credential. It is verified distinct from
`TOKENPLAN_API_KEY`, accepted by a non-billable Model Studio task probe, and
uses public HTTPS `SITE_BASE_URL=https://health.executor.life` for image-to-video
source retrieval. No billable generation occurred before deployment.

Production deployment completed through `deploy.sh -b` at commit `ec47d141b`.
Managed migrations for the AIGC job ledger, confirmation ledger, and duplicate
dispatch guard applied successfully; backend deployment health scored `60/60`.
The public owner-scoped AIGC job route returns `401` without authentication,
and the production process verifies the independent credential, non-Token Plan
identity, validated Model Studio base URL, and `.life` source base URL.

The client surfaces are also live: the Mobile OTA for runtime `1.3.1` was
published to the production channel from `2deb17b47`, and the Web frontend was
rebuilt and restarted through `deploy.sh -f` from the same revision. After the
restart, `https://health.executor.life/` returned `200`; the public health
endpoint remained healthy with database, Redis, and Celery connected.

iOS TestFlight build `1.3.1 (232)` was built from `379322f6a` through the
production EAS profile and submitted to App Store Connect on 2026-07-18. EAS
confirmed the submission finished without an upload error. The release input
passed the App Store pack preflight, TypeScript validation, and `260` mobile
test suites (`1,895` passed, `1` skipped). Apple processing remains external
to this deployment gate before the build becomes selectable in TestFlight.

Domain verification on 2026-07-18: `health.executor.com` has no public A record
via Cloudflare DNS; the local resolver returns reserved benchmark address
`198.18.13.99` and TLS fails. It cannot be used as a Model Studio-fetchable
source URL. `https://health.executor.life` resolves to the production Alibaba
Cloud host, has valid HTTPS, and returns a healthy API response. Configure
`SITE_BASE_URL=https://health.executor.life` unless the `.com` DNS and TLS
configuration is completed and independently re-verified.

## G6 Production Verification

**裁决**: PENDING manual owner confirmation

Verify one confirmed text-to-image and one confirmed image-to-video task from
Mobile, Web, and Mac; verify owner isolation and a private-result URL refresh
after its prior URL expires. This Gate deliberately requires a real user card
click because a synthetic backend request would bypass the product's explicit
paid-generation consent boundary.

## Configuration Record

Production uses an existing independent Model Studio pay-as-you-go credential
with Wan access. A Token Plan key is intentionally rejected for this use. No
secret is stored in source or copied into this dossier.
