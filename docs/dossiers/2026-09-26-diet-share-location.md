# 饮食分享地点编辑

- 用户原话：分享页面没有地址 没有地理位置的编写选项
- Controller: health-harness-orchestrator; overlay: safety-gate
- Run: ed567c33eebd
- 状态：代码修复、本地 G3 和 G4 完成；模拟器视觉验收及发布未执行
- Spec: [饮食分享可选地点](../specs/active/2026-09-26-diet-share-location.md)
- 基线：main e114a377e。已有未提交 `2026-09-23-frontend-publisher-recovery.md` 非本任务，保留。

## 现状与准入

DietShareComposer 缺少地点状态/入口，DietShareCard/presentation 无导出字段。Journey 的城市记录为独立模块，本次不扩展其持久化契约。G1/G2：按用户要求补现有分享界面；仅主动手填和确认、默认不分享，不推断 GPS/住址，不新增服务端权限。

## 工作序列

先加入 RED 测试，最小实现地点编辑和图文一致性；验证取消/清除/重生成失败/会话重置；相关 Jest、TS、lint；固定本地提交供独立安全审查。此次不 push、不部署、不发布。

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
- G5/G6：未请求发布，未执行。
