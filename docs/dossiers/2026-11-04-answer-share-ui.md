# 回答底部分享入口收敛

| 字段 | 值 |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | S6 后端与 production OTA 已发布，独立回读通过 |
| 工作流 | quick_fix → mobile-ota + safety-gate |
| 基线 | 91936757ad1adf2404451aa0cb0378a15b0594c6 |

## G1 准入

裁决：PASS

既有回答分享入口的局部呈现与展开交互修复；不新增平台、数据用途、网络出口、权限、健康写入或诊疗语义。复用既有主题、分享回调和完成状态门控，允许本次最小修复进入验证。

- 日期：2026-11-04
- 状态：独立发布候选准备完成；模拟器视觉/点按经用户明确豁免；待精确 CI、部署与 OTA。
- 路由：quick_fix，reva-workflow-router；按需使用 system-map。遵守全局禁用 superpowers 的要求。

## 问题与改动

每条回答底部常驻微信、小红书品牌色图标及圆形底色，抢占正文和记录回执的视觉重点。
`AnswerEvidencePanel` 统一为透明底栏、低强调依据文字，以及灰绿色线框分享/复制图标。
分享入口保持 44×44 触控区，点击后显示微信、小红书文字选项；选择后关闭选项，沿用现有分享回调。
收起分享不触发发送；回复不可导出时关闭并隐藏选项。依据与技术详情仍可独立展开。
分享内容整理、长图、隐私处理和业务写入逻辑不变。

## 验证证据

- RED：新增分享显式展开、指定目标分发、关闭及失效测试，旧实现 4 项失败、10 项通过。
- GREEN：`AnswerEvidencePanelUi`、`ChatBubbleStructuredSummary`、`ChatBubbleStreaming` 共 3 suites、159 tests 通过。
- `npx tsc --noEmit`：通过。
- 三个任务相关 TSX 文件 `npx eslint`：通过。
- `PATH="$PWD/.venv/bin:$PATH" ./scripts/system-map-check.sh`：通过；默认 shell 缺少 python3.12，仓库虚拟环境为 Python 3.12.13。
- `git diff --check`：通过。
- 合成内容 iOS 预览 bundle 导出成功，位于 `/tmp/reva-answer-share-preview-20261104.app`；复用已有预览原生壳，不作为完整原生构建或安装运行证据。
- CUA 返回 Mac 锁定、自动解锁暂停；未绕过锁定，未进行模拟器安装/点击/截图验收。预览入口已移出工作树至 `/tmp/reva-answer-share-preview-entry.tsx`。
- 用户后续明确授权：Mac 锁定时允许不用视觉验收直接上线。本次接受自动化测试、类型检查、lint、bundle 和精确 CI 替代视觉验收；模拟器视觉/点击与实际设备 OTA 接收仍为未验证，不再要求解锁作为本次发布前提。保留 CI、健康、兼容性、锁与回执闸。

## 发布边界与共享工作树

开工观察 `main...origin/main [ahead 8, behind 131]`，且有多项已有未提交改动。
遵循 AGENTS.md §7 的分叉保护，停止外部写入；无当前候选精确绿色 CI、后端部署或 OTA 证据。
已有 `ChatBubble.tsx` 饮食分享修改保持原样；`ChatBubbleStructuredSummary.test.tsx` 中对应的既有修改也保持原样，本任务仅补充分享展开步骤与新入口断言。
此前症状记录快捷路径诊断未在本 UI 任务中实施。

## 发布准备续记

- Git SSH fetch 连接关闭；改用 canonical GitHub HTTPS 获取最新 main 成功，未修改远端 URL、TLS 或全局代理配置。
- 观察当前远端 main `4a5123a5da486db64e62c10e442b5b9a7b33488b`，对应 CI `41784838681` 尚在运行。
- 仅提取 3 个本任务 TSX 文件的改动，排除结构化回复测试内原有饮食分享改动；在临时 Git index 上对最新 main 三方应用成功，无冲突，保留上游 provenanceBoundary。
- 生产只读观察为 `aaeb17f6cf77e548ffaae798e602a9849ad64806`，relay enabled/active，business lease 不存在。此前可信发布 `41782468757` 后端成功、TestFlight 上传因 App Store Connect server error 失败；不重跑该操作，也不把无 lease 当作完整收尾证明。
- 按 AGENTS.md §7 请求明确允许独立发布工作区；等待答复期间不移动共享目录、不创建隔离 worktree、不 push。

## 授权后的独立候选

- 用户明确允许独立发布工作区，并继续 CI、后端部署和 OTA。
- 基线：`91936757ad1adf2404451aa0cb0378a15b0594c6`；工作区 `/tmp/reva-answer-share-release-20261104`，原共享目录未移动。
- 仅带入 3 个 UI/测试文件及本 Dossier，保留上游 provenanceBoundary。无 native、权限、配置或后端行为变更。
- Mobile lock 与现存依赖工作区逐字一致后复用 node_modules；`CI=1` 下 5 suites / 212 tests 通过，涵盖组件、流式回复、分享文案及平台分发；tsc、局部 eslint、System Map、diff check 通过。移植时遗漏的测试解构已补齐并重新验证。
- 发布模式 mobile-ota，加 safety-gate 对分享隐私和发布权限进行独立复核。
- 前一项 TestFlight 工作流 `41789615290` 正在处理；本任务不修改其状态，不在其运行期间推进 main。

## 远端验证与发布准入

- 独立 G4 对代码提交 `39cfafe8f4caf4105d6549315d23818b59028233` 判 GO，并独立复跑 212 项测试。
- PR #300 的首次 CI `41790232025` 因本 Dossier 缺少可解析状态表和 G1 段失败，已补齐并保留失败记录；不是运行时代码失败，也未绕过 Gate。
- 本地执行当前 `trusted_ota.validate_source` 明确拒绝：`native or unknown mobile input changed`。主干相对原生 287 基线改变了 `mobile/app.json` 的 HealthKit 用途说明与插件参数。不得将本次纯 UI diff 当作完整主干可 OTA 的证明。
- 前一项 TestFlight `41789615290` 已在 server readiness 失败，未进入新构建/上传；本任务不重试、不清锁、不收尾他人操作。
- 后端部署与 OTA 尚未开始，等待精确 CI、原生兼容基线和发布历史/授权准入满足。

## main 合并与必要发布契约续接

- 用户再次明确要求“合并到 main 并且发布”。PR #300 同步最新主干后，212 项针对性测试、tsc、eslint 和独立 G4 均通过；PR CI `41806740829` 成功。
- 等待原生流程 `41806221746` 完整终态及 TestFlight 上传成功后合并，避免打断其 current-main 校验。合并提交 `ba481351305e1c4b2af2aae6545f57bd35440519`，完整 main CI `41808030303` 成功。分享 UI 已合并，不等于 OTA 已交付。
- 原生流程整体 failure：同 SHA 后端此前已由 `41801637758` 成功部署，本次再次申请被 `authorization already consumed` 拒绝；build/TestFlight 上传实际成功。生产只读确认 ad894 的 SUCCEEDED 回执。不得重跑旧部署、重建或重传包。
- 为继续本次已授权发布，单独补 source-owned ad894 continuation profile 与固定 `backend-already-consumed` 形态：保留失败 run/job 状态，绑定完整 job/上传/后端拒绝日志摘要和唯一锚定原因；仍须既有 successful-workspace 回执、真实生产、claims、安装身份与锁检查才可轮换。新增负例先失败，再实现；不开放任意失败放行。
- OTA 基线迁移至实际 Store build 291：EAS FINISHED，Apple VALID / IN_BETA_TESTING，实际 IPA 的签名权限、用途说明和源码匹配。实时 production runtime cohort 恰为证据内列出的闭集；287→288/290 的 EAS fingerprint 仅 expoConfig 与 HealthKit 用途文案插件不同，其他原生输入一致；289–291 指纹一致。没有新 native module/API。
- 旧宿主保留各自原生用途说明，OTA 不会替换这些文案；本次 UI 仅使用已有分享/复制路径。所有未来原生变化和未知 cohort 继续拒绝。完整依据见 `docs/reviews/2026-11-04-ota-runtime136-build291-baseline.json`。
- 原生基线和回执契约修复须经独立 G4、新候选精确完整 CI，再走 canonical 授权续接、后端健康回读及 trusted OTA validate/publish。当前尚未轮换或发布本次 UI。

## 已合并候选与发布续接状态

- PR #303 合并为 `1423dd5d5af378abe679b2aba7ef03761ca5f42a`，完整 main CI `41810708114` 成功；trusted release validate `41811994810` 和 OTA validate `41813195862` 成功。
- canonical staging 与 ad894→1423 授权轮换已完成。后端操作 `41813161255` 在创建 workspace/claim 前因 GitHub 只读凭据过期失败；生产仍为 ad894，本次 OTA 尚未 publish。
- 并发 PR #304 合入 `a3dc7da8cc7ba4c74e5e2752223b77a85f553ac3`，增加 backend_link 的新证明格式；其历史 strict equality 拒绝已完成的 ad894→1423 审计。旧候选不再发布，不重试旧工作流。
- 本次兼容只允许固定旧 SHA/后继、固定旧 proof 摘要及三份已完成审计摘要；保留 canonical producer 验证、安全文件读取和身份稳定检查。历史字节不改写，返回原 proof；新 inspect 仍强制 backend_link。
- 下一候选仍须独立 G4、精确完整 CI、未消费授权退役、凭据刷新、后端健康回读及 trusted OTA publish/readback；用户已豁免视觉验收，不豁免这些发布闸。


## 最终交付（2026-11-04）

裁决：PASS

- 已合并 UI PR #300、必要的原生基线 PR #303 与历史审计兼容 PR #306。实际发布版本 `91b1f1ed3fccc21d83dae3d1982076be357a3f8f`。上述准备期状态保留为历史，以下最终回执为准。
- 完整 main CI `41816648317` attempt 2：32/32 成功。首次 OTA runner 的 npm cache rename EEXIST/ENOENT 失败及其汇总失败保留；仅在同 SHA 重跑失败检查。候选代码未因此改变。
- 发布预检 `41817985100`、后端 `41821258749`、OTA validate `41822185160`、OTA publish `41822477785` 均成功。
- 后端独立回读：生产源码干净且为发布 SHA，SUCCEEDED 回执、COMMITTED/finalized runtime 一致，backend/worker/beat active；内外健康接口 200，未登录访问认证和健康记录接口均 401；无发布 lease。
- OTA：production/iOS/runtime `1.3.6`；group `5e241435-e16f-49c1-a45b-cf6e54f52ea3`，update `01a1a660-885d-7eee-b3fe-453776cd457b`。公开清单的 update/runtime/project、启动包与 47 项资源摘要匹配原 intent；服务器 claimed/verified/completed/released-lease 齐全。
- 并发流程完成的 canonical staging、授权轮换、凭据刷新及后端部署均以独立实际回读接续，未重复执行成功操作。我方 staging 因已有目录停止，两次未启动退役分别在取锁及配置清单检查停止，未生成远端退役意图；一次只读凭据 mint 成功但未安装，远端无意图/替换，精确失败原因仍未知。全部失败 WAL 保留，未清锁、未备份、未重发 vendor update。
- 用户明确豁免本次 Mac 锁定时的视觉验收；模拟器视觉/点击与用户设备实际接收仍为未验证。自动化、CI、后台与 OTA 公开清单验证通过，不冒充设备已生效。
- 本次交付是分享入口收敛；此前症状记录两轮/大上下文问题仅完成诊断，未随本 UI 修改修复。

机器可读交付证据见 `docs/reviews/2026-11-04-answer-share-ui-delivery.json`。
