# AIGC 任务运行可靠性实施计划

## 范围

本轮增强现有单任务 AIGC 链路，不实现 16 秒合成、不增加创作中心、不接入新的原生分享 SDK。

## 不变量

- 生成仍需用户点击一次性确认卡。
- 恢复、通知、播放和分享都不能再次触发 provider 生成。
- 全局并发上限对管理员和普通用户都生效。
- 通知和埋点不包含 prompt、媒体 URL、源图片或健康正文。
- Provider 输出仍先转存到用户私有空间。

## 数据流

```text
Mobile confirmation
  -> owner-scoped confirm API
  -> durable AIGC job
  -> provider task
  -> Celery reconcile
  -> private result
  -> generic completion push
  -> Mobile foreground/network refresh
  -> play/share client events
  -> de-identified operations funnel
```

## 实施顺序

1. Backend policy
   - 查询 `User.is_admin`。
   - 管理员跳过个人 active/daily 限制，保留全局 active 限制。
   - 图生视频规格投影为 `ratio_mode=source`，客户端显示“跟随原图”。
2. Completion notification
   - 仅在状态从 active 首次变成 succeeded 时发送一次。
   - 使用 PushService、quiet hours、通知日志和稳定去重键。
   - 通知正文泛化，payload 只含任务 ID、类型和 Agent deeplink。
3. Mobile recovery
   - active 卡在 App 回前台和网络恢复时立即 GET 最新状态。
   - 事件监听卸载时清理；恢复操作不调用 confirm/retry。
4. Funnel and operations
   - 记录 confirmation consumed、completed、played、shared。
   - 服务端聚合完成率、播放率、分享率和卡住任务数。
   - 客户端事件仅传媒体类型、阶段和目标渠道；禁止任务 ID、prompt、URL 和健康正文。

## 验收

- 普通用户达到个人限额返回可理解提示；管理员仍可生成。
- 达到全局并发时管理员同样被保护。
- 图生视频不再显示固定 `9:16`。
- 切后台再回来、断网再恢复时，active 卡立即刷新且不产生 POST。
- 同一成功任务最多发送一次完成通知。
- 播放和分享不会触发确认或 provider 任务。
- 运维可看到匿名漏斗与卡住任务，不暴露内容。

## 发布

- Backend 变更先通过 `deploy.sh -b` 部署。
- Mobile 仅涉及 TS/TSX，走 production OTA。
- G6 由真机完成切后台、断网、播放和分享烟测。
