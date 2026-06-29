# Dossier: Mobile 阿衡人格文案收敛

| 字段 | 值 |
|---|---|
| slug | `mobile-aheng-persona-copy` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest / static scan |

## S0 · 用户需求(逐字)

> 按照计划直接开干

本切片承接本周计划中的 P1:Mobile Daily Artifact / 健康日序主线。P0 已把 App 名和发布包锁定为 `阿衡`;下一步要避免用户在首屏、onboarding、Chat 动态卡片和通用权限文案中继续看到旧人格 `Reva` / `复元` / `健康助理`。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/components/home/DailyArtifactCard.tsx`:Daily Artifact 已有 top action、证据、完成/跳过/询问入口。
  - `mobile/components/home/RevaTryEntryCard.tsx`:首页到 `/reva-onboarding?mode=demo` 的试用入口。
  - `mobile/components/reva/*`:试用/onboarding/hub/agent 体验。
  - `mobile/components/chat/cards/MedicalExamImportResultCard.tsx`:体检导入后的动态卡片。
- 缺口:
  - 用户可见文案仍出现 `询问 Reva`、`试试新版复元`、`进入复元`、`让 Reva 解读`、`健康助理` 等旧称。
- 硬边界:
  - 不重命名 `Reva*` 组件/类型/route/设计 token。
  - Rokid 专页暂不改,避免外设 SDK 语义和大测试面混入本切片。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`HealthAgendaItem`, `ExecutionEvent`, `ProvenanceRecord`
- core_loop_step:Daily Artifact -> ask/complete/skip -> onboarding/demo -> Chat dynamic card。
- target_surface / safety_level / autonomy_tier:Mobile / low / none。
- spec_required(§8.1):否,只改用户可见文案和测试,不新增健康行为。
- smallest_end_to_end_slice:首屏 ask action、试用入口、onboarding、体检导入动态卡片和通用权限/分享/隐私文案统一为 `阿衡`。
- stale_surface_to_remove:旧称不再进入通用用户可见 surface。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:Daily Artifact、Chat + 动态 UI 卡片、5 分钟 on-ramp、App Store 可用版。
- 不做:不改诊断/处方/剂量边界;不改 Rokid 外设 surface;不改工程符号。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-mobile-aheng-persona-copy-plan.md`
- 执行顺序:
  1. TDD 钉住首页 Daily Artifact 和试用入口预期。
  2. TDD 钉住 onboarding 进入按钮。
  3. TDD 钉住体检导入动态卡片 action。
  4. 修改实现和通用用户可见文案。
  5. 静态扫描目标旧称。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 技术符号大改会破坏 import/route/test;本批禁止。
  - Rokid 专页有大量设备联调文案和测试断言;本批不混入。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 更新失败测试:Daily Artifact ask action、试用入口、onboarding、体检导入动态卡片。
- [x] T2 修改 Mobile 用户可见文案为 `阿衡`。
- [x] T3 跑聚焦 Jest。
- [x] T4 静态扫描目标旧称。
- [x] T5 回写 plan / dossier。

## S5 · 实现

- 修改:
  - `mobile/components/home/DailyArtifactCard.tsx`
  - `mobile/components/home/RevaTryEntryCard.tsx`
  - `mobile/components/reva/RevaKit.tsx`
  - `mobile/components/reva/RevaAgentView.tsx`
  - `mobile/components/reva/RevaScreens.tsx`
  - `mobile/components/reva/useRevaData.ts`
  - `mobile/components/reva/HealthOsScreens.tsx`
  - `mobile/components/chat/cards/MedicalExamImportResultCard.tsx`
  - `mobile/components/chat/ChatInputBar.tsx`
  - `mobile/app/voice-chat.tsx`
  - `mobile/app/family.tsx`
  - `mobile/app/workout-detail.tsx`
  - `mobile/app/import.tsx`
  - `mobile/app/voice-style.tsx`
  - `mobile/app/shared/[shareToken].tsx`
  - `mobile/app/privacy-policy.tsx`
- 测试:
  - `mobile/components/home/__tests__/DailyArtifactCard.test.tsx`
  - `mobile/components/home/__tests__/RevaTryEntryCard.test.tsx`
  - `mobile/app/__tests__/reva-onboarding.test.tsx`
  - `mobile/components/chat/cards/__tests__/MedicalExamImportResultCard.test.tsx`

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/home/__tests__/DailyArtifactCard.test.tsx components/home/__tests__/RevaTryEntryCard.test.tsx app/__tests__/reva-onboarding.test.tsx --runInBand`
  - 预期失败:实现仍是 `询问 Reva`、`试试新版复元`、`进入复元`。
- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/chat/cards/__tests__/MedicalExamImportResultCard.test.tsx --runInBand`
  - 预期失败:实现仍是 `让 Reva 解读这次导入`。
- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/chat/cards/__tests__/MedicalExamImportResultCard.test.tsx components/home/__tests__/DailyArtifactCard.test.tsx components/home/__tests__/RevaTryEntryCard.test.tsx app/__tests__/reva-onboarding.test.tsx --runInBand`
  - 4 suites passed,11 tests passed。
- PASS:目标旧称扫描无命中。

## G4 · 安全闸

- 触发?:未改健康建议生成、写入行为、权限申请逻辑、认证、用药、剂量、诊断边界。
- 隐私政策仍明确不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。
- 裁决:GO。

## S6 · 部署

- 本批未部署。属于 Mobile JS/TS/UI 文案变更,后续可随二维码包或 OTA 一起发布;若本周发版,默认二维码方式。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 本地静态验证:通用用户可见目标旧称不再命中。
- 待后续真机/模拟器走查:确认首页 -> 试试阿衡 -> onboarding -> hub -> Chat 动态卡片视觉无截断。

## G6 · 验证闸(人在环)

- App Store 上线仍受最终截图、demo account、ASC credentials 阻塞;本切片不改变该状态。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续可单独开 `rokid-aheng-user-visible-copy` 切片,处理 Rokid 专页中的旧称和相关测试。
