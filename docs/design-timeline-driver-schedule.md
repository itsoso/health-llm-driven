# 设计 · 今日时间线:驱动标记 + 工作日程合并 + 日程感知 nudge(P1 后端)

日期: 2026-06-17 · 来源: 首页时间线三驱(规划/时间/事件)+ 工作日程整合讨论。

> 标准流程: 系统设计(本文)→ TDD → 严格安全审核(blocking)→ 部署。纯后端,复用已建的 CalDAV busy block(`caldav_sync.today_busy_blocks`),**不碰 EventKit / 不建 busy-window ingest**(已存在)。

## 四问
- **做什么**: ① 给 timeline item 派生 `driver`(plan/time/event_driven)② 把今日工作块(CalDAV busy block)作工作域项插进今日时间线 ③ nudge 门在忙碌窗内静默 P1/P2(P0 穿透)。
- **为什么**: 首页时间线体现三种驱动 + 工作日程合进日脊柱(跨域护城河)+ 健康 nudge 日程感知(会议中不打扰,roadmap §7 钦定)。
- **谁用**: 已连 CalDAV 的锚点用户。
- **边界(不做)**: EventKit / busy-window ingest(已有 CalDAV);JITAI 排空档(P2);精力曲线(P2);**工作块标题不显示**(隐私,只 busy 窗口/时长);移动端 driver chip + work block 渲染(随后 RN,简单)。

## 数据流
```
GET /timeline/today
  ├─ agenda items → _map_agenda_item → + driver = _derive_driver(item)
  ├─ caldav_sync.today_busy_blocks(db, uid) → 工作域 item(kind=work, 无标题, HH:MM)插进 items
  └─ 按时刻/time_window 排
nudge 门(proactive_coordinator.can_notify_proactively / watch_summary push):
  now(北京) ∈ today_busy_blocks 任一窗 ∧ tier∈{P1,P2} → False(静默)
  tier==P0 → 永远穿透(P0 分支在 busy 检查之前,不受影响)
```

## 契约(3 处,全后端)
1. **`_derive_driver(item) -> "plan_driven"|"time_driven"|"event_driven"`**(today_timeline_service):
   - `cadence=="event_triggered"` 或 `kind in {advisory}` → **event_driven**。
   - 常驻承诺协议(用药/复查/补剂/饮水/训练 —— 按 action_kind/source/cadence∈{daily,weekly,monthly,quarterly,annual})→ **plan_driven**。
   - 系统时刻卡(晨起就绪/睡前流程 等无常驻承诺、按时刻点亮)→ **time_driven**。**先勘**这些卡在数据里怎么区分(可能也是 protocol cadence=daily + time_window=morning/bedtime;若无干净判据,按「有无 source/object 的常驻协议」分,歧义偏 plan_driven 并在报告里标明哪些项判不准)。
   - 加进 `_map_agenda_item` 的 out + observation/outcome item(observation=已发生→可标 event_driven 或按来源;outcome 可不标或 plan)。**driver 纯展示,不影响调度/安全。**
2. **工作块进 timeline**(today_timeline_service 的组装函数):
   - `caldav_sync.today_busy_blocks(db, uid)` → 每块产一个 item:`{kind:"work", driver:"plan_driven"(日历=预定承诺), title:"工作 · {时长}min" 或 "忙碌", time_window:由 start HH:MM 映射, status:None, can_complete:False, severity:None}`。**绝不含日历标题/encrypted_title**(只 busy 窗口)。
   - 排序:busy block 有真实 HH:MM,timeline 现按 time_window 排 → 给 work item 映射 time_window(morning/noon/afternoon/evening 按 start 小时),或加排序键。无凭据/无 busy block → timeline 不含 work item,不崩(fail-soft)。
3. **nudge 门加忙碌静默**(proactive_coordinator):
   - `_in_busy_window(db, user_id) -> bool`:now(北京,复用现有 tz)落在 `today_busy_blocks` 任一 [start,end) → True。
   - `can_notify_proactively`:在 **P2 早返 + P0 分支之后**,对 **P1**(及若 P2 走到这)加:`if _in_busy_window(...): return False`。**P0 分支必须在 busy 检查之前 return**(穿透)。watch_summary `_can_include_push` 复用 can_notify_proactively 自动获得。

## 不变量(安全 · reviewer 核对)
1. **P0 永远穿透忙碌静默**(本刀安全重点):安全告警(异常 BP/急症/跌倒)不能因为「在开会」就不推。忙碌静默**只作用 P1/P2**。reviewer 重点核 P0 分支在 busy 检查之前、且测试有「P0 在忙碌窗仍推」对抗用例。
2. **隐私(日历=敏感)**: 工作块 item 与 nudge 门**只用 `today_busy_blocks` 的粗粒度 (HH:MM,HH:MM) 接缝**(已剥 title/PII);timeline 工作块**不带标题**;绝不把 encrypted_title/CalendarEvent 原文带进 timeline 出参或 LLM。
3. **driver 纯展示**: 不影响 agenda 调度、完成、安全。
4. **user_id 边界**: busy block 查询、timeline、nudge 门都按 token user_id。
5. **fail-soft**: 无 CalDAV 凭据/同步失败/无 busy block → timeline 无 work item、nudge 门当「不忙」正常推(别因日历坏了把所有 nudge 静默,也别崩)。

## 测试计划(TDD)
1. driver 派生:event_triggered→event;用药/复查→plan;晨起卡/睡前→time(按勘到的判据);advisory→event。
2. 工作块:有 busy block → timeline 含 kind=work item(无标题、时间对、driver=plan);无凭据/无 block → 不含 work item 不崩。
3. **nudge 门**:now 在忙碌窗 + P1 → False;+ P2 → False;**+ P0 → True(穿透)**;now 不在忙碌窗 → 原行为不变。
4. **隐私**:工作块 item 序列化无 title/encrypted_title/location;nudge 门不取标题。
5. user_id 隔离;fail-soft(日历查询抛错 → nudge 门当不忙、timeline 无 work,不崩)。

## 范围与延后
**本刀**: 上 3 处后端 + 安全(P0 穿透)+ 隐私(无标题)。本地 TDD + 部署。
**延后**: JITAI 排空档(day_schedule_service 已有 solver,P2 接)· 精力曲线叠加 · 工作块标题(用户自己端解密显示)· 移动端 RevaTimelineStrip 渲染 driver chip + work block(RN,随后)。
