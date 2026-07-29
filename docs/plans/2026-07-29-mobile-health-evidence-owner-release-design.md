# Mobile Health Evidence Owner Release Design

## Decision

Keep the low-back authority pack and `symptoms.cauda_equina_warning`.
Release them on the basis of:

1. T1 official-source provenance for every user-facing claim.
2. Reviewed-only retrieval with exact population, risk, and use-case matching.
3. Deterministic answer verification and delivery-time fail-closed sanitation.
4. Adversarial safety tests, including negation and emergency escalation.
5. Explicit product-owner approval recorded as product governance, not as an
   independent clinical review.

The product owner approved this release basis on 2026-07-29. The repository must
not claim that an independent clinician signed the pack.

## Alternatives Considered

### Remove the complete low-back vertical slice

This would remove the current G4 concern but also remove the golden health-evidence
slice that exercises the new architecture. Rejected by the product owner.

### Keep the pack behind a permanent serving hold

This preserves authoring artifacts but prevents the reviewed authority pack from
participating in the runtime. Rejected because the product owner accepts the
official-source review basis for this release.

### Release with an explicit owner-ratified provenance contract

Selected. This makes the real approval basis machine-readable, preserves the
reviewed-only and deterministic safety choke points, and avoids fabricating a
clinical credential.

## Architecture

`review_manifest.json` is the release record for the authority pack. It records
the exact claim IDs, official-source-only policy, automated boundary review, and
product-owner approval. `clinical_claim_release.py` remains the emergency global
kill-switch, but the low-back document IDs are removed from the hold set.

The normal serving path remains:

`HealthTwin query context → intent/risk classification → reviewed System KB
search → authority router → strong model as constrained selector → deterministic
verifier → delivery sanitizer → Mobile/Mac`

Raw Dedao text and paid-course content remain ineligible as clinical evidence.
Only transformed claims backed by T1 official sources may enter the authority
router.

## Safety Boundaries

- No diagnosis, prescription, or dosage generation is introduced.
- Emergency responses remain deterministic and cannot be softened by the model.
- Self-management guidance is released only after red-flag screening.
- Population and use-case mismatches fail closed.
- The runtime feature flag remains a staged rollout control, not a substitute
  for evidence verification.
- Owner approval is labeled `product_owner`, never `clinician`.
- The static global hold can be re-applied immediately without deleting data.

## Verification

The release change must prove:

1. The manifest truthfully records owner ratification and official-source scope.
2. Every low-back claim has a T1 official source and contains no raw Dedao text.
3. Normal System KB search and claim detail can serve the released documents.
4. Authority routing still rejects stale, wrong-population, wrong-use-case,
   unreviewed, and non-T1 evidence.
5. Emergency, negation, verifier, delivery, continuation, Mobile rendering, and
   replay tests remain green.
6. Documentation and generated system-map drift checks pass.

Deployment remains conditional on a fresh G3 and G4 decision after these checks.
