# Simulator acceptance with explicit release-owner risk acceptance

Effective 2026-09-10, the release owner has authorized a simulator-first submission
path for this project. This is an internal risk decision, not an Apple policy
waiver or a claim that simulator testing proves physical-device correctness.
Apple's [guideline 2.1](https://developer.apple.com/app-store/review/guidelines/#app-completeness)
still asks developers to test on-device before submission; the owner accepts the
residual risk of the current candidate lacking complete physical acceptance.

## Alternative final-submit evidence

The original `--real-device-evidence` path remains available and unchanged.
For the authorized alternative use **both** `--simulator-evidence <external.json>`
and `--accept-simulator-risk`. Do not provide physical evidence at the same time.
The final gate's other checks (live reviewer, privacy publication, regulatory
declaration, age rating, OTA freeze, final materials and Store credentials) remain
mandatory. Known failures cannot be waived by this path.

The external evidence JSON contains:

- `candidate`: exact `build_id`, `app_version`, `eas_build_id`, `git_commit_hash`,
  and `build_profile: production`, independently checked against the actual Store artifact;
  `dtxcode >= 2600` and `dtplatform_version` major `>= 26` extracted from that IPA.
- `simulator`: matching `source_sha`, `configuration: Release`, its **actual**
  `build_id`, `device`, and `ios_version`; never relabel the simulator as a Store IPA.
- `tested_at` with timezone, and `tester`.
- `checks`: every key from `REAL_DEVICE_CHECKS` in `check_app_store_release_pack.py`.
  Each is an object with either `status: passed` and a nonempty `evidence` reference,
  or `status: unverified` and a nonempty `reason`. Any failed/unknown status blocks.
  Login, Today context and privacy navigation must have passed in the simulator.
- `risk_acceptance`: `accepted: true`, `accepted_by`, and a `reference` to the
  explicit user authorization, bound to the candidate in this same record.
- `accepted_unverified_checks`: the exact list of unverified check keys, no omissions
  or duplicates. A simulator-only release remains identified as such after submission.

Evidence references must point to actual observed results; the JSON validator
checks completeness and binding, not the truth of arbitrary supplied text.
Do not reclassify an observed failure as unverified to obtain a pass. Fix it and
rerun its check, retaining the original failure. Record hardware-only items and
otherwise unexecuted items separately in their reasons; neither is a success.
The standing simulator preference does not invent acceptance for new failures or
new capabilities outside the recorded risk scope.

## Screenshot provenance

Simulator screenshots may use a different native build number. In the simulator
path the manifest must retain actual `build_id` and specify `capture_environment:
simulator`, `configuration: Release`, the exact `source_sha`, and the Store target
as `candidate_store_build_id`. Privacy, dimensions and visual review still apply.
The explicit source-bound route replaces only native build-number equality, not
candidate identity or screenshot quality. Screenshots are not runtime test results.

After evidence and all other final materials are genuinely verified, mark the
submission pack/Review Notes final, run the full final gate, and submit only if it
passes. Record the policy revision separately from the frozen app source revision;
policy-only changes do not require rebuilding the candidate app or backend.
