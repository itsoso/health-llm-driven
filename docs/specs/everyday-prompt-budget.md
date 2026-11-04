# Everyday prompt budget

> Status: implementation
> Updated: 2026-11-04
> Dossier: ../dossiers/2026-11-02-explicit-model-latency.md

## Decision and admission

Reduce irrelevant prompt overhead for positively identified ordinary conversation, while retaining the selected model, original relevant history and final answer verification.

```yaml
RequirementAdmission:
  request: implement approved fortnight token optimization plan and deploy
  classification: existing Agent performance improvement
  first_user_fit: ordinary mobile conversation
  core_loop_step: understand and respond
  first_class_objects: [ExecutionEvent, SafetyGuardian]
  target_surface: Agent reply and processing metadata
  source_of_truth: authenticated current request and owned original messages
  safety_level: preserve existing medical and write gates
  prescription_or_causal_verdict: none
  autonomy_tier: existing user-authorized reply
  evidence_provenance: provider usage plus content-free payload measurements
  claim_hedging: character estimates are not provider token counts
  verification_window: paired synthetic requests before release; production follow-up separately
  success_metric: lower actual eligible input without extra model calls or lost corrections
  added_user_burden: none
  burden_justification: not applicable
  non_goals: [broad intent shortcut, history truncation, medical model downgrade]
  smallest_end_to_end_slice: closed everyday request to one selected-model reply and saved metadata
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## Evidence and target

The read-only fortnight snapshot (2026-10-21 to 2026-11-04) contains 241 Agent turns. The broad ordinary/follow-up candidate group is not an adjudicated pure-chat set: its 33 API-complete turns have median 16,780 input tokens. Available journal block estimates attribute about 57% to tool definitions and 33% to system instructions; these are character-derived estimates, not provider token decomposition. History is a smaller contributor, so indiscriminate truncation is unjustified.

The eligible-turn target is 1,500–3,000 input tokens or less, not a floor and not an achieved production SLO. Three-second meaningful output remains a separate goal. Existing cache and history flags are already enabled.

## Contract

Full-message positive grammar admits greetings, courtesies, bounded pickup context and topic-free short fiction. Arbitrary short messages, health questions, writes, follow-ups, attachments, entry actions, pending tasks, recovery and unknown history remain on the existing path. Explicit model selection alone may accompany an eligible message; it supplies no health authority.

Owned prior messages must be complete, bounded benign pairs, including verified source-bound gate corrections. Inspect the complete small conversation, not just a benign tail. Longer conversations retain the ordinary path. The normal history builder keeps original source provenance and corrections. No history is cleared for this lane. Health tools and unrelated health/Twin/knowledge preloads are omitted only after admission. Existing final verification and saved/streamed answer agreement remain mandatory.

Provider wrappers record content-free block lengths and counts for each actual invocation, including failures. API-reported usage and cached tokens remain authoritative. Estimates must not replace billing values. Capture truncation is observable. No raw health text, image URL, tool argument or identifier is added to telemetry.

## Verification and rollout

RED-first helper and provider-payload tests; negative medical/pending/owner/attachment cases; selected-model one-call and history-preservation tests; real Pi and PostgreSQL checks where applicable; independent safety review. Compare identical requests and preserve failed measurement attempts. Roll back behavior with the existing domain optimization flag if quality regresses; do not create backup copies.

Release requires exact main CI, fresh integration/live gates and a clean candidate. Backend and OTA are separate receipts. OTA additionally requires compatibility with the real native baseline; the current parallel native release cannot be bypassed. Device presentation and production P95 are not inferred from local payload tests.
