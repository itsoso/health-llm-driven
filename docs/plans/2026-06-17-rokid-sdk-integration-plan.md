# Rokid SDK Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement follow-up tasks task-by-task.

**Goal:** 将 Rokid Glasses 作为 Reva ambient wearable 的视觉/语音/短提示入口接入，而不是做一个孤立的眼镜健康 dashboard。

**Architecture:** 先在现有 Expo mobile app 内新增 `rokid-bridge` 原生模块，负责发现 Hi Rokid、探测 Rokid CXR SDK、打开 companion app，并把眼镜侧事件转成后端已有的 `/ambient/*` 对象。等拿到 Rokid 授权文件、真机和正式样例后，再启用 Android AAR / iOS CocoaPods SDK 并接入 CXR-M/CXR-L 的连接、媒体流、图片、语音和 custom view 能力。

**Tech Stack:** Expo 55, React Native 0.83, Expo native modules, Android Kotlin, iOS Swift, Rokid CXR Maven artifacts, CocoaPods `RGCxrClient` / `RGCoreKit`, FastAPI ambient endpoints.

---

## 1. Current Integration Status

本次已新增第一层 SDK bridge scaffolding:

- `mobile/modules/rokid-bridge/index.ts`
  - 暴露 `getRokidIntegrationStatus()`
  - 暴露 `openHiRokid()`
  - 暴露 iOS SDK facade:
    - `requestRokidAuthorization()`
    - `clearRokidAuthorization()`
    - `openRokidCustomView()`
    - `updateRokidCustomView()`
    - `closeRokidCustomView()`
    - `takeRokidPhotoBase64()`
    - `startRokidRecord()`
    - `stopRokidRecord()`
  - native module 缺失时稳定降级, 不影响 iOS/web/mobile 现有运行
- `mobile/modules/rokid-bridge/android/*`
  - Expo Android native module: `RokidBridgeModule`
  - 探测两个 Hi Rokid 包名:
    - `com.rokid.sprite.global.aiapp`
    - `com.rokid.sprite.aiapp`
  - 探测 SDK class 是否真的链接进 APK:
    - `com.rokid.cxr.client.extend.CxrApi`
    - `com.rokid.cxr.CXRServiceBridge`
    - `com.rokid.cxr.link.CXRLink`
    - `com.rokid.sprite.aiapp.externalapp.auth.AuthorizationHelper`
    - `com.rokid.sprite.aiapp.externalapp.IMediaStreamService`
  - 默认不链接 AAR, 需要 `-Prokid.sdk.enabled=true` 或 `ROKID_SDK_ENABLED=true`
- `mobile/modules/rokid-bridge/__tests__/rokidBridge.test.ts`
  - 覆盖 native 缺失时的稳定降级
  - 覆盖 Android native 可用时的委托行为
  - 覆盖 iOS native 可用时的授权、custom view、拍照和录音委托行为
- `mobile/modules/rokid-bridge/ios/*`
  - Expo iOS native module: `RokidBridgeModule`
  - 探测 Hi Rokid URL scheme: `rokidai://`
  - 默认报告:
    - `sdkLinked`
    - `iosSdkDependencyMode`
    - `callbackScheme=life.executor.health.rokid`
    - `querySchemes=["rokidai"]`
  - 通过 `RokidBridgeAppDelegateSubscriber` 接收 OAuth/deeplink callback, 避免依赖被忽略的 `mobile/ios` 手工改动
  - 默认不链接 `RGCxrClient`, 需要 `ROKID_IOS_SDK_ENABLED=true` 或 `ROKID_SDK_ENABLED=true`
- `mobile/app.config.ts`
  - 注入 iOS `LSApplicationQueriesSchemes=rokidai`
  - 注入 Rokid auth callback URL scheme: `life.executor.health.rokid`
  - 注入 Bluetooth background mode 和使用说明
- `mobile/services/rokidAmbient.ts`
  - 将 Rokid 视觉输入写入 `/ambient/visual-inputs`
  - 将 push-to-talk 语音写入 `/ambient/audio-inputs`
  - 拉取 `surface=rokid_glasses` 的 glance cards
- `mobile/services/__tests__/rokidAmbient.test.ts`
  - 覆盖 visual/audio/glance API contract

为什么默认不直接链接 Android AAR:

- 当前 app Android `minSdk=24`。
- Rokid `client-m` / `client-l` AAR manifest 标注 `minSdkVersion=28`。
- 直接把 AAR 合入现有 app 会迫使整个 Android app 升到 minSdk 28, 这是产品兼容性决策, 不应该被 SDK 预研隐式触发。

启用真实 SDK build 的前置条件:

```bash
cd mobile/android
ANDROID_HOME="$HOME/Library/Android/sdk" \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
./gradlew :app:assembleDebug -Prokid.sdk.enabled=true
```

启用前必须先把 Android app 的 `minSdkVersion` 升到 28 或创建 Rokid-only build variant。

为什么默认不直接链接 iOS Pod:

- 官方 iOS SDK 通过 CocoaPods 分发: `RGCxrClient 1.0.1` 依赖 `RGCoreKit 0.0.2`。
- 官方搜索索引和社区反馈显示有 `RGCxrClient 1.0.2` / `ios_cxr_l_sample` 路径, 但公共 CocoaPods trunk 当前只暴露 `RGCxrClient 1.0.1`; 1.0.2 需要 Rokid specs repo 或正式 SDK 包。
- 本机 Xcode/Swift 工具链可以拉取 Pod, 但公开二进制 framework 是由 Rokid 的 Swift 6.2.4 工具链构建, 当前本机 Swift 6.3.2 无法导入该二进制模块。
- 因此 Reva 主工程默认保持可构建; 真正链接 iOS SDK 需要在兼容工具链或 Rokid 重新发布二进制后开启。

启用 iOS SDK build 的方式:

```bash
cd mobile/ios
ROKID_IOS_SDK_ENABLED=true pod install
SENTRY_DISABLE_AUTO_UPLOAD=true xcodebuild \
  -workspace HealthPilot.xcworkspace \
  -scheme HealthPilot \
  -configuration Debug \
  -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

推荐使用可重复 probe 脚本:

```bash
# 只检查 CocoaPods 是否能看到候选版本
ROKID_IOS_CLIENT_VERSION=1.0.2 \
ROKID_IOS_CHECK_SPEC_ONLY=1 \
scripts/rokid-ios-compat-probe.sh

# 如果 Rokid 提供了 specs repo, 先注入 repo 再跑完整设备构建
ROKID_IOS_SPECS_REPO=<rokid-specs-git-url> \
ROKID_IOS_CLIENT_VERSION=1.0.2 \
scripts/rokid-ios-compat-probe.sh

# 模拟器构建排除 device-only Rokid SDK
ROKID_IOS_SIMULATOR=1 \
ROKID_IOS_CLIENT_VERSION=1.0.2 \
scripts/rokid-ios-compat-probe.sh --skip-build

# 检查公开 iOS framework 的 Objective-C runtime 暴露面
ROKID_IOS_CLIENT_VERSION=1.0.1 \
scripts/rokid-ios-compat-probe.sh --inspect-framework --check-spec-only
```

脚本会:

- 可选添加/更新 Rokid CocoaPods specs repo。
- 检查 `RGCxrClient` 指定版本是否可见。
- 可选下载 `RGCxrClient.framework` 并检查 `RGCxrClient-Swift.h` 暴露的 Objective-C API。
- 用 `ROKID_IOS_CLIENT_VERSION` 让 `RokidBridge.podspec` 链接指定版本。
- 可选用 `ROKID_IOS_SIMULATOR=1` 排除 device-only SDK。
- 运行 `xcodebuild` 并识别 Swift binary/module compatibility 失败。

iOS dynamic bridge 结论:

- 已检查公开 `RGCxrClient 1.0.1` framework 包内的 `RGCxrClient-Swift.h`。
- Objective-C 头文件只暴露了 `RGCxrClientBLE` 等极少量 BLE 相关入口; `CxrClient`、`RGCxrClientAuthManager`、`openCustomView`、`takePhotoWithData`、`startRecord` 没有暴露到 Objective-C header。
- 同一个 framework 的 Swift interface 里能看到这些核心 CXR-L API, 说明它们是 Swift-only surface。
- 因此 Reva 不能通过把 bridge 改成 Objective-C selector/runtime 调用来绕过当前 Swift module import 问题。真实 iOS 能力仍然需要 Rokid 发布兼容当前 Xcode 的二进制、提供可用的 private specs repo/SDK 包, 或使用匹配 Rokid Swift 6.2.4 的构建工具链。
- 短期策略: Android-first 接入真实 SDK; iOS 保持 companion app deep link、状态展示和可构建 scaffold, 等 Rokid iOS binary compatibility 解决后再打开真实 SDK。

## 2. External SDK Facts

已验证:

- Rokid Maven repository 可访问: `https://maven.rokid.com/repository/maven-public/`
- `com.rokid.cxr:client-m` metadata 最新版本: `1.2.2`
- `com.rokid.cxr:client-l` metadata 最新版本: `1.0.3`
- 官方 CXR-L SDK 页面声明支持 Android / iOS。
- Rokid YodaOS-Sprite 文档显示 iOS SDK 通过 CocoaPods 使用 `RGCxrClient`。
- App Store 可找到 Hi Rokid companion app。
- CocoaPods `RGCxrClient 1.0.1` 依赖 `RGCoreKit 0.0.2`。
- GitHub 上已有 React Native + iOS Swift bridge 示例直接使用 `RGCxrClient` / `RGCoreKit`; 它证明 RN 上层 + iOS 原生薄 bridge 形态可行, 但仍无法绕过原生 Swift binary compatibility。
- `RGCxrClient 1.0.1` 的 Objective-C generated header 未暴露 CXR-L 核心 API, 所以 runtime/selector 方案不可作为 Swift import 失败的替代路径。
- `RGCxrClient` Swift interface 暴露的关键能力包括:
  - `CxrClient.shared.auth.authenticate(...)`
  - `openCustomView(...)`
  - `updateCustomView(...)`
  - `closeCustomView(...)`
  - `takePhotoWithData(width:height:quality:callback:)`
  - `startRecord(...)`
  - `stopRecord(...)`
- 两个 AAR URL 均返回 200:
  - `com/rokid/cxr/client-m/1.2.2/client-m-1.2.2.aar`
  - `com/rokid/cxr/client-l/1.0.3/client-l-1.0.3.aar`
- `client-m` 暴露的关键类包括:
  - `com.rokid.cxr.client.extend.CxrApi`
  - `PhotoPathCallback`
  - `PhotoResultCallback`
  - `AudioStreamListener`
  - `MediaStreamListener`
  - `CustomViewListener`
  - `TranslationListener`
- `client-l` 暴露的关键类包括:
  - `com.rokid.cxr.link.CXRLink`
  - `AuthorizationHelper`
  - `GlassPermission`
  - `IImageStreamCallback`
  - `IAudioStreamCallback`
  - `ICustomViewCallback`
  - `IGlassAppCallback`

参考链接:

- [Rokid AR Platform CXR-L SDK](https://ar.rokid.com/sdk?lang=en)
- [Rokid YodaOS-Sprite](https://ar.rokid.com/sprite?lang=en)
- [Hi Rokid on App Store](https://apps.apple.com/us/app/hi-rokid-rokid-glasses/id6749669942)
- [Rokid Academy](https://global.rokid.com/pages/academy)
- [CocoaPods RGCxrClient](https://cocoapods.org/pods/RGCxrClient)
- [CocoaPods RGCoreKit](https://cocoapods.org/pods/RGCoreKit)
- [SeeMemory-RN Rokid iOS bridge example](https://github.com/YuChanGongzhu/SeeMemory-RN/blob/b48cf139aa50875cdcab2fff7bdf31544fb67dec/ios/LocalPods/RTNRokidModule/RTNRokidModule.swift)

公开页面和旧文档只能确认方向, 不能替代 SDK 正式文档。落地前仍需向 Rokid 获取:

- 正式 SDK 文档和 sample app
- appId / 签名 / 授权配置
- 设备型号和 firmware 要求
- Hi Rokid 国际版/国内版包名和 service action 的稳定合同
- 自定义 view / media stream / photo / audio callback 的生命周期规则

## 3. Product Admission

```yaml
RequirementAdmission:
  request: 引入 Rokid SDK 模块并形成可运行的 Rokid health application path
  classification: new_product_behavior + infrastructure + experiment
  first_user_fit: 35-55 岁高强度工作者, 需要低摩擦记录饮食、药盒、补剂标签、环境和运动上下文
  core_loop_step:
    - low-friction capture
    - agenda top action
    - execution event
    - verification review
  first_class_objects:
    - ExecutionEvent
    - WriteIntent
    - HealthAgendaItem
    - LeverageAction
    - SafetyGuardian
    - HealthTwin
  target_surface:
    - Rokid Glasses: 看见场景、接收短提示、主动触发拍摄/语音
    - Mobile Android: SDK bridge、权限、连接、草稿确认
    - Backend: ambient event source of truth、安全、归因
    - Watch: 最终执行确认/稍后/跳过
  source_of_truth: Backend ambient events + Health OS ledger
  safety_level: privacy_sensitive + medical_boundary
  prescription_or_causal_verdict: clinician_review_downgraded where applicable
  autonomy_tier: manual_confirm first
  evidence_provenance: Rokid SDK docs, user-triggered capture, backend safety rules
  claim_hedging: hedged
  verification_window: same day for capture latency; 1-4 weeks for habit/protocol outcomes
  success_metric:
    - visual_capture_to_draft_latency
    - capture_confirmation_rate
    - false_positive_discard_rate
    - privacy_zone_discard_rate
    - resulting_execution_event_rate
```

准入结论: 可以做, 但 Rokid 只能是 Health OS 的 **ambient capture / glance execution surface**。不要把眼镜做成另一个 Dashboard。

## 4. Application Shapes

### Option A: Companion Bridge In Existing Mobile App

推荐作为 P0。

```text
Rokid Glasses
  -> Hi Rokid / CXR SDK
  -> mobile/modules/rokid-bridge
  -> mobile services
  -> /api/v1/ambient/visual-inputs
  -> /api/v1/ambient/audio-inputs
  -> /api/v1/ambient/glance-cards
  -> Watch/Mobile confirmation
```

优点:

- 复用现有登录、token、API client、Health OS backend。
- 不需要在眼镜上承载复杂账号和医疗安全逻辑。
- 和现有 Watch/Mobile/Mac/Web 分工一致。

缺点:

- 依赖手机在场和 Hi Rokid companion 流程。
- 真正低延迟的 media stream / custom view 需要 SDK 授权和真机验证。

### Option B: Rokid External App / Glass App

P1, 在拿到 CXR-L/CXR-M 文档后推进。

形态:

- Android app side 使用 `client-l` / `CXRLink` 与 Hi Rokid/眼镜服务通信。
- 眼镜端只显示极短 UI:
  - food draft captured
  - supplement label recognized
  - agenda next action
  - confirm / later / discard
- 手机端仍负责长编辑、隐私确认、图片保留策略。

优点:

- 更像“眼镜上的 Reva app”。
- 可支持 custom view、图片/音频流和更自然的 hands-free interaction。

缺点:

- 权限、安全、审核和 firmware 差异更复杂。
- 如果在眼镜上做太多健康解释, 会偏离低打扰执行层定位。

### Option C: Independent Glass-Side Health App

P2, 暂不推荐作为近期主线。

只有在 Rokid 提供稳定 glasses-side app SDK、独立账号和分发路径后才考虑。即使做, 也应保持:

- 离线短提示
- 主动拍摄
- 最小确认
- 连接失败缓存

不做:

- 长健康报告
- LLM 对话
- 医疗判断
- 连续后台录制

## 5. Health Use Cases

### 5.1 Food Voice/Visual Capture

```text
user sees meal/menu/label
  -> tap/voice trigger on glasses
  -> Rokid bridge receives photo path or OCR/entity candidate
  -> POST /ambient/visual-inputs intent=food_scan
  -> backend returns recommended_next_action confirm_food_draft
  -> Watch/Mobile confirmation
  -> ExecutionEvent/diet record
```

产品规则:

- 低置信度只生成草稿。
- 公共/办公环境默认不保留原图, 只保留摘要和 hash。
- 用户确认前不写入正式饮食记录。

### 5.2 Medication/Supplement Label Scan

```text
label capture
  -> intent=medication_scan or supplement_scan
  -> OCR/extracted entities
  -> SafetyGuardian checks known meds/supplements
  -> WriteIntent manual_confirm
```

产品规则:

- 不从 OCR 自动新增用药。
- 不根据标签自动改剂量。
- 高风险相互作用只做安全提示和人工确认。

### 5.3 Agenda Glance

```text
backend creates GlanceCard(surface=rokid_glasses)
  -> mobile bridge pulls active cards
  -> glasses show short action
  -> user confirms/later/skips
  -> ExecutionEvent
```

适合:

- 进公司后 20 个俯卧撑/拉伸
- 午饭后 10 分钟步行
- 咖啡因 cutoff
- 户外训练安全提示

不适合:

- 复杂解释
- 长总结
- 药物剂量建议

### 5.4 Contextual Safety Capture

用户主动触发时记录:

- 运动环境: 路况、光照、坡度、拥挤程度
- 出差/酒店: 睡眠环境、空气、饮食选择
- 不适现场: 只保存给自己/医生/家属看的上下文, 必须显式确认

## 6. Implementation Tasks

### Task 1: Bridge API And Status Surface

Status: implemented for Android scaffold and iOS opt-in SDK scaffold.

**Files:**

- Create: `mobile/modules/rokid-bridge/index.ts`
- Create: `mobile/modules/rokid-bridge/__tests__/rokidBridge.test.ts`
- Create: `mobile/modules/rokid-bridge/expo-module.config.json`
- Create: `mobile/modules/rokid-bridge/android/build.gradle`
- Create: `mobile/modules/rokid-bridge/android/src/main/AndroidManifest.xml`
- Create: `mobile/modules/rokid-bridge/android/src/main/java/life/executor/health/rokidbridge/RokidBridgeModule.kt`
- Create: `mobile/modules/rokid-bridge/ios/RokidBridge.podspec`
- Create: `mobile/modules/rokid-bridge/ios/RokidBridgeModule.swift`
- Create: `mobile/modules/rokid-bridge/ios/RokidBridgeAppDelegateSubscriber.swift`
- Create: `scripts/rokid-ios-compat-probe.sh`
- Update: `mobile/app.config.ts`

**Verification:**

```bash
cd mobile
npm test -- --runTestsByPath modules/rokid-bridge/__tests__/rokidBridge.test.ts
npx expo-modules-autolinking resolve --platform android --json | rg "rokid-bridge"
npx expo-modules-autolinking resolve --platform ios --json | rg "rokid-bridge|RokidBridge"
```

### Task 2: Mobile Service Contract

Status: implemented.

Added `mobile/services/rokidAmbient.ts`.

Functions:

- `submitRokidVisualInput(payload)`
- `submitRokidAudioInput(payload)`
- `listRokidGlanceCards()`
- `openRokidCompanionIfAvailable()`

Tests:

- axios receives `/ambient/visual-inputs`
- source defaults to `rokid_glasses`
- privacy defaults to `health_l3`
- glance cards are filtered to `surface=rokid_glasses`

### Task 3: Android SDK Enablement Variant

Decide one of:

1. Raise all Android app minSdk to 28.
2. Create Rokid-only Android build variant with minSdk 28.
3. Keep SDK runtime out of production until the project no longer supports Android < 9.

Recommendation: Option 2 if external users matter; Option 1 if this remains personal-only.

### Task 4: CXR-M/CXR-L Real Calls

After getting official sample:

- Initialize SDK / authorization helper.
- Subscribe to glass connection status.
- Subscribe to photo callback and image stream only after explicit user trigger.
- Subscribe to audio stream only for push-to-talk recording.
- Render custom view only for `GlanceCard` length limits.
- Map every capture to backend ambient events.

### Task 5: Rokid Health Mode UI

Add one Mobile screen:

- Bridge status
- Hi Rokid installed/open button
- SDK linked/class probe
- Last capture state
- Privacy mode: private / workplace / public
- Test capture actions for food, supplement, medication

Do not add a marketing page.

## 7. Risks And Boundaries

Privacy:

- No continuous camera or microphone.
- Default to user-triggered capture.
- Public/workplace captures should store summary/hash first, not raw images.

Medical:

- Visual/OCR recognition cannot create prescription changes.
- Medication and supplement flows stay `manual_confirm`.
- SafetyGuardian remains backend source of truth.

Engineering:

- SDK artifacts are current as of 2026-06-17 but can drift.
- Official docs are required before real SDK calls.
- Android minSdk 28 is the main build constraint.
- iOS SDK binary compatibility is the main Apple-side build constraint: current public `RGCxrClient 1.0.1` cannot be imported by this machine's Swift 6.3.2 compiler.
- Local Gradle verification currently blocked by a malformed Android SDK NDK directory: `/Users/liqiuhua/Library/Android/sdk/ndk/27.0.12077973` lacks `source.properties`.

## 8. Release Criteria

P0 bridge ready:

- JS facade tests pass.
- Expo autolinking discovers `rokid-bridge` on Android and iOS.
- Android module compiles in a clean SDK environment.
- iOS module compiles without linking Rokid Pod by default.
- iOS Pod can be linked in a compatible Swift toolchain or after Rokid republishes the framework.
- Mobile screen can show status and open Hi Rokid.

P1 SDK ready:

- Real device connects through SDK.
- Class probe confirms SDK linked.
- Photo callback creates `/ambient/visual-inputs`.
- Audio callback creates `/ambient/audio-inputs`.
- GlanceCard renders on Rokid surface or Hi Rokid-supported custom view.
- No capture happens without explicit trigger.

P2 product ready:

- Food capture to confirmed record under 30 seconds.
- At least 70% of captures are confirmed or explicitly discarded.
- False positives are visible in discard reason.
- Weekly completed high-leverage health actions increases without notification disable spike.
