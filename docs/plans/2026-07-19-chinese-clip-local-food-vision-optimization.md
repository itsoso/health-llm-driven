# Chinese-CLIP Local Food Vision Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve official-preprocessing fidelity, activate local non-food rejection with a versioned negative label bank, and make FP16/int8 quality evidence impossible to enter as a free scalar.

**Architecture:** Keep the spike isolated from the production diet surface. Match the pinned Chinese-CLIP square bicubic transform in pure Swift, build a v2 identity-only label bank with separate food/non-food prompts, and separate raw physical-device reports from a deterministic variant-comparison artifact derived from complete frozen test runs.

**Tech Stack:** Swift 6, XCTest, Core ML, Vision, Python 3.12, fixed Chinese-CLIP/PyTorch environment, JSON Schema, Ruby `xcodeproj`.

---

## Delivery rules

- Work only in the existing `codex/local-first-private-g2` worktree.
- Follow TDD for every behavior change: add a failing focused test, observe RED, implement minimally, then run the focused and full related suites.
- Never commit checkpoints, `.mlpackage`, `.mlmodelc`, label-bank binaries, authorized images or raw device reports.
- Do not add production Expo/React Native integration or change the Chinese-CLIP G2 BLOCK verdict.
- Stage exact files only; never use `git add -A`.

### Task 1: Match the pinned official bicubic preprocessor

**Files:**

- Modify: `mobile/modules/local-health-kernel/Tests/LocalChineseClipVisionEngineTests.swift`
- Modify: `mobile/modules/local-health-kernel/ios/LocalFoodVisionPreprocessor.swift`
- Modify: `mobile/modules/local-health-kernel/ios/LocalChineseClipVisionEngine.swift`

**Step 1: Write the failing golden test**

Add a 3×2 RGB fixture and assert selected tensor pixels against values produced by the pinned official `image_transform(224)`. Preserve the existing EXIF and region-selection assertions.

**Step 2: Run the focused test and confirm RED**

Run:

```bash
cd mobile/modules/local-health-kernel
swift test --filter LocalChineseClipVisionEngineTests/testPreprocessorMatchesPinnedChineseClipBicubicGolden
```

Expected: FAIL because nearest-neighbor values differ from the bicubic golden.

**Step 3: Implement deterministic bicubic sampling**

Use pixel-center coordinates, a fixed cubic kernel, clamped edge indices, clamped RGB output and the existing official mean/std. Precompute X/Y tap indices and weights per prepared region.

**Step 4: Remove per-element Core ML input boxing**

For the newly allocated contiguous Float32 `MLMultiArray`, copy the validated Swift tensor bytes in one operation. Treat an unexpected data type/count as `invalidPreprocessorOutput`.

**Step 5: Verify and commit**

Run:

```bash
swift test --filter LocalChineseClipVisionEngineTests
swift test
git diff --check
```

Expected: all tests pass.

Commit exact Task 1 files with `perf(local-vision): match Chinese-CLIP bicubic input`.

### Task 2: Build a v2 label bank with non-food negatives

**Files:**

- Create: `mobile/modules/local-health-kernel/ModelSources/chinese-clip-food-labels-v2.json`
- Create: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-label-bank-v2.json`
- Create: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-calibration-v2.json`
- Delete: `mobile/modules/local-health-kernel/ModelSources/chinese-clip-food-labels-v1.json`
- Delete: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-label-bank-v1.json`
- Delete: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-calibration-v1.json`
- Modify: `mobile/modules/local-health-kernel/scripts/build_chinese_clip_label_bank.py`
- Modify: `mobile/modules/local-health-kernel/scripts/tests/test_build_chinese_clip_label_bank.py`
- Modify: `mobile/modules/local-health-kernel/Tests/LocalChineseClipVisionEngineTests.swift`
- Modify: `mobile/modules/local-health-kernel/Tests/LocalFoodVisionBenchmarkTests.swift`
- Modify: `mobile/modules/local-health-kernel/DeviceHost/LocalFoodVisionBenchmarkHostApp.swift`
- Modify: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-coreml-variants.json`
- Modify: `docs/evals/local-diet/README.md`

**Step 1: Write failing v2 source tests**

Require separate fixed prompt sets for food and non-food labels, canonical-ID/category agreement, at least one committed negative label, no negative label in food outputs, and flexible v2 source/output paths derived from the version.

**Step 2: Run and confirm RED**

Run:

```bash
python3 scripts/tests/test_build_chinese_clip_label_bank.py
```

Expected: FAIL because v1 only supports one prompt list and contains no negative label.

**Step 3: Implement and generate v2**

Add owner-authored negative identities for common non-food photo classes. Generate with the pinned text tower into `.build/models/chinese-clip-rn50/chinese-clip-label-bank-v2.bin`, run a second generation to a temporary ignored location, and compare SHA-256 bytes.

**Step 4: Update consumers and measured assets**

Update label/calibration versions, manifest hashes, actual label-bank bytes and total installed bytes. Keep calibration status `blocked_pending_authorized_dataset` with null thresholds and variant evidence.

**Step 5: Verify and commit**

Run:

```bash
python3 scripts/tests/test_build_chinese_clip_label_bank.py
swift test --filter LocalFoodCandidateRankerTests
swift test --filter LocalChineseClipVisionEngineTests
swift test
git diff --check
```

Expected: deterministic builder and all Swift tests pass; generated binary remains ignored; int8 installed assets remain below 50 MiB.

Commit exact Task 2 files with `feat(local-vision): add non-food label bank v2`.

### Task 3: Derive variant evidence from complete raw reports

**Files:**

- Create: `docs/evals/local-diet/chinese-clip-variant-evidence-contract.json`
- Modify: `docs/evals/local-diet/on-device-eval-contract.json`
- Modify: `scripts/test_local_diet_eval_contract.py`
- Modify: `mobile/modules/local-health-kernel/ios/LocalFoodVisionBenchmark.swift`
- Modify: `mobile/modules/local-health-kernel/Tests/LocalFoodVisionBenchmarkTests.swift`
- Modify: `mobile/modules/local-health-kernel/scripts/score_local_food_vision_run.py`
- Modify: `mobile/modules/local-health-kernel/scripts/tests/test_score_local_food_vision_run.py`
- Modify: `mobile/modules/local-health-kernel/scripts/generate_food_vision_device_host.rb`
- Modify: `mobile/modules/local-health-kernel/scripts/tests/generate_food_vision_device_host_test.rb`
- Modify: `mobile/modules/local-health-kernel/DeviceHost/LocalFoodVisionBenchmarkHostApp.swift`
- Modify: `docs/evals/local-diet/README.md`

**Step 1: Write failing evidence-integrity tests**

Assert that raw FP16 and int8 reports reject a delta field; the host CLI rejects `--fp16-delta`; fixture manifests below 300 cases or without all required strata/splits fail; and comparison rejects incomplete/mismatched report pairs.

**Step 2: Run and confirm RED**

Run:

```bash
python3 scripts/test_local_diet_eval_contract.py
python3 scripts/tests/test_score_local_food_vision_run.py
ruby scripts/tests/generate_food_vision_device_host_test.rb
swift test --filter LocalFoodVisionBenchmarkTests
```

Expected: failures expose the current free scalar and weak host manifest validation.

**Step 3: Remove the raw-report delta**

Delete `fp16ToCompressedIdentityPrecisionDelta` from the Swift benchmark input/summary and JSON Schema. Raw reports remain `gateVerdict: blocked` evidence inputs.

**Step 4: Harden the fixture manifest**

Require at least 300 authorized non-private cases, unique opaque IDs, all frozen strata, both splits, valid non-food/mixed-plate invariants and files confined to the fixture directory. Generate the host only for the `test` split.

**Step 5: Add deterministic comparison**

Add `compare` to `score_local_food_vision_run.py`. It must score both complete test reports against the same frozen dataset, verify FP16/int8 profiles and provenance, read installed sizes from the versioned variants manifest, calculate the absolute identity-precision delta, apply frozen gates and emit hashes plus a Schema-valid variant evidence document. There is no delta CLI argument.

**Step 6: Verify and commit**

Run all four focused suites above, then the full Swift and relevant Python/Ruby suites. Expected: all pass, and no CLI or report path accepts a hand-entered delta.

Commit exact Task 3 files with `test(local-vision): derive compression evidence from raw runs`.

### Task 4: Final gates and dossier verdict

**Files:**

- Modify: `docs/dossiers/2026-07-18-local-first-private-mode.md`
- Modify: `docs/evals/local-diet/README.md`
- Modify: this plan if implementation evidence differs from the planned commands

**Step 1: Run the complete verification set**

Run model provenance, label-bank, export, scoring, schema, Ruby host, Swift, generic iOS build, doc drift and dossier consistency checks without piping tests through `tail`.

**Step 2: Record evidence and unchanged blocker**

Document exact pass/fail results, official-preprocessing correction, v2 negative-label status and the evidence-integrity change. Keep G2 `BLOCK` because authorized quality data, full variant reports and representative physical-device/privacy evidence are still absent.

**Step 3: Commit and push**

Commit exact documentation files with `docs(local-vision): record optimization gate results`, verify a clean worktree, and push `codex/local-first-private-g2`.
