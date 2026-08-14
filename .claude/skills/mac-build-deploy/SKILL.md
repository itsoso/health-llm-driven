---
name: mac-build-deploy
description: "macOS 桌面 App (apps/mac, Swift/SwiftPM) 的构建、测试、打包安装与 CI 验证。当要 build/test mac app、装到 /Applications、出 .app 包、排查 mac 编译/CI 失败、或发 mac 版时使用。"
---

# Mac Build & Deploy

`apps/mac/`(Swift 6 + SwiftUI,SwiftPM 包)的开发反馈环 + 分发。`backend-engineer`/`mac-engineer`/`qa-verifier`/`release-engineer` 共用。

## 开发反馈环(本地,秒级~分钟级)
```
cd apps/mac
swift build                                   # 编译
swift test --filter HealthAgentMacCoreTests   # 逻辑/核心测试 (CI 同款)
```
- 快照套件 `HealthAgentMacTests` **只在本地手动**跑(像素 diff 受字体/抗锯齿影响,CI 跑会假红)。
- 改逻辑优先放进 `HealthAgentMacCore`(库 = 可测);视图层薄。

## 打包 / 安装

当前冻结。`package-app.sh` 会进入签名/package/install 路径，不是 compile/test；不得运行其
默认、`--install`、`--open`、`--debug` 或 identity override。只运行 Swift compile/test。

## CI(唯一裁判 —— 本地绿 ≠ CI 绿)
CI `mac-build` job:`macos-latest` + `setup-xcode@v1 latest-stable`(pin)→ `swift build` + `swift test --filter HealthAgentMacCoreTests`。
CI 的 Xcode/工具链常比本地**旧**,会暴露本地不报的编译错(类型检查超时 / main-actor 隔离 / 跨模块 init)。**提交前若改了 Swift,必须以 CI 结果为准**;反复本地绿但 CI 红时,对照 `mac-engineer` agent 的"必踩坑"清单逐条排查。

## CI 失败快速排查(高频根因)
| CI 报错 | 根因 | 修法 |
|---|---|---|
| `unable to type-check in reasonable time` | 长链三元 / 多重 `??` 嵌套 | 拆成 `if/else` + 单 `??` 链 |
| `main actor-isolated ... can not be referenced` | 自由 `some View` 函数 | 给函数/类型加 `@MainActor` |
| 跨模块测试 `missing 'from'` | Core 的 public struct 用了隐式 internal init | 加显式 `public init` |
| 运行时崩溃(启动即崩) | `AppLocalization` 重复 key | 加条目前查重 |

## 正式分发(Developer ID DMG，非 Mac App Store/TestFlight)

> **当前冻结**：Mac route、publish、recover、rollback、formal DMG writer 与所有 direct
> helper 均返回 78。不得用环境变量、raw SSH、内部 Python/shell driver 或 nginx wrapper
> 绕过。direct Python production CLI 也冻结；协议代码只有在 strict non-root、explicit
> `MAC_RELEASE_TEST_MODE=1` 且所有路径位于固定 non-production roots（macOS
> `/private/tmp` 或 `/private/var/folders`；其他平台 `/tmp`，忽略 caller `TMPDIR`）时才可
> 通过独立 test-only harness 跑协议测试。本地 `create-candidate` 也须满足相同隔离条件，
> 只生成候选元数据，不签名、不联网、不发布。`apps/mac/scripts/release-dmg.sh` 整个 shell
> entrypoint 冻结，原 preflight/proof 模式也不例外；writer-bearing 文件不得兼任 checker。
> 任何 read-only checker 必须是独立、受审且不含 writer code 的文件。当前另允许本地
> compile/test；任何 ad-hoc/
> Developer ID signing、notarization、package/install 都冻结。

正式发布设计继续以 SwiftPM `Sources/` 为真源，不需要另建一份漂移的 Xcode target。
仓库内保留的 route-bootstrap、publish、recover 与 rollback 参数只是冻结协议标识，不是
可执行 runbook，也不应复制到终端。

- `--bootstrap-mac-routes` 是首次发布前的一次性 nginx 事务；有正式 Mac receipt、journal
  或 current manifest 后，route rollback 必须拒绝。
- `--publish-mac` 只接受 clean 且精确等于 fresh `origin/main` 的源，要求显式且不回退的
  version/build，完成 Developer ID hardened-runtime 签名、DMG 签名、notarytool accepted、
  staple、挂载校验，再上传 immutable bytes。current/stable 通过 journaled
  crash-recoverable sequence 推进；每个指针单独原子替换，终态要求 receipt/current/stable
  三者一致，不把多文件切换描述成一个原子事务。
- App Store Connect API key ID/issuer 从本地生产环境读取，私钥只从操作者受保护的
  `~/.appstoreconnect/private_keys/` 读取；禁止把值写进日志、Git、stage 或 receipt。
- SSH/信号/终态证明不明确时保留现场并报告 BLOCK；当前 recovery writer 同样冻结，
  禁止盲目重发、手改远端 lease/current 或用较新的 checkout 生成替代恢复工具。
- 发布后必须同时复证 private receipt/disk 与 public `current.json`、immutable URL、
  `/xiaoba-mac.dmg` 的 marker、size、SHA-256。三条公共路径必须是同一产物。

`scripts/package-app.sh` 当前不可作为本地兜底。本流程不等于 Mac App Store/TestFlight；
若以后走商店，必须另立需求并重做 entitlement、
sandbox、签名、审核与回滚设计。

冻结的根因不是 Mac 协议缺少若干校验，而是同 UID writable repo 可用 Git replace、
`.git/info/attributes` + filter、隐藏 untracked import shadow、`BASH_ENV` 与
`PYTHONPATH`/`sitecustomize` 改变 repo 内 launcher 实际执行字节。解冻必须另立 dossier，
由 repo-external root-owned launcher 使用固定解释器、`env -i` allowlist 和 canonical
archive/tree 的仓库外 materialization，并通过新的独立 G4。此前 Mac G5/G6 均 BLOCK。

仓库内 rc78 只是 ordinary-invocation tombstone：Bash caller 可借 `BASH_ENV` 并预定义
`exit`/`builtin` function，不能据此声称 hostile source 已被挡住。真正边界只能在上述
repo-external root-owned `env -i` launcher。
