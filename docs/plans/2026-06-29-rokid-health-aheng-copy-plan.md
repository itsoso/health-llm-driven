# 2026-06-29 Rokid Health 大页阿衡文案收敛计划

> 目标:把 `Rokid 眼镜健康模式` 大页中用户可见的旧称 `Reva` 收敛为 `阿衡`,同时不改 Rokid SDK / CXR-L / CustomView 技术契约。

## 背景

- 前序批次已完成 Chat/Home/Shell 和 Rokid 俯卧撑教练的 `阿衡` 品牌一致性。
- 本周计划把 Rokid Health 大页作为独立切片处理,因为它承载授权、CustomView、语音、拍照、诊断等更大的设备状态机测试面。
- 本页仍有用户可见旧称:授权等待、眼镜视图打开/失败、语音控制 CustomView 标题、权限提示和页面按钮。

## 实施

- 复用 `APP_DISPLAY_NAME` 常量。
- 替换用户能看到的 `Reva` 文案和发送到眼镜端的 CustomView 标题/正文。
- 保留 `Rokid`、`CXR-L`、`CustomView`、`RGCxrClient` 等技术名。
- 保留 `openRokidRevaCustomView` / `createRokidRevaCustomViewLayout` 函数名、`appName: 'Reva'` SDK 授权字段、`Reva build` 和 `appName=Reva` 历史诊断日志,避免破坏 native 兼容和现场日志比对。

## 验收

- Rokid Health 测试确认:
  - iOS 真机验证步骤显示 `阿衡`。
  - 手动打开眼镜视图的按钮、payload、等待态和失败态显示 `阿衡`。
  - 语音控制发送到 CustomView 的 title 显示 `阿衡语音控制`。
  - NoNetwork / not-running 等用户指引回到 `阿衡`。
- 非测试扫描中只允许技术函数名、SDK auth 字段和历史诊断字段继续包含 `Reva`。
- 不改变设备控制、拍照、语音识别、记录写入或权限逻辑。

## 状态

- 当前状态:已实现并通过本地聚焦测试。
