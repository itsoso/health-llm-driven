# Recovery starter self-report scope mismatch

| Field | Value |
| --- | --- |
| status | shipping |
| current_stage | S6 release validation |
| Primary controller | health-harness-orchestrator (incident) |
| Overlay | safety-gate |
| Source baseline | 93725987775cbe6c9e11cb24f48779049acc319f |
| Local run | docs/_generated/harness-runs/17cefdc846ca.jsonl |

## G1/G2 Scope

裁决: PASS

Repair the existing recovery advice starter without granting personal reads.
The producer accepted free-form illness labels, but the consumer's complete-input
proof rejected an otherwise bounded symptom with a self-report qualifier. This
bypassed the existing current-input advice path; an unnecessary model-proposed
read could then terminate the answer with a permission notice. The earlier
recovery-scope fix did not cover this producer/consumer mismatch.

Recognize the exact self-report annotation and the symptom-like suffix only
around a known medical term. Preserve the original wording and uncertainty in
the question. Do not strip unknown annotations or added operations from user
input. The producer now validates the complete proposed starter against the
consumer's grammar; unsupported labels use the existing general discomfort
question. User edits are always revalidated. No changes to data access, tenant
isolation, personal-context suppression, medical guards, APIs or database schema.

## G3 Evidence

All fixtures are synthetic; no user health text or identifiers are retained.

- Before implementation: 14 scope/producer failures, 15 passing cases; two real
  Pi transport regressions also failed on the self-report variant.
- Focused verification with coverage: 269 passed. This is targeted coverage,
  not whole-repository coverage acceptance.
- Project CI shard integration: 3815 passed, exit 0, first attempt. Includes
  actual-generator-to-real-Pi-to-persisted-answer cases and adjacent gateway,
  retry and outcome checks. Provider output is scripted, not a live model run.
- System Map and doc drift checks passed. The path-sensitive live-change gate
  passed with live_llm_required=false; no live evidence or waiver was claimed.
- Offline synthesis gates passed: invariants, core, trajectories and goldens.

## G4 Safety review

裁决: GO

Independent fixed-commit review of ad2645dd095ebd40b8375569643307eb0aa1c51d
found no blocking issue. It verified
closed matching for cancellation, extra reads/writes, third-party text and unknown
annotations; direct personal tool proposals remained blocked in enforce and
shadow modes with no dispatch. The reviewer independently checked the final
six-file scope, generator-to-persisted-answer cases and both test logs. This
follow-up changes delivery evidence only; the reviewed runtime is unchanged.

## Delivery boundary

The standing authorization in docs/governance/deploy.md includes commit, push and
backend deployment after gates. No Mobile files changed, so OTA is not applicable.
Exact candidate CI, trusted release readiness and production validation remain
required. Local scripted provider tests are not production or live-model proof.
