# Dossier: Mobile 今日行动管理闭环

| 字段 | 值 |
|---|---|
| slug | `mobile-today-actions-management` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | S5 验证 |
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

- [x] T1 动态卡片路由改为 `/agenda`
- [x] T2 今日事项分组与文案纯函数
- [x] T3 完成/跳过写回与缓存刷新
- [x] T4 今日行动管理页面与返回闭环
- [ ] T5 模拟器验证、文档、提交、OTA

## G3 · 测试闸

- PASS: 后端动态卡片与今日视图回归 `44 passed`。
- PASS: Mobile 今日行动、写回 Hook、Agenda service 和动态卡片注册回归 `81 passed`。
- PASS: `/agenda` 页面补充双行提交锁定验证，页面专项 `6 passed`。
- PASS: `npx tsc --noEmit`。
- PASS: 本批文件 ESLint 无错误。
- PASS: `npm run design:check`，设计 token 未新增漂移。
- PASS: `python3 scripts/check_doc_drift.py`，代码派生系统地图一致。
- 模拟器旧壳缺少主干新增的 `ExpoVideo` 原生模块，热加载无法作为本批视觉证据；T5 将从当前提交重建模拟器壳后复验。
- **裁决：PASS（自动化），模拟器视觉仍在执行。**

## G4 · 安全闸

- 今日列表只消费当前用户鉴权后的 `/agenda/today`，不新增跨用户查询。
- 完成和跳过继续复用 `/agenda/complete` 的显式人工确认；跳过必须选择原因。
- “稍后”只改变当前会话排序，并明确提示未写成完成，不伪造服务端回执。
- 写入失败保持原状态并显示错误，不做乐观成功声明。
- 未修改药物剂量、诊断逻辑、安全阈值或推送隐私出口。
- **裁决：GO。**

## S6-S8

- 待实现后回写。
