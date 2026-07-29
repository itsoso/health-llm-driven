# Mobile Health Evidence Owner Release Design

## Decision

Keep the low-back authority pack and `symptoms.cauda_equina_warning`.
Release the claims only to the controlled health-evidence runtime on the basis of:

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

### Keep the pack completely unavailable

This preserves authoring artifacts but prevents the reviewed authority pack from
participating in the health-evidence runtime. Rejected because the product owner
accepts the official-source review basis for this release.

### Release through every System KB surface

This would make the claims available to generic search and claim-detail APIs.
Rejected after review found that the legacy knowledge tool can send raw
`summary/body` to the model when the health-evidence feature flag is off,
bypassing the authority artifact check, verifier, and delivery sanitizer.

### Release only through the controlled health-evidence runtime

Selected. This makes the real approval basis machine-readable, preserves the
reviewed-only and deterministic safety choke points, avoids a legacy serving
bypass, and does not fabricate a clinical credential.

## Architecture

`review_manifest.json` is the release record for the authority pack. It records
the exact claim IDs, official-source-only policy, automated boundary review,
product-owner approval, and `health_evidence_runtime_only` serving scope.

`clinical_claim_release.py` keeps the complete pack in the generic serving hold
and adds an exact allowlist for the five claim IDs in the controlled
health-evidence runtime. Entity and eval documents remain authoring/evaluation
artifacts and are never runtime evidence.

The runtime allowlist and the manifest claim list must match exactly in tests.
The manifest is an auditable release record, not a runtime authorization source.
Existing claim metadata is not rewritten for owner approval because the authority
artifact hash already binds it; changing metadata would create a new clinical
artifact rather than approve the reviewed one.

The runtime uses a dedicated internal retrieval function. It may retrieve only
reviewed claims in the runtime allowlist and is not exposed through a public API
or the legacy knowledge tool. Every result must still pass authority applicability
and artifact-integrity validation before the model or verifier can use it.

Delivery and replay re-check the current runtime release permission for every
evidence reference. This check applies to persisted health-evidence metadata even
when new synthesis is feature-flagged off. Removing a claim from the runtime
allowlist therefore revokes both future generation and history/durable replay;
old content is replaced by the deterministic safe fallback.

Read-time query classification is a risk floor, not an exact reconstruction of
the generation turn. A sealed manifest may carry a higher risk promoted from the
frozen Twin/SafetyGuardian packet; a manifest below the risk explicitly stated in
the paired query is rejected. This preserves valid personalized escalation while
preventing a medium envelope from replaying against an emergency query.

The same projection applies to every conversation read surface: Mobile history,
Mac/Desktop trace, cloud-channel replay, GenUI, model conversation history,
history compaction, and public shares. Pre-generated starter answers may not cache
health-evidence text without the complete verification envelope; the initial
release excludes health-evidence answers from that cache.

Selected assistant sharing is also server-owned. Mobile/Web submit only the
authenticated conversation ID and durable message IDs. The server resolves the
paired user query and persisted proof, keeps any unselected support query private,
uses a neutral server-owned title for new and legacy selection shares, and
revalidates on every public read. `/shared/create-text` remains only for genuinely
user-authored arbitrary text; it is not a route for system health answers.

Golden eval is a release gate, not a privileged bypass. Runtime-scoped eval
selection is bound to the immutable eval document ID, and a required claim counts
as found only when the stored artifact matches the current authority policy.

The normal serving path remains:

`HealthTwin query context → intent/risk classification → reviewed System KB
search → authority router → strong model as constrained selector → deterministic
verifier → delivery sanitizer → Mobile/Mac`

Raw Dedao text and paid-course content remain ineligible as clinical evidence.
Only transformed claims backed by T1 official sources may enter the authority
router.

The pre-release source audit found no Dedao contamination and required two
claim-quality corrections. The implementation now says that any listed
neurologic warning is sufficient for escalation rather than implying that all
warnings must coexist. Serious-cause examples are bound to exact official
locators; ACR uses its stable official narrative URL and WHO records an exact
guideline locator. The resulting artifact digests are updated atomically with the
authority policy and tests.

## Safety Boundaries

- No diagnosis, prescription, or dosage generation is introduced.
- Emergency responses remain deterministic and cannot be softened by the model.
- Self-management guidance is released only after red-flag screening.
- Population and use-case mismatches fail closed.
- The runtime feature flag remains a staged rollout control, not a substitute
  for evidence verification.
- Owner approval is labeled `product_owner`, never `clinician`.
- Generic search, claim detail, and legacy knowledge tools cannot serve this pack.
- Removing a claim from the runtime allowlist immediately disables it without
  deleting data, including previously persisted answers.
- A canonical verified envelope binds text, exact evidence references, artifacts,
  sources, risk, and the rendered health card. Read surfaces rebuild the card and
  sources from this envelope instead of trusting stored display metadata.

## Verification

The release change must prove:

1. The manifest truthfully records owner ratification and official-source scope.
2. The manifest claim list exactly matches the runtime allowlist.
3. Every low-back claim has a T1 official source and contains no raw Dedao text.
   Emergency wording uses an explicit “any one” boundary, and each serious-cause
   example has an exact official locator.
4. Generic System KB search and claim detail still exclude the pack.
5. Runtime-scoped retrieval returns only the five released claim documents.
6. Authority routing still rejects stale, tampered, wrong-population, wrong-use-case,
   unreviewed, and non-T1 evidence.
7. Feature-flag OFF and legacy tool paths cannot leak claim `summary/body`.
8. Re-holding a claim sanitizes history and durable replay, including while new
   synthesis is feature-flagged off.
9. A Twin-promoted high/emergency sealed answer survives paired read projection,
   while a manifest below the source-query risk is rejected.
10. Revoked content cannot enter Desktop trace, public shares, pregen, model
   history, or compaction.
11. Mobile/Web selected assistant shares accept only durable server message IDs,
    preserve the visible selection, hide support context and sensitive source
    titles for both new and legacy shares, and revoke safely.
12. Golden eval rejects spoofed eval identity and same-ID tampered claims.
13. Emergency, negation, temporal contrast, verifier, delivery, continuation,
    Mobile rendering, and replay tests remain green.
14. Documentation and generated system-map drift checks pass.

Local G3 has passed and the exact release-candidate HEAD received a fresh G4 GO.
Deployment remains conditional on clean-main integration and green integrated CI;
G5/G6 must still pass before the feature is described as shipped.
