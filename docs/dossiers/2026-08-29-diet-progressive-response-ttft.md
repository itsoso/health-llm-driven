# Dossier: 饮食记录渐进式响应与 TTFT 优化

| 字段 | 值 |
|---|---|
| slug | `diet-progressive-response-ttft` |
| 创建日期 | 2026-08-29 |
| 当前阶段 | S4 发布前准备 |
| 状态 | ready_to_deploy |
| 负责 | Codex |
| 反馈环 | 生产内容安全时延基线 + Backend/Mobile 契约测试 + 部署后分意图里程碑 |

## S0 · 用户需求

> 每次回复时长很长，要优化用户感知 TTFT；需要思考过程并分两步或多步作答，尤其是饮食记录。按照建议实施。

这里的“思考过程”被落实为可验证的执行阶段摘要，而不是暴露模型原始思维链。

## S1 · 基线与根因

- 采样时生产基线：`077ef949e44227f69c6b5fa22bb874843a747635`；当前开发已重放到 CI 成功的 `origin/main` `902ea3f59`。
- 最近 72 小时 34 个内容无关 `[perf.agent]` 样本：总耗时 P50 33078ms、P90 73714ms；文本 TTFT P50 29823ms、P90 53222ms。
- 前置编排 P50 225ms，不是主要瓶颈；LLM P50 21437ms，多轮回合总耗时 P50 34821ms。
- Mobile 已在本地立即插入通用“正在理解”占位，Backend 也立即发送 `accepted`，但两者缺乏饮食语义阶段，用户仍然感知为卡住。
- 为避免“模型声称已记录但实际未写入”，现有突变回合会缓冲模型内容直到写入回执验证。这条安全约束必须保留。
- 当前日志没有意图标签，也没有首个有用进度/写入验证里程碑；上述基线是通用 Agent 基线，不能冒充饮食专属数据。
- 明确文字记餐已经有确定性目标编译器、营养估算器、验证器、写入网关和回执收口，但仍在首轮等待 LLM 选择工具，存在可消除的决策耗时。

## G1 · 准入

- first_class_objects: `WriteIntent`、`ExecutionEvent`、`HealthTwin`。
- core_loop_step: capture -> interpret -> persist -> verify。
- safety_level: privacy-sensitive health write。
- **裁决: PASS。** 用户明确批准实施；这是现有核心闭环的性能和可感知性优化，不新增医疗结论或自动化权限。

## G2 · 可行性与安全压测

- 只让现有目标编译器确认的 `simple_health_record/diet/create` 且无附件输入进入确定性快路径。
- 快路径不另建写入逻辑，复用现有营养估算、目标守卫、validator、ToolGateway、write checkpoint、verified receipt 和卡片构建。
- 营养估算是独立模型调用，设置 3 秒硬超时；内层取消 provider 协程，外层同时防止线程继续占用用户回合。
- 性能数据分开记录工具决策 LLM 轮次、营养估算次数/超时/模型、总模型等待时和总调用次数，不把跳过工具决策误报成“零模型成本”。
- `diet_verified` 和“已写入”必须在 verified receipt 后发送；估算/验证失败回退既有恢复流程，不能静默成功。
- 图片、复合指令、问题、否定或歧义输入不进入文字快路径；低置信度照片继续要求人工确认。
- Mobile 用单一进度面板更新阶段，不制造多条消息；阶段文案不包含原始思维链。
- 埋点禁止携带输入、食物、图片、数值、记录 ID 或用户 ID。
- **裁决: PASS。** 方案缩短一条高置信度路径且不放宽写入、隐私、幂等或确认边界。

## S2 · 设计

- Backend 增加饮食语义进度阶段和内容无关性能里程碑。
- 明确文字记餐的第 0 轮直接注入确定性工具计划，后续仍走统一执行管线。
- Mobile 将新增阶段映射为中文，并在既有 `ThinkingStepsPanel` 中展示当前和已完成阶段。
- Mobile 上报 `agent_turn_milestone`：`local_feedback`、`server_accepted`、`first_useful`、`write_verified`。
- 无数据库迁移；SSE 与客户端事件均为向后兼容的加法协议。

## G3 · 测试

- 已按 TDD 先得到 RED：后端缺少里程碑白名单和快路径；Mobile 缺少阶段映射、严格事件清洗和单面板阶段累积。
- Backend 受影响面分两个隔离进程回归：493 passed + 334 passed，合计 827 passed。覆盖内层模型取消、外层回退、一次写入、verified receipt 后成功阶段、同 `client_turn_id` 重试无二次估算/写入、图片确认和饮食 API/写入适配器。
- Mobile 全量回归：297 suites passed；2616 passed、1 skipped；发布预检相关面额外 43 suites / 737 tests passed；复审修复后 Hook 84 tests passed。
- TypeScript `tsc --noEmit`、API type generation `--check`、Python `ruff check`/`py_compile`、`git diff --check` 通过。
- Mobile lint 为 0 errors / 93 个仓库既有 warning；改动文件聚焦 lint 为 0 errors / 7 个既有 warning。
- System Map、Mobile Navigation、文档漂移、密钥扫描、Dossier 一致性、Agent Skill 治理和 22 项发布契约通过；生成产物无需更新。
- 主干 CI 成功基线：`902ea3f59`。
- **裁决：PASS。**

## G4 · 评审

- 快路径只接受 `simple_health_record/diet/create`、无附件、非只读且 Runtime 未阻断的目标。
- 只有营养估算得到完整、有界 payload 才跳过工具决策模型；估算不可用立即回退既有模型修复链。
- 所有写入继续通过目标守卫、validator、ToolGateway、write checkpoint 与 verified receipt；`diet_verified` 在 verified `tool_result` 之后发送。
- 图片路径只新增“已保存 / 正在识别 / 请核对”阶段，低置信确认边界不变。
- 客户端里程碑为严格枚举的阶段、整数耗时、动作类别和图片布尔值；前后端都拒绝内容字段。
- 首轮评审发现并已修复：营养模型未硬超时、模型成本记账不完整、通用 SSE 状态覆盖饮食阶段、Mobile 本地饮食分类漏掉“午餐牛肉饭”/“桃子一个”。
- 修复后复审额外验证了营养查询后缀不污染记餐 TTFT 分桶、provider 模型名埋点，以及 Mobile `done.thinking_steps` 与本地饮食阶段去重合并。
- 独立复审结论：`APPROVE`，无 Critical / Important 阻断项。
- **裁决：PASS。**

## G5 · 部署健康

- PENDING。要求提交并推送干净主干、目标 SHA 一致、后端部署健康闸通过；Mobile 纯 JS/TS 改动走 production OTA。

## G6 · 上线验证

- PENDING。要求生产 SHA/OTA 可追溯，真实文字记餐验证阶段顺序与回执后成功，并在收集至少 30 个饮食样本后复核分位数。
