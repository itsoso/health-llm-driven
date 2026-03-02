# 跑后智能分析 - 设计文档

**日期**: 2026-03-02
**状态**: 待实现

## 概述

用户跑步/运动结束后，通过对话、快捷按钮或 Siri 触发：自动同步 Garmin 数据 → 找到最新运动记录 → 调用 OpenClaw 多模型分析 → 返回完整训练报告。

## 触发方式

### 1. AI 助手对话（Action 系统）

用户在健康顾问对话中说"我跑完了"、"运动结束"等，OpenClaw 识别意图后输出：
```json
<<<ACTIONS:[{"type": "workout_analyze", "workout_type": "running"}]>>>
```
后端 `_handle_workout_analyze_action()` 处理，结果注入对话历史。用户可继续追问。

### 2. AI 助手快捷按钮

新增"运动完成"快捷按钮，发送预设文字，走同一 Action 链路。

### 3. Siri 快捷指令

直接调用 REST 端点 `POST /api/v1/workout/post-run-analyze?format=brief`，Siri 屏幕弹出简洁摘要。

## 后端架构

### 新端点：`POST /api/v1/workout/post-run-analyze`

**认证**: JWT + X-API-Key 双认证

**请求体**:
```json
{
  "format": "full",         // "full" | "brief"
  "workout_type": "running" // 可选，默认取最近一条
}
```

**处理流程**:

| 步骤 | 操作 | 约束 |
|------|------|------|
| 1 | Garmin sync (缓存 token 登录) | 最多3次轮询，每次间隔10s |
| 2 | 查 WorkoutRecord，取最近2小时内最新记录 | 无匹配返回提示 |
| 3 | 构建分析 prompt (运动数据 + 历史对比 + 用户画像) | — |
| 4 | POST /api/openclaw/analyze 提交多模型分析 | — |
| 5 | 轮询 /status/{batch_id}，每10s一次 | 最多6次(1分钟) |
| 6 | 格式化返回 | full/brief 两种格式 |

### 返回格式

**full** (AI 助手 + 快捷按钮用):
```json
{
  "workout": {
    "type": "running",
    "distance_km": 5.2,
    "duration_min": 32,
    "pace": "6'09\"",
    "avg_hr": 152,
    "max_hr": 168,
    "hr_zones": {"warmup": 10, "fat_burn": 25, "aerobic": 45, "anaerobic": 15, "max": 5},
    "training_effect_aerobic": 3.2,
    "training_effect_anaerobic": 1.8,
    "calories": 380
  },
  "multi_model_analysis": {
    "model_results": [
      {"site": "lb-gpt-5.1", "content": "..."},
      {"site": "lb-gemini-3-pro", "content": "..."},
      {"site": "lb-claude-4.5-sonnet", "content": "..."},
      {"site": "lb-kimi-k2.5", "content": "..."}
    ],
    "aggregation": "综合分析结果..."
  }
}
```

**brief** (Siri 用):
```json
{
  "summary": "本次跑步5.2km，配速6'09\"，心率控制良好。建议拉伸15分钟，重点小腿和髂腰肌。明天建议轻松恢复。"
}
```

## 分析 Prompt 模板

```
你是运动科学专家。请分析以下运动数据并给出专业指导：

【本次运动】
- 类型：{workout_type}
- 距离：{distance}km / 时长：{duration} / 配速：{pace}/km
- 心率：平均{avg_hr} / 最大{max_hr} / 静息心率{resting_hr}
- 心率区间：热身{z1}% | 燃脂{z2}% | 有氧{z3}% | 无氧{z4}% | 极限{z5}%
- 训练效果：有氧{ae_effect} / 无氧{an_effect}
- 消耗：{calories}大卡

【近期训练历史】
- 本周第{week_count}次运动，上次{last_type} {last_distance}km 配速{last_pace}
- 近30天平均周运动量：{monthly_avg}

【用户画像】
- {gender}，{age}岁，体重{weight}kg
- 静息心率{resting_hr}，最大心率参考{max_hr_ref}

请输出：
1. 本次训练总结（表现评价，与历史对比）
2. 心率区间分析（分布是否合理，训练效果评估）
3. 跑后拉伸方案（具体动作名称 + 每个动作持续时间，针对本次运动类型定制）
4. 恢复建议（营养补充、水分、休息安排）
5. 下次训练建议（建议时间间隔、强度、运动类型）
```

## Chat Action 集成

### System Prompt 新增

```
当用户表达运动/跑步/锻炼/训练完成的意图（如"跑完了"、"刚练完"、"运动结束了"、
"帮我分析刚才的运动"、"同步一下运动数据"等），输出 action：

<<<ACTIONS:[{"type": "workout_analyze", "workout_type": "根据用户描述判断"}]>>>

workout_type 可选值：running / cycling / swimming / hiit / strength / yoga / other
如用户未明确说明运动类型，默认为 "other"，系统会自动检测最新记录的类型。
```

### Action Handler

在 `_execute_actions()` 中新增分发：
```python
elif action_type == "workout_analyze":
    result = await self._handle_workout_analyze_action(action, user_id)
```

Handler 内部调用 `PostWorkoutService`，将返回的分析结果格式化为对话内容追加到回复中。

## 关键约束

| 约束 | 实现方式 |
|------|----------|
| Garmin 缓存登录 | 复用 GarminConnectService token cache (23h有效) |
| Garmin 最多3次轮询 | 每次间隔10s，3次无数据返回"未检测到新运动记录" |
| OpenClaw 轮询 ≤6次 | 每10s一次，超时返回 partial 结果或提示稍后查看 |
| API Key 安全 | OpenClaw api_key 存入 .env，不硬编码 |
| 扩展性 | workout_type 参数支持后续骑行/游泳等不同 prompt 模板 |

## 文件变更清单

| 文件 | 类型 | 变更说明 |
|------|------|----------|
| `backend/app/services/post_workout_service.py` | 新建 | 核心业务逻辑：sync → detect → prompt → analyze → format |
| `backend/app/services/openclaw_client.py` | 新建 | 封装 OpenClaw analyze API 提交+轮询 |
| `backend/app/api/workout.py` | 修改 | 新增 post_run_analyze 端点 |
| `backend/app/services/chat_service.py` | 修改 | system prompt 增加 workout_analyze action + handler |
| `frontend/src/app/ai-assistant/page.tsx` | 修改 | 新增"运动完成"快捷按钮 + 运动分析卡片渲染 |
| `frontend/src/services/workoutApi.ts` | 修改/新建 | 新增 API 调用方法 |

## 未来扩展

- Apple Watch 独立触发（Garmin → 数据就绪 → Watch App 推送）
- 运动类型自动识别（无需用户指定，从 WorkoutRecord 直接读取）
- 训练周期分析（周/月维度的训练负荷管理）
- 与智能计划联动（运动完成自动更新计划进度）
