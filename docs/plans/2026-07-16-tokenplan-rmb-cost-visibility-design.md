# TokenPlan 人民币成本可见性设计

## 目标

让用户在 Mobile、Web、Mac 的每次 Agent 回复上直接看到人民币金额，同时让 Admin 能按用户、模型和调用方观察套餐容量成本。Token 数与按量价降级为展开后的技术明细。

## 已确认口径

- 高级套餐固定月费：`¥698`。
- 月度容量：`100,000 Credits`。
- 容量单价：`¥0.00698 / Credit`。
- 单次调用先按模型、输入、输出和缓存估算 Credits，再换算为人民币。
- 客户端主金额显示为 `本次约 ¥x.xx`；`约`不可省略，直到阿里云提供可逐次对账的 Credits 真值。
- 现有 `cost_cny` 保留为按量价格对照，不再作为 TokenPlan 主金额。

## 估算模型

阿里云公开示例中，qwen3.6-plus 的输入、缓存和输出费用对应 `100 Credits / ¥1` 的按量价值。系统据此使用公开人民币按量单价估算 Credits：

```text
按量价值 = 非缓存输入 Token × 输入单价
         + 缓存输入 Token × 输入单价 × 缓存折扣
         + 输出 Token × 输出单价

估算 Credits = 按量价值 × 100
套餐容量成本 = 估算 Credits × 698 / 100000
```

公开价格表不存在的模型不得伪造套餐金额，回退为按量价对照并标记无套餐估算。

## 数据契约

在既有 `llm_usage` 中追加：

- `tokenplan_credits_estimate`
- `tokenplan_cost_cny`
- `tokenplan_cost_estimated`
- `tokenplan_cost_source`
- `tokenplan_monthly_fee_cny`
- `tokenplan_monthly_credits`

字段纯附加，旧客户端保持兼容。原始 Token 与 `cost_usd/cost_cny` 不改写。

## 三端展示

折叠态：

```text
约¥0.02 · 29.2s · 5轮 · qwen3.7-plus
```

展开态：

```text
套餐折算    约¥0.02
按量价对照  约¥0.03
Token       输入 1.8k · 输出 620 · 总 2.5k · 5次
```

Admin 总览显示固定月费、窗口内套餐容量折算、按量价对照和节省估算；用户/模型/调用方列表按容量成本排序和展示，不再用原始 Token 等权代表成本。

## 边界

- 本功能是成本观测，不是面向用户收款、账单或额度扣减系统。
- 失败重试产生的模型消耗照常计入。
- 仅处理费用展示，不改变模型路由、健康建议或 Agent 写路径。
- 阿里云控制台仍是 Credits 真值；后续可增加明细导入进行日级对账。

