# Feature Spec: 每日时点日程(timing-solver)

> Status: implementing
> Owner: backend (health-os 调度器线)
> Updated: 2026-06-17
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md · docs/design/health-os/os-design.md · docs/design/health-os/planning-methodology.md
> Related code: backend/app/services/{timing_solver,timing_adapter,day_schedule_service,recheck_floor,schedule_safety_seam}.py

> 说明:本 spec 为已落地的 timing-solver 子系统补治理(governance spec §8.1:新 ranker/
> verification loop / 写路径需 feature spec)。cut 1–4 已合入 main;cut 5–6 见 §13/§14。

## 1. Decision

把用户每日的药/补剂/动作按「全部硬约束」(药代时点、螯合间隔、餐锚、昼夜、恢复门控、
通知预算)求解成一条可执行时间轴,作为 agenda / Write 层提议的时点来源。

## 2. Problem

- 谁:中年慢病早期用户,多药+多补剂(创始人:7 药 + 3 补剂),时点彼此冲突(左甲状腺素须空腹、
  钙铁须错峰、PPI 须餐前、镁睡前)。
- 现状:`fuel_strategist` 只按时钟 `_meal_slot_now` 分餐槽,不解药代/螯合/昼夜约束;
  无统一时点求解器(os-design / planning-methodology 都点名「唯一真缺」)。
- 不做的后果:用户自己排时点 → 螯合冲突(钙铁同服铁吸收↓50%)、空腹药排错、依从崩。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 每日把药/补剂/动作排上满足全部硬约束的时间轴
  classification: new_product_behavior
  first_user_fit: yes — 多药多补剂的中年慢病早期用户,执行带宽不足
  core_loop_step: Agenda top action / Watch·Mobile execution(下发时点)
  first_class_objects: HealthAgendaItem, WriteIntent, SafetyGuardian, HealthProtocol
  target_surface: Backend(真相)→ Mobile/Watch(执行)
  source_of_truth: Backend(timing_solver 纯函数 + day_schedule_service)
  safety_level: medical_boundary
  prescription_or_causal_verdict: none   # 只排时点/间隔,绝不生成/调整剂量,不出因果裁决
  autonomy_tier: manual_confirm          # 提议时点,用户确认;clinical 写永久封顶 manual
  evidence_provenance: planning-methodology §5(约束规则)/ §6(节律库)+ 药品说明书/医嘱
  claim_hedging: hedged                  # 时点为「建议/遵医嘱」,非个体化处方
  verification_window: 依从 7 天滚动(adherence_7d_pct)
  success_metric: 时点提醒确认率 / 螯合冲突计数=0 / 通知未关闭率
  added_user_burden: 低 — 替代用户自排时点,净减负担
  burden_justification: 一次确认换掉每日多药时点的心算
  non_goals: 见 §4
  smallest_end_to_end_slice: medications → adapter → solver → {scheduled/rejected/deferred}(已落地 cut 1-4)
  stale_surface_to_remove_or_archive: 暂无(fuel_strategist 的 _meal_slot_now 保留,后续评估收口)
  spec_required: yes
```

## 4. Non-Goals

- 不生成/调整任何剂量或疗程(剂量 100% 来自医嘱;R4)。
- 不重实现 DDI/DSI 逻辑 —— 硬禁忌由 SafetyGuardian 算,本系统消费其裁决(cut 5)。
- 不出「对你有效/恶化」因果裁决(处方/激素指标 → clinician_review)。
- 不做自治执行 —— 全 manual_confirm,Write 层用户确认(自治分级是另一线)。
- 围训练碳水时点(需真实 WorkoutRecord 开始时间)暂不实现(cut 后续)。
- 不自行缩短复查间隔到短于医嘱/生物下限(由 recheck_floor 护栏保证)。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthAgendaItem` | scheduled 项作为当日 agenda 时点来源(cut 6 接入) |
| `SafetyGuardian` | 提供硬禁忌裁决 → `forbidden_reasons`(cut 5 接入);命中项 → rejected 走告警 |
| `HealthProtocol` | 补剂/动作协议的时点由 solver 落桩 |
| `WriteIntent` | 时点提醒作为 manual_confirm 写提议(cut 6) |

## 6. User Flow

```text
每日构建(晨同步 / 信号变化)
  -> day_schedule_service.build_day_schedule(db, user_id)
     -> medications(药+补剂)──timing_adapter──▶ Item[]
     -> user_profile(作息)──────────────────▶ DayContext
     -> SafetyGuardian 硬禁忌 ──▶ forbidden_reasons   [cut 5]
  -> timing_solver.solve_day_schedule
  -> {scheduled, rejected(走告警), deferred}
  -> agenda 时点 / Watch top action / Write 提醒(manual_confirm)   [cut 6]
  -> 用户确认 → ExecutionEvent → 依从 7 天验证
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | 真相:求解 + 安全裁决消费 | `build_day_schedule(db,user_id)` → {scheduled/rejected/deferred} |
| Watch | 低摩擦执行 | 取当下/下一时点项 confirm/later/skip |
| Mobile | 当日时间轴 + Write 确认 | 渲染 scheduled,rejected 走安全告警卡 |

## 8. Data Contract

```yaml
apis: GET /api/v1/schedule/today(cut 6,返回 {scheduled,rejected,deferred})
events: ExecutionEvent(已有)
models: 无新模型(读 Medication / UserProfile)
fields: 无新增列
enums: AnchorType(timing_solver 内部常量,非 DB)
backward_compatibility: 纯新增,不改现有路由/表
migration: 无
```

## 9. Safety, Privacy, And Medical Boundary

- 触及:medication / supplement / lab(复查间隔)路径。
- 确定性规则:SafetyGuardian(DDI/DSI/PGx)给硬禁忌;recheck_floor 给复查下限;solver 强制螯合间隔。
- 系统**不得**:生成/调剂量、出因果裁决、缩短医嘱复查间隔、把处方药剂量丢弃(quiet 不丢处方)。
- 审计:Write 提议经 write_intent(已有原子门 + 审计)。
- 隔离:user_id 取自 token;build_day_schedule 按 user_id 过滤。

## 10. AI Behavior

无 LLM 参与求解 —— timing_solver 是确定性纯函数(可回测、可审计)。LLM 仅可在上层
解释/措辞,不进求解或安全裁决路径(governance invariant 6)。

## 11. Acceptance Criteria

```gherkin
Given 用户在服 PPI(餐前30)、左甲状腺素(空腹)、钙(随餐)、铁(空腹)
When build_day_schedule 求解当日时间轴
Then PPI 排早餐前30min、左甲状腺素与钙/铁间隔≥4h、钙与铁间隔≥2h

Given 某项命中 SafetyGuardian 硬禁忌(如维K×华法林)   [cut 5]
When 求解
Then 该项进 rejected(走告警通道),不排上时间轴

Given 一条处方夜间药落在静默窗(22:00–08:30)
When 求解
Then 该药仍按医嘱时点排,绝不顺延/丢弃到次日

Given 建议复查间隔短于指标生物下限或医嘱
When recheck_floor 夹取
Then 取更严下限,不缩短医嘱
```

## 12. Verification Plan

```bash
# Backend(已绿)
cd backend && source venv/bin/activate
export SECRET_KEY=test-secret-key-32-chars-minimum!! GARMIN_ENCRYPTION_KEY=mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=
python -m pytest tests/test_timing_solver.py tests/test_timing_adapter.py \
  tests/test_recheck_floor.py tests/test_day_schedule_service.py -q --no-cov   # 37 passed

# Repo hygiene
git diff --check
# 注:若后续改 safety 规则数 → 同步 scripts/check_doc_drift.py
```

## 13. Rollout And Rollback

- 无 flag:cut 1–4 是纯后端服务,未接任何客户端,零用户影响(休眠就绪)。
- cut 6 接 agenda/endpoint 时再评估灰度;rollback = 不调用该服务即可。
- 无迁移、无 schema 变更。

## 14. Open Questions

阻塞 cut 6+ 前需定:
- **cut 6 表面**:`/schedule/today` 端点 vs 直接投影进现有 agenda_service?source-of-truth 不重复。
- 围训练时点:WorkoutRecord 多为事后记录,缺「今日计划开始时间」数据源。

已解决:
- ~~**cut 5 安全 seam**:如何映射 Alert → `med.id`?~~ → `schedule_safety_seam.compute_seam(meds)`
  纯函数,由待排 meds 自身派生最小 twin 跑 DDI/DSI 规则(同源匹配消除跨表名字漂移),取
  HIGH/CRITICAL,`data_citation` 物质名匹配回行:补剂→`forbidden_reasons`(拒排走告警)、
  处方药→`Item.warning`(保留排程标警告;R4 永不 forbid)。与 SafetyGuardian 独立告警通道叠加。

不阻塞首片(cut 1–4 已独立成立)。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-17 | 初稿(补已落地 cut 1–4 的治理;定义 cut 5–6 契约) | governance §8.1 要求 + dogfood admission gate |
| 2026-06-17 | cut 5 安全 seam 落地(`schedule_safety_seam`):DDI/DSI 硬禁忌 → 补剂拒排 / 处方药行警告;safety review GO | dsi/ddi 规则已稳定,接通 forbidden_reasons + Item.warning |
