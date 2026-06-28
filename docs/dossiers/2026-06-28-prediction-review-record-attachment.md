# Dossier: Prediction Review Record Attachment MVP

| 字段 | 值 |
|---|---|
| slug | `prediction-review-record-attachment` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | backend deploy |

## S0 · 用户需求(逐字)

> 继续

- 上下文解释: 第十三切片已上线 `prediction_timeline`，但真实运行时行动仍缺少稳定 `prediction_record` attachment。下一批按 G0.3 推进“prediction record 持久化合同 / 跨对象 attachment / confidence history”的最小后端闭环。
- 谁用 / 解决什么 / 现在怎么绕过: 用户能看到 Review 时间线，但只有 action snapshot 里手工带 `prediction` 或 `prediction_record` 时才会进入 backtest；现有 `PersonalPrediction` 已经能给 Trajectory 使用，但 Agenda/Daily Plan 完成事件没有稳定附着它，导致真实用户执行后难以形成预测回测样本。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/services/personal_models/personal_prediction.py`: 已返回稳定 `PersonalPrediction` 合同。
  - `backend/app/services/health_trajectory.py`: 已把 `personal_prediction_context` 附着到 trajectory risk。
  - `backend/app/services/action_ranker.py`: 已能按 `personal_prediction_context` 提升可回测行动。
  - `backend/app/services/health_operating_review.py`: 已能读取 `action_snapshot.prediction` 或 `action_snapshot.prediction_record` 并生成 backtest/timeline。
- 缺口:
  - `agenda_service._TRAJECTORY_CONTEXT_KEYS` 未保留 `personal_prediction_context`，运行时投影丢失预测上下文。
  - `daily_plan` feedback/event 只把 action 原样写入 `InterventionEvent.action_snapshot`，没有将 `personal_prediction_context` 标准化为 `prediction_record`。
  - Review backtest result 暂未透出 `prediction_type/source_model/evidence_tier/uncertainty/review_hint`，后续 next-step/confidence history 没有稳定字段。
- 硬约束:
  - 不新增 DB schema。
  - 不新增 ML/forecaster。
  - 不自动改变行动排序或重排。
  - 不新增诊断、处方、剂量或因果证明文案。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `PersonalPrediction`, `HealthAgendaItem`, `ExecutionEvent`, `OutcomeReview`
- core_loop_step: Predict -> Act -> Review -> Learn
- target_surface / safety_level / autonomy_tier: Backend Daily Plan feedback + Review API / medical_boundary / suggest
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`。
- smallest_end_to_end_slice: Agenda 保留 prediction context -> Daily Plan completion snapshot 写 `prediction_record` -> Review backtest result 暴露 record metadata。
- stale_surface_to_remove: 无。
- **裁决**: PASS

## S2 · PRD

- 链接: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
- 引用的权威能力: PersonalPrediction 必须声明 horizon、expected signal、uncertainty、evidence tier、claim boundary，并只能用于行动排序、轨迹解释和后续复盘。
- 边界(不做): 不建新表、不做全量 prediction persistence、不新增 dashboard、不新增自动重排、不做临床结论。
- 验收 Gate: 一个带 `personal_prediction_context` 的 Daily Plan action 完成后，其 `InterventionEvent.action_snapshot.prediction_record` 可被 Review backtest 消费，并保留非因果边界。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 分阶段 + 反馈环路由:
  - TDD 后端合同测试。
  - 保留 Agenda prediction context。
  - Daily Plan feedback/event 写标准 `prediction_record` snapshot。
  - Review result 暴露 record metadata。
  - backend deploy + prod smoke。
- 长杆 / spike: 新 DB 表和跨对象持久化 attachment 推迟到后续切片。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不改变自治等级；不把 prediction backtest 写成因果证明；不新增自动计划变更；只把已有 prediction context 转为可复盘 snapshot。
- **待拍板分叉(STOP 问人)**: 无，用户要求继续按规划执行。
- **裁决**: PASS

## S4 · 研发任务分解

- 任务表:
  - [x] T1 RED: Agenda 投影应保留 `trajectory_context.personal_prediction_context`。
  - [x] T2 RED: Daily Plan feedback/event 应把 `personal_prediction_context` 标准化写入 `prediction_record`。
  - [x] T3 RED: Review backtest result 应透出 prediction record metadata。
  - [x] T4 GREEN: 实现 attachment helper 与 review metadata。
  - [x] T5 验证、部署、计划回写。
- 分支: `codex/prediction-review-record-attachment`
- 并发检查: 基于 `origin/main` 隔离 worktree，主工作区存在 Claude/harness 并发改动，不混入本切片。

## S5 · 实现

- 新增 `backend/app/services/personal_models/prediction_record.py`，集中维护可附着的 PersonalPrediction 子集、标准 `prediction_record` snapshot 与非因果边界。
- `health_trajectory` 复用同一 helper 生成 `personal_prediction_context`，`agenda_service` 透传该字段。
- `daily_operating_plan` 将匹配的 PersonalPrediction 附到已有 action 上；低置信预测仍可作为复盘记录携带，但不新增行动或自治决策。
- `daily_plan` feedback/event 在写 `InterventionEvent.action_snapshot` 前把 carried context 标准化为 `prediction_record`。
- `health_operating_review` backtest result 透出 `source_model/prediction_type/domain/unit/uncertainty/evidence_tier/model_version/review_hint/requires_clinician`。
- `mobile/services/healthOperatingReview.ts` 同步 additive metadata 类型，服务层测试覆盖 ready backtest payload。

## G3 · 测试闸

- RED:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ... pytest test_agenda::... test_personal_predictions::... test_daily_plan_feedback::... test_health_operating_review::... -q --no-cov` -> 5 failed，缺口分别为 Agenda 丢 context、Daily Plan 未附 context、feedback/event 未写 `prediction_record`、Review metadata 缺失。
- GREEN:
  - 同 focused 命令 -> 5 passed, 9 warnings。
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai ... pytest backend/tests/test_agenda.py backend/tests/test_personal_predictions.py backend/tests/test_daily_plan_feedback.py backend/tests/test_health_operating_review.py backend/tests/test_health_trajectory.py backend/tests/test_action_ranker.py -q --no-cov` -> 45 passed, 11 warnings。
  - `python -m compileall -q` 改动模块 -> PASS。
  - `mobile` Jest `services/__tests__/healthOperatingReview.test.ts` -> 4 passed。
  - `mobile` `tsc --noEmit` -> PASS(隔离 worktree 临时链接主工作区 `node_modules` 后执行)。
- 集成闸:
  - `scripts/dump_system_map.py` -> PASS，`service_files=302`。
  - `backend/scripts/check_dossier_consistency.py` -> PASS。
  - `scripts/check_doc_drift.py` -> PASS。
  - `git diff --check` -> PASS。

## G4 · 安全闸

- 触发?: medical_boundary prediction/review 元数据，但无新建议、无新写自治、无药物/剂量。
- 自查:
  - `prediction_record` 只是已展示 prediction context 的执行快照。
  - Review 仍使用 observation/non-causal boundary。
  - 低置信预测只作为复盘记录携带，继续暴露 uncertainty/evidence_tier/boundary，不触发自动干预。
- **裁决**: PASS

## S6 · 部署

- 路由: backend deploy。
- 代码 SHA: `c47cd109749433ffad35c73af30c81802a9fe212`。
- 后端部署: `./deploy.sh -b` 从干净 deploy worktree 部署 `origin/main@c47cd109`。
- 回滚点: `feedffb4`。
- Mobile 发布: 因 main 中有 Mobile JS/TS 变更未 OTA，按纯 JS/TS 路径发布 production OTA；未走 TestFlight，未构建 native 二维码包。
- OTA: group `20d8c133-08f5-4873-9bda-c9d450fc3d5a`；iOS update `019f0e7c-fad9-7bec-9b17-b7b2b6539a02`。

## G5 · 部署健康闸

- `deploy.sh -b` 健康度 `60/60`，PASS。
- 服务器服务状态: `health-backend`、`celery-worker`、`celery-beat` 均为 `active`。
- 服务器 HEAD: `c47cd109749433ffad35c73af30c81802a9fe212`。
- **裁决**: PASS

## S7 · 上线验证

- 生产 `/api/v1/health` 返回 `200`，body: `api=running/database=connected/redis=connected/celery=connected`。
- 生产 `/api/v1/daily-plan/review?window_days=7` 未鉴权返回 `401`，确认敏感 Review API 仍受 Bearer auth 保护。
- Mobile OTA 已发布到 production channel，设备下次冷启或后台 30s+ 可拉取新 bundle。

## G6 · 验证闸

- 后端目标路径已在 production 部署并通过 smoke。
- 本切片 Mobile 改动为 service 类型/test 与随 main 发布的 JS bundle；无新增可见 UI，不需要真机视觉确认。
- **裁决**: PASS

## S8 · 沉淀

- 已回写:
  - `docs/plans/2026-06-27-health-runtime-governance-plan.md`
  - `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`
- 后续切片:
  - `Specialist` / `Problem` attachment。
  - confidence change history。
  - inconclusive 原因和 next-step/replan。
  - 可查询的长期 prediction record 索引。
