# Configurable System One decision providers

Status: implementing (code verified; live decision-provider evaluation pending). Owner: Reva backend. Updated: 2026-09-24.

## Decision and admission

Add an optional backend decision boundary with Jev, Laya and other System One
compatible HTTP services. Keep chat models and tool execution in their existing
factories/gateway. This is infrastructure supporting the existing Health OS
query/explanation loop; SafetyGuardian and WriteIntent authority stays unchanged.
The production extension adds a Web administrator panel and an additive control
table. It adds no autonomous health write or medical claim.
Privacy-sensitive egress and administrative control are the principal risks. Default off preserves existing
behavior. No additional user burden except explicit consent for a new recipient.

## Smallest end-to-end slice

Agent turn -> deterministic answer tier -> optional typed decision -> tier floor
and finite read-only capability advice -> existing model selector and tools ->
redacted decision metadata in persisted message and done event.

The model may raise the answer tier and recommend an existing read capability;
it cannot lower the deterministic tier, authorize execution, invent tools, alter
IntentFrame write flags, waive cancellations, or change ToolGateway checks.
Capabilities are advice to the current agent, not direct tool dispatch. The
transport supports choice, score and noul; this initial route uses choice.

## Configuration and contract

`DECISION_MODE=off|shadow|on`; shadow performs real I/O but leaves routing intact.
`DECISION_PROVIDER=jev|laya|systemone`. Base URL and model are configurable;
compatible servers share the HTTP adapter, other protocols implement
`DecisionProvider.evaluate`. Requests and complete responses are validated.
No automatic provider fallback, retry, redirects or environment proxies.
Timeouts, invalid input, invalid response and authorization denial are explicit
fallback outcomes; the established agent remains responsible for the task.

Only current user message is sent by the route. No profile, history, tool data,
credential, attachment or user identifier is included. Existing PII scrubber
runs before transport. HTTPS remote destinations are disclosed by exact endpoint;
changing the recipient description/address changes the opaque consent revision.
Local means strict loopback only. The existing generic consent API schema remains
unchanged; clients already render recipients and treat policy_version as opaque.

## Acceptance and verification

- All three configurations select the correct endpoint/model; all primitives
  round-trip with strict vocabulary, finite probability and usage validation.
- Off makes no call; shadow makes a consented call without applying the result.
- No high-stakes downgrade, write authority change or silent cloud failover.
- Remote sends require current per-user consent; recipient changes invalidate it.
- Failures contain safe codes and metadata, never prompts, responses or keys.
- Integration tests exercise AgentExecutor, answer selection and message metadata.
- Run focused pytest with coverage, consent and gateway regressions, System Map
  drift checks, LLM change gate, and available live regression. Mock HTTP tests
  establish adapter wiring only, not actual model quality or remote availability.

## Rollout and rollback

Ship disabled; configure a chosen service, accept updated recipient disclosure,
then evaluate Chinese requests before enabling on. Roll back with the durable
switch or DECISION_MODE=off. Thresholds require recalibration after switching
models/providers. The user subsequently authorized production deployment and an
enable/disable control exclusively for active administrator user_id=3.

The global switch starts disabled and uses a revision-based update plus an audit
record in one PostgreSQL transaction. Both API methods authenticate and enforce
the designated administrator. Invalid provider configuration still permits
turning the switch off; concurrent or stale updates receive HTTP 409.

Laya runs on the production host as a separate, unprivileged loopback service.
The trusted publisher prepares a first-use Laya profile only if no decision
configuration exists; explicit existing settings always win. A separate random
bearer key enters the existing sealed candidate environment transaction. The
database switch remains off even though the server is ready for mode=on.
Backend rollback retains the independent idle service and additive database table.
Unknown partial installs and mismatched existing installations block publication.

## Changelog

- 2026-09-24: Accepted infrastructure slice and bounded privacy/routing contract.

## Historical verification before the production extension (2026-09-24)

- Focused provider/routing/consent/AgentExecutor suite: 63 passed, 2 pre-existing
  skips. Coverage of decisions + consent: 94.35%, above the 80% gate. Includes
  a real loopback socket with a protocol fixture, not actual Laya inference.
- Isolated PostgreSQL consent/grant/revoke/user-isolation tests: 6 passed.
- Broader regression: 3776 passed, 2 skipped, 2 model-routing failures, and
  2 local DB-role fixture errors. The fixture cases pass in isolated PostgreSQL.
  Independent original-HEAD comparison reproduces both model-routing failures;
  this change does not claim the entire existing suite is green.
- Independent privacy/safety review: GO after fixing optional-config isolation
  and giant numeric response validation.
- System Map check and focused Ruff checks passed.
- Existing LLM regression: offline suites and 5 live orchestrator cases passed;
  this proves the existing LLM path only, not Jev/Laya service availability.
- No new API credentials supplied, no actual Jev/Laya inference benchmark,
  no commit/push/deployment, and decision routing remains off by default.

Current production-extension results and release gates are tracked in
`docs/dossiers/2026-09-24-laya-production.md`; the historical results above do not
prove this extension or any production deployment.
