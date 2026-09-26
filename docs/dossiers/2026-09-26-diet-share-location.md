# 饮食分享地点编辑

| 字段 | 值 |
|---|---|
| 状态 | shipping |
| 当前阶段 | S7 · OTA 已发布并回读；客户端视觉验收待完成 |
| 负责 | Codex / 用户 |

- 用户原话：分享页面没有地址 没有地理位置的编写选项
- Controller: health-harness-orchestrator; overlay: safety-gate
- Run: ed567c33eebd
- 状态：production OTA 已发布，服务端更新接口已验证；模拟器视觉验收尚未完成
- Spec: [饮食分享可选地点](../specs/active/2026-09-26-diet-share-location.md)
- 基线：main e114a377e。已有未提交 `2026-09-23-frontend-publisher-recovery.md` 非本任务，保留。

## G1 · 现状与准入

裁决：PASS。用户要求补齐已有饮食分享的地点编辑；范围与隐私契约见下方和关联 spec。

DietShareComposer 缺少地点状态/入口，DietShareCard/presentation 无导出字段。Journey 的城市记录为独立模块，本次不扩展其持久化契约。G1/G2：按用户要求补现有分享界面；仅主动手填和确认、默认不分享，不推断 GPS/住址，不新增服务端权限。

## 工作序列

实现阶段先加入 RED 测试，最小实现地点编辑和图文一致性；验证取消/清除/重生成失败/会话重置；相关 Jest、TS、lint；固定本地提交供独立安全审查。实现轮未发布；用户随后明确要求“发布 ota”，现进入 iOS production OTA 流程。

## 证据

- Router: implementation + safety；Codex adapter，缺失的独立 TDD/verification capability 按仓库 RED/GREEN/新鲜验证规则执行，不启用 superpowers。
- System Map 路径未索引，回源码；`system-map-check.sh` 在实现前通过。
- RED：composer/card 新增 3 项测试先失败（无地点 prop、编辑入口和海报字段），旧 60 项通过。
- G3：`CI=1 npx jest --runInBand components/diet/__tests__ components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx app/__tests__/dietCapture.test.tsx --silent`：12 suites / 273 tests PASS。
- `npx tsc --noEmit` PASS；全部改动 TS/TSX 的 ESLint PASS；`git diff --check`、`system-map-check.sh` PASS。
- 手填地点、确认/取消/清除、图文一致、截图失败重试、换餐/身份失效、两个父入口和控制字符/长度限制均有测试。
- 模拟器可用（显式设置 DEVELOPER_DIR），但安装的是既有内嵌 JS bundle；没有运行本次源码的模拟器界面或拍摄本次 UI 截图，不能把旧包当成验收通过。视觉/键盘原生验收仍待发布候选验证。
- G4 首轮：固定提交 `80bdae6d7`，独立 `share_location_safety` 裁决 NO-GO：旧预览排队的导出回调缺少 phase/资源校验，可在确认新地点后调用旧闭包。其独立 5 suites / 174 tests 通过，原测试未覆盖该窗口。
- 整改：增加内容 revision、preview phase 和当前截图 URI 校验；保留旧回调的回归测试先证明旧文字可被导出（RED），再覆盖生成中以及生成完成后的旧回调拒绝，连同复用截图 URI 的情况。
- 整改候选 `93840c666`：同一组 12 suites / 274 tests PASS；tsc、ESLint、secret scan、diff、System Map 检查再次 PASS。覆盖率专项 28 tests PASS：Composer 行覆盖 92.05%，位置归一/图文函数行和分支覆盖 100%。
- G4 复审：新独立 reviewer `share_location_safety_recheck` 对完整 `e114a377e..93840c666` 裁决 GO，无阻断；独立 Composer/Card/location 3 suites / 68 tests PASS。确认旧回调（含 URI 复用）被拒绝、取消/清除/身份失效及图文一致符合约束。GO 仅为代码安全结论，不代表视觉/发布门禁通过。
- 无 API/DB/原生权限/依赖变化，不涉及 PostgreSQL 验证。
- 发布前新鲜验证：CI=1 `scripts/run-all-tests.sh --mobile`，314 suites / 3057 passed / 1 skipped，tsc PASS；CI=1、SQLite、Asia/Shanghai 的 OTA/release-lock 集成 30 tests PASS。
- 结构闸首次发现本档案缺少机器可读状态表和 G1 裁决标题，已补齐事实结构；没有放宽校验器或补造验收。
- 精确主干 `c0eb135eb87c4b90c00117b8c53e0875c1d05078` 的 [CI 36230354846](https://github.com/itsoso/health-llm-driven/actions/runs/36230354846) completed/success；与 G4 候选的 Mobile/shared tree 一致。
- 干净发布目录 `/tmp/reva-diet-location-ota.L8Aw0g/source`：复用同 lock 依赖；再次 CI-mode Mobile 314 suites / 3057 passed / 1 skipped + tsc PASS，OTA/release-lock 集成 30 PASS，秘密扫描 PASS。原工作区非本任务文档未带入。

## G5 · OTA 发布与回读

裁决：PASS。2026-09-26 16:42（Asia/Shanghai）使用 `scripts/mobile-ota.sh production`，Hermes 一次打包、一次上传成功，无 fallback。

- Platform/channel/runtime：iOS / production / **1.3.4**。
- [EAS group](https://expo.dev/accounts/itsoso/projects/health-pilot/updates/008cd999-2007-4c17-8398-4d5dfa91c287)：`008cd999-2007-4c17-8398-4d5dfa91c287`。
- iOS update：`01a0dce1-3585-7a20-a905-746e9f4504a1`。
- 发布 SHA：`c0eb135eb87c4b90c00117b8c53e0875c1d05078`；tree digest：`f45e8996074ba50baadc133b2dc3e1463e55e29b33f4a4d7d776134a8b6f3528`。
- sourcemap 的 Composer/Card/地点归一/饮食页/ChatBubble 五个运行源与干净候选逐字一致。
- `eas update:view` 回读 group、update、runtime、commit 全部一致；production 更新接口按 iOS + runtime 1.3.4 + multipart/mixed 请求返回同一 update ID、runtime 和 launch asset。
- 初次接口读取使用不兼容的 JSON Accept 得到 406；改用协议要求的 multipart/mixed 后成功，不重复发布。
- 发布 manifest/audit 保留在发布目录；主工作区 ignored manifest 和 `.last-ota-commit` 已同步同一成功事实。旧 production group `0b70c3d4-3e8b-422f-b7f5-4fab854907aa` 属于 **1.3.3**，不得当作 1.3.4 回滚目标；本 runtime 无上一 OTA，必要时走正式 rollback-to-embedded 流程，不在此次执行。
- 原生兼容基线：TestFlight 1.3.4 (272)，EAS build `bfdd2bc9-db49-4ccd-bfbc-679287be4855` FINISHED；与其源 `cad1fd1d3` 相比无 app config、native module、依赖或插件改动。

## G6 · 客户端验收边界

服务端已提供更新，不代表每台设备已安装。当前模拟器为 runtime 1.3.3，不能接收该 1.3.4 更新；不操作或等待用户手机，不把旧模拟器包当成新 UI 验收。用户须先使用 1.3.4 安装包，重开 App 并按更新提示应用。模拟器视觉/键盘及第三方 App 分享实际交接仍未验证；本次未发布新原生包、Android 或后端。
