---
name: mac-build-deploy
description: "macOS 桌面 App (apps/mac, Swift/SwiftPM) 的构建、测试、打包安装与 CI 验证。当要 build/test mac app、装到 /Applications、出 .app 包、排查 mac 编译/CI 失败、或发 mac 版时使用。"
---

# Mac Build & Deploy

`apps/mac/`(Swift 6 + SwiftUI,SwiftPM 包)的开发反馈环 + 分发。任何平台 adapter 都执行同一构建、验证和发布合同。

## 开发反馈环(本地,秒级~分钟级)
```
cd apps/mac
swift build                                   # 编译
swift test --filter HealthAgentMacCoreTests   # 逻辑/核心测试 (CI 同款)
```
- 快照套件 `HealthAgentMacTests` **只在本地手动**跑(像素 diff 受字体/抗锯齿影响,CI 跑会假红)。
- 改逻辑优先放进 `HealthAgentMacCore`(库 = 可测);视图层薄。

## 打包 / 安装(本地分发)
```
scripts/package-app.sh            # 出 apps/mac/dist/HealthAgentMac.app (ad-hoc 签名, 不入库)
scripts/package-app.sh --install  # 同时装到 /Applications
scripts/package-app.sh --open     # 打包后直接打开
scripts/package-app.sh --debug    # debug 配置
```
产物 `apps/mac/dist/` 不提交。显示名见 Info.plist;App 直连**生产** `https://health.executor.life/api/v1`。

## CI(唯一裁判 —— 本地绿 ≠ CI 绿)
CI `mac-build` job:`macos-latest` + `setup-xcode@v1 latest-stable`(滚动版本,并非精确 pin)→ `swift build` + `swift test --filter HealthAgentMacCoreTests`。
CI 的 Xcode/工具链可能与本地不同，会暴露本地不报的编译错(类型检查超时 / main-actor 隔离 / 跨模块 init)。**提交前若改了 Swift,必须以 CI 结果为准**，并按下表逐条排查。

## CI 失败快速排查(高频根因)
| CI 报错 | 根因 | 修法 |
|---|---|---|
| `unable to type-check in reasonable time` | 长链三元 / 多重 `??` 嵌套 | 拆成 `if/else` + 单 `??` 链 |
| `main actor-isolated ... can not be referenced` | 自由 `some View` 函数 | 给函数/类型加 `@MainActor` |
| 跨模块测试 `missing 'from'` | Core 的 public struct 用了隐式 internal init | 加显式 `public init` |
| 运行时崩溃(启动即崩) | `AppLocalization` 重复 key | 加条目前查重 |

## 正式分发(尚未启用)
当前仅 ad-hoc 本地签名。要上 TestFlight / Developer ID 需建 Xcode App target(指向同一 `Sources/`)+ 换正式签名 —— 这是未来工作,现在不要假装能直接发商店。
