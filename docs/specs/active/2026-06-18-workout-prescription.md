# Feature Spec: 锻炼时点处方化 + 计划↔实际闭环 + 多端表面

> Status: implementing (cut A) · Owner: backend(timing 调度器线)
> Updated: 2026-06-18
> Related: `docs/specs/active/2026-06-17-day-timing-schedule.md` §14(本稿回答其 workout open question)·
> `app/agents/movement_coach/` · `app/services/{day_schedule_service,timing_solver}.py` · `models/daily_health.py`(WorkoutRecord)

## 1. Decision
把首页/手表上通用的「锻炼 N 分钟」块升级成 **movement_coach 处方**(ACWR × readiness × ACTN3 →
类型/强度/时长/RPE),并建立**计划时点 ↔ 实际 WorkoutRecord 的闭环**。处方以**结构化字段**下发,
三端(Mobile / Watch 本期,Rokid Glasses 后续)各按形态渲染同一份真相。

## 2. Problem
锻炼块是哑的(只写时长),不说今天该练什么/多重;而 movement_coach 早能算"过载→deload /
optimal×hard→高强度",这套个体化训练负荷判断没落到日程。且排的时点与用户实际练的时点脱节,
系统学不到真实偏好(护城河缺口)。

## 3. Non-Goals
- 不生成/调整任何**剂量/疗程**(R4 只管药补;运动强度是 hedged 教练建议,非处方)。
- 不出"训练对你某指标有效/有害"的**因果裁决**(走 clinician_review)。
- 不做运动中实时指导(live-run 另线)。
- 不自动改医嘱/复查;RED→休息门控沿用。
- Rokid Glasses 渲染本期不做(契约预留)。

## 4. 结构化处方契约(三端共享真相)
`workout:today` 调度项携带 `prescription`(而非烤死的 title 串):
```jsonc
{
  "id": "workout:today", "domain": "movement", "time": "17:30",
  "title": "Z2 有氧 45min",            // 简短串,小屏直接用
  "prescription": {
    "intensity": "moderate",            // high | moderate | low | rest | unknown
    "type": "aerobic_z2",               // interval_or_strength | aerobic_z2 | easy_aerobic | recovery
    "duration_min": 45,
    "rpe": "6-7",                        // unknown/rest 时省略
    "guidance": "Z2-Z3 有氧 45-60min,或中重量力量 RPE 6-7",
    "gene_note": "ACTN3 XX:增加长距离 Z2 比例"   // 可选(无则省略)
  }
}
```
intensity=rest → 不排锻炼块,出「今日主动恢复」项(走 rejected,reason=guidance)。

## 5. 表面契约(优先级:Watch + Mobile 本期;Rokid 后续)
| 端 | 形态 | 渲染 | 状态 |
|---|---|---|---|
| Mobile | 全屏 | title + 时长 + RPE + guidance 全文 + gene_note;可开始/记录 | 本期 |
| Watch | 腕上小屏 | title + 强度 chip(high/mod/low 配色)+ 时点;rest→「今日恢复」 | 本期 |
| Rokid Glasses | HUD/语音 | 极简一行「现在:Z2 有氧 45min」+ 语音 | 后续(同契约,仅加渲染层) |

后端是唯一真相,算一次;新增端只写渲染层,零后端改动。

## 6. Data Flow
```
build_day_schedule(db,user_id)
  └─ workout_prescription(db,user_id)  [fail-soft → None 回退通用块]
        twin=build_twin(use_cache)→ recovery_coach.zone + movement_coach._resolve_training_status(ACWR)
        → _today_intensity(status,zone) + _gene_bias → {intensity,type,duration,rpe,guidance,gene_note}
  └─ _maybe_workout_item(profile,ctx,rx): rest→拒排(恢复项);否则 Item(prescription=rx)
  └─ solve_day_schedule → scheduled[].prescription
  └─ agenda_service / /watch/summary 透传 prescription → Mobile + Watch 渲染
   实际执行 → WorkoutRecord(start_time)  ──[cut E]──► 计划↔实际配对(依从+时点学习)
```

## 7. Cuts
- **A(本期)处方化下发 + Mobile + Watch 渲染**:无 schema 变更。
- **E1(后续)计划↔实际读出**:新 `PlannedWorkout` 表(date/planned_start/intensity)+ 配对依从;+1 model(迁移+doc-drift)。
- **E2(后续)学到真实时点** → 回灌 `pick_workout_start` 默认窗。
- **Rokid(后续)** 第 3 端渲染。

## 8. Safety / Medical Boundary
- safety_level: **medical_boundary**;`prescription_or_causal_verdict: none`;`claim_hedging: hedged`。
- 只消费 movement_coach 既有 hedged 输出 + RED/急性 休息门控,无新增医疗逻辑。
- 取数全 fail-soft:build_twin / readiness / ACWR 任一失败 → 回退通用块,失败记 log(不静默吞)。
- 不反推训练→指标因果(E 闭环只记时点+依从)。

## 9. Acceptance
```gherkin
Given ACWR>1.5(过载)+ readiness=hard
Then 锻炼块 intensity=low(强制降强度),不出高强度间歇

Given readiness=rest(或急性不适)
Then 不排锻炼块,出「今日主动恢复」项

Given ACTN3 XX
Then prescription.gene_note 含"增加长距离 Z2"

Given 处方计算异常(取数失败)
Then 回退通用「锻炼 N 分钟」块,排程不炸,记 warning log
```

## 10. Verification
```bash
cd backend && source venv/bin/activate
export SECRET_KEY=… GARMIN_ENCRYPTION_KEY=…
pytest tests/test_workout_prescription.py tests/test_day_schedule_service.py \
       tests/test_schedule_into_agenda.py tests/test_timing_solver.py -q --no-cov
# mobile: npx tsc --noEmit ; watch: cd apps/watch && swift test
```

## 11. Changelog
| Date | Change |
|---|---|
| 2026-06-18 | 初稿 + cut A 实现(处方化 + Mobile/Watch 渲染);E1/E2/Rokid 列后续 |
