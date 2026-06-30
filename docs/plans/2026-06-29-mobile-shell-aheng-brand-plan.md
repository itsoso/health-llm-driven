# 2026-06-29 Mobile Shell 阿衡品牌一致性计划

> 目标:把登录页、锁屏态和 Siri 使用说明中的旧英文名 `HealthPilot` 收敛为 `阿衡`,避免发布前最外层入口与 App Store 名称不一致。

## 背景

- 本周 P0 是发布一致性,用户已确定主屏短名与 AI 人格统一为 `阿衡`。
- Chat/Home 主路径已经完成阿衡人格收敛。
- 登录页、Face ID 锁屏态和 Settings 的 Siri 示例仍显示 `HealthPilot`,属于上架前高可见旧品牌残留。

## 实施

- 新增 `mobile/constants/brand.ts`,集中声明 `APP_DISPLAY_NAME = '阿衡'`。
- 登录页标题使用 `APP_DISPLAY_NAME`。
- 将根布局内联锁屏抽成 `AppLockScreen`,显示 `APP_DISPLAY_NAME`,并保留解锁交互。
- Settings 的 Siri 语音记录示例使用 `APP_DISPLAY_NAME`。

## 验收

- 登录页测试确认显示 `阿衡`,不显示 `HealthPilot`。
- 锁屏组件测试确认显示 `阿衡`,不显示 `HealthPilot`,且点击“解锁”触发回调。
- Settings 测试确认 Siri 示例包含 `阿衡`,不包含 `HealthPilot`。
- 非测试代码扫描 `mobile/app mobile/components mobile/utils` 不再命中 `HealthPilot`。

## 状态

- 当前状态:已实现并通过本地聚焦测试。
