# 多端体检记录导入设计

**目标:** 在 Web、Mac、Mobile 三端统一提供体检/化验报告导入能力，让报告能进入个人健康基线，并可被 Reva 后续解读、复核和编排使用。

**产品原则:**
- 体检导入是一级健康档案能力，不是某个聊天附件能力。
- 后端以 `/medical-exams/import/*` 为唯一 canonical 写入路径，三端不再各自维护独立报告系统。
- 导入成功不等于健康结论成立。所有 OCR/AI 解析结果都必须提示用户复核后再用于判断。
- 导入后的下一步必须清晰：查看体检记录、复核异常项、让 Reva 解读。

## 现状判断

后端已经具备 PDF、图片、文本、CSV、JSON 导入能力，并会写入 `MedicalExam`、`MedicalExamItem` 和 `MedicalIndicator`。Mobile 已有 `/import` 导入页和上传 service，但体检记录页入口不明显；Web 体检页已有 PDF 上传预览，但没有通用图片/文本导入体验；Mac 已有 `LabUploadClient` 和 RecordHub 导入卡片，但呈现仍偏“Lab upload”而不是“体检报告导入”。

## 方案

采用“统一后端契约 + 三端薄客户端”的方案：

1. 保持后端 API 不变，避免本轮引入新的 schema、任务队列和类型生成风险。
2. 在客户端增加小型导入结果归一化层，把 PDF、图片、文本不同响应统一成 `examId/itemsCount/abnormalCount/reviewRequired/source`。
3. Web 体检页提供“导入体检报告”面板，支持 PDF、图片和文本兜底。PDF 继续保留预览，图片和文本直接导入。
4. Mobile 体检记录页增加显式“导入报告”入口，跳转 `/import?focus=medical`。从该入口选择 PDF 时直接按体检报告导入，不再询问“基因/体检”。
5. Mac RecordHub 的导入卡片改为“导入体检报告”，成功后显示标准摘要、复核提示，并可带上下文打开 Agent。

## 安全和隐私

- 三端必须使用已登录用户的现有鉴权，不传 `user_id` 查询参数作为归属依据。
- 文件上传只走现有受保护 API，不在客户端保存原文件。
- UI 文案明确“解析结果需要复核”，避免把 OCR 结果包装成医疗诊断。
- 本轮不新增药物、诊断或处方建议行为。

## 验收

- Web: 体检页能导入 PDF、图片、文本，并在成功后刷新体检记录列表。
- Mobile: `/medical-exams` 有清晰导入入口；从该入口进入 `/import?focus=medical` 后，PDF 直接进入体检导入路径。
- Mac: RecordHub 显示体检报告导入卡片；成功结果有摘要、复核提示和 Ask Agent 动作。
- 三端的导入结果都能表达“指标数、异常数、复核要求、下一步”。
