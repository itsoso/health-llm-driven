# 饮食分享地点编辑

- 用户原话：分享页面没有地址 没有地理位置的编写选项
- Controller: health-harness-orchestrator; overlay: safety-gate
- Run: ed567c33eebd
- 状态：S5 / 实现及 G3 本地验证完成，待 G4 独立评审
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
- G4：待固定本地代码提交后独立审查。无 API/DB/原生权限/依赖变化，不涉及 PostgreSQL 验证。
- G5/G6：未请求发布，未执行。
