# LifeNav 整合交付记录

Status: implemented-local; external-validation-blocked
Owner: Health Harness
Baseline: 5aff9e45a
Plan: docs/plans/2026-10-09-lifenav-reva-integration-plan.md
Spec: docs/specs/active/2026-10-09-lifenav-health-navigation.md

## 授权与边界

用户要求“开干 全部做完”。推进计划内全部可执行交付；保留原工作区。外部真实共享必须接收方身份/源码/数据流核验，不能从临时站点名称推定。W6需完整七天实际使用，W7在其价值验证后另行裁决，不能预先打开写权限。

## 工作包

W0: PostgreSQL隔离集群已就绪；LifeNav源码/稳定实例缺失，已询问用户。
W1: 源occurrence、已生成空计划marker、只读泛化摘要、完整内容版本和记录归并已实现。
W2/W4: Mobile周导航、应用内详情、二次确认、幂等重试、过期清理已实现；HTTPS跨App回跳和完整模拟器现场验收未通过。
W3: 专用授权/兑换/撤权/审计与外部只读接口、Mobile列表撤权已实现；接收端发起与本人授权创建UI流程等待LifeNav端核验与联调。
W5: 接收端源码待取得；已交付docs/ops/lifenav-integration.md协议、字段与回退要求，未实现或验证真实LifeNav客户端。
W6: 尚未开始七天现场验收。
W7: 条件未满足，维持关闭。

## Gate

设计：本地feature spec按整合计划明确源owner和安全边界，独立审查通过。
安全：lifenav_readiness最终范围代码GO；锁、权限、隐私及源写一致性复核已修复。
测试：新鲜结果见下；部署/真实外接/七天现场Gate尚未完成，不能宣称全计划完成或上线。

## 证据

初始测试先失败：新增模块不存在；随后独立审查发现旧allowed续期、版本不完整、空计划缺marker、敏感计数泄漏和事务中途提交，逐项修复复核。补充来源卡生命周期失败测试（active未变completed），复用原源卡同步、执行snapshot与action_domain后通过。

- PostgreSQL17独立临时集群：58项同批通过（导航、授权、并发、旧反馈、复盘、仲裁）。最终仅含本任务文件的候选快照补齐来源卡同步、关闭开关旧合同、真实planner事务、AdviceGuard与登录权限后：86项全部通过。
- SQLite（补充真实planner事务测试前）：60通过、5项PostgreSQL专用测试明确跳过；不是并发/事务语义的证明。
- Mobile：19测试及TypeScript通过；详情内存清理、超时重试和409重核对有自动测试。
- 锁修复：确认和源planner都owner-first FOR NO KEY UPDATE；专用并发测试证明同操作只一次、异内容409、与FK KEY SHARE兼容。
- 双端OpenAPI类型按锁定Python依赖生成并检查；System Map与Mobile图按候选代码生成检查。
- 高置信秘密扫描与diff格式检查通过；没有新增依赖或原生配置变更。全部开关默认关闭，接收方配置默认空。

只暂存本任务文件；其他agent的原始/新增dirty修改保留。生成物从本任务暂存树的临时快照生成，避免纳入他人的新增服务/页面结构。未push、deploy或发布；主干有本地同步提交及来源独立的dirty工作，发布需重新准备干净精确SHA候选与真实CI。

## Mobile模拟器验收

2026-10-09（Asia/Shanghai）实际执行，合成界面证据不等于真实后端联调或发布验收：

- 原有 iPhone 17 模拟器 `2D49F985-8B2F-4BE1-BAA8-CA5A672D9428` 与已装应用保持完整。已有包为 1.3.4/build 1，嵌入 bundle 缺少当前健康周导航接口/回跳路由，且面向生产 API；未用旧包结果冒充候选验收。
- 使用当前源码执行 Expo iOS bundle 导出，禁用 dotenv，API 固定为 `http://127.0.0.1:19091/api`。2949 个模块打包成功；候选 JS SHA-256：`36a37738e778f4b176c1e2e3d1a9b31f58ce9ceb0d49ba17aa800ef33efb89d7`。核对 bundle 含新导航接口、localhost API，不含默认生产 API。
- 在 `/tmp/lifenav-synthetic-ui-20261009/app.app` 的复制原生壳中配置独立 bundle ID `life.executor.health.lifenavsynthetic` 与合成 scheme，关闭复制包的 Expo updates 并临时签名；未修改提交中的原生配置。新建独立模拟器 `49D3DCC8-A1C9-4A03-B5BE-31850C50BDD9`，安装与实际启动成功。复制原生壳加当前 JS 只能提供交互/布局验证，不能证明完整原生候选构建与发布 Gate。
- 实际截图显示当前登录界面，iOS 回跳“打开”系统确认弹窗尚未接受。CUA 返回 Mac 已锁定且因检测到物理输入暂停自动解锁；未绕过锁屏，因此本人登录恢复、账号切换、回跳最终派发、行动二次确认及保存后刷新均仍未完成模拟器现场验收。未读取生产健康原文，合成 API 未收到登录或业务请求。
- 新鲜验证：4 个相关 Jest suites、19 项测试通过；`npx tsc --noEmit` 与 `git diff --check` 通过。已覆盖版本冲突、同操作 ID 超时重试、未知/过期安全状态、view_only 排期与本人确认分离、授权引用格式及摘要/详情到期清除。上述自动测试不能替代未完成的模拟器现场项目。
- 本机临时证据：`/tmp/lifenav-synthetic-ui-20261009/opaque-link-login.png` 与 `evidence.json`。截图与独立模拟器保留供后续验收；临时路径不是持久 CI/发布回执。localhost 合成 API 已停止，并确认 19091 端口无监听。
