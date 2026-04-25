# notifications.py 拆分计划

## 现状

- `backend/app/tasks/notifications.py` = 1409 行
- 18 个 `@celery_app.task` 装饰的函数
- 26 个 `_helper` 函数

属于"巨石单文件第二大", 仅次于 `garmin_connect.py`.

## 风险点

`celery_app.py` beat schedule 用**完全限定字符串**指向任务:

```python
"task": "app.tasks.notifications.send_plan_morning_reminder",
"task": "app.tasks.notifications.daily_anomaly_check",
# ... 8 个类似
```

简单的 `mv notifications.py → notifications/reminders.py` 会让 Celery worker 找不到任务名, 生产 Beat scheduler 静默失败 (任务到点不触发).

## 推荐方案 (Package 化, 保持 backward compat)

```
backend/app/tasks/notifications/
├── __init__.py          # re-export 所有 task: send_xxx = ...send_xxx
├── reminders.py          # send_sleep_reminders, send_water_reminder, send_exercise_reminder
├── plan.py               # send_plan_morning_reminder, send_plan_evening_summary, send_plan_item_reminders
├── insights.py           # generate_daily_insights_for_all + _generate_daily_insight_for_user
├── anomaly.py            # daily_anomaly_check
├── trend.py              # daily_trend_analysis, send_trend_morning_push
├── morning.py            # send_morning_health_summary, generate_daily_briefing_message
├── weekly.py             # generate_weekly_report_message
├── action_card.py        # check_action_card_followups
├── doctor.py             # generate_doctor_weekly_report
└── _helpers.py           # 共用 helpers (_render_xxx_section 等)
```

`__init__.py`:
```python
from .reminders import send_sleep_reminders, send_water_reminder, send_exercise_reminder
from .plan import send_plan_morning_reminder, send_plan_evening_summary, send_plan_item_reminders
# ... 同上 18 个 task
```

这样 `app.tasks.notifications.send_xxx` 仍可工作 (Celery beat 不破),
同时 `app.tasks.notifications.reminders.send_sleep_reminders` 也可工作.

## 实施步骤

1. 建 `notifications/` dir + `__init__.py` 空文件
2. 把 1 个简单 task 移过去 (e.g. `send_water_reminder` → `reminders.py`)
3. 在 `__init__.py` 加 re-export
4. 跑 `pytest backend/tests/` 全过
5. **本地启 Celery worker** 验证 task 还能被 broker 识别
6. 重复步骤 2-5, 每次移 1-2 个 task
7. 最后删原 `notifications.py`
8. **生产部署后**, 立刻看 systemd journal 确认 Celery beat 没报 task-not-found

## 不要做的事

- ❌ 不要在一个 commit 里全移 — 难回滚
- ❌ 不要改 celery_app.py 的字符串路径 — 那会把生产 beat 状态搞混
- ❌ 不要在没 staging 的情况下直接合 main —— Celery beat 出错只在生产能发现

## 工时估算

- 6-8h 实现 + 本地 Celery 验证
- 1h 生产 watch + roll forward / back
- 总计: 半天到 1 天

## 何时做

不在这次 session 范围. 推荐:
- 在有 staging 环境的窗口做
- 或 用 feature flag 灰度
- 或 接手人手动跑过 send_water_reminder 等任务确认 worker 接收到
