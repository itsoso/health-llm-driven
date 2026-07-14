# KBase Consumer Feedback Outbox Design

**Status:** Approved by continuation of the feedback-driven reverification plan.

## Goal

Automatically report real Health consumption outcomes to the immutable Dedao
Knowledge Release that supplied the claim, without adding network latency or a
new failure mode to health answers and review operations.

## Architecture

Use `KBAudit` as a durable outbox. Existing answer paths continue to write
`kb_citation_usage`. Dedao draft adjudication audits gain release provenance.
A scheduled Celery flusher reads relevant audits after a persisted audit-ID
cursor, groups claim IDs by release, and posts idempotent feedback through the
existing `DedaoKBaseReleaseClient`.

Imported claims retain both `release_id` and the producer's original
`release_claim_id`. Feedback event IDs are derived from the Health audit ID and
release ID, so retries are safe. The cursor advances only after all posts in a
batch succeed.

## Signal Policy

- A claim visibly used in a final answer reports `used/used_for_answer`.
- An explicit administrator `reject` or `background_only` decision reports
  `rejected`; `background_only` uses `out_of_scope`.
- `needs_evidence` is not rejection and produces no feedback.
- Model-only conflict or stale suggestions do not produce feedback. Those
  outcomes require a later deterministic or human-confirmed signal.

## Safety And Failure Handling

The outbox carries release IDs, producer claim IDs, outcome enums, and audit
IDs only. It never sends queries, answers, notes, user IDs, health records, or
reviewer IDs. Network errors fail the Celery task and preserve the previous
cursor. Already accepted posts replay with the same idempotency key.

The flusher is skipped when the release URL is not configured. Synchronizing a
release never emits `used`; only actual citation usage or explicit review
decisions do.

## Verification

Tests cover provenance preservation, usage grouping, review rejection,
no-signal cursor advancement, idempotent retry, and failure cursor retention.
Focused tests run before backend test and release gates. Deployment validation
uses a bounded synthetic audit tied to the existing real release and verifies
the producer assessment count without transmitting personal content.
