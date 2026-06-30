# 2026-06-29 Rokid 俯卧撑教练阿衡文案收敛计划

> 目标:把 Rokid 俯卧撑教练中用户可见的旧称 `Reva` 收敛为 `阿衡`,同时不改 Rokid SDK / CustomApp / CustomView 技术契约。

## 背景

- 前序批次已完成 Chat/Home/Shell 的 `阿衡` 品牌一致性。
- 本周计划明确 Rokid 专页旧称需独立切片处理,避免把外设 SDK 文案和大测试面混入主路径批次。
- `mobile/app/rokid-pushup-coach.tsx` 中 wrong CXR session mode 的用户引导仍提示“完全退出 Reva”和“不要先打开 Reva 眼镜视图”。

## 实施

- 复用 `APP_DISPLAY_NAME` 常量。
- 仅替换 Rokid 俯卧撑教练 wrong session mode 错误引导中的用户可见旧称。
- 不改 `Rokid`、`CXR-L`、`CustomView`、`CustomApp`、native package、URL scheme 或 SDK 函数名。

## 验收

- `rokid-pushup-coach` 测试确认 wrong session mode 提示显示“完全退出阿衡”和“不要先打开阿衡眼镜视图”。
- 同一测试确认旧文案“完全退出 Reva”不再出现。
- 俯卧撑教练非测试代码扫描不再命中 `Reva` 或 `HealthPilot`。

## 状态

- 当前状态:已实现并通过本地聚焦测试。
