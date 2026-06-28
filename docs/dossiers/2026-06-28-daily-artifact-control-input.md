# Dossier: Daily Artifact 控制输入语义展示

| 字段 | 值 |
|---|---|
| slug | `daily-artifact-control-input` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S5 实现 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA |

## S0 · 用户需求(逐字)

> 继续

- 上下文解释: 第十切片完成 Mac 数据连接中心后，按 PRD/Plan/Code 对比继续推进最高优先级未完成项。最新代码显示 B 线后端和 Watch 已具备 `trajectory_context` / `target_state_variable` / `verification_signal`，Mobile Agenda 也已有摘要工具；剩余缺口是首页 Daily Artifact top action 没稳定展示“目标状态变量 + 验证信号”。
- 谁用 / 解决什么 / 现在怎么绕过: Mobile 首页用户需要一眼知道今日最重要行动试图改变什么状态变量、用什么信号验证；现在只能看到行动标题、do_now/why_now 和 evidence 列表，仍像“任务卡”，不是“控制输入”。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/services/daily_artifact_service.py`: Daily Artifact 从 `agenda.runtime_range` 派生单个 top action。
  - `backend/app/services/agenda_service.py`: smart/runtime item 已包含 `trajectory_context`、`target_state_variable`、`verification_signal`、`verify_by.trajectory`。
  - `mobile/services/trajectoryDisplay.ts`: 已能把 target、horizon、verification 和 boundary 转成用户可读短句。
  - `mobile/components/home/DailyArtifactCard.tsx`: 首页 Daily Artifact 卡片真入口。
  - `mobile/services/dailyArtifact.ts`: Mobile Daily Artifact 归一化真入口。
- 缺什么:
  - 后端 `_top_action_view()` 未把 trajectory control-input 字段稳定透传。
  - Mobile `DailyArtifactTopAction` 类型和归一化未保留这些字段。
  - 首页卡片未展示目标/周期/验证窗口。
- 硬约束:
  - 不新增写路径。
  - 不新增诊断、处方、剂量或因果承诺。
  - 只展示已有 runtime/smart agenda 合同中的 suggest-only 字段。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `HealthTrajectory`, `HealthAgendaItem`, `DailyArtifact`
- core_loop_step: Decide -> Execute -> Verify
- target_surface / safety_level / autonomy_tier: Mobile Home Daily Artifact / medical_boundary / suggest
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` Runtime Context 合同。
- smallest_end_to_end_slice: backend top_action 透传 trajectory 字段 + Mobile service 保留 + DailyArtifactCard 展示。
- stale_surface_to_remove: 无。
- **裁决**: PASS

## S2 · PRD

- 链接: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
- 引用的权威能力: `HealthTrajectory` 驱动每日行动选择；Today top action 解释目标状态变量、验证信号和安全边界。
- 边界(不做): 不改排序、不改 ActionRanker、不做新 ML、不做 prediction dashboard、不改完成/跳过写路径。
- 验收 Gate: Mobile 首页 Daily Artifact top action 能显示目标状态变量、周期和验证窗口，且不隐藏安全边界。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 分阶段 + 反馈环路由:
  - 后端合同测试 RED/GREEN。
  - Mobile service 和 UI 测试 RED/GREEN。
  - backend deploy + mobile OTA。
- 长杆 / spike: 无新平台能力。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不把 trajectory 文案升级成因果或医疗结论；不新增写入；只复用已有 boundary。
- **待拍板分叉(STOP 问人)**: 无，用户已要求继续按计划执行。
- **裁决**: PASS

## S4 · 研发任务分解

- 跨端 API 契约: Daily Artifact `top_action` 继续是旧合同超集，新增可选 `trajectory_context`、`target_state_variable`、`verification_signal`、`claim_boundary`。
- 任务表:
  - [ ] T1 RED: 后端 Daily Artifact top_action 缺少 control-input 字段。
  - [ ] T2 RED: Mobile service 归一化和首页 UI 不展示 control-input 摘要。
  - [ ] T3 GREEN: 后端透传、Mobile 类型/归一化、首页卡片展示。
  - [ ] T4 验证、部署、OTA、文档回写。
- 并发检查: 已 `git fetch` + fast-forward 到 `origin/main` `6a9bccf9`。

## S5 · 实现

- 委托: Codex
- 分支: `main`
- commit: 待提交

## G3 · 测试闸

- RED: 待记录。
- GREEN: 待记录。
- 集成闸: 待记录。

## G4 · 安全闸

- 触发?: medical_boundary 展示文案，但不新增建议、不新增写路径。
- 自查:
  - 只显示已有 suggest-only 字段。
  - 安全边界继续展示。
  - 不新增诊断、处方、剂量、因果承诺。
- **裁决**: GO

## S6 · 部署

- 路由: backend deploy + mobile OTA。
- 部署 SHA / 回滚点: 待定。

## G5 · 部署健康闸

- 待定。

## S7 · 上线验证

- 待定。

## G6 · 验证闸

- 待定。

## S8 · 沉淀

- 待上线验证后回写计划状态。
