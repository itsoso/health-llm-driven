# Prompt 预算与公共任务执行优化

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 本地验证完成，分支交接；未发布 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 范围准入

裁决：PASS。范围是用户授权的既有体验、路由和上下文传输优化及其分支交接，不新增产品入口、健康对象、用户数据权限或自动发布行为。权限、质量地板、写入回执和安全输出边界继续由原系统负责；失败候选不得进入运行路径。本文记录本地实现与证据，不代表全量 CI、生产效果或发布准入。

状态：本地实现、验证与独立安全复审完成；未提交、推送或部署。用户授权：按上一轮生产 prompt 审计规划执行。Controller：Health Harness；overlay：safety。沿用独立 worktree，保留此前 Web 和 Laya 优化。

## 基线与目标

本轮 fetch 后远端 main 为 `f201d85b4f0d726b09ff0f8b16acf403d70f3e57`；工作区起点为 `a8853dea1207163aaa412974dddfbc050ce3eeea`。两者之间仅有 voice release dossier 文档差异，相关执行代码一致。真实请求基线见 [审计](../reviews/2026-10-04-prompt-token-audit.md)：工具 schema 占主要输入，已有工具选择器未接入实际 provider 请求；独立天气被送入通用健康流程；food recognition caller 未恢复，污染后续用量归因。

范围是既有任务执行与观测修复，不增加健康对象、授权、数据接收者或自主写入。目标：同一合成公共请求输入缩减至少 30%，天气只保留一次生成调用；健康风险地板、附件、写操作和模糊追问不被公共路径接管。若出现越权、数据丢失、健康边界退化或占位天气被当成真值，停止发布。

## 实现

- `caller_scope` 在成功、异常、嵌套调用后恢复 caller；食物文本识别的线程桥接保留上下文中的用户与 AI 同意状态。
- `_call_llm` / `_call_llm_stream` 实际发送前裁剪工具 schema，只取已有授权集合的子集。Pi 与网关保留既有权限与执行职责；附件、未知域、依赖历史和写入保留原集合。
- 仅完整匹配的独立天气或自我介绍进入紧凑提示词，不发送健康历史、不请求 Laya、不加知识库。城市只接受有限闭集；其余请求走原流程。风险分类仍先执行，未放宽 fast 模型地板。
- 天气通过原工具网关读取，再单次生成答案；缺少位置直接询问城市，失败直接说明未完成。拒绝 unavailable 默认温度、空预报，移除附带的运动建议。HTTP 与进程内读取使用同一可用性契约。
- prompt 预算日志补充 run_id、request_index、tools/answer 阶段，仅记录脱敏关联元数据。现有字符近似值仍不等于 tokenizer token；直接 agent gateway 分支的日志覆盖仍有限。

公共路径与工具裁剪复用 `DOMAIN_PROMPT_OPTIMIZATION`。代码默认 false；上轮审计读取的生产配置为 true，本轮没有改生产配置。回退可关闭此开关，caller 修复不受影响。Laya 的独立置信度改动沿用上一轮候选；本轮对无需决策的闭集任务省去调用，未调整生产超时或置信度阈值。

## 真实 API 用量

通过真实 Pi 捕获优化前后固定合成请求帧，以相同 `qwen3.8-max` API 重放，逐次确认 `token_source=api`。基线的工具轮次由测试 provider 驱动；真实回复未反向驱动下一帧，因此属于固定请求回放，不是端到端线上 A/B。

| 合成请求 | 优化前输入 token | 优化后输入 token | 输入减少 | 模型调用 |
| --- | ---: | ---: | ---: | --- |
| 杭州今天天气怎么样 | 22,964 | 660 | 97.13% | 2 → 1 |
| 请介绍一下你自己 | 11,287 | 515 | 95.44% | 1 → 1 |

天气候选回答准确引用合成工具结果中的杭州、10:00、多云、18℃，未添加运动建议；介绍候选保留授权及诊断边界，未引用健康历史。两条样本不能证明总体线上降幅、临床质量、缓存后账单节省或 P95/P99 改善。原始请求和完整回复仅留本机临时文件，仓库只保存去标识聚合 [证据](../reviews/2026-10-04-prompt-budget-evidence.json)。

可复现 payload 捕获：使用隔离测试数据库运行 `test_public_payload_replay`，设置 `REVA_PROMPT_REPLAY_OUTPUT` 输出字符/调用统计，`REVA_PROMPT_LIVE_PAYLOADS` 输出合成 provider 请求帧。真实 API 重放使用现有 harness 的内存测试用户、审计同意流程与模型工厂，不绕过同意校验。

## 验证与边界

- 实现前红测试覆盖实际 provider 工具投影、冗余 Laya 调用、天气缺失位置、失败后多余生成和预算日志关联；安全复审补充了实际 unavailable 天气/预报红测试，修复后通过。
- 主链路、Gateway、任务分类、安全路由、重试、读修复、Pi 及新增相关测试：4,057 passed。
- 最终天气、公共分类、provider 请求、caller、日志定向验证：100 passed。无位置、HTTP 失败、默认天气和空预报均覆盖。
- live LLM gate：invariants 12/12、health core 50/50、真实 orchestrator 5/5，评分 0.98；trajectory contract 12/12、goldens 9/9。该 harness 内存库未建用量日志表，存在既有日志持久化警告；不能据此声称用量持久化已验证。独立公共回放显式建表并取得 API 真值。
- LLM change gate 本地通过；System Map 已重生成并通过漂移检查；Ruff 无新增问题，executor 保留远端已有 11 条；`git diff --check` 通过。
- 独立安全复审 GO，审查中发现的占位天气问题已修复。仅本地/合成验证，无生产发布、全 CI、真实用户任务成功率或设备验收结论。

发布后仍需同窗口分任务观察真实 input/cache tokens、调用轮数、任务完成率及 P95；不要把本轮小样本改善外推为所有健康问题的优化幅度。若任务完成率下降、错误天气重新出现或长尾恶化，关闭预算开关并回查关联 run_id。
