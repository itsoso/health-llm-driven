# Chat Medical Exam Runtime Skill

**目标:** 让 Reva 对话页直接支持体检报告导入，并以动态 UI 卡片承接结果。

## 决策

采用产品运行时 skill，而不是把研发层 `product-pipeline` skill 搬进用户对话。

- 研发层 skill: 管需求、PRD、规划、测试、部署 Gate。
- Chat runtime skill: 管用户在对话里的确定性动作、写入权限、结果卡片和后续对话。

## Skill Contract

`medical_exam_import`

- 触发方式: 用户在 Chat 附件菜单显式点击“导入体检报告”。
- 写入范围: `medical_exam`。
- 自治等级: 用户显式动作后执行，不自动把普通图片写入健康档案。
- 执行器: 客户端确定性调用 `/medical-exams/import/pdf|image`。
- 结果: 插入 `medical_exam_import_result` 动态卡片。
- 安全提示: OCR/AI 解析结果需要复核后再用于判断。

## UX Flow

1. 用户进入 Chat，点附件菜单。
2. 选择“导入体检报告”。
3. 可从文件选 PDF/图片、拍摄报告、从相册选报告图片。
4. 导入成功后，对话流里出现结果卡片。
5. 卡片提供“查看体检记录”和“让 Reva 解读”两个动作。

## 后续演进

- 增加粘贴文字入口，复用 `/medical-exams/import/text`。
- 对普通图片 + “体检/化验”语义做软识别，但必须先弹确认卡再写库。
- 后端 SSE 支持下发同名卡片，让服务端工具调用和客户端 runtime skill 使用同一 UI 协议。
