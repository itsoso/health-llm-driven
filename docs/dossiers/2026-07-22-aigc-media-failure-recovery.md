# Dossier: AIGC Media Failure Recovery

| 字段 | 值 |
|---|---|
| slug | `aigc-media-failure-recovery` |
| 创建日期 | 2026-07-22 |
| 当前阶段 | G6 上线验证完成 |
| 状态 | complete |
| 负责 | Codex |
| 反馈环 | Backend pytest / Mobile+Web component tests / production trace / deploy / Mobile OTA |

## S0 · 用户需求

用户确认生成健康饮食短视频后，界面暴露内部 `aigc_confirm_*` 标识，媒体任务只显示
“未完成”且没有可执行的恢复入口；饮食记录成功和媒体生成失败混在同一回复中。

## G1 · 准入裁决

- core_loop_step: Agent 创作草稿 -> 用户确认 -> 外部媒体任务 -> 私有结果。
- first_class_objects: `AIGCMediaConfirmation`, `AIGCMediaJob`。
- safety_level: external_provider_and_cost。
- autonomy_tier: manual_confirm。
- smallest_end_to_end_slice: 隐藏内部回执 -> 分类失败 -> 安全重试 -> 独立任务状态。
- 裁决: **PASS**。这是现有 Agent Native 创作能力的可靠性和错误契约修复。

## G2 · 可行性 + 安全压测

- 生产 trace 证明本次百炼请求返回 HTTP 401，且没有 provider task ID；TokenPlan 文本套餐
  与独立按量 AIGC 媒体凭证无关。
- 只有供应商明确拒绝、没有 task ID 的失败允许用户显式重试。
- `submission_unknown` 和已有 task ID 的失败不得重发，避免重复计费。
- 草稿确认 ID 继续作为内核幂等回执保存，但不得面向用户显示。
- 日志只记录 job ID、kind、稳定错误码和 HTTP 状态，不记录 prompt、媒体 URL 或密钥。
- 裁决: **PASS**。

## S4 · 研发任务分解

- [x] 百炼错误按认证、限流、请求拒绝和服务故障分类。
- [x] 为无 task ID 的终态失败增加所有者隔离、并发安全的显式重试。
- [x] Mobile/Web 失败卡片展示可执行恢复动作。
- [x] Mobile 隐藏 AIGC 草稿的内部写回执。
- [x] Agent 文案不再引用“上方卡片”等易失位置。
- [x] 增加失败率和认证故障的运维日志/监控入口。
- [x] 将确认卡到任务卡的状态转换写回对话，刷新或跨端打开不再丢失任务状态。
- [x] 为历史已消费确认增加所有者隔离的只读恢复接口，旧卡可恢复为原任务而不重复提交。
- [x] 对供应商明确 401 拒绝做一次无重复计费风险的即时重放；传输结果不确定仍禁止自动重放。
- [x] Web/Mobile 仅轮询 active 任务，并在挂载时恢复最新状态，避免重复即时请求。
- [x] Mobile 已完成视频在 Agent 对话内播放，并可将本地 MP4 分享到微信或小红书。
- [x] 播放、分享与生成动作隔离；重复分享点击合并，临时文件在成功或失败后清理。

## G3 · 测试裁决

- Backend: 77 AIGC/observability tests passed（供应商错误分类、确认/重试幂等、API owner scope、任务恢复、策略与监控聚合）。
- Mobile: 130 tests passed；TypeScript 编译通过；ESLint 0 errors。
- Web: 33 tests passed；TypeScript 编译通过；ESLint 0 errors。
- System map/doc drift 与代码一致；Ruff 通过。
- 裁决: **PASS**。

### 2026-07-22 durable recovery follow-up

- Backend focused suite: 144 passed；API owner/recovery suite: 9 passed；新增重复历史卡批量修复、跨用户 404、401 单次重放测试。
- Web: 35 passed；TypeScript 编译通过；changed-file ESLint 0 errors。
- Mobile: 60 passed；TypeScript 编译通过；changed-file ESLint 0 errors。
- System map/doc drift 与代码一致；Ruff 与 `git diff --check` 通过。

### 2026-07-23 inline video sharing follow-up

- 完成视频卡新增紧凑的微信/小红书分享入口，小红书使用官方应用图标。
- 分享前刷新所有者隔离的任务投影，再把私有短视频下载为临时 MP4 交给 iOS 分享面板。
- 播放和分享不会调用确认、重试或生成接口；连续点击只执行一次分享。
- Mobile 定向测试覆盖播放不触发生成、分享参数、重复点击合并、下载失败清理。

### 2026-07-23 image sharing reliability follow-up

- AIGC 完成图片接入与视频一致的微信/小红书分享入口，分享前刷新短时签名地址。
- 统一图片分享支持远程签名图、带认证头的对话图片、本地截图和 iOS 裸临时路径。
- 远程图片先下载为本地媒体文件，分享结束或失败后清理；图片分享不触发任何生成接口。
- Agent 对话图片长按菜单新增“分享图片”，受保护图片沿用当前登录凭证下载。

## G4 · 安全与隐私裁决

- `submission_unknown` 或已有 provider task ID 的任务不可重试，避免重复生成与重复计费。
- 重试沿用原 job/confirmation，并使用 owner filter、advisory lock 和条件更新控制并发。
- 用户投影只暴露稳定错误码和安全文案；监控只汇总状态，不返回 prompt、图片、任务 ID、密钥或供应商响应正文。
- `aigc_confirm_*` 保留在运行时写回执中供审计，但 Mobile 不再将其作为健康数据回执展示。
- 裁决: **PASS**。

## Acceptance

- 401/403 不再显示成笼统的“稍后重试”，而是稳定的授权故障状态。
- 明确拒绝且没有 provider task ID 的任务可由用户点击一次安全重试。
- 提交结果不确定的任务不展示重试按钮。
- 对话中不出现 `aigc_confirm_*`，饮食记录成功状态不被媒体失败覆盖。
- Mobile 和 Web 使用同一后端任务投影与恢复语义。

## G5 · 部署健康裁决

- 生产 Backend/Web release commit: `26d05b74516ea2947623172e775ba67f9861518b`。
- Next.js production build 成功；前端与后端均核验为该精确 SHA。
- 数据库 40 MB 备份、231 张表恢复演练、站外 age 加密归档哈希和 HMAC 校验全部通过。
- 部署后系统健康评分 60/60 PASS；线上 skills manifest 22/22 一致。
- 裁决: **PASS**。

## G6 · 上线验证裁决

- `https://health.executor.life/api/v1/health` 返回 API、PostgreSQL、Redis、Celery 全部 healthy。
- Admin 页面返回 HTTP 200；生产监控能聚合 AIGC 媒体任务且不暴露任务正文。
- 历史失败任务投影返回 `can_retry=true`，可在同一任务卡片中显式恢复；当前 7 天窗口识别到 2 个可安全重试任务。
- iOS production OTA runtime `1.3.2` 发布成功：commit `6cb610a0e6f1265cdc659b9105e895a488e39baf`，group `bb3a3828-15bb-4af8-808d-e75c11cc99d0`，update `019f8a8b-860e-7013-afa3-344540f32837`。
- OTA 发布工具链按 `brace-expansion` 主版本分别锁定安全兼容版本；Expo iOS fingerprint `a4d7c3209f83a2d3da1d1498bbeb331f665959f9` 生成通过，production dependency audit 为 0 漏洞。
- Mobile 发布脚本回归 15 passed、TypeScript 编译通过；AIGC Mobile 卡片测试通过。全量 Mobile 基线另有 1 个既存 Siri Swift 生成文件漂移（2068/2069 tests passed），与本次纯 JS OTA 及 AIGC 恢复链路无关，未混入本次修复。
- 已确认供应商 key 可访问任务查询接口，但当前视频模型提交仍需在百炼北京区域核对按量 API Key、Workspace 与模型权限；代码已将后续 401/403 映射为 `provider_auth_failed` 并进入运维告警。
- 裁决: **PASS（应用恢复链路上线；供应商模型权限作为外部运维项继续处理）**。
