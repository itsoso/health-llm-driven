# 设计 · 王牌② 餐后散步窗 JITAI(降级 MVP)

日期: 2026-06-17 · 来源: [apple-watch-health-opportunities-roadmap.md](plans/2026-06-16-apple-watch-health-opportunities-roadmap.md) §5 王牌②

实现状态: v0 已落地。实现时补了一条仓库语义: `event_triggered` 默认不上日历,但带
`implied_quantity.trigger_date` 的一次性协议会在触发当天进入 agenda / Watch due list。

> 标准流程: 系统设计(本文)→ 测试先行(TDD)→ 严格安全审核(blocking)→ 发布。纯后端,本地 TDD + 部署。频控 gate(`proactive_coordinator.can_notify_proactively`)已上线 → roadmap「频控落地前不得上线」前提已满足。

## 四问

- **做什么**: 记一餐(午/晚)→ 后端自动开一个「餐后散步」协议(时间窗型,P1)→ 投进议程 + 推手腕(频控)→ 用户一键完成 → 落 `ExerciseRecord` 进时间线。
- **为什么**: 对糖前 HbA1c 6.3 锚点用户,餐后散步是带时间戳的离散循证微动作(`metabolic.py` 已有话术,附录 A B 级证据),与季度 CGM/HbA1c 做 L1↔L4 归因 = 单点 ROI 最高。
- **谁用**: 锚点用户。记一餐走现有 `/diet/records`(skill/手动);完成走我已上线的 `/watch/actions/complete`。
- **边界(不做)**: **被动计步打卡**(需 HKWorkoutSession native,延后)· **因果归因挂载**(effect_estimator 因果框架延后 Phase 2,本刀只生成 nudge + 落 ExerciseRecord,**不下因果断言**)· InterventionEvent 链接(延后)。降级 MVP = 「接受后手动一键完成」验闭环。

## 数据流

```
记一餐 POST /diet/records (午/晚)
   ▼ [新钩子,commit 后,fail-safe try/except 不阻塞记餐]
create_postmeal_walk_protocol(db, user_id, meal_time, meal_type)
   │  幂等:同 (user, 餐次, 日) 已有 walk 协议 → 不重复建;每日 ≤2(午+晚)
   ▼ HealthProtocol(domain=exercise, cadence=event_triggered, time_window=postmeal_window(), source_model=exercise_records, implied_quantity={exercise_type:walk,duration_min:20,intensity:easy,trigger_date,trigger_meal_type})
   ▼ 日常投影(全复用)
agenda_service.today() → watch_summary.build_watch_summary()
   │  _push_tier(exercise pending)=P1  [新分支]
   │  **安全门:有 active critical 安全告警时,抑制运动 P1 nudge(safety > 行为 nudge)**
   │  proactive_coordinator.can_notify_proactively(P1)  [复用频控;due list 仍可见,push_items 被抑制]
   ▼ 推手腕(P1,频控)
一键完成 POST /watch/actions/complete  [复用王牌①,原子幂等门]
   ▼ _write_domain_record: source_model=exercise_records  [新分支]
   ▼ ExerciseRecord(exercise_type=walk, duration, intensity, notes="via protocol: 餐后散步")
```

## 契约(5 处改动,全后端)

1. **`postmeal_window(meal_type, meal_time) -> str`**(新工具):午→`afternoon`(或 noon)、晚→`evening`、早→`morning`。**先核对 `DietRecord.meal_type` 真实字面量**(早餐/午餐/晚餐 vs breakfast/lunch/dinner —— 历史 kind 漂移坑,别假设)。
2. **`create_postmeal_walk_protocol(db, user_id, meal_time, meal_type) -> HealthProtocol|None`**(新工厂,仿 `create_water_cup_protocol`):domain=exercise,cadence=event_triggered,time_window=postmeal_window,source_model=`exercise_records`,implied_quantity={exercise_type:"walk",duration_min:20,intensity:"easy",trigger_date,trigger_meal_type},`can_default_complete=False`(运动需显式确认,守 R12)。**幂等**:查当天同餐次已有 walk 协议则返回 None 不重复;**每日上限**:仅午/晚触发(≤2/日)。
3. **`/diet/records` POST 钩子**:`db.commit()` 后,仅 `meal_type∈{午,晚}` 时调工厂;**`try/except` 包裹,失败只 log 不阻塞记餐**(记餐成功是主语义)。
4. **`_write_domain_record` 加 `exercise_records` 分支**:`ExerciseRecord(user_id, record_date=day, exercise_type=m.get("exercise_type")or"walk", duration=m.get("duration_min"), intensity=m.get("intensity")or"easy", notes="via protocol")`;**先核对 ExerciseRecord 真实必填列**;写失败向上抛(守 R12,复用王牌①的原子门 → 双击幂等不重复落)。
5. **`watch_summary._push_tier` 加 exercise 分支**:`type=="exercise" && status=="pending" → "P1"`。**安全抑制**:push 组装处,若近期有未确认/未抑制的 critical `AnomalyAlert`,或 24h 内 SafetyGuardian 审计 `top_severity>=CRITICAL`,**不把运动 P1 推上手腕**(safety > 行为 nudge;只查已落库证据,不在 watch_summary 路径 build_twin)。

## 不变量(安全 · reviewer 核对)

1. **safety > 行为 nudge(本刀安全重点)**: active critical/急性安全告警时不推餐后散步 nudge —— 别在用户报「胸口闷」(王牌⑤ critical)或异常 BP 时还催他去运动。**reviewer 重点核这条的实现(在哪门、判定源、会不会漏)。**
2. **不下因果断言**: 本刀只生成 nudge + 落 ExerciseRecord,**不声称「散步降低了你的血糖」**;归因挂载延后,任何对外措辞标「相关非因果」或不提因果。
3. **幂等(协议创建 + 完成)**: 同餐次同日不重复建 walk 协议;完成走王牌①的原子门(双击不重复落 ExerciseRecord)。
4. **R12 不假装**: 完成落真实 ExerciseRecord,写失败向上抛;`can_default_complete=False`(运动不静默判完成,必须用户点)。
5. **不阻塞记餐**: 钩子失败只 log,记餐主流程不受影响(fail-safe,但别静默吞成「记餐也失败」—— 记餐本身的错该照常冒泡)。
6. **频控**: 推送走 `can_notify_proactively(P1)`(不穿透静默、计入全局周上限);每日 ≤2 餐。
7. **user_id 边界**: 协议/ExerciseRecord 都按 token user_id。

## 测试计划(TDD)

1. 记午餐 → 当天新增 1 条 walk HealthProtocol(domain=exercise, cadence=event_triggered, time_window 正确)。
2. 同午餐再记一次 → **不重复建**(幂等,仍 1 条)。
3. 记早餐/加餐 → **不触发**(只午/晚)。记午+晚 → 2 条(每日上限)。
4. 钩子内工厂抛错 → **记餐仍成功**(diet record 落库),只 log。
5. walk 协议完成(/watch/actions/complete)→ 落 1 条 ExerciseRecord(type=walk, duration=20);双击 → 仍 1 条(原子门)。
6. `_push_tier` exercise pending → P1。
7. **安全抑制**:构造 active critical 安全告警 → watch_summary 不把 walk P1 推上手腕(push_items 不含它);无 critical 时正常推。
8. `postmeal_window` 各餐次 → 正确 time_window;meal_type 字面量与 DietRecord 真实值对齐。
9. user_id 隔离;无 token 401(完成端点已有)。

## 范围与延后

**本刀**: 1-5 五处后端改动 + 安全抑制门。本地 TDD + 部署。

**延后**: 被动计步打卡(HKWorkoutSession native)· InterventionEvent 链接 + effect_estimator 因果归因(Phase 2)· ExerciseRecord.context_source 来源追踪 · 餐后窗内重复提醒(reminder_service 轮询)· watch 端「开始散步」session UI。
