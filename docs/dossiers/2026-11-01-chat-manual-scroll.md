# 主 Agent 手动滚动回跳修复

| 字段 | 值 |
| --- | --- |
| 状态 | delivered |
| 当前阶段 | G5 后端与 OTA 已发布；G6 自动线上证据 PASS，模拟器手势及设备接收未验证 |
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

## 初始 G4–G6 预检（历史阶段）

独立审查、精确 SHA CI、后端部署、trusted OTA validate/publish 与线上回读待完成。
生产只读预检确认旧 fad537e2 的后端和 OTA 均 SUCCEEDED、无活动 business lease、
GitHub relay enabled/active；固定 GitHub App 只读 credential 已过期，需按既有同权限
刷新流程准备新候选，不允许绕过凭据校验。

## 首次 CI 失败与测试调度修复

`4802c860627962c1c005bf43bf6832755508bcf4` 已合入 main，完整 CI
`41298852550` 的聊天隔离套件失败：后续用例/cleanup 超时并出现跨用例卸载。
发布尚未执行，线上保持旧 fad537e2；没有新 stage、刷新凭据或发布 claim。

本机默认 Node25 原 93 tests 通过，而 CI 同款 Node22 复现 15 failed / 78 passed，
首个超时出现在现存 momentum 用例后的 cleanup，随后级联。将滚动测试假计时器
限定为滚动延时，保留 nextTick、setImmediate、queueMicrotask 的真实调度后，
同一 Node22 完整聊天套件 93/93 passed，3.315 秒；不放宽超时，不跳过断言，
不改运行时实现。新候选须重新通过完整 CI。

候选4802的模拟器 Release 构建成功；首次本地构建因缺少 Sentry organization 的
源码映射上传失败，明确关闭仅本地自动上传后构建成功，不改生产配置。原生 UI
实际手势仍等待 Mac 解锁，不将构建成功视为 G6。

## 发布交接断点（2026-11-01，已解除）

- 功能提交 `4802c860627962c1c005bf43bf6832755508bcf4` 与测试调度提交
  `1146e8f6bc38301723528ba74539517852219bcd` 均已合入 main。
  1146 完整 CI `41299780349` 32/32 成功，trusted-release validate
  `41300700641` 成功；Node22 聊天及滚动策略 99/99 通过。
- 1146 canonical stage 单次执行在完成 source 校验后，最终 current-main 检查
  发现主干已前进而退出 1。未部署、未领取业务发布 claim；原失败证据及 source
  保留，不重放该脚本。独立回读确认源干净且生产仍为 fad537e2。
- 随后主干依次前进至 b222227a、852c97c9。b222 完整 CI
  `41301019612` 成功；852 完整 CI `41301795386` 最近观察仍在运行，
  不能声明其完整 CI 已绿。两个增量的独立代码安全审查均 GO。
- 本线程 validate `41301825270` 输入 b222，但 dispatch 时 main 已到852，
  在无生产凭据的源码检查阶段失败；未部署。另一路 validate `41301780652`
  对 b222 成功，不属于本线程发起的操作。
- 新鲜只读生产核验发现另一流程已完成同 App/installation/repository 的读取凭据
  刷新，审计 `77e81c9105d04afe91197473e8c7e688` 为 CREDENTIAL_REFRESHED。
  本线程未刷新凭据、未轮换授权；旧凭据绑定失效，未修改摘要继续执行。
- 当前生产及授权仍为 `fad537e2cb4e6d81a219d4ab5791d3896a5bd1d2`，
  旧 backend/OTA 回执保持 SUCCEEDED；852 source/release 不存在，business lease
  当时不存在。它们不证明另一流程已结束，也不证明本次修复已上线。
- 独立 reviewer 明确 G5 BLOCK：先确认单一发布负责人或完成交接。
  launcher/build 锁只串行单次操作，不能协调整条 stage→rotate→backend→OTA。
  暂停新的 dispatch/stage/凭据刷新/授权轮换/部署/OTA，所有草案未执行。
  此处是基于实际并行操作的发布安全判断，不是重新索取用户已授予的发布许可。
- 已向用户异步请求发布任务协调及 Mac 解锁，尚无答复。G6 模拟器真实手势验收
  仍未验证。此段仅本地记录，避免为文档再次推进正在协调的主干候选。


## 协调解除与固定 852 发布

用户确认另一任务已完成，可继续核验最新主干。重新核验 main 为
`852c97c9b1cad892cb2fa44859700ac5a96bce9e`；完整 CI
[41301795386](https://github.com/itsoso/health-llm-driven/actions/runs/41301795386)
32/32 成功，独立代码审查覆盖其中的 Edu operator 和 Mobile Notebook 增量。
本流程不执行 Edu viewer 激活操作。

- [Trusted release validate 41303325224](https://github.com/itsoso/health-llm-driven/actions/runs/41303325224)
  成功。首次 852 stage 在读取旧 fad canonical 源时因唯一 Python 缓存被拒绝，
  发生于锁及候选目录创建之前，未修改生产，原失败完整保留。
- 独立检查固定缓存内容：header 绑定源码时间和大小，递归比较编译代码字段（包括
  filename/firstlineno/linetable/exceptiontable）一致，源码等于固定 Git blob；
  不执行缓存，不推断其生成者。受审脚本 b5bb27b7 在原 launcher/build 锁内
  仅 unlink 此文件、rmdir 随后空目录，完成回执 ac9a75e7；前后保护状态未变。
- 独立恢复 stage bdd40fcd 绑定原失败及清理回执，使用新操作记录且保留全部原门禁；
  完整 strict fsck 后成功，完成摘要
  `826935b23c7b9b2d9aae73a9382e76514791ee84ef7bd97a360462c06ee47a7a`。
  独立回读确认 canonical 852 干净，生产仍 fad，无 business lease。
- 使用已经真实完成的外部只读凭据刷新审计，明确标记来源，不重复 mint 或伪造本线程
  刷新回执。独立审查发现辅助脚本在实际 INSTALLED 后仍要求未来 900 秒预算会误报；
  修正为执行前预算门禁、返回后完整性及成功终态检查，4 个模拟边界测试通过。
  最终 c8f24542 一次授权轮换成功为 INSTALLED，独立回读安装摘要与852一致。
- [后端发布 41305063179](https://github.com/itsoso/health-llm-driven/actions/runs/41305063179)
  成功，实际完成回执为852/SUCCEEDED，原始摘要
  `e2672584cb4874bc9808408a08d2c7e7214c6a390242157e59193ff2345ad592`。
  独立校验生产HEAD干净、授权匹配、health-backend/celery-worker/celery-beat/reva-laya
  均 active/running，内网与公网健康均 healthy，business lease absent。
- [OTA validate 41305586857](https://github.com/itsoso/health-llm-driven/actions/runs/41305586857)
  成功。旧只读凭据临近到期，在已部署852、OTA未开始且无lease的固定边界进行同App、
  同installation、同repo、同read-only scope刷新。独立审查及前后回读通过，原外部
  审计保留，不轮换生产授权，不创建原本不存在的build锁。
- [OTA publish 41306012202](https://github.com/itsoso/health-llm-driven/actions/runs/41306012202)
  已单次发布完成。服务器 completed 为852/SUCCEEDED，原始摘要
  `d99746243dfe94ddd949fe199646ac67e4dca8678b0e0fc25c8dc97716ad79d3`；
  verified receipt 摘要 `d6ccbe79bbdc67354eb824dd0f70768e27d599d9f80ffd1cc3c1e61a9f5c9439`。
  原 lease 已正确归档，business lease absent，完整回执链经独立校验。
- 官方公开 manifest 新鲜读取通过 contract 校验：production / iOS / runtime `1.3.6`，
  update `01a19714-0e2d-7d22-8c61-f6760101dc5d`，group
  `53c202f5-5a8b-444b-b2fe-962e42ff3954`，launch hash
  `AVx7E8wT9YR1wWp8vM6k6Fzj3c0PZ8RO9b--K5nWeIA`；启动包及全部47个资源
  hash 均与本次 claimed artifact 匹配，未复用旧 fad 的公开证明。
  本地独立证据：`/private/tmp/reva-chat-scroll-852c97c9-backend-acceptance.json`、
  `/private/tmp/reva-chat-scroll-852c97c9-ota-acceptance.server-proof.json`、
  `/private/tmp/reva-chat-scroll-852c97c9-ota-acceptance.public-manifest-proof.json`。

全过程未创建备份、回退副本或读取历史备份正文。Mac 解锁答复尚未收到，实际模拟器
手势以及设备接收本次 OTA 仍未验证；构建、测试和公开 manifest 不能替代此项。
