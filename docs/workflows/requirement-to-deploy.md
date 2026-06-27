# Requirement To Deploy Workflow

> Status: v1 baseline
> Updated: 2026-06-27
> Contract: `docs/specs/product-pipeline-contract.md`
> Map: `docs/system-map.json`

This workflow is the system-transparency view of the existing product pipeline.
It does not create a second process. It binds each pipeline stage to the system
map so a coding agent can find the product object, surface, implementation
files, tests, deploy path, and verification record.

## 1. Intake

Capture the user request verbatim in a Dossier when the work is product-level or
end-to-end. For small mechanical fixes, the Dossier can be skipped, but the
system map still governs whether the affected capability and surface are known.

Minimum output:

```yaml
request:
classification:
affected_capabilities:
target_surfaces:
source_of_truth:
```

## 2. Admission

Use `docs/specs/reva-product-governance-spec.md` to fill
`RequirementAdmission`. The request must map to at least one first-class product
object or be explicitly classified as infrastructure, docs, cleanup, or test
work.

Gate result:

| Result | Action |
|---|---|
| PASS | Continue to PRD/Plan or implementation. |
| REFRAME | Rewrite the requirement and return to intake. |
| REJECT | Record the reason; do not implement. |

## 3. System Map Lookup

Before editing code, locate or add the capability in `docs/system-map.json`.

For existing capability work, the agent must identify:

- capability id;
- owning surfaces;
- source-of-truth PRD/spec/plan;
- implementation files;
- test files;
- deploy path;
- safety level.

For a new capability, add it with `status: planned` or `status: partial` before
implementation. If the agent cannot name these fields, it should stop and write
or update a Feature Spec first.

## 4. Implementation

Implement against the source-of-truth surface and backend contract named in the
map. Do not create parallel daily-loop logic on another surface unless the spec
states the cross-surface contract and stale-surface disposition.

Implementation order:

1. Tests first for new behavior or check scripts.
2. Backend source-of-truth changes.
3. Client or surface changes.
4. Type generation when backend schema changes.
5. System map and product map update.

## 5. Verification

Run the narrow tests listed under the affected capability first. Then run the
structural gates:

```bash
python scripts/check_system_map.py
python scripts/validate.py
```

For deployable changes, follow the gates in
`docs/specs/product-pipeline-contract.md`:

- G3 testing;
- G4 safety review for medication, genotype, lab, CGM, symptom, red-flag,
  authentication, CORS, or write paths;
- G5 deploy health;
- G6 production or device verification.

Never pipe tests to `tail` without preserving the exit code.

## 6. Deployment Route

Use the deploy route named in `docs/system-map.json`.

| Route | Use when |
|---|---|
| `backend_ci` | Backend API, service, model, safety, task, or data contract changes. |
| `mobile_ota` | Mobile JS/TS/UI changes without native configuration changes. |
| `mobile_ota_or_eas` | HealthKit/native-adjacent work; confirm whether native build is required. |
| `watch_eas_or_xcode` | Watch target, WatchConnectivity, native bridge, or watchOS app changes. |
| `safety_review_required` | Deterministic safety or user-facing health advice changes. |
| `git_ci` | Docs, scripts, map, or skill changes that do not deploy runtime services. |

## 7. Closeout

Before finishing:

1. `docs/system-map.json` references all new source-of-truth files.
2. `docs/product-map.md` reflects meaningful capability or surface changes.
3. Dossier records gate results for end-to-end work.
4. Tests and structural gates are green, or failures are explicitly reported.
5. The final answer names the changed capability and verification evidence.
