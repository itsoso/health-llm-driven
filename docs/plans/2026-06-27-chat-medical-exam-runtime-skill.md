# Chat Medical Exam Runtime Skill

**目标:** 让 Reva 对话页在 Web、Mobile、Mac 三端直接支持体检报告导入，并以动态 UI 卡片或对话上下文承接结果。

## 决策

采用产品运行时 skill，而不是把研发层 `product-pipeline` skill 搬进用户对话。

- 研发层 skill: 管需求、PRD、规划、测试、部署 Gate。
- Chat runtime skill: 管用户在对话里的确定性动作、写入权限、结果卡片和后续对话。

## Skill Contract

`medical_exam_import`

- 触发方式:
  - Web: 用户在 `/ai-assistant` composer 点击体检报告文件按钮，选择 PDF/图片。
  - Mobile: 用户在 Chat 附件菜单显式点击“导入体检报告”，选择 PDF/图片、拍摄报告或相册图片。
  - Mac: 用户在 Chat 附件、拖拽或粘贴图片路径加入体检/化验文件，发送前由 `AgentChatViewModel` 导入。
- 写入范围: `medical_exam`。
- 自治等级: 用户显式动作后执行；普通图片只有在用户选择体检导入入口或作为 medical attachment 发送时才写入健康档案。
- 执行器: 客户端确定性调用 `/medical-exams/import/pdf|image`。
- 结果:
  - Web/Mobile: 插入 `medical_exam_import_result` 动态卡片，并预置/提供“让 Reva 解读”的后续 prompt。
  - Mac: 写入 `lab_report_imports` extra context，随用户消息进入 Agent 流，并在 RecordHub 显示复核提示。
- 安全提示: OCR/AI 解析结果需要复核后再用于判断。

## UX Flow

1. 用户进入 Chat。
2. 选择体检报告导入入口或添加体检/化验附件。
3. 可从文件选 PDF/图片；Mobile 额外支持拍摄报告、从相册选报告图片。
4. 导入成功后，Web/Mobile 对话流出现结果卡片；Mac 在发送前把导入结果写入 Agent context。
5. 用户继续发起解读，Agent 基于刚导入的 exam_id、指标数、异常数和复核边界给出解释与行动建议。

## 后续演进

- 增加粘贴文字入口，复用 `/medical-exams/import/text`。
- 对普通图片 + “体检/化验”语义做软识别，但必须先弹确认卡再写库。
- 后端 SSE 支持下发同名卡片，让服务端工具调用和客户端 runtime skill 使用同一 UI 协议。
- Mac Chat 增加显式“体检报告”附件快捷项和导入完成提示卡，减少用户对通用 paperclip 的理解成本。
