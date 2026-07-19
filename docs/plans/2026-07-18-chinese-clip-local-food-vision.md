# Chinese-CLIP Local Food Vision Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce a reproducible, license-pinned Chinese-CLIP RN50 image-only Core ML candidate and make an evidence-based PASS/BLOCK decision for fully local iOS food-photo recognition without integrating it into the production App.

**Execution outcome (2026-07-19):** All eight stages were executed. Provenance, deterministic label generation, FP16/int8 conversion parity, the 39,626,225-byte selected asset, Swift local inference/ranking, the evidence contract, the isolated host and fail-closed scoring/calibration machinery pass. Final G2 verdict is **BLOCK**, not PASS: no authorized 300-case dataset is available, held-out FP16/int8 identity precision is unmeasured, all registered physical devices were unavailable, and the low/mid/high plus airplane-mode/privacy matrix is absent. No production diet-screen integration was performed.

**Architecture:** Run the Chinese-CLIP text tower only on the build machine to create a versioned Chinese food-label embedding bank. Run only the RN50 image tower on iOS, combine whole-image and bounded Vision saliency crops, rank normalized embeddings against the local label bank, and return at most three identity candidates behind calibrated unknown/non-food gates. Nutrition and portions remain outside the model and all writes remain manual-confirm.

**Tech Stack:** Python 3.12 isolated build environment, PyTorch, official `cn_clip`, Core ML Tools, JSON Schema, Swift 6, Core ML, Vision, Accelerate, XCTest/Swift Testing, Ruby `xcodeproj`, Xcode physical-device tooling.

---

## Delivery rules

- Execute in the existing clean `codex/local-first-private-g2` worktree; do not work on local `main`.
- Use TDD for scripts, Swift ranking, engine orchestration, report scoring and host generation.
- Download/model artifacts live only in ignored `mobile/modules/local-health-kernel/.build/models/`; never commit checkpoints, `.mlpackage`, `.mlmodelc`, private photos or embeddings derived from private photos.
- Pin immutable upstream revisions and SHA-256 values before conversion. A changed digest is an error, never an automatic lockfile refresh.
- The App artifact contains only the image tower and label vectors. Do not bundle RBT3/tokenizer files.
- Candidate outputs contain food identity/provenance only. Do not add grams, calories, macros, ingredients or nutrition fields.
- Do not add Expo/React Native production integration in this plan. That requires a separate implementation plan after the independent intelligent-enhancement G2 is PASS.
- Missing representative devices, an unverified license, a missing dataset grant or a failed metric produces `BLOCK`/`FAIL`; never substitute simulator data or weaken a threshold.
- Commit only the exact files for each task. Do not use `git add -A`.

## Task 1: Lock model provenance, licenses and artifact boundaries

**Files:**

- Create: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-rn50.json`
- Create: `mobile/modules/local-health-kernel/scripts/verify_chinese_clip_manifest.py`
- Create: `mobile/modules/local-health-kernel/scripts/tests/test_verify_chinese_clip_manifest.py`
- Create: `mobile/modules/local-health-kernel/ThirdPartyNotices/Chinese-CLIP-code-MIT.txt`
- Create: `mobile/modules/local-health-kernel/ThirdPartyNotices/Chinese-CLIP-model-Apache-2.0.txt`
- Modify: `.gitignore`
- Modify: `docs/evals/local-diet/README.md`

### Step 1: Write the failing manifest contract test

The test must reject mutable refs, missing hashes, non-HTTPS sources, unknown licenses and output paths outside `.build/models`. It must also assert `components.shipped == ["image_encoder"]` and `components.buildTimeOnly == ["text_encoder", "tokenizer"]`.

Use a manifest shape like:

```json
{
  "schemaVersion": 1,
  "modelId": "OFA-Sys/chinese-clip-rn50",
  "modelRevision": "<full immutable Hugging Face commit>",
  "checkpoint": {
    "url": "https://huggingface.co/OFA-Sys/chinese-clip-rn50/resolve/<revision>/clip_cn_rn50.pt",
    "sha256": "<64 lowercase hex characters>"
  },
  "sourceCode": {
    "repository": "https://github.com/OFA-Sys/Chinese-CLIP",
    "revision": "<full Git commit>",
    "license": "MIT",
    "licenseSha256": "<64 lowercase hex characters>"
  },
  "modelLicense": {
    "spdx": "Apache-2.0",
    "licenseSha256": "<64 lowercase hex characters>"
  },
  "components": {
    "shipped": ["image_encoder"],
    "buildTimeOnly": ["text_encoder", "tokenizer"]
  },
  "artifactRoot": ".build/models/chinese-clip-rn50"
}
```

### Step 2: Run the test and confirm RED

```bash
cd mobile/modules/local-health-kernel
python3 scripts/tests/test_verify_chinese_clip_manifest.py
```

Expected: FAIL because the verifier and manifest do not exist.

### Step 3: Implement a standard-library verifier before downloading anything

The verifier must validate the schema, full commit/hash formats, URL revision agreement, exact component boundary and output root. Add a `--verify-files` mode that hashes an already-downloaded checkpoint and both notice files, but no network code.

```python
def require_sha256(value: str, field: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ManifestError(f"{field} must be a lowercase SHA-256")

def require_component_boundary(components: dict) -> None:
    if components != {
        "shipped": ["image_encoder"],
        "buildTimeOnly": ["text_encoder", "tokenizer"],
    }:
        raise ManifestError("only the image encoder may ship")
```

### Step 4: Resolve and pin real upstream evidence

Resolve `main` to immutable full revisions and download the model once into `.build/models/chinese-clip-rn50/source/`. Copy the repository's exact MIT text; for the model, preserve a snapshot/hash of the Apache-2.0 declaration plus the canonical Apache-2.0 license text and their source URLs. Calculate all SHA-256 values and populate the manifest. Do not guess or copy shortened web UI hashes.

```bash
mkdir -p .build/models/chinese-clip-rn50/source
shasum -a 256 \
  .build/models/chinese-clip-rn50/source/clip_cn_rn50.pt \
  ThirdPartyNotices/Chinese-CLIP-code-MIT.txt \
  ThirdPartyNotices/Chinese-CLIP-model-Apache-2.0.txt
python3 scripts/verify_chinese_clip_manifest.py \
  --manifest model-manifests/chinese-clip-rn50.json \
  --verify-files
```

Expected: exit 0 and a single non-sensitive summary containing model ID, pinned revisions and matching hashes. No model contents or authorization headers may be logged.

If the model's Apache-2.0 declaration cannot be independently preserved, final license review finds it insufficient, or the code/model terms conflict, record G2 `BLOCK` and stop the plan here.

### Step 5: Verify ignore rules and tests

```bash
git check-ignore .build/models/chinese-clip-rn50/source/clip_cn_rn50.pt
python3 scripts/tests/test_verify_chinese_clip_manifest.py
git status --short
```

Expected: the checkpoint is ignored; all tests pass; no model artifact appears in Git status.

### Step 6: Commit

```bash
git add .gitignore \
  mobile/modules/local-health-kernel/model-manifests/chinese-clip-rn50.json \
  mobile/modules/local-health-kernel/scripts/verify_chinese_clip_manifest.py \
  mobile/modules/local-health-kernel/scripts/tests/test_verify_chinese_clip_manifest.py \
  mobile/modules/local-health-kernel/ThirdPartyNotices/Chinese-CLIP-code-MIT.txt \
  mobile/modules/local-health-kernel/ThirdPartyNotices/Chinese-CLIP-model-Apache-2.0.txt \
  docs/evals/local-diet/README.md
git commit -m "chore(local-vision): pin Chinese-CLIP provenance"
```

## Task 2: Build a deterministic Chinese food label bank

**Files:**

- Create: `mobile/modules/local-health-kernel/ModelSources/chinese-clip-food-labels-v1.json`
- Create: `mobile/modules/local-health-kernel/scripts/build_chinese_clip_label_bank.py`
- Create: `mobile/modules/local-health-kernel/scripts/tests/test_build_chinese_clip_label_bank.py`
- Create: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-label-bank-v1.json`
- Modify: `docs/evals/local-diet/README.md`

### Step 1: Write failing label-source and fake-encoder tests

Cover duplicate canonical IDs, duplicate aliases after Unicode normalization, empty source fields, forbidden nutrition/portion keys, prompt-template drift, non-finite vectors, incorrect dimensions, non-unit output and unstable JSON byte output. Inject a fake text encoder so unit tests do not load the real checkpoint.

The committed source file contains identity metadata only:

```json
{
  "schemaVersion": 1,
  "labelSetVersion": "cn-food-labels-v1",
  "promptTemplateVersion": "cn-food-prompts-v1",
  "promptTemplates": ["{name}", "一张{name}的照片", "一份{name}"],
  "labels": [
    {
      "canonicalFoodId": "food.rice.cooked.white",
      "name": "白米饭",
      "aliases": ["米饭"],
      "category": "staple",
      "source": "owner_authored"
    }
  ]
}
```

The test must recursively reject keys matching `calorie`, `kcal`, `macro`, `protein`, `fat`, `carb`, `gram`, `portion`, `营养`, `热量`, `克` or `份量`.

### Step 2: Run and confirm RED

```bash
cd mobile/modules/local-health-kernel
python3 scripts/tests/test_build_chinese_clip_label_bank.py
```

Expected: FAIL because the builder does not exist.

### Step 3: Implement deterministic source validation and vector serialization

Normalize text with Unicode NFC, preserve stable source order, encode every prompt, L2-normalize each prompt vector, average, normalize again, and serialize floats in a deterministic binary or JSON representation. The output manifest records the source SHA-256, prompt version, model revision, embedding dimension, output SHA-256 and row count derived by the script.

```python
prompt_vectors = [unit(encoder.encode_text(t.format(name=name))) for t in templates]
label_vector = unit(np.mean(prompt_vectors, axis=0))
```

Do not hand-enter the row count into narrative documentation. It belongs only in the generated manifest.

### Step 4: Generate with the real build-time text tower

```bash
python3 scripts/verify_chinese_clip_manifest.py \
  --manifest model-manifests/chinese-clip-rn50.json \
  --verify-files
python3 scripts/build_chinese_clip_label_bank.py \
  --model-manifest model-manifests/chinese-clip-rn50.json \
  --labels ModelSources/chinese-clip-food-labels-v1.json \
  --output .build/models/chinese-clip-rn50/chinese-clip-label-bank-v1.bin \
  --output-manifest model-manifests/chinese-clip-label-bank-v1.json
```

Run the command twice into two temporary outputs and compare SHA-256 values. Expected: byte-identical outputs.

### Step 5: Verify and commit

```bash
python3 scripts/tests/test_build_chinese_clip_label_bank.py
git check-ignore .build/models/chinese-clip-rn50/chinese-clip-label-bank-v1.bin
git diff --check
git add \
  mobile/modules/local-health-kernel/ModelSources/chinese-clip-food-labels-v1.json \
  mobile/modules/local-health-kernel/scripts/build_chinese_clip_label_bank.py \
  mobile/modules/local-health-kernel/scripts/tests/test_build_chinese_clip_label_bank.py \
  mobile/modules/local-health-kernel/model-manifests/chinese-clip-label-bank-v1.json \
  docs/evals/local-diet/README.md
git commit -m "feat(local-vision): build Chinese food label embeddings"
```

## Task 3: Convert only the RN50 image tower to Core ML

**Files:**

- Create: `mobile/modules/local-health-kernel/scripts/requirements-chinese-clip.lock`
- Create: `mobile/modules/local-health-kernel/scripts/export_chinese_clip_coreml.py`
- Create: `mobile/modules/local-health-kernel/scripts/tests/test_export_chinese_clip_coreml.py`
- Create: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-coreml-variants.json`
- Modify: `docs/evals/local-diet/README.md`

### Step 1: Write failing export-contract tests

Use a tiny fake PyTorch image encoder to assert that the exporter:

- accepts an image tensor only;
- exposes one normalized image embedding output;
- contains no token IDs, text inputs, tokenizer or text-encoder weights;
- targets iOS 16 or newer;
- writes model revision, preprocessing and precision metadata;
- rejects an output outside `.build/models/`;
- does not silently fall back from a requested compression mode.

### Step 2: Run and confirm RED

```bash
cd mobile/modules/local-health-kernel
python3 scripts/tests/test_export_chinese_clip_coreml.py
```

Expected: FAIL because the exporter is missing.

### Step 3: Pin a dedicated compatible conversion environment

Create an isolated Python 3.12 environment under `.build/`; pin exact versions and hashes where the package manager supports them. Do not reuse or modify `backend/venv`.

```bash
python3.12 -m venv .build/chinese-clip-venv
.build/chinese-clip-venv/bin/pip install -r scripts/requirements-chinese-clip.lock
```

If Core ML Tools and the pinned PyTorch/cn_clip revision cannot coexist, update the lock through an explicit dependency review and rerun Task 1 provenance verification; do not install unpinned latest packages.

### Step 4: Implement the image-only exporter

Follow the official `pytorch_to_coreml.py` preprocessing and layer behavior, but wrap only `model.encode_image`. Normalize the embedding in-model or declare the exact normalization boundary in metadata and enforce it in Swift. Export:

- `fp16` reference variant;
- one compressed candidate supported by the chosen Core ML Tools version.

Do not add more compression variants until one candidate has been measured.

### Step 5: Run PyTorch/Core ML parity checks

Use committed synthetic/public-domain image fixtures with no health data. For each fixture, compare unit-normalized output vectors and fail on NaN/Inf, wrong dimension or cosine agreement below the predeclared tolerance. Record the measured tolerance in `chinese-clip-coreml-variants.json`; do not choose it after seeing food-quality results.

```bash
.build/chinese-clip-venv/bin/python scripts/export_chinese_clip_coreml.py \
  --model-manifest model-manifests/chinese-clip-rn50.json \
  --variant fp16 \
  --output .build/models/chinese-clip-rn50/coreml/fp16/ChineseClipRN50Image.mlpackage
.build/chinese-clip-venv/bin/python scripts/export_chinese_clip_coreml.py \
  --model-manifest model-manifests/chinese-clip-rn50.json \
  --variant compressed \
  --output .build/models/chinese-clip-rn50/coreml/compressed/ChineseClipRN50Image.mlpackage
.build/chinese-clip-venv/bin/python scripts/tests/test_export_chinese_clip_coreml.py
```

### Step 6: Compile and measure actual assets

```bash
xcrun coremlcompiler compile \
  .build/models/chinese-clip-rn50/coreml/fp16/ChineseClipRN50Image.mlpackage \
  .build/models/chinese-clip-rn50/coreml/fp16-compiled
xcrun coremlcompiler compile \
  .build/models/chinese-clip-rn50/coreml/compressed/ChineseClipRN50Image.mlpackage \
  .build/models/chinese-clip-rn50/coreml/compressed-compiled
du -sk .build/models/chinese-clip-rn50/coreml/*-compiled
```

Populate the variants manifest from measured files, not parameter-count estimates. If the compressed model plus label bank exceeds 50 MB, record `BLOCK`; do not continue to product integration.

### Step 7: Verify and commit

```bash
git check-ignore .build/models/chinese-clip-rn50/coreml/fp16/ChineseClipRN50Image.mlpackage
git diff --check
git add \
  mobile/modules/local-health-kernel/scripts/requirements-chinese-clip.lock \
  mobile/modules/local-health-kernel/scripts/export_chinese_clip_coreml.py \
  mobile/modules/local-health-kernel/scripts/tests/test_export_chinese_clip_coreml.py \
  mobile/modules/local-health-kernel/model-manifests/chinese-clip-coreml-variants.json \
  docs/evals/local-diet/README.md
git commit -m "feat(local-vision): export RN50 image tower to Core ML"
```

## Task 4: Implement and calibrate the pure Swift candidate ranker

**Files:**

- Create: `mobile/modules/local-health-kernel/ios/LocalFoodVisionTypes.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalFoodCandidateRanker.swift`
- Create: `mobile/modules/local-health-kernel/Tests/LocalFoodCandidateRankerTests.swift`
- Modify: `mobile/modules/local-health-kernel/Package.swift`

### Step 1: Write failing ranking tests

Cover unit normalization, cosine ranking, canonical-ID deduplication across aliases and crops, stable tie ordering, Top-3 cap, minimum score, Top-1/Top-2 margin, non-food rejection, NaN/Inf, dimension mismatch and an empty/unknown result. Assert candidate types have no nutrition or portion fields.

```swift
let result = try ranker.rank(
    regionEmbeddings: [wholeImage, salientCrop],
    labelBank: labels,
    policy: .init(minimumScore: 0.31, minimumMargin: 0.04, maximumCandidates: 3)
)
#expect(result.candidates.count <= 3)
#expect(result.decision == .candidate || result.decision == .unknown)
```

The numeric values above are test-fixture values only. Production thresholds must come from Task 7 calibration and live in a versioned calibration artifact.

### Step 2: Run and confirm RED

```bash
cd mobile/modules/local-health-kernel
swift test --filter LocalFoodCandidateRankerTests
```

Expected: compile failure because the ranker types are absent.

### Step 3: Implement the smallest pure ranker

Use Accelerate/vDSP where available, with a deterministic scalar fallback for package tests. Validate vectors before arithmetic. Merge per-region results by canonical ID while preserving evidence (`whole_image`, `salient_region`, `ocr`, `barcode`) and the winning region index. Never softmax over a changing label set and call it calibrated confidence.

### Step 4: Verify all Swift tests

```bash
swift test --filter LocalFoodCandidateRankerTests
swift test
```

Expected: ranker tests and the existing capability/benchmark tests pass with no network or model artifact.

### Step 5: Commit

```bash
git add \
  mobile/modules/local-health-kernel/Package.swift \
  mobile/modules/local-health-kernel/ios/LocalFoodVisionTypes.swift \
  mobile/modules/local-health-kernel/ios/LocalFoodCandidateRanker.swift \
  mobile/modules/local-health-kernel/Tests/LocalFoodCandidateRankerTests.swift
git commit -m "feat(local-vision): rank local food identity candidates"
```

## Task 5: Add the Vision + Core ML orchestration engine behind protocols

**Files:**

- Create: `mobile/modules/local-health-kernel/ios/LocalFoodVisionPreprocessor.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalChineseClipVisionEngine.swift`
- Create: `mobile/modules/local-health-kernel/Tests/LocalChineseClipVisionEngineTests.swift`
- Modify: `mobile/modules/local-health-kernel/Package.swift`

### Step 1: Write failing orchestration and privacy tests

Inject crop generation, model prediction, label loading and ranking. Cover:

- exactly one whole-image inference plus at most three salient regions;
- EXIF orientation and bounded 224×224 preprocessing;
- invalid/tiny/overlapping region rejection;
- barcode/OCR evidence taking priority over visual similarity;
- low confidence returning `.unknown`;
- model missing, corrupt model, cancellation, memory pressure and thermal stop;
- no URL/network interface in the engine;
- temporary pixel buffers and embeddings not persisted;
- output contains model/label/calibration provenance and no nutrition/portion.

### Step 2: Run and confirm RED

```bash
cd mobile/modules/local-health-kernel
swift test --filter LocalChineseClipVisionEngineTests
```

Expected: compile failure because the engine does not exist.

### Step 3: Implement protocol-first orchestration

Keep Core ML/Vision adapters behind `#if canImport(CoreML)` and `#if canImport(Vision)` so macOS unit tests use fakes. Load compiled model and label bank only from explicitly supplied URLs. Set `MLModelConfiguration.computeUnits = .all`, but record the actual device/OS in benchmark output because hardware scheduling is not guaranteed.

Use Vision saliency only to propose bounded crops; the model still receives the whole image. Merge evidence in this order:

1. exact user selection;
2. valid local barcode mapping;
3. reviewed OCR match;
4. Chinese-CLIP visual candidates.

The engine must not know about HTTP, auth tokens, cloud inference or the production diet repository.

### Step 4: Verify package and platform compilation

```bash
swift test --filter LocalChineseClipVisionEngineTests
swift test
xcodebuild \
  -scheme LocalHealthCapabilityProbe \
  -destination 'generic/platform=iOS' \
  -derivedDataPath .build/chinese-clip-generic-ios \
  CODE_SIGNING_ALLOWED=NO build
```

Expected: all unit tests pass and the package builds for the existing iOS 16 minimum.

### Step 5: Commit

```bash
git add \
  mobile/modules/local-health-kernel/Package.swift \
  mobile/modules/local-health-kernel/ios/LocalFoodVisionPreprocessor.swift \
  mobile/modules/local-health-kernel/ios/LocalChineseClipVisionEngine.swift \
  mobile/modules/local-health-kernel/Tests/LocalChineseClipVisionEngineTests.swift
git commit -m "feat(local-vision): run Chinese-CLIP fully on device"
```

## Task 6: Extend the evidence contract and create an isolated vision benchmark host

**Files:**

- Create: `mobile/modules/local-health-kernel/ios/LocalFoodVisionBenchmark.swift`
- Create: `mobile/modules/local-health-kernel/Tests/LocalFoodVisionBenchmarkTests.swift`
- Create: `mobile/modules/local-health-kernel/DeviceHost/LocalFoodVisionBenchmarkHostApp.swift`
- Create: `mobile/modules/local-health-kernel/scripts/generate_food_vision_device_host.rb`
- Create: `mobile/modules/local-health-kernel/scripts/tests/generate_food_vision_device_host_test.rb`
- Create: `scripts/test_local_diet_eval_contract.py`
- Modify: `docs/evals/local-diet/on-device-eval-contract.json`
- Modify: `docs/evals/local-diet/README.md`

### Step 1: Write failing schema tests for custom Core ML runs

Keep old system-model reports valid. For `modelProfile.engine == "custom_core_ml"`, conditionally require:

- model artifact SHA-256;
- label-bank and calibration versions;
- installed model + label asset bytes;
- precision variant (`fp16` or the named compressed variant);
- 1-second completion rate;
- FP16-to-compressed identity-precision delta for compressed runs.

Reject device identifiers that contain UDIDs/serial numbers and reject `dataset.containsPrivateUserData == true`.

```bash
backend/venv/bin/python scripts/test_local_diet_eval_contract.py
```

Expected: FAIL because the schema does not yet accept/require the custom-model evidence.

### Step 2: Update the schema without breaking existing evidence

Add conditional `if/then` requirements instead of making new fields universal. Run the old real-device system-model JSON and new custom-model fixtures through the same validator.

### Step 3: Write failing benchmark and host-generator tests

The Swift benchmark tests inject engine, clock, memory sampler and thermal state, covering cold/warm runs, repeated cases, crash capture, cancellation, aggregation and exact JSON field names. The Ruby test requires a physical iOS 16 App target and verifies that only explicitly supplied model, label bank and authorized fixture directory become resources.

The host source must include `LOCAL_FOOD_VISION_BENCHMARK=` and must not reference `HealthKit`, `URLSession`, `PHPhotoLibrary` or production diet repositories.

### Step 4: Run and confirm RED

```bash
cd mobile/modules/local-health-kernel
swift test --filter LocalFoodVisionBenchmarkTests
ruby scripts/tests/generate_food_vision_device_host_test.rb
```

Expected: FAIL because the benchmark and generator are missing.

### Step 5: Implement the non-production host

The generator accepts explicit paths:

```bash
ruby scripts/generate_food_vision_device_host.rb \
  --output .build/food-vision-host/LocalFoodVisionBenchmarkHost.xcodeproj \
  --team-id "$DEVELOPMENT_TEAM" \
  --model .build/models/chinese-clip-rn50/coreml/compressed/ChineseClipRN50Image.mlpackage \
  --label-bank .build/models/chinese-clip-rn50/chinese-clip-label-bank-v1.bin \
  --fixtures "$AUTHORIZED_FOOD_EVAL_DIR"
```

The generator must refuse missing/relative/out-of-root assets, a fixture manifest with unclear licensing, or `containsPrivateUserData: true`. The host emits one machine-readable report line and no per-photo names, paths, pixels or embeddings.

### Step 6: Verify and commit

```bash
swift test
ruby scripts/tests/generate_food_vision_device_host_test.rb
cd ../../..
backend/venv/bin/python scripts/test_local_diet_eval_contract.py
git diff --check
git add \
  mobile/modules/local-health-kernel/ios/LocalFoodVisionBenchmark.swift \
  mobile/modules/local-health-kernel/Tests/LocalFoodVisionBenchmarkTests.swift \
  mobile/modules/local-health-kernel/DeviceHost/LocalFoodVisionBenchmarkHostApp.swift \
  mobile/modules/local-health-kernel/scripts/generate_food_vision_device_host.rb \
  mobile/modules/local-health-kernel/scripts/tests/generate_food_vision_device_host_test.rb \
  scripts/test_local_diet_eval_contract.py \
  docs/evals/local-diet/on-device-eval-contract.json \
  docs/evals/local-diet/README.md
git commit -m "test(local-vision): add physical-device evidence host"
```

## Task 7: Build the authorized Chinese-food quality set and calibrate unknown handling

**Files:**

- Create: `docs/evals/local-diet/chinese-clip-dataset-contract.json`
- Create: `mobile/modules/local-health-kernel/scripts/score_local_food_vision_run.py`
- Create: `mobile/modules/local-health-kernel/scripts/tests/test_score_local_food_vision_run.py`
- Create: `mobile/modules/local-health-kernel/model-manifests/chinese-clip-calibration-v1.json`
- Modify: `docs/evals/local-diet/README.md`

### Step 1: Define the dataset gate before collecting scores

The dataset contract requires at least 300 authorized, non-private cases with frozen expected identities and these independently reportable strata:

- common single-item Chinese foods;
- Chinese composite dishes;
- mixed plates with per-item labels;
- packaged foods and drinks;
- visually confusable pairs;
- non-food and degraded/adversarial inputs.

Do not commit the images. Commit only a redacted dataset manifest containing opaque fixture IDs, license status, expected canonical IDs and stratum. A source without redistribution/evaluation permission is excluded.

### Step 2: Write failing scorer tests

Test exact definitions for identity precision, missing-item rate, non-food rejection, correction count, Top-1/Top-3, per-stratum metrics, crash-free completion, P95 warm latency and 1-second completion. Test that duplicate predictions do not inflate precision and that omitted expected mixed-plate items increase missing-item rate.

```bash
cd mobile/modules/local-health-kernel
python3 scripts/tests/test_score_local_food_vision_run.py
```

Expected: FAIL because the scorer is missing.

### Step 3: Implement deterministic scoring and threshold search

The calibration routine may search score/margin thresholds only on a calibration split. Freeze the selected thresholds and dataset split IDs in `chinese-clip-calibration-v1.json`, then evaluate once on the held-out test split. Never tune on the final test report.

The scorer must hard-code the existing release thresholds from the eval contract, not accept lower values from command-line flags.

### Step 4: Compare FP16 and compressed variants

Run the exact same frozen test split for both variants and produce separate reports. Select the compressed version only when:

- absolute identity-precision drop from FP16 is `<= 0.02`;
- all absolute quality thresholds still pass;
- installed model + label bytes are `<= 50 MB`.

If FP16 passes and compressed fails, the outcome is still BLOCK unless FP16 also fits the 50 MB budget. Do not silently ship the larger artifact.

### Step 5: Verify and commit only non-private evidence machinery

```bash
python3 scripts/tests/test_score_local_food_vision_run.py
git diff --check
git add \
  docs/evals/local-diet/chinese-clip-dataset-contract.json \
  docs/evals/local-diet/README.md \
  mobile/modules/local-health-kernel/scripts/score_local_food_vision_run.py \
  mobile/modules/local-health-kernel/scripts/tests/test_score_local_food_vision_run.py \
  mobile/modules/local-health-kernel/model-manifests/chinese-clip-calibration-v1.json
git commit -m "test(local-vision): calibrate Chinese food recognition"
```

## Task 8: Run representative physical-device benchmarks and adjudicate G2

**Files:**

- Create: `docs/evals/local-diet/runs/<date>-<device-class>-<os>-chinese-clip-<variant>.json` for each non-private run
- Modify: `docs/evals/local-diet/on-device-eval-contract.json`
- Modify: `docs/evals/local-diet/README.md`
- Modify: `docs/dossiers/2026-07-18-local-first-private-mode.md`
- Modify: `docs/plans/2026-07-18-local-first-private-mode.md`

### Step 1: Run all pre-device verification

```bash
cd mobile/modules/local-health-kernel
python3 scripts/tests/test_verify_chinese_clip_manifest.py
python3 scripts/tests/test_build_chinese_clip_label_bank.py
.build/chinese-clip-venv/bin/python scripts/tests/test_export_chinese_clip_coreml.py
python3 scripts/tests/test_score_local_food_vision_run.py
swift test
ruby scripts/tests/generate_device_host_test.rb
ruby scripts/tests/generate_food_vision_device_host_test.rb
cd ../../..
backend/venv/bin/python scripts/test_local_diet_eval_contract.py
backend/venv/bin/python scripts/check_doc_drift.py
```

Expected: all commands exit 0. Do not pipe tests through `tail`.

### Step 2: Build, install and launch on each representative device

Repeat for low-, mid- and high-tier supported iPhones. The currently available iPhone 17 Pro Max is only the high-tier sample and cannot satisfy the matrix alone.

```bash
cd mobile/modules/local-health-kernel
ruby scripts/generate_food_vision_device_host.rb \
  --output .build/food-vision-host/LocalFoodVisionBenchmarkHost.xcodeproj \
  --team-id "$DEVELOPMENT_TEAM" \
  --model .build/models/chinese-clip-rn50/coreml/compressed/ChineseClipRN50Image.mlpackage \
  --label-bank .build/models/chinese-clip-rn50/chinese-clip-label-bank-v1.bin \
  --fixtures "$AUTHORIZED_FOOD_EVAL_DIR"
xcodebuild \
  -project .build/food-vision-host/LocalFoodVisionBenchmarkHost.xcodeproj \
  -scheme LocalFoodVisionBenchmarkHost \
  -destination "platform=iOS,id=$DEVICE_ID" \
  -derivedDataPath .build/food-vision-host-derived \
  build
xcrun devicectl device install app \
  --device "$CORE_DEVICE_ID" \
  .build/food-vision-host-derived/Build/Products/Debug-iphoneos/LocalFoodVisionBenchmarkHost.app
xcrun devicectl device process launch \
  --device "$CORE_DEVICE_ID" \
  --console --terminate-existing \
  life.executor.health.local-food-vision-benchmark
```

Capture the single `LOCAL_FOOD_VISION_BENCHMARK=<json>` line, remove transport-only device identifiers, validate it against the schema, and save it under `docs/evals/local-diet/runs/`.

### Step 3: Run privacy and failure checks

For at least one run per tier:

- enable airplane mode before first benchmark launch;
- verify model and label assets load without network;
- inspect network traffic to confirm zero photo/crop/embedding/candidate egress;
- corrupt a copied test model and confirm an explicit local failure with manual/OCR fallback;
- run repeated warm cases long enough to observe thermal state;
- cancel mid-run and confirm no report claims completion and no partial record is written.

No benchmark host may access the Local Health database, so record-write count must remain zero by construction.

### Step 4: Fill the memory ceiling from observed baselines

Only after all tiers have valid reports, set the custom Core ML `maxPeakMemoryDeltaMb` policy in `on-device-eval-contract.json`. The ceiling must preserve headroom on the lowest representative device; it cannot be derived only from the high-tier phone.

### Step 5: Make one explicit verdict

Record all Gate dimensions in the dossier:

- provenance/license;
- PyTorch/Core ML parity;
- compressed-vs-FP16 quality delta;
- food identity precision;
- mixed-plate missing-item rate;
- non-food rejection;
- correction burden;
- package size;
- cold/warm latency and 1-second completion;
- peak memory, thermal state and crash-free rate;
- airplane-mode/privacy behavior.

Verdict rules:

- `PASS`: every required field is present and every threshold passes on every representative tier.
- `FAIL`: evidence is complete and at least one non-negotiable threshold fails.
- `BLOCK`: required license, dataset or representative-device evidence is missing.

Do not average a failing tier or stratum into a pass.

### Step 6: Update the parent plan without product integration

If PASS, mark Chinese-CLIP as eligible for a **future** production integration plan. If FAIL/BLOCK, leave Task 8’s model enhancement disabled and preserve Vision/OCR/manual behavior. In either case, do not edit `mobile/app/diet.tsx` in this plan.

### Step 7: Final verification and commit

```bash
backend/venv/bin/python scripts/test_local_diet_eval_contract.py
backend/venv/bin/python scripts/check_doc_drift.py
git diff --check
git status --short
git add \
  docs/evals/local-diet/on-device-eval-contract.json \
  docs/evals/local-diet/README.md \
  docs/evals/local-diet/runs/<exact-new-run-files> \
  docs/dossiers/2026-07-18-local-first-private-mode.md \
  docs/plans/2026-07-18-local-first-private-mode.md
git commit -m "test(local-vision): record Chinese-CLIP G2 verdict"
git push origin codex/local-first-private-g2
```

Expected: committed run files contain no photos, paths, UDIDs, serial numbers or private food histories; branch push succeeds. Product integration remains a separately authorized next phase.
