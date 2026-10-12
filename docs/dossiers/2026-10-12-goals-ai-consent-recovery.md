# 健康目标：AI 授权读取失败恢复

| 字段 | 值 |
|---|---|
| slug | goals-ai-consent-recovery |
| 日期 | 2026-10-12 |
| 当前阶段 | G6 PASS，实现已发布 |
| 状态 | shipped |
| 负责 | root |

## G1 准入

裁决: PASS。用户明确要求修复健康目标授权错误，改只读失败恢复和分类反馈，不放宽授权，不重放生成或同意写入。

用户证据：健康目标页弹出“暂时无法确认 AI 授权”，截图时间 07:41。按 quick_fix + safety 处理；本线程只做本地实现与验证，发布 owner 为优化 README。

## 已确认与未知

- 调用链：GoalsScreen → generateGoalsFromAnalysis → API request interceptor → requireAIConsent → GET /auth/ai-consent。未通过授权检查时，生成 POST 不进入传输层。
- 原实现把策略读取、协议和会话等异常统一显示为网络问题；目标页又把本地授权取消/失败统一弹“生成失败”。代码与 RED 回归确认这两个缺陷。
- 无凭证公开授权接口 GET 返回 401，符合认证要求。只读检查近三小时 backend journal 与当前 nginx access.log 无匹配授权访问记录，不能据此推断请求未发生或确定截图原始原因。未查询用户健康内容、凭证或 consent 正文。
- 不将本地恢复路径修复宣称为截图线上根因已修复；实际用户重试仍待发布后确认。

## 修改

- policy GET 每次最多 8 秒，对网络错误、超时和 502/503/504 仅重试一次。401、403、协议不完整不重试；revision 改变或撤回期间不继续重试。
- 分别说明登录失效、服务端不可用、无权读取和协议不完整；未知/网络异常提示可去设置查看状态。移除通用“草稿会保留”保证，目标页没有用户草稿。
- 旧账号读取失败不弹窗干扰新账号；失败保持授权关闭。已有服务器同意记录仍需本次读取有效才恢复授权。
- 目标页仅抑制本地 AIConsentRequiredError 的重复通用提示；服务端 403 ai_consent_required 单独提示重新确认，不自动重放生成请求。
- 设置中的授权管理使用同一只读恢复策略；授权 PUT、撤回 PUT、目标生成 POST 均不增加重试。

## 验证与审查

- RED：新增 5 例失败，覆盖瞬时读取恢复、401/503 分类、旧账号失败抑制、目标页重复弹窗。
- 51 个测试通过：aiConsent、api、goals 页面、goalsConsentFlow。
- goalsConsentFlow 使用实际 Axios interceptors、consent 与 goals service，仅替换 transport adapter；证明授权失败/拒绝时零生成请求、瞬时读失败恢复后仅一次生成、服务器撤销授权时清除缓存且不自动重放。
- 初次独立安全审查 NO-GO：过宽 isAIConsentError 会吞服务端 403，造成无反馈。已按上项修复，并补页面与 transport 回归；全新 reviewer goals_consent_rereview 复审 GO，独立运行三个测试文件 22/22 通过。这是本地增量预审，不是固定 SHA 发布裁决。
- TypeScript：`npx tsc --noEmit` 通过。
- System Map 官方检查通过。未运行真实模型、生产授权操作或目标生成；本地交接时没有发布证据，最终交付见下方记录；没有OTA操作。

## 接力

由统一 owner 固定候选、完成独立 SHA 审查与 CI，按发布边界交付。发布后以用户实际操作验证这次授权读取能否成功；若仍失败，按新的错误分类定位会话、网络或服务端问题，不放宽 consent。

## 统一 owner 最终交付

实现已纳入55dad9b3c后端/Web发布及e580383da原生1.3.5(278)。固定候选独立G4、精确绿色CI、本地CI-mode、实际签名/来源/公开完整IPA摘要及模拟器三次启动横屏验证通过；详细SHA、回执、保留失败和未覆盖项见[统一发布dossier](2026-10-12-daily-draft-admin-model.md)。原本地预审与接力边界记录保留为历史，不是当前未发布声明。没有OTA或TestFlight操作。

安装页：[1.3.5(278)](https://health.executor.life/mobile-install/ios/20261012-admin-model-e580383da-278/install.html)。登录后原生业务路径、真实用户截图原始故障与真机安装/硬件未验证；组件、真实路由或Axios transport测试不能冒充这些验收。发布实现不保证截图原始网络/会话原因已经确定。
