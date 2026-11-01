# 主 Agent 手动滚动回跳修复

| 字段 | 值 |
| --- | --- |
| 状态 | implementation_verified |
| 当前阶段 | G3 自动回归通过；G4 代码审查 GO，待固定 SHA；发布待完成 |
| 工作流 | quick_fix → mobile-ota |

## G1 范围

修复主聊天页上下滑动后被拉回图片区域。复用用户已明确授权的隔离 worktree，
基线 `9c269f00dab1093258ea1457abbc94a3583bb883`；共享 main 的未提交工作不动。
不改变健康数据、鉴权、写入、API、原生依赖或 runtime。

## 根因与实现

- 原 `maintainVisibleContentPosition` 跟随跳到底部按钮显隐反复开关。本机锁定版本的
  React Native Fabric `RCTScrollViewComponentView.mm` 在 mountingTransactionWillMount
  用旧 props prepare，在 mountingTransactionDidMount 用新 props adjust。由关闭变开启
  时 prepare 可能跳过而 adjust 使用旧 frame，存在原生锚点回跳路径。
  改为从挂载开始保持同一配置；继续保留向前加载历史的可见行位置。
- 原 120px 接近底部阈值会让未到末尾的手动拖动恢复自动跟随；改为仅容忍 8px 的
  底部舍入误差。显式发送、选择会话、跳到最新仍可主动恢复跟随。
- focus/foreground 不再强制覆盖手动浏览意图。拖动取消定时重试、惯性滑动、
  首次历史加载以及图片/卡片多次布局跟随路径保留。

## G3 验证

- 新增 5 个回归场景在旧实现全部失败：稳定原生锚点、停在末尾前 50/100px、
  浏览历史后切回前台/页面。
- 修复后聊天页与滚动策略 2 suites / 99 tests 通过，包含原有卡片布局顺序、
  拖动取消、惯性、回到底部、发送新消息与历史入口回归。
- TypeScript、定向 ESLint、设计 token、System Map、diff check 与秘密扫描通过。
- 完整 CI-mode Mobile 主套件通过；隔离输入框 84、聊天 93、认证 34、GPS 7 通过。
- 独立 reviewer `diet_detail_safety_review` 两套件 99/99 passed；确认 Fabric 调用顺序，
  代码审查 GO，固定 commit 绑定待补；原生 UI 验收不能由 Jest 代替。
- Mac 锁屏阻挡 iOS Simulator 手势验收；已异步请求解锁，尚无设备或原生 UI 成功证据。

## G4–G6

独立审查、精确 SHA CI、后端部署、trusted OTA validate/publish 与线上回读待完成。
生产只读预检确认旧 fad537e2 的后端和 OTA 均 SUCCEEDED、无活动 business lease、
GitHub relay enabled/active；固定 GitHub App 只读 credential 已过期，需按既有同权限
刷新流程准备新候选，不允许绕过凭据校验。
