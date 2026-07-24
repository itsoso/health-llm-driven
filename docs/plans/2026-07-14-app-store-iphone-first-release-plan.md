# App Store iPhone First Release Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-14 |
| Dossier | `docs/dossiers/2026-07-14-app-store-iphone-first-release.md` |
| 目标 | 产出 Agent Native、Mobile First 的 iPhone App Store RC |
| 发布路由 | native config -> EAS production build -> TestFlight -> App Review Gate |

## 首发范围

- iPhone、portrait、iOS 16+。
- 主屏直接进入小巴 Agent 对话。
- 文字、实时语音、按住说话、拍照/选图、动态卡片、确认写入、今日刷新、分享与图片保存。
- HealthKit、通知、定位、相机、照片、麦克风均可拒绝；拒绝后文字对话仍可用。
- iPad、Watch、Rokid、Siri intents 不进入标准 production 二进制。

## Task 1 · Production Scope

1. 先写配置测试，锁住 iPhone-only、portrait-only、无可穿戴/眼镜/Siri、无后台定位/音频/蓝牙。
2. 把可选原生能力移到显式 build env/profile。
3. 让 Watch EAS post-install 在未启用时直接跳过。
4. 校验 Expo resolved config，而不是只读静态 `app.json`。

验收:标准 production 配置不声明 iPad、Watch、Rokid、Siri 或后台模式；独立 profile 仍可显式启用可选能力。

## Task 2 · Contextual Permissions

1. 登录只注册通知 listener/category；已授权设备可静默重绑 token，但不得弹系统授权框。
2. 用户在“推送通知”页开启推送时才申请系统权限；拒绝时保持服务端关闭并给出可理解反馈。
3. 移除进入主界面后的 GPS 自动弹窗；只在位置页点击“使用 GPS”时申请。
4. 保留相机、照片、HealthKit、语音的显式动作触发与拒绝降级。

验收:冷启动、登录和进入 Agent 主屏均不触发系统权限请求。

## Task 3 · Privacy And Deletion

1. Privacy manifest 与隐私营养标签对齐 App 实际收集类型。
2. 隐私政策更新品牌、数据类别、处理方/用途、保留与删除、跨境与联系方式。
3. 账号删除从一次性 audit 升级为持久、幂等、可查询、可运营处理的请求。
4. 审核说明与生产二进制能力保持一致。

验收:删除请求有唯一状态、重复请求不重复建单、处理失败不伪装成功；审核材料不宣称未进入二进制的能力。

## Task 4 · Agent Core Reliability

1. 对文字/语音/图片统一走输入状态机与同一提交契约。
2. 写操作必须具备 draft -> confirm -> writing -> verified/failed 状态和幂等键。
3. 覆盖饮食新增/修改/删除、全天汇总、图片持久化、Markdown 流式渲染、App 前后台切换。
4. 保留当前“今日行动渐进式计划”WIP，通过同一核心回归后再合入。

验收:无裸 JSON/tool tag、无重复写、无图片丢失、失败可重试且不误报完成。

## Task 5 · Release Gates

1. 增量 Jest/pytest/tsc、隐私与 App Store 检查、依赖风险分级。
2. iPhone 模拟器做布局、键盘、Markdown、状态卡和权限拒绝回归。
3. commit/push 后从干净 `main` 触发 EAS production `--auto-submit`。
4. 新 build 生成当前 UI 截图和审核说明。
5. 真机验证实时语音、按住说话、拍照/选图、微信/小红书分享、写入与删除请求。

### Build 235 补充闸门

1. 验收文件必须绑定版本 `1.3.2`、Build `235`、production EAS build ID 和源代码提交，旧 Build 的截图或真机结果不可复用。
2. 真机额外覆盖流式 Markdown、切 App 后回复恢复、草稿保留、打开/发送后定位到最新消息、图片保存分享、视频播放不触发二次生成。
3. OTA 重载前必须等待当前输入和图片草稿写入；保存失败时停止重载并给出可重试反馈。
4. 网络状态同时检查链路连接和互联网可达性，避免“已连 Wi-Fi 但无外网”被误判在线。

## Stop Conditions

- 任一核心回归失败、原始健康数据泄漏、医疗边界违规或删除请求不可追踪:停止发布，回 Task 3/4。
- EAS 构建失败或新包未进入 App Store Connect:不进入 G6。
- 真机语音/拍照/分享未验证:可保留 TestFlight，但不提交 App Review。
