# Dossier: AIGC 任务运行可靠性

| 字段 | 值 |
|---|---|
| slug | `aigc-runtime-reliability` |
| 创建日期 | 2026-07-23 |
| 当前阶段 | S6 已发布，G6 模拟器通过、待真机烟测 |
| 状态 | deployed_device_smoke_pending |
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
  - Backend 初始 commit：`1726f81613a62cbdcd2265e1242f0738cf732e81`；当前生产已包含后续确认恢复修复 `3da3fb92abf5282eb3cd24748b5b7404bb3840c7`。
  - 数据库备份、231 表恢复演练和加密站外归档通过。
  - 生产健康度：60/60；线上 revision 和 Skills manifest 均核验通过。
  - 当前 Mobile production OTA：runtime `1.3.2`，group `2208d1eb-facc-4d87-a0f7-0e4bf382f193`，iOS update `019f9006-e9a1-7c74-9140-fba1f4b1a3c4`。
- G6 上线验证：PARTIAL PASS
  - 2026-07-23 在 `Reva Runtime QA`（iOS 26.5）Development Client 上加载当前生产 OTA 对应的 Mobile code revision `3da3fb92abf5282eb3cd24748b5b7404bb3840c7`。
  - 前后台切换：回到桌面再进入 App，当前会话与卡片状态正常恢复，未出现异常覆盖层。
  - 播放：已完成视频可在 Agent 对话内直接播放；点击播放后没有新增消息、确认卡或 AIGC 任务。
  - 分享：微信和小红书入口均成功准备 3.2 MB 视频文件并调起 iOS 系统分享面板。
  - 说明：Development Client 验证的是同一份 JS 逻辑，不等同于生产 OTA 二进制验收。
  - 真机仍阻塞：`suntice`（iOS 26.6）在 Xcode 中为 Offline，无法验证生产 OTA 应用、APNs 完成推送、网络断开/恢复，以及微信/小红书原生目标接收。
  - **裁决：保持未关闭**。物理 iPhone 在线后执行上述四项，全部通过才能将 G6 改为 PASS。

## 2026-07-24 · 后台与离线轮询收口

### 问题

- 生成中的任务卡在 App 进入后台后仍会继续定时查询，既不能给用户带来可见进展，也会产生无效网络请求和耗电。
- 网络监听只比较 `isConnected`，Wi-Fi 仍连接但互联网从不可达恢复时，任务状态不会立即核对。
- “请保持网络可用”容易让用户误以为必须停留在当前页面等待生成。

### 修复与不变量

- AIGC 卡片仅在 App 位于前台且互联网可达时执行有界退避轮询；切到后台或离线后暂停，离线回前台也不发起无效请求，且不取消服务端任务。
- App 回到前台或互联网从不可达恢复时立即查询 owner-scoped 任务账本，不触发确认接口，不创建第二个付费任务。
- 生成中文案明确为“可离开此页面，完成后小巴会通知你”，后台 Celery 仍负责核对任务和完成通知。
- HappyHorse 原生单任务继续只暴露 5/8/15 秒；官方单任务上限为 15 秒。16 秒需要父子任务、连续性控制和视频合成，未完成独立验证前不伪装支持。

### 增量验证

- Mobile 任务卡、分享与隐私事件：111 passed。
- Backend AIGC API、服务、策略、确认和任务：87 passed（隔离测试数据库）。
- production OTA 已从提交 `ea6ff9fff4f80b33c6276feff60a0330fb58ce80` 发布到 runtime `1.3.2`：update group `340e55b5-db1e-4936-a3ec-aa308393477d`，iOS update `019f9310-b05c-7c90-a085-04a270f5a823`。
- production channel 已通过 EAS 远端查询复核为 Active，当前活动更新与上述 group、iOS update、runtime 和 commit 完全一致。
- 最新主干提交 `99cf56c5a4d6026a22161c673ebb28d2ba66fc38` 的 CI `30076812152` 全绿；Mobile 类型、类型漂移、Agent Runtime PostgreSQL、前端、Mac 与全部 Backend 分片均通过。
- Backend 已部署精确提交 `99cf56c5a4d6026a22161c673ebb28d2ba66fc38`：生产备份与 231 表恢复演练通过，站外加密归档 SHA-256/HMAC 通过，健康度 `60/60`，Skills manifest `22/22`。
- G6 仍保持 PARTIAL：需要在生产 OTA 真机上验证后台停留、断网恢复和完成通知，不能用模拟器证据替代。
