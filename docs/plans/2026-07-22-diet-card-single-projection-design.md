# 饮食卡单一投影设计

## 背景

用户在记录饮食后仍会看到两张饮食卡。当前链路同时存在服务端持久化、服务端卡片组合和 Mobile 流式收尾三种重复源；此前的 `5b8dc161b` 只覆盖“上下文餐食已经保存后，模型又调用 `health_record`”这一条分支，因此无法覆盖正常无工具重放、历史恢复和 Mobile 本地兜底。

## 已复现根因

1. `AgentExecutor` 持久化卡片时会移除临时 `photo_url`；API 收尾却先把已清洗历史卡与仍带 URL 的实时卡按完整 JSON 合并，再统一清洗。两张卡在合并时不同、清洗后相同，最终历史里留下两个相同描述符。
2. `recorded_intake_kinds` 只把 `record` / `record_quality` 当成已占位的摄入卡，不识别已有的 `diet_draft`。上下文图片已经给出 recorded 或 pending 饮食卡时，query builder 仍可能追加一个低优先级 legacy `diet_draft`。
3. Mobile 已收到 SSE `card` 后，如果 `done.cards` 缺失或为空，仍运行本地 `dispatchCard`。`health_record` 会命中本地 `RecordCardSpec`，于是服务端饮食卡旁又出现一张本地 `record/diet`。
4. 确定性的 `diet_daily_summary` 通过正文 `reva-ui` fence 渲染，但 API 的“正文已经拥有可视化”判断不识别该 fence，仍可能追加 legacy `diet` 快照。

## 核心不变量

- 同一 assistant turn 的卡片只允许有一个服务端权威终态投影；流式卡是临时投影，不是第二份业务结果。
- 去重必须发生在持久化归一化之后，不能用会被随后删除的临时字段决定身份。
- 已有显式/上下文摄入卡时，低优先级 query 派生草稿不得再代表同一种摄入行为。
- 确定性结构化可视化已经回答查询时，不再追加同类 legacy 快照。
- 去重只收敛同轮、同一投影来源；不得按 `diet` 类型粗暴删除不同餐次、不同记录或其他轮的合法卡片。

## 设计

### 服务端持久化

`_persist_done_cards` 先分别对历史卡和本轮卡执行 `cards_for_persistence`，再调用 `_merge_card_descriptors`。这样签名 URL 等临时字段先被移除，语义相同的描述符会在唯一一次 canonical merge 中收敛为一张。

### 服务端组合

引入“本轮已被卡片表示的摄入类型”语义，识别 `record`、`record_quality` 和 `*_draft`，并递归读取 `cards_group`。API 组装 query cards 前，用该集合抑制同类型 legacy draft。上下文 `diet_draft` 无论是 `recorded=true` 还是 pending，都占据 diet 投影槽位，但不改变其写入状态。

`_answer_owns_its_visualization` 解析闭合的 `reva-ui` JSON fence，仅对确定性已注册的可视化类型返回 true；任意字符串或未知 type 不触发抑制。

### Mobile 流式收尾

- SSE `card` 继续立即显示，保证渐进反馈。
- `done.cards` 非空时，把它作为当前 `sourceTurnId` 的权威快照：删除该轮临时卡，再一次性插入最终卡组。
- `done.cards` 为空/缺失但本轮已经收到服务端卡时，保留已有流式卡，并跳过本地 `dispatchCard`。
- 只有整轮从未收到任何服务端卡、终态也没有卡时，才允许旧的本地关键词 fallback。
- 只处理当前 `sourceTurnId`，不影响前一轮仍待确认的 medication 卡等跨轮状态。

## 失败与安全边界

- 卡片持久化失败不伪造第二张本地“已记录”卡。
- 不改变饮食写入、确认、回执或幂等契约；本次只改变卡片投影和持久化去重顺序。
- 未知/不合法卡仍由既有 registry 丢弃。
- 不按业务类型全局去重，因此同轮真正不同的多记录卡和跨领域卡继续保留。

## 验证

- 后端：临时 URL 归一化去重；上下文 recorded/pending 两态抑制 legacy draft；确定性 diet summary fence 抑制 legacy snapshot；不同卡不误删。
- Mobile：`card -> done(no cards)` 只保留服务端卡且不调用 fallback；streamed 旧描述符 + done 新描述符最终只保留权威新版。
- 回归：相关 backend pytest、完整 `useChatEngine` suite、Mobile TypeScript、`git diff --check`。
