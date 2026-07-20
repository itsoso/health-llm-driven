# Dossier: Mobile 今日行动管理闭环

| 字段 | 值 |
|---|---|
| slug | `mobile-today-actions-management` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | S4 分解 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Mobile Jest / iOS Simulator / production OTA |

## S0 · 用户需求（逐字）

> 点击管理活动会跳转到第二张图片，但是无法跳回来，另外列表也有问题，无法管理，重新梳理这个链路，优化。

- 用户从小巴的今日行动卡进入管理页，需要处理今天要做的事并可靠返回对话。
- 当前只能进入全量行动/告警列表，无法形成完成闭环。

## S1 · Discovery

- 后端 `backend/app/services/inline_cards.py` 将今日管理入口写成 `/alerts`。
- `/alerts` 位于隐藏 Tab，`headerShown=false`，页面无返回入口。
- `mobile/app/(tabs)/alerts.tsx` 查询全部 active action cards 和 safety alerts，不是今日议程。
- `mobile/app/agenda.tsx` 已有 `/agenda/today` 和 `/agenda/complete` 能力，但页面信息重复、缺少返回和完整管理操作。

## G1 · RequirementAdmission

- classification: `bugfix + product_change`
- first_class_objects: `LeverageAction`, `AgendaItem`, `EvidenceEvent`
- core_loop_step: `recommend -> act -> measure`
- target_surface: `Mobile`
- source_of_truth: `/agenda/today`, `/agenda/complete`
- safety_level: `medical_boundary`
- autonomy_tier: `manual_confirm`
- smallest_end_to_end_slice: 小巴卡片进入今日议程，完成/跳过写回，返回小巴并刷新。
- stale_surface_to_remove: 今日管理不再进入 `/alerts`；安全告警页继续独立保留。
- **裁决：PASS**。用户已确认方案 A。

## S2/S3 · 设计与规划

- 设计：`docs/plans/2026-07-20-mobile-today-actions-management-design.md`
- 实施：`docs/plans/2026-07-20-mobile-today-actions-management.md`
- 非目标：不新增自动执行、不修改药物剂量、不重做语音输入、不删除安全告警页。
- 未决问题：无。

## G2 · 可行性与安全压测

- 复用已有接口，无新 schema、无新原生能力，Mobile 可 OTA。
- 所有健康写入保持用户确认；失败不显示成功。
- **裁决：PASS**。用户选择方案 A。

## S4 · 研发任务

- [ ] T1 动态卡片路由改为 `/agenda`
- [ ] T2 今日事项分组与文案纯函数
- [ ] T3 完成/跳过写回与缓存刷新
- [ ] T4 今日行动管理页面与返回闭环
- [ ] T5 模拟器验证、文档、提交、OTA

## G3 · 测试闸

- 待执行。

## G4 · 安全闸

- 触及既有健康写路径，但不改变服务端权限或自治等级；待实现后复核。

## S6-S8

- 待实现后回写。
