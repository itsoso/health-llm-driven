# Dossier: 滚动 7 天健康运行时首个端到端切片

| 字段 | 值 |
|---|---|
| slug | `rolling-health-runtime-next-slice` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S6 部署前 |
| 状态 | shipping |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA |

## S0 · 用户需求(逐字)

> 按 PRD 完整执行，先对比 PRD/Plan/Code，选择最高优先级未完成切片，走 product-pipeline，直接实现、验证、发布，并回写计划状态。

- 谁用 / 解决什么 / 现在怎么绕过: Reva 的日常用户需要看到未来 7 天健康行动路线，而不是只能看到孤立的今日议程或功能列表。
- 锚点用户相关性: 35-55 慢病/代谢/恢复风险用户需要低摩擦执行，每天只有一个清晰下一步，同时能看到接下来几天复查、饮水、运动等行动。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/api/agenda.py`: `/agenda/today`、`/agenda/range` 和 `/agenda/complete` 已存在。
  - `backend/app/services/agenda_service.py`: `today`、`smart_today`、`range_view` 已能聚合协议、复查、trajectory context 和 verification window。
  - `mobile/services/agenda.ts`: Agenda/SmartAgenda service 已存在。
  - `mobile/app/agenda.tsx`: Agenda 页面已接入 Reva visual token 和 smart agenda panel。
- 缺什么:
  - 缺少 `mode=runtime` 的 7 天同构投影合同。
  - 缺少 item 级 `runtime_context`、`replan_reason` 和统一 safety boundary。
  - Mobile 缺少 runtime range service/hook 和可见入口。
- 硬约束 / 平台·安全边界:
  - 首刀不新增表、不做药物/剂量/临床自治、不绕过 `/agenda/complete`。
  - 默认 `regular` range 响应必须保持兼容。
  - 健康建议保持保守表述，runtime projection 只是行动编排和解释。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `HealthAgendaItem`, `ExecutionEvent`, `HealthTrajectory`, `SafetyGuardian`
- core_loop_step: 感知 -> 行动排序 -> 执行 -> 验证
- target_surface / safety_level / autonomy_tier: Backend + Mobile Agenda / medical_boundary / manual_confirm
- spec_required(§8.1): yes
- smallest_end_to_end_slice: `/agenda/range?mode=runtime` + Mobile Agenda “7天运行时”面板。
- stale_surface_to_remove: none in this slice
- 裁决: PASS。理由: 直接服务 PRD 的 Daily Artifact、HealthTrajectory、Agenda 收敛，不新增并列 daily loop。
- 用户确认: 用户要求直接实现。

## S2 · PRD

- 链接: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
- 引用的权威能力: Daily Artifact、HealthTrajectory、Health Agenda、Anti-Habituation OS。
- 边界(不做): 不做新 ML model、不做 autonomous write、不做 IoT control、不做临床预测 dashboard。
- 验收 Gate: API 合同测试、Mobile service 测试、Mobile 类型检查、部署后 smoke。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 分阶段 + 反馈环路由: 后端 deploy + mobile OTA。
- 长杆 / spike: DataConnection/Consent/Provenance 仍是后续 A 切片；本次选择 B 的最小 runtime projection。

## G2 · 可行性 + 安全压测

- 评审方式: Codex repo-grounded challenge + project product-pipeline。
- 硬阻断(已焊进规划): 不写真实记录、不提升自治等级、不生成临床结论、不破坏 default range 合同。
- 待拍板分叉: none，本次为 additive read path。
- 裁决: PASS。

## S4 · 研发任务分解

- 跨端 API 契约: `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`
- 任务表:
  - [x] T1 后端 runtime mode 合同测试。
  - [x] T2 后端 `runtime_range_view` 和 API mode。
  - [x] T3 Mobile runtime range service test。
  - [x] T4 Mobile service/hook/Agenda panel。
  - [x] T5 文档和计划状态回写。
- 并发检查: 从 `origin/main` 新建隔离 worktree；未触碰主工作区并发 WIP。

## S5 · 实现

- 分支: `codex/rolling-runtime-next-slice`
- 实现文件:
  - `backend/app/api/agenda.py`
  - `backend/app/services/agenda_service.py`
  - `backend/tests/test_agenda_range_complete.py`
  - `mobile/services/agenda.ts`
  - `mobile/hooks/useAgenda.ts`
  - `mobile/app/agenda.tsx`
  - `mobile/services/__tests__/agenda.test.ts`

## G3 · 测试闸

- 后端合同测试: `9 passed`
- Mobile service Jest: `7 passed`
- Backend compileall: passed
- Mobile TypeScript: passed
- Mobile changed-file ESLint: 0 errors；测试文件保留既有 `jest.mock` import-order warning。
- Mobile full lint: blocked by pre-existing unrelated hook-rule errors in `app/consultations.tsx` and `app/monthly-reports.tsx`。
- 裁决: GO。相关新增代码测试通过；全量 lint 红为既有无关问题，未扩大。

## G4 · 安全闸

- 触发: medical_boundary read projection。
- 评审: additive read path review。
- 裁决: GO。原因: 不新增写路径、不改变药物/补剂/复查完成规则、不绕过 manual_confirm；runtime context 固定安全边界。

## S6 · 部署

- 路由: backend deploy + mobile OTA。
- 部署 SHA / 回滚点: 待提交后补。

## G5 · 部署健康闸

- 健康分: 待部署后补。
- prod smoke: 待部署后补。
- 裁决: 待执行。

## S7 · 上线验证

- 真实路径验证: 待部署后补。

## G6 · 验证闸(人在环)

- 需求在 prod 对 anchor 用户真成立: 待用户真机确认。

## S8 · 沉淀

- 文档同步: 本 Dossier + active spec + plan 状态。
- 状态: 待 shipped。
