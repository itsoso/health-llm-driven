# Family relationship and read-only health records

> Status: implemented locally; release and live linkage pending
> Updated: 2026-09-29
> Source baseline: 623407d6d

## Decision and admission
Allow an authenticated family owner to view a consenting family member's existing
medical examinations and illness timeline in Mobile and Web without switching accounts.
Support explicit daughter/son relationships and household nicknames.

RequirementAdmission:
- classification: product_change
- first_user_fit: parents coordinating a child's follow-up
- core_loop_step: evidence -> follow-up -> review
- first_class_objects: HealthProblem, HealthTwin, ExecutionEvent
- target_surface: Mobile and Web; Backend is the authorization/data source of truth
- safety_level: privacy_sensitive
- prescription_or_causal_verdict: none
- autonomy_tier: manual_confirm (joining/sharing); reads do not mutate health data
- evidence_provenance: existing user-owned examinations and illness records
- claim_hedging: n/a, no new medical advice
- verification_window: immediate identity and report readback
- success_metric: owner sees authorized child's records; unrelated/sibling access denied
- added_user_burden: existing-account invitation acceptance, reversible sharing
- non_goals: account merge, prescription writes, implicit guardianship verification,
  unrestricted impersonation, external messaging, third-party AI processing
- smallest_end_to_end_slice: invitation -> daughter relationship -> member card ->
  read-only report details and illness progress -> revocation
- stale_surface: retain existing family dashboard, add details rather than duplicate
- spec_required: yes

## Contract
Existing FamilyGroup/FamilyMember remain canonical. No schema migration.
Relationships add daughter/son while preserving child. Existing registered users
join through authenticated invitation acceptance, not arbitrary user ID attachment.
Managed profiles may only be linked/read/edited by their existing managing user.
Legacy registered editable links are denied: the former direct-ID endpoint could
create them without consent. Registered readonly memberships originate authenticated
invitation acceptance in existing application write paths. This is an application
provenance invariant, not proof about arbitrary manual database edits. Reaccepting
an invitation converts a legacy registered link to readonly sharing. Dashboard
returns all caller memberships for individually revocable sharing even when the
caller owns a separate household. Detailed record responses use Cache-Control
no-store; clients do not persist shared records.

GET /family/members/{user_id}/health returns member identity, latest examinations
with items and display values, and illness episodes with progress. All queries
scope to the validated subject. Only self or the group's owner with target
can_view can read. An ordinary sibling cannot read this endpoint. Inactive users,
revoked membership/sharing, and proxy sessions cannot expand authorization.
Family listing/dashboard respect the same health-sharing boundary. API keys retain
the existing family-route restriction. Browsing does not replace the active JWT.

PATCH /family/members/{member_id}/relationship changes owner-relative relationship
and nickname only, without changing permissions. Invitation acceptance explains
read sharing. Leaving/removal immediately revokes reads; read-only membership does
not permit proxy editing. Existing managed-member editing remains available only
to the managing owner.

## Acceptance and verification
- Authenticated acceptance retains existing report ownership and nickname.
- Parent reads target reports/illness and no other user's records.
- Unrelated users/siblings and stale/revoked grants fail closed.
- Arbitrary existing-user association cannot grant health access.
- Mobile and Web identify the viewed member and remains in the parent's account.
- Both clients report loading, empty, denied and retry states distinctly.
- Web replaces the invitation placeholder with authenticated create/accept flows.
- Existing managed proxy sessions retain an accessible switch-back control.
- Backend tests on PostgreSQL; focused Mobile/Web behavior/service tests and TypeScript.
- Independent safety review; generated map/nav checks and git diff --check.

## Rollout
Backend and Web precede Mobile OTA; neither release nor live account linkage is claimed
from local tests. Preserve child account and original medical records. Revert UI
and new read endpoints to roll back; do not delete any health records.

## Changelog
- 2026-09-29: accepted narrowly scoped family read flow and consent boundary.
