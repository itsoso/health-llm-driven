# Apple Watch Companion 实现计划(技术执行)

> 产品/范围决策见姊妹文档 `2026-06-15-apple-watch-ultra3-health-wrist-companion.md`(R4)。
> 本文只回答 **"怎么造"**:技术路线、目标结构、config-plugin 注入、数据流、分阶段切片、反馈环、风险。
> 不在本文写产品取舍(已定);不在本文写代码(实现时按切片做)。

## 0. 决定一切的约束:RN 不能出 watchOS

`mobile/` 是 Expo SDK 55 / RN 0.83 —— **没有 watchOS 运行时**。Watch App 必须是 **原生 SwiftUI watchOS target**,加进 prebuilt `ios/` 工程。直接后果:

1. **不能 OTA**。每次改 watch 代码都要 native build(EAS build 或本地 archive)→ 本仓库**最慢反馈环**。对策见 §5。
2. **`expo prebuild --clean` 会抹掉手加的 target** → 必须用 **config plugin** 注入(不能只在 `ios/` 里手改)。模式已验证:`mobile/plugins/withIntentsExtension.js`(423 行,用 `@expo/config-plugins` 的 `withXcodeProject`/`withEntitlementsPlist`/`withInfoPlist` + `xcode` lib 注入原生 AppIntents extension)。
3. **复用已有 token 桥**:`mobile/modules/shared-keychain` 把 JWT 写进 App Group;但 **App Group 不跨设备**到手表 → 手表的 token 必须经 **WatchConnectivity** 从 iPhone 取(v1 手表不独立持 token)。

## 1. 目标结构(prebuilt ios/ 内)

```
ios/
  HealthPilot.xcodeproj
  HealthPilot/                     # 主 iOS app(RN)
  RevaIntents/                     # 已有 AppIntents extension(withIntentsExtension 注入)
  RevaWatch Watch App/             # ★新增 watchOS app target(SwiftUI)
    ContentView / TodayStatusView / CaptureView / ActionFeedbackView
    WatchConnectivityClient.swift  # 与 iPhone 通信
    WatchModels.swift              # Today status / Food draft / Action item(Codable)
  RevaWatch Complication/          # ★新增 WidgetKit complication(Smart Stack + 表盘)
```
逻辑(解析/格式化/状态映射)尽量放进**可单测的 Swift 文件**,视图薄(抄 `apps/mac` 的 `HealthAgentMacCore` 库化思路)。

## 2. config plugin:`withWatchApp.js`

仿 `withIntentsExtension.js`,新增 `mobile/plugins/withWatchApp.js`,在 `app.json` plugins 注册。职责:

1. `withXcodeProject`:用 `xcode` lib `addTarget`(productType `com.apple.product-type.application.watchapp2` + watch extension)、`addPbxGroup`(源文件分组)、`addBuildPhase`、设 `WKCompanionAppBundleIdentifier = life.executor.health`、watch bundle id `life.executor.health.watchkitapp`。
2. `withInfoPlist`:主 app Info.plist 加 watch 关联键(若需);watch target 自己的 Info.plist 写 `WKApplication`。
3. `withEntitlementsPlist`:watch target 加 App Group(本机 watch 侧)+(若用 HealthKit on watch)healthkit entitlement。
4. 把新增 Swift 源文件随 plugin 拷进 `ios/`(`withDangerousMod` 写文件,或从 `mobile/native/watch/` 源目录同步)——保证 prebuild --clean 后仍在。

> ⚠️ 这是本计划**风险最高、最易错**的一步(Xcode pbxproj 操作)。withIntentsExtension 是活的参考;先让它**只注入一个空 watch target 能 build 上架**(=§6.P0 的前置),再往里加屏。

## 3. 数据流与鉴权(v1)

```
Watch(SwiftUI: 执行+确认)
  └─ WatchConnectivityClient  ──WCSession──>  iPhone(RN + 原生 bridge module)
                                               - 持 token(shared-keychain)
                                               - 把请求转发 /api/v1/*
                                               - 离线队列 + 确认 UI
                                               └─ REST ──> Backend(同一套 /api/v1)
```
- **v1 手表不直接联网**:所有写操作经 WatchConnectivity 转给 iPhone(iPhone 持 token、排队、必要时弹确认)。低敏只读(今日状态)可后续放开 direct REST。
- 需要一个 **RN↔native bridge**(Expo module)在 iPhone 侧收 WCSession 消息 → 调已有 `mobile/services/*` 或直接 REST。可新建 `mobile/modules/watch-bridge/`(仿 shared-keychain 的 expo-module 结构)。
- App Intent 路径(Action Button/Siri/Shortcuts)复用并扩展 `withIntentsExtension` 的 intents(记录饮水/症状/饮食/查看今日状态)。

## 4. 后端要新增/对齐的端点(可先行,不依赖 watch 环境)

| 端点 | 说明 | 现状 |
|---|---|---|
| `GET /agenda/today` | Watch Today Status 直接消费(训练灯/protocol/红线) | ✅ 已建(本会话) |
| `POST /diet/voice/parse` | 语音 transcript → 结构化食物草稿(rule+memory+LLM 分层,见产品文档 §7) | 新建 |
| `POST /diet/records` 或 `/diet/voice/confirm` | 确认写 DietRecord(raw 入 notes) | `/diet/records` 已有,confirm 薄封装 |
| `POST /agenda/complete`(track/value) | action feedback(完成/跳过/调整)回写 | ✅ 已建(双轨) |
| voice capture 审计 | raw_text / device_source=watch / confidence / parser_version | 随 parse 端点带 |

> 后端这块**纯后端可测、不依赖 watch**,适合作为并行的"先铺路"工作(切片 P-back)。语音解析涉对外健康建议/食物 → 过 `safety-gate`。

## 5. 反馈环对策(本仓库最慢的环)

- **逻辑先行、可单测**:状态映射、food draft 合并、WC payload 编解码放进纯 Swift 文件,本地 `swift test` / Xcode preview 跑,不上真机。
- **真机 build 只做集成**:WatchConnectivity / HealthKit / Complication 必须真机 + 配对手表(Sim 配对很坑)。用 `mobile-testflight-release` 的远端 EAS build 异步出包,周末批量验。
- **禁止**:改一行 watch 代码就 EAS build 等 20 分钟。先把能本地验的全验完,再批量上真机。

## 6. 分阶段切片(每阶段独立可验收)

**P0 — 管线打通(最小,先做)**
- `withWatchApp.js` 注入 watch target + 一个 Complication 显示今日状态灯(读 `/agenda/today` 经 WC 中继)+ 1 个 App Intent「记录饮水」。
- 验收:EAS build 出包 → 真机配对手表 → 表盘 complication 出灯 → 腕上触发记录饮水 → 后端有记录。**证明 config-plugin 注入 + WC 中继 + 回写全链路通。**

**P1 — 语音食物(最高价值)**
- 后端 `/diet/voice/parse` + confirm(过 safety-gate)→ Watch CaptureView 录音→转写→草稿→改份量→确认→写 DietRecord。低置信腕上最多追问 1 个问题。
- 验收:腕上一句话记一餐,iPhone 可编辑,后端 DietRecord + raw 审计。

**P2 — Action Feedback + 3 屏成形**
- Today Status / Capture / Action Feedback 三屏;通知动作(完成/跳过/稍后/调整)回写 DailyPlan / InterventionEvent。
- 验收:不开 iPhone 也能完成今日最重要反馈。

**P-back(并行,纯后端)**:P1 的解析/确认端点 + 审计,先于 watch 环境做好。

## 7. 风险 / 待拍板

- **Action Button 不能强占**:只能提供 App Intent + Shortcut 配置说明 + App 内入口(产品文档 §5.3 已定)。
- **pbxproj 注入**:watch target 的 Xcode 工程操作是最脆的;P0 先验"空 target 能上架"再加料。
- **HealthKit on watch vs iPhone**:v1 健康数据仍走 iPhone HealthKit bridge(已有),watch 不直接读 HK,降复杂度。
- **CI**:watch native 不进现有 CI(同 mac 早期);逻辑 Swift 包可考虑后续加 `swift test` job。
- **多租户无关**:单租户,无额外隐私面;token 不下发到 watch(WC 中继)是隐私正确方向。

## 8. 验收门(每切片)

- 后端改动:`pytest` 相关 + `doc-drift-fix`;语音/健康建议端点过 `safety-gate`。
- config plugin:`npx expo prebuild --platform ios --clean` 后 watch target 仍在 + `ios/` 能 `xcodebuild` 通过。
- 集成:远端 EAS build(`mobile-testflight-release`)+ 真机配对手表手验。
