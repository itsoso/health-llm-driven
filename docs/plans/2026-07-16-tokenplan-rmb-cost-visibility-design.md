# TokenPlan 人民币成本可见性设计

## 目标

让用户在 Mobile、Web、Mac 的每次 Agent 回复上直接看到人民币金额，同时让 Admin 能按用户、模型和调用方观察套餐容量成本。Token 数与按量价降级为展开后的技术明细。

## 已确认口径

- 高级套餐固定月费：`¥698`。
- 月度容量：`100,000 Credits`。
- 容量单价：`¥0.00698 / Credit`。
- 单次调用按模型公开原价、输入、输出和已知缓存规则估算 Credits，再换算为人民币。
- 客户端主金额显示为 `本次约 ¥x.xx`；`约`不可省略，直到阿里云提供可逐次对账的 Credits 真值。
- 现有 `cost_cny` 保留为按量价格对照，不再作为 TokenPlan 主金额。

## 估算模型

阿里云公开示例中，模型原价与 Credits 近似对应 `100 Credits / ¥1`。系统据此用公开原价估算 Credits；当前按量活动价另算为对照，避免把两类活动折扣重复叠加：

```text
Credits 计价基数 = 非缓存输入 Token × 原价输入单价
                 + 缓存输入 Token × 原价输入单价 × 已知缓存折扣
                 + 输出 Token × 原价输出单价

估算 Credits = Credits 计价基数 × 100 × Credits 活动系数
套餐容量成本 = 估算 Credits × 698 / 100000

按量价对照 = Token × 当前按量活动价 × 按量活动系数
```

当前 `qwen3.7-max` 在活动截止前使用隐式缓存 20%、Credits 5 折和按量 5 折；`qwen3.7-plus` 的按量对照使用当前 8 折。系统没有创建显式缓存，因此其他模型出现 `cached_tokens` 但套餐文档没有明确计费口径时，不猜测金额。公开价格表不存在的模型同样不得伪造套餐金额，统一标记无套餐估算。

## 数据契约

在既有 `llm_usage` 中追加：

- `tokenplan_credits_estimate`
- `tokenplan_cost_cny`
- `tokenplan_payg_value_cny`
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

Admin 总览显示固定月费、窗口内套餐容量折算、按量价对照和节省估算；用户/模型/调用方列表展示容量成本，不再用原始 Token 等权代表成本。

## 边界

- 本功能是成本观测，不是面向用户收款、账单或额度扣减系统。
- 失败重试产生的模型消耗照常计入。
- 仅处理费用展示，不改变模型路由、健康建议或 Agent 写路径。
- 阿里云控制台仍是 Credits 真值；后续可增加明细导入进行日级对账。
