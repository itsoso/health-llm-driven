# P1-B 事件前提醒 (Pre-Event Reminders)

- **状态**: active
- **日期**: 2026-06-19
- **PRD**: `docs/prd/2026-06-19-proactive-planning-prd.md` §3-B
- **层**: 可变业务层(`backend/app/tasks/`) + 一张去重表(模型层)

## 决策 (Decision)

排程项 / 日历事件**开始前**按类提前量,主动推一条 hedged 提醒到用户本人设备,
给用户缓冲(收尾会议、准备服药、热身)。每分钟 Celery 扫描"未来 N 分钟将开始的项"。

复用既有机制,不重造:
- 推送 = `PushService.send_notification`(同用药提醒)
- 稀缺门 = `proactive_coordinator.can_notify_proactively`(R15 通知预算)
- 排程项来源 = `day_schedule_service.build_day_schedule`(timing-solver 真实数据)
- 会议来源 = `caldav_sync` 同步进库的 `CalendarEvent`

## 非目标 (Non-Goals)

- 不做提前量的 per-user 配置 UI(常量内置,代码改即可调;后续迭代再做)。
- 不做餐/睡眠的事件前提醒(lead=0)—— 已被既有分时提醒 / 睡眠提醒覆盖,不重复打扰。
- 不写回日历、不改 timing-solver、不新增 API 路由。
- 不做 LLM 合成文案(确定性模板,无模型成本、无幻觉风险)。

## 提前量 (Lead Times)

常量 `LEAD_MINUTES`(`app/tasks/event_reminders.py`),0 = 不做事件前提醒:

| 类 (kind) | 提前量(分钟) | 来源 |
|---|---|---|
| meeting(日历会议) | 10 | `CalendarEvent` |
| medication(服药) | 15 | 排程 domain=medication |
| supplement(补剂) | 15 | 排程 domain=supplement |
| movement(锻炼/workout) | 20 | 排程 domain=movement |
| diet(餐) | 0 | 不提醒 |
| sleep(睡眠) | 0 | 不提醒 |

**触发窗口**: 项开始 `T`,当 `now ∈ [T − lead, T − lead + 1min)` 时推(1 分钟扫描节拍,
北京时区 `Asia/Shanghai`,与全应用一致)。

## 去重 (Dedup)

新表 `sent_event_reminders`(model `SentEventReminder`):

```
(user_id, item_key, remind_date)  UNIQUE
```

- `item_key` = 排程项/事件稳定标识:`med:123` / `supplement:45` / `workout:today` /
  `cal:<event_id>`。**不存 PII**(无标题/无正文)。
- `remind_date` = 北京日历日。
- 机制:先 `INSERT` 占坑 —— 成功 → 本次推;`IntegrityError` 冲突 → 已推过,跳过。
  保证每项每天**至多一次**,扫描边界抖动 / beat 重试都不会二次推。
- 配对 managed 迁移:`migrations/managed/20260619_120000_create_sent_event_reminders.{postgresql,sqlite}.sql`
  (`CREATE TABLE IF NOT EXISTS`,幂等)。

> 为什么不复用用药提醒的"下一分钟不再匹配"隐式去重:事件前提醒在 `T−lead` 单点触发,
> 若 beat 抖动/补偿在同一分钟二次执行就会重推;显式占坑表更稳,且让"已推"可观测。

## 稀缺门 (Scarcity)

全部过 `can_notify_proactively(db, user_id, tier=...)`,**不绕过**:

- meeting / medication → `P0`(较高优先级)
- supplement / movement → `P1`(可忽略;静默时段不推)

推送后写 `audit.log_proactive_trigger(agent_type="event_reminder_watch", tier=...)`,
让预算计数把本提醒计入周上限(`*_watch` 埋点是 `proactive_coordinator` 的计数源)。

## 数据流 (Data Flow)

```
Celery beat (每分钟)
  → scan_event_reminders()
     ├─ 候选用户 = 活跃用药/补剂用户 ∪ 今日有会议的用户
     └─ for user:
          collect timed items:
            build_day_schedule(db,user).scheduled[]  (med/supplement/movement/diet)
            CalendarEvent 今日带时刻事件                (meeting)
          for item (lead>0):
            if now == T − lead:
              can_notify_proactively(tier) ── False ─▶ skip
              SentEventReminder INSERT ── 冲突 ─▶ skip
              PushService.send_notification(本人设备)
              log_proactive_trigger(event_reminder_watch, tier)
```

fail-soft:单用户 / 单项失败被捕获并记日志,不中断整批。

## 安全 (Safety — medical_boundary)

- 文案 hedged:仅"该做某事 / 可以准备一下 / 留点时间热身",**无剂量、无处方、无因果断言**。
- 不做自动给药 / 自动剂量;只是时点提醒。
- 服药提醒只复述用户已登记的药名,不追加任何医嘱措辞。

## 隐私 (Privacy)

- 会议提醒推给**用户本人设备**,可带会议标题 —— 这是本人直接通知,**非 LLM/agent 路径**,
  `caldav_sync.calendar_event_for_llm` 的脱敏门**不适用于此处**。
- 标题经 `CalendarEvent.get_title()` 解密**只用于推送正文**,绝不进任何 LLM/agent 路径。
- 去重表不落任何 PII(只存稳定 `item_key`)。

## 测试

`tests/test_event_reminders.py`:lead 窗口命中一次、窗口外不推、workout=20min、
diet=0 永不推、去重不二次推、稀缺门 False 不推且不占坑、会议标题进本人推送、
fail-soft 单用户失败不中断、`LEAD_MINUTES` 常量回归。

## 文件

- `backend/app/tasks/event_reminders.py` — 任务实现
- `backend/app/models/sent_event_reminder.py` — 去重表 model
- `backend/migrations/managed/20260619_120000_create_sent_event_reminders.{postgresql,sqlite}.sql`
- `backend/app/celery_app.py` — include + beat `*/1`
- `backend/tests/test_event_reminders.py`
