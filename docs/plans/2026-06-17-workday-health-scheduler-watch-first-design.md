# Workday Health Scheduler Watch-first Design

日期: 2026-06-17
状态: v0.1, 已确认 Watch App 优先
范围: Apple Watch, Health Agenda, HealthProtocol, ActionRanker, 后续 Mobile/Mac/Web

## 0. 目标

把“进公司之后按日程提醒我做俯卧撑、久坐打断、饮食、补剂和药物”做成一个可持续的日内健康调度能力。

第一阶段优先 Apple Watch, 因为 Watch 是最接近执行现场的设备:

- 到公司后立刻提醒一个低摩擦启动动作。
- 久坐或会议空档后提醒 1 个微运动。
- 午餐后提醒步行或轻活动。
- 用药、补剂、饮水、饮食记录在腕上一键确认。
- 身体状态差时自动降级, 不硬推每小时 20 个俯卧撑。

## 1. 产品判断

固定规则“每小时 20 个俯卧撑”不应作为系统核心。它适合作为一个用户偏好, 但不能直接作为默认执行策略。

默认策略应是自适应:

| 状态 | 动作策略 | 示例 |
|---|---|---|
| Green | 可做标准力量微运动 | 俯卧撑 12-20 个, 深蹲 15 个 |
| Yellow | 降级到低冲击 | 上斜俯卧撑 6-10 个, 步行 5-10 分钟 |
| Red | 停止力量推动 | 站立、轻走、拉伸、症状观察 |

原因:

- 中年人更需要长期可坚持的复利动作, 不是一次高强度热情。
- Watch 可以读取或接收 readiness, RHR, HRV, sleep, training load 等状态信号。
- 日程和会议会打断执行, 固定整点提醒容易制造失败感。
- 用药和补剂必须按已确认方案执行, 不能由 AI 自动调剂量。

## 2. Watch-first 体验

### 2.1 今日状态

Watch 首页只显示三件事:

1. 今日就绪度: green / yellow / red / gray。
2. 当前最该做的一件事。
3. 待完成数量。

动作出现时必须可以直接处理:

- 完成。
- 稍后。
- 跳过。
- 如需要, 跳过时记录原因。

v1 先支持完成, 稍后/跳过进入后续批次。

### 2.2 工作日微运动

系统把微运动建模为 HealthProtocol, 通过 Health Agenda 投影到 Watch。

示例协议:

```json
{
  "domain": "training",
  "name": "到公司后俯卧撑 12 个",
  "cadence": "daily",
  "time_window": "morning",
  "completion_mode": "one_tap",
  "source_model": null
}
```

完成后第一阶段只写 `HealthProtocolEvent`, 不伪造运动记录。原因是“做了一个协议动作”和“完成一次正式运动训练”不是同一事实。

后续如果需要记录 reps, 再引入带 payload 的运动协议完成:

```json
{
  "exercise_type": "俯卧撑",
  "reps": 12,
  "intensity": "micro"
}
```

### 2.3 到公司触发

触发源分三层:

| 层 | 触发 | v1 |
|---|---|---|
| L0 | 固定工作日上午窗口 | 可以先做 |
| L1 | iPhone 位置围栏 / 公司 Wi-Fi / Mac 解锁 | 后续 |
| L2 | 日程 + 会议空档 + 专注模式 + 可穿戴状态联合判断 | 后续核心 |

Watch App v1 不直接做位置判断。它消费后端已经生成的 `top_action`。

### 2.4 提醒密度

默认工作日提醒预算:

- 微运动: 3-5 次/天。
- 用药/补剂: 按方案必要提醒。
- 饮食: 饭后记录或饭后步行。
- 补数据: 低频, 不和微运动抢通知。

通知疲劳是产品硬约束。用户连续跳过时, 系统应降低强度或减少频次。

## 3. 系统设计

### 3.1 数据流

```text
Calendar / Workday / Wearables / User Preferences
  -> WorkdayHealthScheduler
  -> HealthProtocol or Daily Agenda Action
  -> agenda_service.today()
  -> watch_summary.build_watch_summary()
  -> WatchSummary.top_action
  -> Watch App one-tap complete
  -> HealthProtocolEvent
  -> Weekly review / ActionRanker adjustment
```

### 3.2 v1 契约

本次先打通 Watch App 执行契约:

- `training`, `activity`, `exercise` 类型的 HealthProtocol 可以在 Watch 上一键完成。
- 非 `health_protocol` 来源的训练建议仍只读, 例如 `training_decision`。
- 完成端点继续只接受 `agenda-health_protocol-{id}`。
- 训练/活动协议如果没有 `source_model`, 完成只写协议事件, `written = "none"`。

这避免两个错误:

- 不把恢复建议误标为已完成。
- 不把微运动协议伪装成完整运动记录。

### 3.3 后续 WorkdayHealthScheduler

后续新增服务负责生成当天微运动动作:

```python
WorkdayHealthScheduler.generate_today(user_id, date)
```

输入:

- 工作日和到公司时间偏好。
- 日历忙闲窗口。
- 今日 readiness / sleep / RHR / HRV / training load。
- 最近 7 天完成率和跳过原因。
- 疼痛、疲劳、急性病安全信号。

输出:

- 3-5 个微运动候选。
- 1 个当前 top action。
- 每个动作的强度、窗口、降级理由。

## 4. 分期

### P0: Watch 可完成训练/活动协议

- 更新 Watch Core 可完成 kind。
- 保持非 health_protocol 训练建议只读。
- 后端测试覆盖训练 HealthProtocol 进入 top_action。

### P1: Watch UI 运动动作体验

- top action tile 展示强度和窗口。
- 支持稍后、跳过。
- watch event 增加 snoozed/skipped。

### P2: WorkdayHealthScheduler 后端

- 生成工作日微运动计划。
- 根据 readiness 降级。
- 接入 agenda。

### P3: 日程和到公司触发

- Mobile 位置围栏或 Mac 解锁事件。
- 日历忙闲避让。
- 按用户工作时间偏好排程。

### P4: 饮食、补剂、药物深度计划

- 午餐后步行和饮食记录联动。
- 补剂只执行已确认方案。
- 药物严格走医生处方和 Medication Autopilot。

## 5. 安全边界

- Red 状态不推力量训练。
- 胸痛、头晕、异常心率、血压异常时不推荐俯卧撑。
- 用药提醒只做执行和依从, 不做开方或调量。
- 补剂提醒必须经过相互作用和证据边界检查。
- Watch 不持 token, 继续经 iPhone 中继。

## 6. 成功指标

- `watch_movement_action_shown`
- `watch_movement_action_completed`
- `top_action_completion_rate`
- `micro_action_skip_rate`
- `skip_reason_too_tired_rate`
- `notification_disable_rate`
- 4 周后的体重、腰围、RHR、HRV、步数、训练负荷趋势

第一阶段的工程成功标准:

- Watch 能正确把训练/活动 HealthProtocol 渲染为可完成。
- 非协议训练建议仍不可完成。
- 完成请求仍经过后端鉴权和所有权校验。
- 后端和 Watch 测试通过。
