# 饮食结果卡片 UI 优化

| Field | Value |
| --- | --- |
| status | blocked |
| current_stage | G3 local verification complete / release blocked |
| Controller | quick_fix |

## G1 Scope admission

裁决: PASS。按用户截图优化现有饮食结果卡，仅调整视觉层，不新增用户行为、健康建议或读写权限。

## 实现

- 已记录卡片采用 surface 底色，保留饮食类别图标和营养素颜色。
- 将完整保存回执移至热量旁，去掉独立重复勾图标；长回执允许换行。
- 两列营养格使用横向标签和读数，保留列间距，窄格允许自然换行。
- 底部查看/修正按钮等宽居中，保持 48 点最小触控高度。
- 识别、确认、修正、导航、估算说明与建议内容不变。

## 验证

- 修改前聚焦回归 112 项通过；修改后卡片目录 24 suites / 250 tests 全通过。
- `npx tsc --noEmit`、`git diff --check` 和 System Map 检查通过。
- 实际组件 React Native Web 本地合成样例：320 宽度下按钮均为 125×48，390 宽度下均为 160×48；完整文案同排可见，营养标签和数值无重叠。
- 预览使用实际字体及图标；照片为占位，路由和隐藏编辑器为适配器，交互由现有 Jest 回归验证。证据位于 `/tmp/reva-diet-ui-oct19/`；测试日志 `/tmp/reva-diet-ui-tests.log`。
- 未完成当前源码的 iOS 原生模拟器验收，不将浏览器预览或已安装旧包作为原生通过证据。

## 发布断点

- 开始时主干为 `6e2e52a591dde9a18d485373dcbf8fc1d9c07207`；检查时 CI `39204535003` 仍 in_progress。
- 现有统一发布 Dossier 记录前序发布/授权回执尚待闭合，且共享工作树有其他任务改动。保留其工作与发布操作，不接管租约、不重试或轮换。
- 本次未 push、部署或 OTA；后续须在统一发布状态闭合后绑定包含本改动的精确候选，重新通过完整 CI、CI-mode 和适用发布 Gate。
