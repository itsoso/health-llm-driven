# Dossier: Today DynamicView

| 字段 | 值 |
|---|---|
| slug | `today-dynamic-view` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | backend focused pytest + mobile Jest/tsc + deploy/OTA smoke |

## S0 · 用户需求

> 按照 Agent Native 理念,今日 tab 应该由阿衡在每次用户打开时动态生成,而不是固定 dashboard。

- 目标用户:每天打开移动端 Today 的用户。
- 要解决的问题:当前 Today 仍由前端并行拉多份数据并固定排序渲染,缺少由阿衡统一编排的动态页面合同。

## S1 · Discovery

- `mobile/app/(tabs)/index.tsx` 当前直接拉 `safety`、`twin`、`daily-plan`、`daily-artifact`、`timeline`、`dashboard`,并固定顺序渲染首页。
- `backend/app/services/daily_artifact_service.py` 已从 `agenda.runtime_range` 生成一个 Daily Artifact。
- `backend/app/services/agenda_service.py` 已有 `runtime_range_view` 可输出滚动健康运行时。
- `mobile/components/chat/cards/registry.tsx` 已有服务端卡片渲染和动作 allowlist,可复用为后续 Chat/Today 动态 UI 地基。

## G1 · 准入裁决

- classification: product_change
- first_user_fit:高强度工作者打开 App 时直接看到当前最该做的安全健康行动。
- core_loop_step:Digital Health Twin -> Safety Gate -> Agenda top action -> Mobile execution -> ExecutionEvent。
- first_class_objects:`HealthTwin`,`SafetyGuardian`,`HealthAgendaItem`,`LeverageAction`,`ExecutionEvent`,`WriteIntent`。
- target_surface:Backend source of truth + Mobile Today。
- source_of_truth:backend `/dynamic-views/today`;现有 `daily-artifact` 和 `agenda.runtime_range` 作为输入。
- safety_level:medical_boundary。
- autonomy_tier:manual_confirm;本切片不新增写路径。
- evidence_provenance:复用 runtime agenda / Daily Artifact 的 `source`,`runtime_context`,`safety_boundary`。
- verification_window:focused contract tests + mobile renderer tests + production smoke。
- success_metric:Today 可消费 `mobile.today` DynamicView,并在 endpoint 失败时回退现有首页。
- 裁决: PASS。

## S2/S3 · 范围与计划

- 计划: `docs/plans/2026-06-29-today-dynamic-view.md`。
- 原子能力范式: `docs/specs/active/2026-06-29-agent-native-dynamic-ui-atomic-capabilities.md`。
- 最小切片:
  1. 新增后端 `POST /dynamic-views/today`。
  2. 返回 `TodayDynamicView` with `view_id`,`context_hash`,`sections[]`,`cards[]`,`safety_boundary`。
  3. Mobile 新增 service + renderer,Today 优先渲染 DynamicView,失败时保留当前静态首页。
- 不做:
  - 不让 LLM 输出任意 UI/endpoint。
  - 不新增药物剂量、诊断、处方或自动执行。
  - 不删除现有 Today 静态组件。

## G2 · 可行性 + 安全压测

- 风险:动态页面接口故障导致首页空白。
  - 缓解:前端只在 DynamicView 可用且有 section 时启用,否则使用现有首页。
- 风险:服务端下发任意动作扩大写权限。
  - 缓解:复用 Chat registry allowlist;后端只下发 `route.open` 只读动作;Daily Artifact 完成/跳过继续走现有合同。
- 风险:重复生成造成性能压力。
  - 缓解:响应带 `expires_at` 和 `context_hash`;前端 React Query 短 staleTime,后续可服务端缓存。
- 裁决: PASS。

## S4 · 任务分解

- [x] T1 后端 contract RED: `/dynamic-views/today` 还不存在。
- [x] T2 后端 service/route GREEN。
- [x] T3 Mobile service/renderer RED。
- [x] T4 Mobile service/renderer GREEN。
- [x] T5 TodayScreen 优先使用 DynamicView 并保留 fallback。
- [x] T6 focused verification。
- [x] T7 deploy + OTA + production smoke。

## Gate 记录

- G3 测试:
  - RED 后端: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_today_dynamic_view.py -q --no-cov` -> 2 failed,`ImportError` + `404 Not Found`,证明 service/route 未接。
  - GREEN 后端: 同命令 -> 2 passed。
  - RED mobile: `npm test -- --runTestsByPath services/__tests__/todayDynamicView.test.ts components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand` -> failed,缺少 service/renderer。
  - GREEN mobile: 同命令 -> 4 passed。
  - 页面回归: `npm test -- --runTestsByPath app/(tabs)/__tests__/home.test.tsx services/__tests__/todayDynamicView.test.ts components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand` -> 19 passed。
- G4 安全:
  - 新 endpoint 使用 `get_current_user_required`,不暴露跨用户数据。
  - DynamicView 只组合现有 `DailyArtifact` + `agenda.runtime_range`;不新增 DB 写路径。
  - `runtime_agenda` card 只下发 `route.open`；Daily Artifact 完成/跳过继续走既有 manual-confirm/skip-reason 合同。
  - 医疗边界继续透传 `safety_boundary`;不诊断、不处方、不自动调药。
  - 裁决: PASS。
- G5 部署:
  - git commit: `38f266a8c36d8522750951dc37461694030fa2f2` (`feat(today): compose dynamic view`)。
  - push: `origin/main` updated `d7d215ac..38f266a8`。
  - backend deploy: `./deploy.sh -b -y` -> deployed remote HEAD `38f266a8c36d8522750951dc37461694030fa2f2`。
  - health score: `60/60 PASS`。
  - services: `health-backend`,`celery-worker`,`celery-beat` all `active`。
  - Mobile OTA: `./scripts/mobile-ota.sh production "feat(today): compose dynamic view"` -> production update group `42c2e3fd-8145-490c-a402-793b3191b6d6`, iOS update `019f13d3-69d4-706d-9b96-886fe55eab91`, runtime version `1.3.1`。
- G6 上线验证:
  - `GET https://health.executor.life/api/v1/health` -> `healthy`, database/redis/celery connected。
  - unauthenticated `POST https://health.executor.life/api/v1/dynamic-views/today` -> `401`,证明新 route 在线且受认证保护,不是 `404`。
  - 裁决: PASS。
