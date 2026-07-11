# 饮食打卡极致体验设计

## 架构决策

视觉模型输出保持“候选事实”：食物名、显示份量、单项营养和视觉置信度。后端清洗 UI/OCR 文案并生成 canonical meal description；若食物名命中 reviewed food table 的显式 `calibration_names`，且份量能确定为 g/kg/克/斤，则使用存在的表字段重新计算单项营养与总量，并附 `food_id` / `source`。表字段不完整时来源为 `mixed`，不能标成完全校准；没有被 curator 明确批准的泛化 canonical 或 alias 不自动命中。不满足条件时保留模型估算，但 UI 显示“图片估算”而不是伪装精确。Agent 的食物照片和默认纯图片提示即使由商业多模态模型处理，也必须先经过同一确定性清洗与校准链路；普通图片 fallback 不具备饮食写入资格。

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

每个状态只有一个主动作；离开页面时用用户隔离的 SecureStore 保存不含图片 Base64 和无界模型正文的紧凑快照，24 小时内进程重启可恢复，App 启动时清除过期快照。恢复缓存是辅助层，任何写入失败都不得阻断正式确认；展示恢复卡前必须用 owner-scoped status API 验证 token 仍为 pending，404/409/410 时删除本地残留。服务端图片草稿同样按 24 小时 TTL 回收，确认、取消和过期操作用行锁避免并发接管或删除；正式记录删除后的图片 tombstone 由每日任务按引用真值重试。所有“已记录”文案都必须有 `diet_record_id` 回执。

确认前或确认后修改食物身份时，未被用户重新填写的营养值必须置空，并清除旧 `food_id`、AI 原文、置信度和健康提示，来源改为 `user_corrected`；只改餐次等非营养字段不得误清 fiber 或 provenance。Mobile 负责交互层 dirty 判断，Backend 负责跨客户端的最终强制清理。

## 错误与降级

- 食物为空或仅 UI 文案：拒绝草稿，提示重拍餐食本身。
- 表匹配失败：保留模型估算和低/中置信标记，不阻塞用户修正。
- 识别超时：保留照片草稿，允许改用文字，不自动重试多次扣费。
- 确认超时：同一 idempotency key 查询/重试，不创建第二条记录。
- 图片 5 秒内未加载：切换为无照片指标卡继续生成；图片分享不可用时退回不含私有图片 URL、用户标识或健康详情的简短文本系统分享。分享 Promise 结束后释放临时 PNG。

## 测试

- 纯函数测试：quantity parser、canonical description、table calibration、totals。
- API 测试：recognize、create/confirm、owner isolation、idempotency、失败清理。
- Mobile 测试：状态机、分项 UI、低置信、修正、分享状态。
- 视觉测试：模拟器 390x844 与 430x932；分享图 1080x1440 像素检查。
