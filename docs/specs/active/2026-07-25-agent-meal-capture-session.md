# Feature Spec: Agent 多图餐食采集事务

## 服务端契约

`MealCaptureSession` 由 `(user_id, source_message_id)` 唯一标识，包含有序图片资产、语义决策、可选草稿、可选正式记录和稳定卡片身份。

### Card data v2

```json
{
  "card_id": "diet-capture:5e26c5c9",
  "capture_session_id": "5e26c5c9",
  "recorded": true,
  "record_id": 123,
  "photo_asset_ids": ["asset-a", "asset-b"],
  "photo_urls": ["<short-lived>", "<short-lived>"],
  "photo_asset_id": "asset-a",
  "photo_url": "<short-lived>"
}
```

- 复数字段为真源；单数字段只用于旧客户端兼容。
- `card_id` 绑定 capture session，在草稿确认、自动写入、实时重连和历史恢复之间保持不变；`record_id`/`draft_token` 只是当前业务投影。
- 持久化消息 meta 必须删除所有 URL，只保留 IDs。
- 历史读取按当前 owner 重新签名。

## Exactly-once

- 同一 session 至多一个 `DietRecord` 或一个 active `DietPhotoDraft`。
- 同一记录/草稿至多一个可见卡片。
- 重试不得改变图片 ordinal，也不得重复调用业务写入。

## Mobile

- 复数图片显示首图封面和数量；进入查看器后横向浏览。
- 单图卡片保持当前布局。
- 图片加载错误是卡片局部错误，不升级为整轮失败。
- 修正动作更新 `record_id` 对应记录。

## 安全与隐私

- 所有资产查询带 `user_id`。
- 签名 URL 不进入 DB、日志或分享正文。
- Trace 只记录 ID、阶段、时长和错误类型，不记录图片或识别正文。
