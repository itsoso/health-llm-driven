# Dossier: AIGC 任务运行可靠性

| 字段 | 值 |
|---|---|
| slug | `aigc-runtime-reliability` |
| 创建日期 | 2026-07-23 |
| 当前阶段 | S6 已发布，待 G6 真机烟测 |
| 状态 | deployed |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA + device smoke |

## S0 · 用户需求

> 思考还有哪些优化点？
>
> 可以

- 谁用：在 Mobile Agent 中确认、等待、播放和分享 AIGC 图片或短视频的用户。
- 解决什么：App 切换或断网后状态不及时、完成后没有通知、图生视频比例描述可能误导、管理员仍受个人额度限制，运维缺少完整漏斗。
- 当前绕过：用户需要留在对话中等待或手动重开；管理员达到每日次数后也只能等待次日。

## S1 · Discovery

- Celery 已每分钟核对 active AIGC 任务，但成功后没有完成通知。
- Mobile 任务卡挂载和定时轮询会刷新，未监听 App 回前台或网络恢复。
- HappyHorse 图生视频保持源图比例，但卡片仍可能展示请求默认比例。
- AIGC 每用户并发和每日次数限制直接按 `user_id` 计算，没有管理员豁免。
- 运维已有状态、模型、类型、错误、时延和输出体积；缺少确认后成功、播放和分享漏斗。

## G1 · 准入裁决

- classification：product_change + infrastructure。
- first_class_objects：Agent Run、ExecutionEvent。
- core_loop_step：人工确认 → 外部执行 → 回执 → 用户消费结果。
- target_surface：Backend 为状态真源；Mobile 为确认、播放和分享 surface。
- safety_level：privacy_sensitive。
- autonomy_tier：`manual_confirm`，不改变。
- success_metric：任务完成后可恢复、可通知、可消费；重复操作不产生第二个付费任务。
- smallest_end_to_end_slice：前后台恢复、完成通知、比例修正、管理员个人额度豁免、漏斗事件。
- **裁决：PASS**。用户已批准按优先级实施。

## S2/S3 · Quick Flow Tech Spec

详见 [`docs/plans/2026-07-23-aigc-runtime-reliability.md`](../plans/2026-07-23-aigc-runtime-reliability.md)。

## G2 · 可行性与安全压测

- 管理员只豁免个人 active/daily 限制，仍受全局并发限制。
- 完成推送仅使用“创作已完成”类别文案，payload 只带任务 ID 和 owner-scoped deeplink。
- 客户端恢复只读状态，不触发确认或再次生成。
- 图生视频展示“跟随原图”，不伪造输出比例。
- 客户端漏斗事件不含 prompt、媒体 URL 或健康正文。
- **裁决：PASS**。无待拍板项。

## S4 · 研发任务

- [x] T1 先补管理员额度、比例投影和完成通知失败测试。
- [x] T2 补 Mobile 前后台/网络恢复与漏斗事件失败测试。
- [x] T3 实现 Backend 策略、通知和去重。
- [x] T4 实现 Mobile 恢复、准确规格展示和事件埋点。
- [x] T5 补运维漏斗聚合与告警信号。
- [x] T6 G3/G4 验证、提交、部署和 OTA。

## Gate 状态

- G3 测试：PASS
  - Backend 策略/事件/观测：110 passed。
  - Backend AIGC API/确认/任务/能力/推送：69 passed。
  - Mobile 任务卡/事件：90 passed。
  - Mobile TypeScript：`tsc --noEmit` passed。
- G4 安全：PASS
  - 完成推送锁屏文案不含 prompt、健康正文或媒体地址。
  - 客户端事件白名单拒绝 job ID、prompt、结果 URL 等资源和内容字段。
  - 管理员仅豁免个人限额，全局并发保护仍生效。
- G5 部署健康：PASS
  - Backend commit：`1726f81613a62cbdcd2265e1242f0738cf732e81`。
  - 数据库备份、231 表恢复演练和加密站外归档通过。
  - 生产健康度：60/60；线上 revision 和 Skills manifest 均核验通过。
  - Mobile production OTA：runtime `1.3.2`，group `28eb6675-b8e1-4c05-b9d2-74f648173b1a`，iOS update `019f8fd5-59e1-7050-8b06-cffdd3368c12`。
- G6 上线验证：pending
  - 待真机完成：active 任务切后台恢复、断网恢复、完成推送、播放和微信/小红书分享。
