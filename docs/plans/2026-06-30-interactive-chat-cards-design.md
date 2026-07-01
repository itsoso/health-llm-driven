# 2026-06-30 Interactive Chat Cards Design

## 目标

把阿衡对话里的动态 UI 卡片从“可视化结果”升级为“可确认、可修改、可执行、可反馈”的 Health OS 交互组件。第一阶段只做两个最高频闭环:

- `quick_record_card`: 对话快速记录后的确认卡。
- `diet_draft`: 饮食记录的专用确认卡,承接“午餐吃了…”这类自然语言输入,先展示估算营养和确认动作,用户确认后才写入 `/diet/records`。
- `next_action_card`: 当前最重要行动的执行卡。

## 设计原则

- 卡片是小型状态机,不是静态报告。
- 数据和动作必须由后端确定性生成或由既有 `WriteIntent` / Agenda contract 承接;LLM 不获得任意 endpoint 执行权。
- 导航类 `route.open` 可直接展示。
- 写动作必须 `requires_manual_confirm=true`;前端继续 fail-closed。
- 高风险动作如用药、剂量、预约、购买、IoT 控制只生成草稿或进入详情,不一键执行。

## Action Contract v1

在现有 `ChatCardActionDescriptor` 上增加可选交互元数据:

```ts
{
  id: "confirm_pushups_30",
  label: "确认记录",
  action: "write_intent.confirm",
  style: "primary",
  requires_manual_confirm: true,
  payload: { write_intent_id: 123 },
  confirmation: {
    title: "记录 30 个俯卧撑？",
    detail: "将写入今天的运动记录",
    confirm_label: "确认记录",
    cancel_label: "再看看"
  },
  optimistic: true,
  disabled_reason: null
}
```

前端行为:

- 有 `disabled_reason` 时按钮可见但禁用,显示原因。
- 有 `confirmation` 且是写动作时,点击先弹确认框。
- `optimistic=true` 只影响按钮 loading/已执行视觉,不能绕过后端结果。
- 失败必须 toast 错误,不能静默。

## quick_record_card

用途: 用户说“我刚做了 30 个俯卧撑”“午餐吃了牛肉面”“喝了 300ml 水”后,对话中出现可确认记录卡。

饮食类高频入口优先走 `diet_draft`,因为饮食有餐次、食物、热量、蛋白/碳水/脂肪/纤维、餐后行动等专用字段,比通用记录卡更适合直接确认与修正。

展示:

- 记录类型: 饮食 / 饮水 / 运动 / 体重 / 血压 / 症状 / 补剂。
- 结构化摘要: 项目、数量、时间、来源。
- 不确定字段: 以“待确认”标识。

交互:

- `确认记录`: `write_intent.confirm`,必须 manual-confirm。
- `修改`: `route.open` 到记录页并带预填上下文。
- `忽略`: `write_intent.dismiss`,必须 manual-confirm。

## next_action_card

用途: 用户问“我现在该做什么”“下一步行动是什么”时,展示当前最重要行动。

展示:

- 行动标题、时间窗、优先级、为什么现在。
- 验证指标和验证窗口。
- 健康边界文案。

交互:

- `完成`: `agenda.complete`,必须 manual-confirm。
- `稍后`: 第一阶段先 `route.open` 到 Agenda;后续扩展 snooze endpoint。
- `跳过并说明`: 第一阶段先 `route.open` 到 Agenda;后续扩展 skip reason sheet。
- `问为什么`: `route.open` 回 Chat 并带 prompt。

## 第一阶段范围

- 扩展前端 action type,渲染确认弹窗/禁用态/loading 态。
- 给 `runtime_agenda` 的 next action 添加 `agenda.complete` 写动作。
- 新增 `quick_record_card` 作为 `record` 的交互升级协议,优先消费后端下发 actions。
- 不新增高风险写接口。
- 不做 undo 后端语义;视觉上预留,实际以服务端结果为准。

## 验收

- unsafe 写动作仍被 UI 过滤。
- safe 写动作点击前出现确认框。
- 确认后调用现有 dispatcher 并刷新 Today/Agenda/WriteIntent。
- `quick_record_card` 可以展示确认/修改/忽略。
- `next_action_card` 可以完成当前行动,无 source 时禁用完成按钮。
