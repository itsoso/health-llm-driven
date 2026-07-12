# 饮食打卡极致体验设计

## 架构决策

视觉模型输出保持“候选事实”：食物名、显示份量、单项营养、身份置信度和份量置信度。后端把模型输出当作不可信输入，白名单清洗 UI/OCR 文案、药物、补剂、重复项、异常数值和无界字段，并生成 canonical meal description；若食物名命中 reviewed food table 的显式 `calibration_names`，且视觉份量能换算为 g/kg/克/斤，则使用存在的表字段重新计算单项营养与总量，并附 `food_id` / `source`。表字段不完整时来源为 `mixed`，不能标成完全校准；没有被 curator 明确批准的泛化 canonical 或 alias 不自动命中。营养表只校准单位重量营养密度，不证明照片份量准确，因此所有照片克重仍保留 `portion_basis=vision_estimate`，UI 显示“表值 × 估算份量”；无法可靠判断份量时为 `unknown`，不能编造精确值。Agent 的食物照片和默认纯图片提示即使由商业多模态模型处理，也必须先经过同一确定性清洗与校准链路；普通图片 fallback 不具备饮食写入资格。

Mobile 把草稿呈现为分项清单，不再只显示一句合并描述。相机和单图相册入口只负责取得图片，之后共用同一套压缩、识别、草稿恢复和人工确认管线；纯图片系统选择器不预请求全图库读取权限，只接收用户显式选中的一张图片。后端结构化清洗后的照片候选不再被 Mobile 的通用文字启发式二次分类，文字、语音和外部草稿仍保留本地防护。主按钮仍是“确认记录”，修正进入已有 MealForm；确认前不存在正式 DietRecord。图片先落成 owner-scoped server draft，返回短期 draft token；确认只发送 token 和结构化数据，从而避免同一 base64 上传两次，并通过 Idempotency-Key 防止崩溃重试重复写。

分享使用独立 `DietShareCard`，尺寸锁定 3:4，包含用户主动选择的餐食照片、餐次、食物、宏量营养和一句克制总结。`react-native-view-shot` 生成本地 PNG，再走系统 share sheet，覆盖微信和小红书而不绑定私有 SDK。分享只允许已确认记录；默认不显示姓名、体重、疾病、基因或药物。

## 状态机

```text
idle -> capturing|selecting -> preparing -> recognizing -> draft_ready
draft_ready -> correcting -> draft_ready
draft_ready -> confirming -> persisted
capturing/selecting/preparing/recognizing/confirming -> failed -> retryable state
persisted -> rendering_share -> share_ready -> shared|cancelled
```

每个状态只有一个主动作；除 `idle` 外隐藏新增 FAB，避免遮挡确认卡或并发启动第二次取图。离开页面时用用户隔离的 SecureStore 保存不含图片 Base64 和无界模型正文的紧凑快照，24 小时内进程重启可恢复，App 启动时清除过期快照。恢复缓存是辅助层，任何写入失败都不得阻断正式确认；展示恢复卡前必须用 owner-scoped status API 验证 token 仍为 pending，404/409/410 时删除本地残留。服务端图片草稿同样按 24 小时 TTL 回收，确认、取消和过期操作用行锁避免并发接管或删除；正式记录删除后的图片 tombstone 由每日任务按引用真值重试。所有“已记录”文案都必须有 `diet_record_id` 回执。

确认前或确认后修改食物身份时，未被用户重新填写的营养值必须置空，并清除旧 `food_id`、AI 原文、置信度和健康提示，来源改为 `user_corrected`；只改餐次等非营养字段不得误清 fiber 或 provenance。Mobile 负责交互层 dirty 判断，Backend 负责跨客户端的最终强制清理。

## 错误与降级

- 食物为空或仅 UI 文案：拒绝草稿，提示重拍餐食本身。
- 相机不可用或已有清晰餐食照片：允许从相册选择一张，继续同一识别状态机。
- 模型输出药物、补剂、重复项或异常营养值：在草稿前剔除或置为未知；识别正文和食物名不得进入服务日志。
- 表匹配失败：保留模型估算和低/中置信标记，不阻塞用户修正。
- 识别超时或限流：保留真实可操作错误，不得误报成“图片没有食物”；允许改用文字，不自动重试多次扣费。
- 确认超时：同一 idempotency key 查询/重试，不创建第二条记录。
- 图片 5 秒内未加载：切换为无照片指标卡继续生成；图片分享不可用时退回不含私有图片 URL、用户标识或健康详情的简短文本系统分享。分享 Promise 结束后释放临时 PNG。

## 测试

- 纯函数测试：quantity parser、canonical description、table calibration、portion provenance、非食物拒绝、异常值、去重上限和 totals。
- API 测试：recognize、create/confirm、owner isolation、idempotency、失败清理。
- Mobile 测试：状态机、分项 UI、低置信、修正、分享状态。
- 视觉测试：模拟器 390x844 与 430x932；分享图 1080x1440 像素检查。
