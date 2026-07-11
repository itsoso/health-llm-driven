# 饮食打卡极致体验设计

## 架构决策

视觉模型输出保持“候选事实”：食物名、显示份量、单项营养和视觉置信度。后端清洗 UI/OCR 文案并生成 canonical meal description；若食物名命中 reviewed food table，且份量能确定为 g/kg/克/斤，则使用表值重新计算单项营养与总量，并附 `food_id` / `source`。不满足条件时保留模型估算，但 UI 显示“图片估算”而不是伪装精确。

Mobile 把草稿呈现为分项清单，不再只显示一句合并描述。主按钮仍是“确认记录”，修正进入已有 MealForm；确认前不存在正式 DietRecord。下一阶段把图片先落成 owner-scoped server draft，返回短期 draft token；确认只发送 token 和结构化数据，从而避免同一 base64 上传两次，并通过 Idempotency-Key 防止崩溃重试重复写。

分享使用独立 `DietShareCard`，尺寸锁定 3:4，包含用户主动选择的餐食照片、餐次、食物、宏量营养和一句克制总结。`react-native-view-shot` 生成本地 PNG，再走系统 share sheet，覆盖微信和小红书而不绑定私有 SDK。分享只允许已确认记录；默认不显示姓名、体重、疾病、基因或药物。

## 状态机

```text
idle -> capturing -> recognizing -> draft_ready
draft_ready -> correcting -> draft_ready
draft_ready -> confirming -> persisted
capturing/recognizing/confirming -> failed -> retryable state
persisted -> rendering_share -> share_ready -> shared|cancelled
```

每个状态只有一个主动作；离开页面时本地草稿可恢复，服务端图片草稿按 TTL 回收。所有“已记录”文案都必须有 `diet_record_id` 回执。

## 错误与降级

- 食物为空或仅 UI 文案：拒绝草稿，提示重拍餐食本身。
- 表匹配失败：保留模型估算和低/中置信标记，不阻塞用户修正。
- 识别超时：保留照片草稿，允许改用文字，不自动重试多次扣费。
- 确认超时：同一 idempotency key 查询/重试，不创建第二条记录。
- 图片分享不可用：退回现有文本 + Web share URL，并明确告知。

## 测试

- 纯函数测试：quantity parser、canonical description、table calibration、totals。
- API 测试：recognize、create/confirm、owner isolation、idempotency、失败清理。
- Mobile 测试：状态机、分项 UI、低置信、修正、分享状态。
- 视觉测试：模拟器 390x844 与 430x932；分享图 1080x1440 像素检查。
