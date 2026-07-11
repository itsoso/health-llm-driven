# Dossier: 饮食打卡极致体验

| 字段 | 值 |
|---|---|
| slug | `diet-capture-excellence` |
| 创建日期 | 2026-07-11 |
| 当前阶段 | S5 实现 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Backend pytest / Mobile Jest + TypeScript / Simulator / backend deploy / EAS TestFlight |

## Correct Course

- [ ] Correction Block

## S0 · 用户需求（逐字）

> 聚焦睡眠、运动和饮食三个主要功能。先把饮食打卡做到极致，准确性、性能和交互体验做到最好，并且可以分享小红书和微信，截屏，要有高级感，让95和00后人群感觉用这个App很有面子。

- 谁用 / 解决什么 / 现在怎么绕过：高频拍照、语音或文字记餐的 Mobile 用户；当前需要等待黑盒识别、手动核对一段合并文字，再以普通文本分享。
- 锚点用户相关性：饮食是每天发生多次的 Capture 闭环，也是睡眠、运动和代谢分析的数据基础。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/app/diet.tsx` 已有拍照 -> 识别 -> 草稿 -> 人工确认 -> 写入状态流。
  - `backend/app/services/ai/food_recognition.py` 已输出结构化食物、份量、宏量营养和视觉置信度。
  - `backend/app/services/food_nutrition_lookup.py` 与 reviewed food table 已用于语音和聊天草稿，但未接视觉识别。
  - `backend/app/api/diet.py` 已有 owner-scoped 私有图片、写入幂等键和 fail-closed 内容防护。
  - `mobile/utils/share.ts` 已有系统分享和微信可接受的 Web 分享回退。
- 已证实缺口：
  - 视觉结果直接信任模型营养值，明确克数没有用 reviewed food table 校准。
  - 视觉 `meal_description` 可与清洗后的 foods 不一致；fiber 没有完整贯通响应。
  - 确认卡只显示合并描述，未展开每个食物、份量、来源和低置信度。
  - 照片 base64 在识别与确认写入间重复上传，且草稿未具备服务端可恢复身份。
  - 近 30 天生产聚合中饮食记录有数据，但 `ai_recognized` / `image_url` 均无有效样本，食物识别 caller 也无可用时延样本；主入口可观测闭环缺失。
  - 现有分享是文本/链接，没有适配小红书 3:4 与微信分享的图片卡。
- 硬约束：营养是估算，不宣称医学精确；确认前不写 DietRecord；图片 owner 隔离；不引微信私有 SDK；失败必须可见且可重试。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects：`ExecutionEvent`、`WriteIntent`、`HealthTwin`。
- core_loop_step：Capture -> 确认写入 -> Today/Review -> 分享反馈。
- target_surface / safety_level / autonomy_tier：Mobile + Diet API / privacy_sensitive / manual_confirm。
- spec_required：是；改变用户可见识别契约、健康写入数据来源和图片分享行为。
- smallest_end_to_end_slice：一张餐食照片得到可解释草稿，明确克数由营养表校准，用户确认后只写一次。
- stale_surface_to_remove：黑盒合并描述、无来源的伪精确营养、仅文本分享。
- **裁决：PASS**。用户已明确要求按优先级持续直接实施。

## S2 · PRD

- 链接：`docs/prd/2026-07-11-diet-capture-excellence.md`
- 引用权威：R5 Food Voice Capture、R10 Mobile 主体验、R4 确定性写入边界。
- 边界：不做诊断、处方、自动写入、食物秤级精度承诺或微信私有 SDK。
- 未决问题：无阻塞问题；外部食物数据库和分享模版 A/B 属后续增量。

## S3 · 规划

- 设计：`docs/plans/2026-07-11-diet-capture-excellence-design.md`
- 实施：`docs/plans/2026-07-11-diet-capture-excellence.md`
- Feature Spec：`docs/specs/active/2026-07-11-diet-capture-excellence.md`
- 顺序：P0 准确性/可纠错 -> P0.5 单次上传/幂等 -> P1 图片分享 -> 真机/生产指标。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + 现有 DietRecord / private upload / system share contract 对照。
- 已焊入限制：只有明确重量单位才允许表值覆盖；无确定份量保留估算并降置信；分享必须用户显式触发；未确认草稿不可分享为“已记录”。
- 待拍板分叉：无。
- **裁决：PASS**。定义环文档无待澄清项，进入 P0。

## S4 · 研发任务分解

- [x] T1 视觉结果清洗、份量解析、营养表校准与 provenance（backend deploy）
- [x] T2 Mobile 分项确认卡、低置信提示和修正入口（OTA）
- [x] T3 服务端照片草稿身份、单次大载荷和写入幂等（backend deploy + OTA）
- [x] T4 3:4 高质感饮食分享卡、图片生成和系统分享（EAS）
- [x] T5 识别/确认/纠错/分享埋点与 p50/p95 看板（backend deploy + OTA）
- [ ] T6 模拟器视觉、真机微信/小红书、生产数据闭环验收
- 并发检查：2026-07-11 `origin/main` 与当前干净集成 worktree 一致；原始用户工作区不纳入暂存。

## S5 · 实现

- T1：明确克重且命中审核食物表时覆盖模型营养值；无法换算克重时保留视觉估算并明确来源；Agent 照片入口复用同一校准，去掉重复视觉调用。
- T2：确认卡展示逐项食物、份量、热量、置信度、营养表/视觉估算来源，低置信或未校准份量提示核对。
- T3：识别成功返回 owner-scoped `photo_draft_token`，确认不再重复上传 Base64；令牌强制幂等、跨用户不可认领、取消立即清理、24 小时后由既有每日清理任务回收。
- T4：新增固定 3:4 饮食故事卡，捕获为 1080x1440 PNG，并通过系统分享面板投递微信/小红书；分享图不含用户名或其他健康数据。
- T5：新增无正文的识别/确认/分享终态事件，观测聚合直接输出各阶段样本数、失败数、p50、p95；识别响应另带 vision/calibration/photo_draft/total 分段耗时。

## G3 · 测试闸

- focused backend regression：120 passed。
- focused Mobile regression：37 passed；TypeScript check passed。
- Dossier consistency、OpenAPI type generation、system-map generation、doc-drift checks passed。
- 待执行：全量 backend/Mobile、模拟器截图、真机微信/小红书分享与生产验证。

## G4 · 安全闸

- 触发：健康数据写入、AI 营养估算、私有图片和社交分享。
- 待复审。

## S6 · 部署

- 路由：backend deploy -> type sync -> Mobile OTA；T4 native dependency 走 TestFlight。

## G5 · 部署健康闸

- 待执行。

## S7 · 上线验证

- 待执行。

## G6 · 验证闸

- 待真机确认。

## S8 · 沉淀

- 待完成。
