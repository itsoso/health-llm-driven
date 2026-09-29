# Health status statements: clarify intent before treatment or writes

Status: implementing. Updated: 2026-09-29.

## Decision and admission

Bug fix for existing chat: distinguish a user's health/medication status report
from a request for clinical advice or a persistent change. Backend owns the
shared prompt; Mobile/Mac/Web continue displaying the existing response contract.
HealthProblem remains user-reported, SafetyGuardian retains all medical checks,
and WriteIntent requires existing authorization/confirmation. No new autonomy,
schema, tool permissions, provider, model, or prescription behavior.

## Evidence and scope

Read-only, authenticated-owner-scoped production audit: 110 paired turns across
seven days; 54 complete, 36 blocked, 12 waiting, 6 failed, 1 partial, 1 legacy.
17 permission replies and 4 generic medical holds. Historical versions are mixed;
these are not the current release's failure rates. Timed turns (107): P50 25.47s,
P95 120.52s, P99 198.66s. No raw production prompts or health payloads stored here.
Latest reported case classified ambiguous medication intent and ended in an
unsupported dose-action hold after two model rounds. Pre-sanitized output was
not retained in this audit; false-positive versus unsafe generation is unknown.

## User flow / contract

Read the current utterance and relevant prior context. For an ambiguous report
of improvement/no longer needing medication: acknowledge only what the user
reports, ask whether this is a status update or a requested record/reminder
change, and do not fetch unrelated data or create a regimen. Do not pronounce
recovery, recommend stopping medication, or claim a write. Explicit advice,
urgent symptoms, clinician provenance, pending confirmations and explicit
changes retain their existing paths and safeguards. A status-only follow-up is
not permission to change a record. Rules apply to full/lite/panel prompts and
compact empty-answer retries; no keyword-only shortcut. Preserve the old compact
health-context budget in addition to the shared intent rule.

Synthetic real-provider reproduction also exposed an existing false positive
for a question deferring discontinuation to a clinician. A candidate grammar
exception was rejected by independent review because appended discontinuation
synonyms could evade the existing tripwires. It is withdrawn: the medical
validator stays byte-identical to the production baseline. This slice changes
prompt behavior only; broader medical-language precision remains future work.

## Acceptance and rollout

Test prompt propagation before implementation; retain medical-boundary positive
and negative tests. Run focused tests, real-provider synthetic checks and the
required live regression gate, CI-mode integration, independent safety review,
then exact-revision CI and normal backend deployment. Synthetic checks must not
use production health data. Prompt guidance is not a new authorization boundary.
No latency improvement claim without a comparable post-change batch. Backend
only: no OTA or TestFlight needed. Roll back using the normal prior-revision
release workflow if clarification quality or safety regresses.

Non-goals: retrospectively rewriting health data, automatic discontinuation,
generic permission relaxation, UI card redesign, or solving every audited case.
