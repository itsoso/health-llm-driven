# 回答底部分享入口收敛

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
