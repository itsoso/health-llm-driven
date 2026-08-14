# Reva Apple Watch Companion

腕上方便管理日常健康:今日状态 + 一键打点(喝水/俯卧撑/跑步/补剂/语音记餐)+ 关键推送(运动/补剂/睡眠/复查)。

Watch App 优先独立展示: iPhone App 登录后通过 WatchConnectivity applicationContext
把 token 同步到 Watch 本机 Keychain;Watch 刷新今日状态、打点和埋点时优先直连
`/api/v1`,不要求 iPhone App 前台打开。旧 iPhone relay 保留为 token 未同步或直连失败时的兜底。
Watch 启动时会先展示上次成功的 `WatchSummary` 缓存,再异步刷新;缓存只用于可用性兜底,实时性仍以刷新结果和 freshness 标识为准。

## 结构与「测试边界」

| 目录 | 内容 | 测试 |
|---|---|---|
| `Sources/WatchCompanionCore/` | **纯逻辑**:summary 解码、表盘状态映射、打点校验+请求构造 | ✅ `swift test`(host,14 用例) |
| `Tests/WatchCompanionCoreTests/` | 上面的单测 | ✅ |
| `WatchApp/` | watchOS SwiftUI app(三屏 + WC 客户端 + 听写)——薄壳,逻辑全调 Core | 真机验(WatchKit 在 mac 编不过,不入 host 测试 target) |
| `WatchComplication/` | WidgetKit 表盘 complication | 真机验 |

> 设计纪律(对齐 `apps/mac`):**所有可测逻辑放 Core 并 swift test;UI/WC/complication 是声明式薄壳,真机验证**。改 watch 行为时,先在 Core 加逻辑+测试,再在壳里接。

后端契约:`GET /api/v1/watch/summary`(腕上摘要)、打点走已有写端点(`/water/records/quick`、`/daily-health/exercise`、`/diet/voice/parse`)。改后端这些 shape 时,**必须同步** `WatchSummary.swift` + 其 fixture 测试(防静默漂移)。Watch 直连请求必须经过 `WatchBackendRequest` 白名单构造,不要在 UI 层手写任意后端 path。

## 跑逻辑测试(随时,无需设备)

```bash
cd apps/watch && swift test
```

## 注入 watch target 并编译验证(脚本化,已跑通)

`xcode` npm lib 对 watch target 支持脆弱,改用 **ruby `xcodeproj`** 脚本注入(更可靠):

```bash
cd mobile && npx expo prebuild --platform ios          # 生成/刷新 ios/
cp ../apps/watch/WatchApp/*.swift ../apps/watch/Sources/WatchCompanionCore/*.swift ios/RevaWatch/   # 单一真相源
ruby ../apps/watch/scripts/inject_watch_target.rb       # 注入 RevaWatch watchOS app target(幂等)
cd ios && xcodebuild -project HealthPilot.xcodeproj -target RevaWatch \
  -sdk watchsimulator -configuration Debug CODE_SIGNING_ALLOWED=NO build   # ✅ 编译验证(已 BUILD SUCCEEDED)
```

脚本一次注入**三个东西**(幂等,prebuild --clean 后重跑):
1. `RevaWatch` watchOS app target(`WatchApp/` + `Sources/WatchCompanionCore/`)
2. `RevaComplication` widget extension target(`WatchComplication/`,嵌入 watch app)
3. iPhone WC bridge(`mobile/native/watch/WatchPhoneBridge.swift` → 主 target HealthPilot)

> 2026-06-16 实测(watchOS 26.5 SDK):RevaWatch **BUILD SUCCEEDED**、RevaComplication **BUILD SUCCEEDED**、
> WatchPhoneBridge `swiftc -typecheck` 通过。整条原生链路已编译验证(非纸面)。
> config-plugin `mobile/plugins/withWatchApp.js`(把本脚本移植成 survive prebuild 的自动注入)= 下一步。

## 真机集成(只剩设备步骤)

- **激活 bridge**:App 启动时调 `WatchPhoneBridge.shared.activate()`(AppDelegate 或一个极小 Expo module 里一行),登录 token 变化时 `SharedKeychainModule` 会通知 bridge 同步到 Watch。
- **Capabilities**:watch app + widget + 主 app 加 App Group `group.life.executor.health`(complication 缓存);bridge token 复用 Siri 的 `siri_auth_token`,Watch 本机保存到 Keychain。
- **真机运行**:装到配对手表跑通(complication 出状态灯、腕上喝水/俯卧撑回写、关键推送)。
- **发版边界**:标准 `production` 是 iPhone-only，不包含 Watch。Watch 使用独立
  `watch-production` profile，并必须另建 dossier，通过多 target 签名/版本、物理
  Watch、TestFlight 与商店资料 Gate；见 `mobile-testflight-release` skill。

1. `cd mobile && npx expo prebuild --platform ios`(生成/刷新 `ios/`)。
2. Xcode 打开 `ios/*.xcworkspace` → File ▸ New ▸ Target ▸ **watchOS App**(bundle `life.executor.health.watchkitapp`,companion=`life.executor.health`)。
3. 把本目录的 `WatchApp/*.swift` + `Sources/WatchCompanionCore/*.swift` 加进 watch app target;`WatchComplication/*.swift` 加进 widget extension target。
   - Core 源**与 host 测试共享同一份文件**(单一真相源);target 引用即可,别拷贝改。
4. iPhone 侧加 **watch-bridge**(WCSession delegate,持 token、把 watch 的 `{op:"summary"|"quick_record"}` 转发后端)。约定见 `WatchConnectivityClient.swift` 顶部消息协议。
5. Capabilities:watch app + widget 加 App Group(complication 缓存)。
6. 验证可固化后,写 `mobile/plugins/withWatchApp.js`(仿 `withIntentsExtension.js` 的 `withXcodeProject`)把以上 target/源/capability 注入,保证 `prebuild --clean` 不丢。
7. 正式发布不要套用 iPhone 的 `production` 候选，也不要直接调用供应商 CLI。
   `watch-production` 必须先接入受控 build-only 交易，再从仓库根目录的受控入口创建
   候选；构建选择、TestFlight 验收和 App Review 提交分别过 Gate。本次 iPhone
   formal release 明确不包含 Watch。

## 不做(v1 边界)

腕上长对话 / 影像 / 本地诊断 / 常驻监听。腕表只做「执行 + 确认 + 一眼状态」,深度分析在 iPhone/Mac/Web。
