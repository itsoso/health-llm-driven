# Dossier: Daily Artifact 控制输入语义展示

| 字段 | 值 |
|---|---|
| slug | `daily-artifact-control-input` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
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
- 并发检查: 已 `git fetch` + fast-forward 到 `origin/main`；开发提交为 `c6af470e5ebfff6eb5eb6fbf2c046eeb54c57772`，部署前远端继续前进到 `bb08085eb54ce36c9a143c7313952494f570c5f8`。

## S5 · 实现

- 委托: Codex
- 分支: `main`
- commit: `c6af470e5ebfff6eb5eb6fbf2c046eeb54c57772`
- 代码改动:
  - `backend/app/services/daily_artifact_service.py` 的 `_top_action_view()` 透传 `trajectory_context`、`target_state_variable`、`verification_signal` 和 `claim_boundary`。
  - `mobile/services/dailyArtifact.ts` 保留 Daily Artifact top action 的控制输入字段。
  - `mobile/services/trajectoryDisplay.ts` 抽成 Agenda 和 Daily Artifact 共用的 display input。
  - `mobile/components/home/DailyArtifactCard.tsx` 在首页行动卡片展示目标/周期和验证摘要。

## G3 · 测试闸

- RED:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_daily_artifact.py -q --no-cov` 先失败于 `KeyError: 'trajectory_context'`，随后失败于 `target_state_variable` 缺少 fallback。
  - `npm test -- --runTestsByPath services/__tests__/dailyArtifact.test.ts components/home/__tests__/DailyArtifactCard.test.tsx --runInBand` 先失败于首页找不到 `目标: 腰围 · 周期: 90天上游轨迹`，service 归一化也未保留 `trajectory_context`。
- GREEN:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_daily_artifact.py -q --no-cov` -> `3 passed, 9 warnings`。
  - `npm test -- --runTestsByPath services/__tests__/dailyArtifact.test.ts components/home/__tests__/DailyArtifactCard.test.tsx services/__tests__/trajectoryDisplay.test.ts --runInBand` -> `3 passed, 8 tests`。
- 集成闸:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_daily_artifact.py backend/tests/test_agenda_range_complete.py backend/tests/test_action_ranker.py backend/tests/test_watch_summary.py backend/tests/test_inline_cards_runtime_agenda.py -q --no-cov` -> `39 passed, 9 warnings`。
  - `npm test -- --runTestsByPath services/__tests__/dailyArtifact.test.ts components/home/__tests__/DailyArtifactCard.test.tsx services/__tests__/trajectoryDisplay.test.ts services/__tests__/agenda.test.ts --runInBand` -> `4 passed, 15 tests`。
  - `cd mobile && npx tsc --noEmit` -> exit 0。
  - `backend/venv/bin/python -m compileall -q backend/app/services/daily_artifact_service.py && backend/venv/bin/python backend/scripts/check_dossier_consistency.py && backend/venv/bin/python scripts/check_doc_drift.py && git diff --check` -> dossier/doc drift/diff 检查通过。

## G4 · 安全闸

- 触发?: medical_boundary 展示文案，但不新增建议、不新增写路径。
- 自查:
  - 只显示已有 suggest-only 字段。
  - 安全边界继续展示。
  - 不新增诊断、处方、剂量、因果承诺。
- 复查方式: Codex safety self-review；由于当前工具策略不允许未显式请求时主动派子 agent，未启动 safety-privacy-reviewer。
- 结果: diff 只新增字段透传和 UI 展示；无新增写路径，完成/跳过路径不变；无药物、剂量、诊断或因果承诺升级。
- **裁决**: GO

## S6 · 部署

- 路由: backend deploy + mobile OTA。
- 代码提交: `c6af470e5ebfff6eb5eb6fbf2c046eeb54c57772`。
- 后端部署 HEAD: `bb08085eb54ce36c9a143c7313952494f570c5f8`（包含并发 harness gate 提交）。
- deploy.sh 回滚点: `6a9bccf9`。
- Mobile OTA:
  - branch/channel: `production`
  - runtime version: `1.3.1`
  - update group: `1ad7bd94-3ae9-4614-b713-05743488775b`
  - iOS update id: `019f0da5-f3cd-7136-94d8-aabc9bd34a22`
  - EAS dashboard: `https://expo.dev/accounts/itsoso/projects/health-pilot/updates/1ad7bd94-3ae9-4614-b713-05743488775b`

## G5 · 部署健康闸

- `./deploy.sh -b` 成功。
- 部署健康分: `55/60 ✅ PASS`。
- skills manifest: 本地 `22` = 线上 `22`。
- 生产服务 HEAD: `bb08085eb54ce36c9a143c7313952494f570c5f8`。
- 生产 smoke:
  - `GET http://127.0.0.1:8000/api/v1/health` -> `200`。
  - `GET http://127.0.0.1:8000/api/v1/daily-artifact/me` 未鉴权 -> `401`，说明路由已注册；不是旧进程 `404`。
- **裁决**: PASS

## S7 · 上线验证

- Mobile OTA `./scripts/mobile-ota.sh production "Daily Artifact shows target and verification controls"` 成功发布。
- EAS 输出 iOS bundle `entry-b7516e1e93a45d3a05551c1fcb3e1590.hbc`，设备冷启动或后台 30s+ 后拉取。
- 本切片无新增真实世界写动作；上线验证以路由活性、OTA 发布和本地合同/UI 测试为准。

## G6 · 验证闸

- PASS。Daily Artifact 首页现在能通过同一 trajectory display 工具展示:
  - 目标状态变量；
  - 轨迹周期；
  - 验证信号/窗口/不确定性。
- 尚未完成: Review 页面中的 prediction backtest 时间线，以及更广泛 provider provenance 覆盖；保留到后续切片。

## S8 · 沉淀

- 已回写 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` 和 `docs/plans/2026-06-27-health-runtime-governance-plan.md`。
- 后续最高价值切片转向:
  - Review prediction backtest；
  - DataConnection 重连/撤权删除/token refresh；
  - runtime provenance 扩展到 HealthKit/wearable/device key facts。
