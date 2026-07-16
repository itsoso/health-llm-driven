# Dossier: Mobile Fast Feedback Loop

| 字段 | 值 |
|---|---|
| slug | `mobile-fast-feedback-loop` |
| 创建日期 | 2026-07-15 |
| 当前阶段 | S5 验证与部署 |
| 状态 | validating |
| 负责 | Codex |
| 反馈环 | Fast Refresh / focused tests / USB Release / Mobile OTA |

## S0 Intake

User request:

> “思考后续有没有更快的更新手段”
>
> “确保最小研发周期，最快迭代速度，最快测试”

Success means a single documented command for each feedback layer, fast related tests in the inner loop, cached USB device builds, verified OTA publication, and an explicit in-app apply path.

## S1 Current State

- `scripts/mobile-ota.sh` publishes iOS updates and guards clean-main provenance, but a transient EAS asset-processing timeout currently requires a manual rerun.
- `scripts/mobile-local-device.sh` runs a clean Expo prebuild and CocoaPods update, which is correct for first native setup but too expensive for each iteration.
- `expo-updates` is already installed and diagnostics expose update metadata, but the app has no foreground check/fetch/apply experience.
- `mobile/app.config.ts` already supports a side-by-side development bundle identifier.
- The existing production binary checks on launch, but adoption still depends on later process restarts.

## Requirement Admission

```yaml
request: shortest trustworthy mobile development and release feedback loop
classification: infrastructure + product_change
first_user_fit: improves delivery reliability for the primary Mobile Agent surface
core_loop_step: engineering maintenance of Mobile execution surface
first_class_objects: none; infrastructure exemption
target_surface: Mobile and release tooling
source_of_truth: Git main + Xcode device result + EAS update result
safety_level: none
autonomy_tier: none
verification_window: same development session
success_metric: warm feedback duration and verified artifact identity
```

## G1 · 准入裁决

- first_class_objects: infrastructure exemption
- core_loop_step: engineering maintenance of Mobile execution surface
- target_surface / safety_level / autonomy_tier: Mobile and release tooling / none / none
- spec_required: yes, because the app gains an update apply affordance
- smallest_end_to_end_slice: focused tests + cached USB build + verified OTA + explicit apply
- stale_surface_to_remove: manual OTA rerun and restart-only adoption instructions
- 裁决: PASS。Engineering infrastructure plus a low-risk update affordance; no health recommendation, safety decision, or write autonomy changes.
- 备选结果: ☐ REFRAME ☐ REJECT
- 用户确认:☒

## S2 Design

- Design: `docs/plans/2026-07-15-mobile-fast-feedback-loop-design.md`
- Three layers: Fast Refresh, incremental USB Release, verified OTA/TestFlight.
- No new native dependency and no background forced reload.

## G2 · 可行性 + 安全压测

- 评审方式:☒ codex challenge
- 硬阻断:fast checks cannot replace production gates; reload must remain explicit
- **待拍板分叉(STOP 问人)**:none
- 裁决: PASS。用户确认:☒

Existing Expo Dev Client, Expo Updates, Xcode, `devicectl`, and EAS channels cover the proposed behavior. Explicit apply prevents draft loss. Fast checks remain separate from release gates.

## S3 Plan

Implementation plan: `docs/plans/2026-07-15-mobile-fast-feedback-loop.md`.

## S4 · 研发任务分解

- [x] T1 Expo Update adapter and state machine.
- [x] T2 Foreground download and explicit apply banner.
- [x] T3 Settings update control and real version.
- [x] T4 Changed-file fast test command.
- [x] T5 Cached USB device Release command.
- [x] T6 OTA narrow retry and published-ID verification.
- [ ] T7 Integrated physical-device and production evidence. Production OTA is verified; physical-device UI acceptance is waiting for Xcode device services.
- 并发检查:current `main`; unrelated untracked backend and PRD files remain out of scope.

## Delivery Gates

| Gate | Status | Evidence |
|---|---|---|
| G3 tests | PASS | 248 Jest suites / 1745 tests; focused 21 tests; TypeScript PASS; lint 0 errors; 10 script tests |
| G4 safety | not required | No health/safety/write behavior |
| G5 deployment | PASS | Production group `c1f5c338-2756-4373-aaef-978ef23604c4`; iOS update `019f692d-b167-77ae-880f-8af137440c4e`; runtime `1.3.1` |
| G6 device validation | pending | iPhone is paired but `ddiServicesAvailable=false`; USB script now fails before Xcode with a direct connect/unlock instruction |

### G3 Evidence

- `./scripts/mobile-fast-test.sh`: PASS in about 12 seconds for the current diff; 4 related suites and 21 tests.
- Full Jest: 248 suites and 1745 tests PASS. The historical suite leaves asynchronous handles open after assertions; the local `--all` helper uses explicit `--forceExit`, while CI remains the authoritative no-force-exit gate.
- `npm run lint`: PASS with 0 errors. Existing repository warnings remain unchanged outside this scope.
- Incremental `tsc --noEmit`: PASS.
- `python3 -m pytest scripts/test_mobile_fast_feedback_scripts.py -q`: 10 PASS.

### G5 Evidence

- Commit deployed: `e07f421cc8c6256a3f8de1860ba6ff9feeed0d24`.
- EAS production update group: `c1f5c338-2756-4373-aaef-978ef23604c4`.
- EAS iOS update: `019f692d-b167-77ae-880f-8af137440c4e`.
- EAS runtime: `1.3.1`.
- USB acceptance stopped before build because the paired iPhone was not an available Xcode destination. No device-success claim is made.

## Constraints

- Preserve unrelated worktree files.
- Never clean or overwrite user work to speed up the build.
- Never report OTA success without an EAS update ID.
- Never auto-reload while user work may be in progress.
- Do not replace TestFlight for native/App Store release.
