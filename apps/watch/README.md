# Reva Apple Watch Companion

腕上方便管理日常健康:今日状态 + 一键打点(喝水/俯卧撑/跑步/补剂/语音记餐)+ 关键推送(运动/补剂/睡眠/复查)。

## 结构与「测试边界」

| 目录 | 内容 | 测试 |
|---|---|---|
| `Sources/WatchCompanionCore/` | **纯逻辑**:summary 解码、表盘状态映射、打点校验+请求构造 | ✅ `swift test`(host,14 用例) |
| `Tests/WatchCompanionCoreTests/` | 上面的单测 | ✅ |
| `WatchApp/` | watchOS SwiftUI app(三屏 + WC 客户端 + 听写)——薄壳,逻辑全调 Core | 真机验(WatchKit 在 mac 编不过,不入 host 测试 target) |
| `WatchComplication/` | WidgetKit 表盘 complication | 真机验 |

> 设计纪律(对齐 `apps/mac`):**所有可测逻辑放 Core 并 swift test;UI/WC/complication 是声明式薄壳,真机验证**。改 watch 行为时,先在 Core 加逻辑+测试,再在壳里接。

后端契约:`GET /api/v1/watch/summary`(腕上摘要)、打点走已有写端点(`/water/records/quick`、`/daily-health/exercise`、`/diet/voice/parse`)。改后端这些 shape 时,**必须同步** `WatchSummary.swift` + 其 fixture 测试(防静默漂移)。

## 跑逻辑测试(随时,无需设备)

```bash
cd apps/watch && swift test
```

## 真机集成(设备步骤 —— 待迭代)

watchOS app 必须是独立 `watchapp2` Xcode target,加进 Expo prebuilt 的 `ios/` 工程。`xcode` npm lib 对 watch target 支持脆弱(见 `docs/plans/2026-06-15-apple-watch-companion-implementation-plan.md` §2「最脆点」),建议**先 Xcode 手工建 target 验证可上架,再写 config-plugin 固化**:

1. `cd mobile && npx expo prebuild --platform ios`(生成/刷新 `ios/`)。
2. Xcode 打开 `ios/*.xcworkspace` → File ▸ New ▸ Target ▸ **watchOS App**(bundle `life.executor.health.watchkitapp`,companion=`life.executor.health`)。
3. 把本目录的 `WatchApp/*.swift` + `Sources/WatchCompanionCore/*.swift` 加进 watch app target;`WatchComplication/*.swift` 加进 widget extension target。
   - Core 源**与 host 测试共享同一份文件**(单一真相源);target 引用即可,别拷贝改。
4. iPhone 侧加 **watch-bridge**(WCSession delegate,持 token、把 watch 的 `{op:"summary"|"quick_record"}` 转发后端)。约定见 `WatchConnectivityClient.swift` 顶部消息协议。
5. Capabilities:watch app + widget 加 App Group(complication 缓存)。
6. 验证可固化后,写 `mobile/plugins/withWatchApp.js`(仿 `withIntentsExtension.js` 的 `withXcodeProject`)把以上 target/源/capability 注入,保证 `prebuild --clean` 不丢。
7. 发版走远端 EAS:`cd mobile && npx eas-cli build -p ios --profile production --auto-submit`(见 `mobile-testflight-release` skill;watch app 随 iOS app 一起打包分发)。

## 不做(v1 边界)

腕上长对话 / 影像 / 本地诊断 / 常驻监听。腕表只做「执行 + 确认 + 一眼状态」,深度分析在 iPhone/Mac/Web。
