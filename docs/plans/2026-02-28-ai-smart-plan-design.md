# AI 智能计划 — 设计文档

日期：2026-02-28

## 概述

基于用户历史健康数据（运动、饮食、睡眠、打卡、Garmin），AI 自动生成个性化周计划，拆解到每日行动项，与打卡系统联动追踪执行，并通过反馈循环持续优化。

## 核心价值

将 App 从"记录型"升级为"教练型"：用户不再只记录数据，而是获得 AI 基于数据给出的具体行动指导。

## 方案选择

评估了 3 个方案，选择**方案 B：完整计划模块**。

| 方案 | 复杂度 | 用户体验 | 可追踪性 | 选择 |
|------|--------|---------|---------|------|
| A. 复用 Goals + AI 对话 | 低 | 一般 | 差 | ✗ |
| B. 完整计划模块 | 中 | 好 | 好 | ✓ |
| C. 增强日程模式 | 低 | 一般 | 一般 | ✗ |

## 数据模型

### WeeklyPlan（周计划）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| user_id | Integer FK → users | 用户 |
| week_start | Date | 周一日期 |
| status | String(20) | draft/active/completed/archived |
| focus_areas | JSON | AI 识别的本周重点（数组） |
| weekly_summary | Text | AI 生成的周总览文字 |
| completion_rate | Float | 整体完成率（自动计算，0-100） |
| ai_model | String(100) | 生成时使用的模型标识 |
| user_feedback | Integer | 用户评分 1-5（可选） |
| created_at | DateTime | |
| updated_at | DateTime | |

唯一约束：`(user_id, week_start)`

### PlanItem（计划项）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| plan_id | Integer FK → weekly_plans | 所属周计划 |
| day_of_week | Integer | 1=周一 ~ 7=周日 |
| category | String(20) | exercise/diet/rest/habit/other |
| title | String(200) | 如"跑步30分钟" |
| description | Text | 具体指导（AI 生成） |
| target_value | Float | 目标数值（可选） |
| target_unit | String(20) | 单位（次/分钟/kcal/ml） |
| checkin_template_id | Integer FK → checkin_templates | 关联打卡模板（可选） |
| is_completed | Boolean | 完成状态，默认 False |
| completed_at | DateTime | 完成时间 |
| sort_order | Integer | 排序 |
| created_at | DateTime | |

索引：`(plan_id, day_of_week)`

## 后端 API

路由前缀：`/api/v1/smart-plan`

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/generate` | JWT | 手动生成本周/下周计划 |
| GET | `/current` | JWT | 获取当前周计划（含全部 PlanItem） |
| GET | `/history` | JWT | 历史计划列表（分页） |
| GET | `/{plan_id}` | JWT | 计划详情 |
| PATCH | `/{plan_id}/items/{item_id}` | JWT | 手动标记完成/取消完成 |
| POST | `/{plan_id}/feedback` | JWT | 用户评分反馈（1-5） |
| DELETE | `/{plan_id}` | JWT | 删除计划 |

### POST /generate 参数

```json
{
  "target_week": "next"  // "current" 或 "next"，默认 "current"
}
```

### GET /current 返回

```json
{
  "id": 1,
  "week_start": "2026-02-24",
  "status": "active",
  "focus_areas": ["增加有氧运动", "控制晚餐碳水", "保持早睡"],
  "weekly_summary": "根据你上周的数据...",
  "completion_rate": 72.0,
  "items": [
    {
      "id": 1,
      "day_of_week": 1,
      "category": "exercise",
      "title": "跑步30分钟",
      "description": "有氧训练，心率控制在130-145bpm",
      "target_value": 30,
      "target_unit": "分钟",
      "checkin_template_id": 5,
      "is_completed": true,
      "completed_at": "2026-02-24T18:30:00"
    }
  ]
}
```

## 核心生成逻辑（SmartPlanService）

```
generate_weekly_plan(user_id, target_week):

  1. 收集健康上下文
     - 复用 ChatService._build_health_context()
     - 包含：运动/饮食/睡眠/打卡/Garmin 数据

  2. 收集反馈上下文
     - 上周计划完成率（如有）
     - 完成好的项目 vs 未完成的项目
     - 用户评分反馈

  3. 获取用户可用打卡模板
     - 查询所有 is_active=True 的 CheckinTemplate
     - 传给 LLM 用于匹配

  4. 构造 prompt 调用 LLM
     - 系统提示：你是健康教练，基于用户数据生成结构化周计划
     - 要求输出 JSON 格式
     - 约束：每天 3-5 个行动项，运动项尽量匹配已有打卡模板名称
     - 考虑用户已有习惯和偏好

  5. 解析 LLM 响应
     - 提取 focus_areas、weekly_summary
     - 解析每天的 PlanItem
     - 自动模糊匹配 checkin_template_id（模板名称相似度）

  6. 写入数据库
     - 如果本周已有 active 计划，将其状态改为 archived
     - 创建新 WeeklyPlan + PlanItems
     - 返回完整计划
```

## 打卡联动机制

在现有打卡记录创建流程中增加一个钩子：

```python
# 在 CheckinRecord 创建后触发
def on_checkin_created(checkin_record):
    # 查询本周是否有 active 的 WeeklyPlan
    plan = get_active_plan(user_id, current_week)
    if not plan:
        return

    # 查找匹配的 PlanItem
    today_weekday = checkin_record.checkin_date.isoweekday()  # 1-7
    matching_items = find_items(
        plan_id=plan.id,
        template_id=checkin_record.template_id,
        day_of_week=today_weekday,
        is_completed=False
    )

    for item in matching_items:
        item.is_completed = True
        item.completed_at = now()

    # 更新整体完成率
    update_completion_rate(plan)
```

## 自动生成定时任务

- **时间**：每周日 20:00（北京时间）
- **触发**：Celery beat 定时任务
- **条件**：仅为有足够数据的活跃用户生成（最近 7 天有打卡或 Garmin 数据）
- **行为**：生成下周计划，状态为 draft（用户可查看并激活）

## 前端页面

### 路由：`/smart-plan`

### 页面结构

```
┌─────────────────────────────────────────┐
│  🧠 本周智能计划    2/24-3/2   [重新生成] │
│  重点: 增加有氧 | 控制晚餐碳水 | 早睡     │
│  完成进度: ████████░░ 72%               │
├─────────────────────────────────────────┤
│  [一] [二] [三] [四✓] [五] [六] [日]     │
├─────────────────────────────────────────┤
│  周五 · 2月28日                          │
│                                         │
│  🏃 运动                                │
│  ┌─ □ 跑步 30分钟 (关联打卡)        ────┐│
│  │   有氧训练，心率130-145bpm           ││
│  └──────────────────────────────────────┘│
│  ┌─ ☑ 拉伸 10分钟 (已完成 ✓)       ────┐│
│  └──────────────────────────────────────┘│
│                                         │
│  🥗 饮食                                │
│  ┌─ □ 午餐增加蛋白质                ────┐│
│  │   建议: 鸡胸/鱼/豆腐，目标30g蛋白   ││
│  └──────────────────────────────────────┘│
│                                         │
│  😴 作息                                │
│  ┌─ □ 23:00 前入睡                 ────┐│
│  └──────────────────────────────────────┘│
├─────────────────────────────────────────┤
│  AI 教练说：本周步数比上周提升15%，      │
│  继续保持！今天建议做一次轻松有氧...     │
└─────────────────────────────────────────┘
```

### 交互

- 日期标签切换查看每天计划，已完成的日期带 ✓ 标记
- 计划项卡片可点击手动标记完成（未关联打卡的项目）
- 关联打卡的项目自动同步完成状态，显示"已打卡"
- 顶部进度条实时更新
- "重新生成"按钮重新调用 AI（旧计划归档）
- 空状态：「生成我的第一份计划」按钮

### 小程序

- 首页增加「本周计划」卡片，显示今日待完成项数量
- 点击进入计划详情页（与前端类似布局）

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| 新用户数据不足 | 生成通用模板计划 + 提示"累积更多数据后计划会更精准" |
| LLM 返回格式异常 | 重试 1 次，仍失败返回错误 + 保留原始文本 |
| 本周已有计划 | 旧计划 status → archived，生成新计划 |
| 打卡模板匹配失败 | PlanItem.checkin_template_id 留空，用户手动完成 |

## 不做（YAGNI）

- 不做计划内容编辑（只能重新生成）
- 不做推送通知（后续可加）
- 不做多人共享计划
- 不做计划模板市场

## 技术栈

- 后端：FastAPI + SQLAlchemy + Celery
- LLM：OpenClaw API（与现有 ChatService 相同）
- 前端：Next.js + React Query + Tailwind
- 小程序：Taro + React
