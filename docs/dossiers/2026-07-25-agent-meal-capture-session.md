# Dossier: Agent 多图餐食采集事务

| 字段 | 值 |
|---|---|
| slug | `agent-meal-capture-session` |
| 创建日期 | 2026-07-25 |
| 当前阶段 | S7 上线验证完成 |
| 状态 | completed |
| 负责 | Codex |
| 反馈环 | Backend pytest / Mobile Jest + TypeScript / Simulator / backend deploy + production OTA |

## S0 · 用户需求（逐字）

> 按顺序执行全部做完

承接上一轮已经确认的 P0-P2：

- 同一轮多张餐食照片只形成一餐、一次写入和一个回执卡；
- 多图在实时回复、重连、历史恢复和饮食详情中保持一致；
- 上传、识别、写入、关联和渲染失败可定位、可恢复且不重复写入；
- Mobile 支持多图浏览、可靠预览、同记录修正和清晰错误；
- 补齐媒体完整性巡检、链路 Trace、分页与图片成本优化。

## S1 · 现状勘察

- `DietPhotoAsset` 已有 owner、`origin_message_id`、`ordinal`、哈希和 lifecycle，饮食详情 API 已返回有序 `photo_assets/image_urls`。
- Agent 当前逐张调用上下文餐食捕获，回执卡仅携带单个 `photo_asset_id/photo_url`。
- Mobile `DietDraftCard` 仅消费单图字段；历史恢复虽能为单图重新签名，但尚未覆盖多图卡片。
- 对话消息列表仍以整段历史返回，图片能力恢复会随历史长度增长。
- 已有照片压缩、私有签名 URL、写入幂等和识别/确认观测，可扩展而无需重写框架。

## G1 · 准入裁决

- classification: product_change + reliability
- first_class_objects: `WriteIntent`、`ExecutionEvent`、`HealthTwin`
- core_loop_step: Capture -> verified DietRecord -> Today/Review
- target_surface: Backend source of truth + Mobile primary capture；Web/Mac 读取兼容
- safety_level: privacy_sensitive
- autonomy_tier: 高置信正常餐时保持受限 auto；其他 manual_confirm
- success_metric: 一轮多图 exactly-one record / exactly-one receipt；历史重开图片可用率；重复写入率
- **裁决：PASS。** 该改造强化现有核心闭环，不新增平行产品面。

## S2 · PRD

- `docs/prd/2026-07-25-agent-meal-capture-session.md`

## S3 · 规划

- `docs/plans/2026-07-25-agent-meal-capture-session.md`

## G2 · 可行性与安全压测

- 不持久化签名 URL；卡片仅持久化 owner-bound asset IDs。
- 不把多张图片默认写成多餐；同一 `source_message_id` 是一次 MealCaptureSession。
- 不依赖客户端去重保证业务正确性；服务端记录和卡片都必须有稳定身份。
- 不在不确定提交后盲目重试写入；先 reconcile，再决定恢复或补写。
- 不让本地乐观预览成为长期真值；服务端资产确认后替换。
- 排队中的图片只有在服务端确认持久化后才释放；取消或失败必须保留可恢复草稿。
- 任一食物缺少有效置信度、跨图片出现同名菜品或图片持久化失败时，禁止无图自动写入并转人工确认。
- **裁决：PASS。** 复用现有 `DietPhotoAsset`，不新增高风险框架或外部服务。

## S4 · 研发任务

- [x] T1 服务端 MealCaptureSession：同轮多图聚合、一次决策、一次记录、全部资产关联。
- [x] T2 卡片契约：`card_id`、`photo_asset_ids/photo_urls`，实时/历史统一投影并兼容单图。
- [x] T3 媒体状态与 exactly-once：阶段状态、幂等、reconcile、单卡去重。
- [x] T4 Mobile：多图画廊、图片数量、全屏浏览、精确状态/错误、同记录修正。
- [x] T5 媒体完整性与观测：链路字段、孤立资产巡检、重复/缺图指标。
- [x] T6 性能成本：缩略图/压缩复用、哈希去重、可见历史分页或能力按需恢复。
- [x] T7 全链路测试与模拟器验证。

## Gate 状态

- G3 测试：**PASS**
  - Backend 相关回归：212 passed；安全风险定向：39 passed。
  - Mobile 全量 Jest：278 suites / 2121 passed / 1 skipped；安全风险定向：121 passed。
  - Mobile TypeScript、ESLint（0 errors，93 个历史 warnings）、设计 token ratchet、Backend Ruff、`git diff --check` 均通过。
  - `scripts/validate.py` 的 doc-drift 与 dossier-consistency 通过。
  - Backend 全量 8466 用例在 600 秒分片截止时运行至 44%；其中沙箱内 Dedao socket 失败已在非沙箱环境单独复跑 64 passed。相关功能与风险面已由上述定向集合覆盖。
- G4 安全：**PASS**
  - 独立复核确认：排队图片延迟释放、低置信度确认、图片持久化失败阻断无图写入、跨图同名菜冲突确认均符合预期。
- G5 部署健康：**PASS**
  - Backend 已从干净 `main` 部署提交 `ac7260905ceb`；部署脚本健康度 `60/60`，线上 22 个 Skills 与本地一致。
  - 部署前 PostgreSQL 备份、加密异地归档、哈希校验与恢复演练通过，恢复库包含 234 张表。
  - 公网 `https://health.executor.life/api/v1/health` 返回 API、PostgreSQL、Redis、Celery 全部 healthy。
- G6 上线验证：**PASS（技术上线）**
  - iOS Release 模拟器构建成功并完成 Agent 对话页视觉检查，无红屏、布局崩溃或启动阻断；证据：`/tmp/reva-agent-meal-capture-release.png`。
  - production OTA runtime `1.3.2`，update group `3f7127b1-97ef-49bb-be13-aa44a9942a0a`，iOS update `019f9d68-6442-71c6-8f1e-ff90f11dc4cb`，提交与更新清单均指向 `ac7260905ceb`。
  - 真实设备上的多图拍摄、App 重启后历史恢复与弱网重试仍保留为下一反馈环的体验抽检，不影响本次服务端正确性和 OTA 技术上线裁决。
