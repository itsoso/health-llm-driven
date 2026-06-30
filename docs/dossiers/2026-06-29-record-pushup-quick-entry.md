# Dossier: 俯卧撑快速记录入口

| 字段 | 值 |
|---|---|
| slug | `record-pushup-quick-entry` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest |

## S0 · 用户需求(逐字)

> 要具备快速记录的能力，记录饮食，记录俯卧撑等运动情况

本切片承接本周计划 P1/P3 中的快速记录主路径。饮食和体重腰围已经在记录页高频入口,但俯卧撑在页面下方力量训练卡或 Rokid 专页中,不够低摩擦。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/app/(tabs)/record.tsx`:高频记录区、更多记录区、StrengthCard。
  - `mobile/components/dashboard/StrengthCard.tsx`:俯卧撑等力量动作的快速加量。
  - `mobile/app/rokid-pushup-coach.tsx`:俯卧撑计数和保存入口,本地计数可用。
  - `mobile/app/(tabs)/__tests__/recordEntry.test.tsx`:记录页入口测试。
- 缺口:
  - 记录页顶部没有直接“俯卧撑”入口。
- 硬边界:
  - 不改 exercise 写入 schema。
  - 不要求 Rokid 眼镜可用;只是把已有本地/眼镜计数入口提到高频区。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`ExecutionEvent`, `HealthAgendaItem`, `ProvenanceRecord`
- core_loop_step:快速记录 -> 今日执行数据 -> 后续建议/复盘。
- target_surface / safety_level / autonomy_tier:Mobile / low / none。
- spec_required(§8.1):否,复用既有记录入口,不新增健康建议或写入模型。
- smallest_end_to_end_slice:高频记录区新增 `俯卧撑` 并跳转 `/rokid-pushup-coach`。
- stale_surface_to_remove:无。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:低摩擦记录、运动记录、Mobile 核心用户动线。
- 不做:不改运动分析、不改眼镜 SDK、不改后端 schema。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-record-pushup-quick-entry-plan.md`
- 任务:
  1. TDD:测试高频记录区必须出现 `俯卧撑`。
  2. TDD:测试点击后进入 `/rokid-pushup-coach`。
  3. 实现入口。
  4. 验证记录页测试。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 直接写 exercise API 会扩大安全/失败面;本批只路由到已有计数页。
  - `更多记录 -> 运动` 应继续保留为历史记录入口。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 更新 `recordEntry` 测试。
- [x] T2 在 `highFrequencyRecords` 增加 `俯卧撑`。
- [x] T3 跑聚焦测试。
- [x] T4 回写 plan / dossier。

## S5 · 实现

- `mobile/app/(tabs)/record.tsx`:新增 `pushup` quick record entry。
- `mobile/app/(tabs)/__tests__/recordEntry.test.tsx`:断言入口和路由。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/recordEntry.test.tsx' --runInBand`
  - 预期失败:找不到 `俯卧撑`。
- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/recordEntry.test.tsx' --runInBand`
  - 1 suite passed,3 tests passed。

## G4 · 安全闸

- 触发?:未改写入 API、用药、诊断、剂量、隐私或认证。
- 裁决:GO。

## S6 · 部署

- 本批未部署。属于 Mobile JS/UI 入口变更,后续可随二维码包或 OTA 一起发布。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 待后续真机/模拟器走查:记录页顶部高频区点击 `俯卧撑`,确认进入计数页并可保存本组。

## G6 · 验证闸(人在环)

- 无新增人审阻塞。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续可把常用力量动作的最近使用频率纳入高频区排序,但本批先固定用户明确提到的俯卧撑。
