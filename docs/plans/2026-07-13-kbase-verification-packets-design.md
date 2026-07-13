# KBase Verification Packets Design

## Problem

Claim-level adjudication prevents release-wide approval, but reviewers still
have to inspect every claim without a consistent machine-generated evidence
brief. The abandoned evidence-pull branch predates immutable KBase Releases and
the persistent fingerprint-bound review workspace, so merging it would create a
second ingestion path and weaken the current gate.

## Decision

Generate a `VerificationPacket` inside the existing Health review workspace.
The packet is advice to the reviewer, not an adjudication. It combines
deterministic checks with an optional structured model assessment and is bound
to the exact workspace fingerprint and claim content hash. A rebuild, sync, or
claim mutation makes the packet stale.

## Packet Contract

Each packet contains:

- claim identity, workspace fingerprint, and claim content hash;
- source completeness, external-evidence, freshness, duplicate, and
  contradiction checks;
- a proposed decision: `approve`, `needs_evidence`, `reject`, or
  `background_only`;
- confidence, concise rationale, missing-evidence requirements, and cited
  source identifiers;
- generator identity, prompt/contract version, and generation timestamp;
- status: `ready`, `blocked`, or `stale`.

The model receives only the selected claim and bounded source metadata. It must
return strict JSON. Invalid, unsupported, or uncited output becomes `blocked`;
there is no free-text fallback that can influence adjudication.

## Data Flow

1. An admin requests a packet for one unresolved claim.
2. The service snapshots the claim under the shared workspace lock and runs
   deterministic checks.
3. The optional model adapter receives the bounded snapshot and returns a
   structured proposal.
4. The service rechecks the workspace fingerprint before atomically appending
   the packet to `verification_packets.jsonl`.
5. The review UI shows checks and proposal beside the claim.
6. “Apply suggestion” sends the existing adjudication command with the current
   fingerprint. The reviewer remains the adjudication actor.

## Safety Boundaries

- Packet generation never mutates claims, finalizes a workspace, or publishes.
- Medical claims are never auto-approved or auto-published.
- Deterministic blockers override model recommendations.
- A packet cannot be applied when stale, blocked, uncited, or below the minimum
  confidence threshold.
- Audit rows contain identifiers and decision metadata, never article bodies or
  model prompts.
- Existing serving, finalization, and publication gates remain unchanged.

## Admin Experience

The current two-pane Release Review panel adds one compact verification section:
generate or refresh packet, inspect checks and citations, and apply an eligible
suggestion. The primary adjudication buttons remain available. Stale packets
show an explicit refresh action; blocked packets explain what evidence is
missing. No publication control is added.

## Verification

Backend tests cover deterministic proposals, strict model parsing, fingerprint
staleness, content-hash mismatch, atomic persistence, audit redaction, and the
absence of claim mutations. API tests cover authentication, validation, 409
conflicts, and applying only eligible packets through the existing adjudication
path. Frontend tests cover generation, stale/blocked states, citations, apply
payloads, and the absence of automatic approval or publish commands.
