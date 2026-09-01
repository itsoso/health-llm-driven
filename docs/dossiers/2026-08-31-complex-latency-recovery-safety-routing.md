# Dossier: 复杂回答时延与恢复数据安全升档

| 字段 | 值 |
|---|---|
| slug | `complex-latency-recovery-safety-routing` |
| 创建日期 | 2026-08-31 |
| 当前阶段 | G5 发布准备；后端先行、Mobile OTA 待后端健康检查 |
| 状态 | release_authorized |
| 负责 | Codex / 用户确认 |
| 反馈环 | Backend pytest + LLM regression gate + iOS Simulator 三档验收 |

## 2026-08-31 Correction Block · TTFT 与首个有用信息

用户在上一切片后继续要求优化速度与 TTFT。本修订重新打开 S2/S3/G3/G4；此前 G5 发布授权不自动覆盖这批新代码，且本轮明确不执行 commit、push、deploy 或 OTA。

2026-08-31 用户随后在本轮明确回复“发布”，重新授权本批代码的 commit、push、后端 deploy 与 Mobile OTA；安全和质量 Gate 仍必须全部通过，后端发布与健康读回必须先于 OTA。

### 新发现

- 旧 `llm_ttft_ms` 在 Health Evidence 编译之后才起钟，不能代表用户请求入口到首段验证正文的端到端 TTFT。
- Health Evidence 正文为安全而完整缓冲；首个正文 token 发生在完整生成和确定性验证之后，因此其 TTFT 长尾受完整输出长度影响。
- `accepted/status` 能改善等待感，但不能计作正文 TTFT；结构化 `answer_evidence` 才是可核对的首个有用信息。

### 修订决策

- 新增端到端 TTFT/total、turn setup、health compile 和 first evidence 指标，保留旧字段兼容。
- balanced 使用 512 thinking token；high-stakes 与 deep analysis 不封顶。
- Health Evidence 最终回答上限 1200 token，不限制思考且不绕过验证器。
- `request_persisted` 后先发 owner-scoped、schema-bounded 的 `answer_evidence.v1`，Mobile 在流中即时落到 assistant 气泡。
- 三个行为各有独立回退配置；关闭早期事件不影响 done/历史依据。

### 当前验证证据

- TDD RED：后端 6 个行为断言和 Mobile 3 个跨端断言先因能力缺失失败；两个回退断言随后单独 RED。
- TDD GREEN：后端首批 14/14 通过；回退 2/2 通过；Mobile SSE/parser/hook/transparency 131/131 通过。
- 截断安全回归 1/1 通过：provider `finish_reason=length` 时不释放半截模型文本，只发布确定性 verifier 重建内容，并把回合标记为 `interrupted`。
- 独立 safety-privacy reviewer：**GO**。确认 owner isolation、持久化后发送、投影 fail-closed、verifier 唯一正文释放点、三项独立回退均成立。评审发现 `ChatBubble` 的旧终态门控会让 early evidence 到达后仍不可见；已先 RED 复现，再改为流中即时显示，并在流式/中断状态禁用复制分享、为未完整回复加核对提示。相关 UI 40/40 通过。
- Mobile 相关完整集合在补入两条 UI 护栏后为 181/181、TypeScript 通过；全仓 lint 为 0 error / 93 个仓库既有 warning，改动文件单独 lint 为 0 error / 0 warning。
- 后端受影响集合在当前本地环境为 655 passed、2 failed、2 errors：两个旧用例依赖 `STAGED_RESPONSE_MODE=off`，在该模式下 2/2 通过；两个旧 `/agent/send` integration stub 先被本机缺失 PostgreSQL role `health_app_runtime` 阻塞，切 SQLite 后又因 fake `run_stream` 不创建 coordinator 所要求的真实 conversation 而失败。本轮新增 send-meta 纯测试通过。
- LLM live gate 首次被本机 PostgreSQL role 缺失与 fallback 429 阻塞；改用一次性本地 SQLite 额度账本后默认 TokenPlan/MiniMax 路径真实执行并通过：invariants 12/12、health agent core 50/50、orchestrator 5/5（平均分 0.94、平均耗时 10252ms）、trajectory contract 12/12、goldens 9/9，无回归。
- Release preflight：主干 CI 基线 `0160b0bfb` 为 green；secret scan、System Map/doc drift、Dossier 一致性、API 类型漂移、23 个 release invariant 与 Mobile changed-file 345/345 全部通过。
- 固定候选提交 `330aedbda` 的发布前独立复审为 **NO-GO**：长按通用菜单仍允许复制流式/中断/失败的半截回答，绕过紧凑依据面的终态门控。已用 streaming、interrupted、error 三类 RED 回归复现，并在菜单可见性与复制/分享/播报 handler 两层加入终态防护；定向 33/33 已通过，等待新固定提交复审。
- 修复提交 `14078c987` 的独立复审为 **GO**：三类半截回答的导出入口均关闭，复制/分享/播报 handler 具备二次终态检查，完整 assistant 与 user 操作未回归；相关 Mobile 7 个套件 174/174 通过。
- `system-map-check.sh`、doc drift、`git diff --check` 均通过。
- 这些结果证明契约和门控，不是线上 A/B；在同批请求的 `end_to_end_ttft_ms` 分位数和质量闸完成前，不宣称已经变快。

### 待完成

- [x] 后端 Health Evidence / Agent Executor / send meta 定向回归；完整受影响集合的 4 个既有环境/模式问题已如实记录。
- [x] Mobile 类型检查、lint 与相关完整测试。
- [x] LLM change classification 与 live regression gate 均完成；真实 orchestrator 5/5 通过。
- [x] 独立 safety-privacy reviewer 对早期 L3 投影和 1200-token 健康回答给出 GO。
- [x] `git diff --check`、System Map/doc drift。

## S0 · 用户需求（逐字）

> 之后继续执行：把复杂问题完整耗时压到可接受范围；当恢复数据异常或缺失时，自动提升模型并采用更保守的运动建议。完成后再跑一次简单、均衡、高风险三档模拟器验收。

- 谁用 / 解决什么：Mobile 对话用户需要复杂健康问题在可接受时间内完整结束；当睡眠、HRV、训练准备度等恢复数据缺失、过期、冲突或明显不可信时，系统不能沿用普通模型和积极训练建议。
- 当前绕过：用户只能等待长回答，或自行判断数据是否同步完整并主动要求更保守的建议。

## S1 · Discovery

- 已有两阶段响应：`agent_executor._phase_one_acknowledgement` 在 `STAGED_RESPONSE_MODE=on` 时立即发送确定性承接语。
- 已有三档分类：`classify_answer_task_tier` 将用户问题分为 `casual / balanced / high_stakes`，用户可见医疗正文不允许落到 fast 模型。
- 已有深分析升档：只有调用 `health_analysis` 后，自动选择的均衡模型才会提升到高风险模型。
- 已有恢复数据真源：`wearable_router.build_snapshot` 提供 owner-scoped 指标、来源、新鲜度、跨设备冲突和数据质量问题；`lab_plausibility.annotate_if_implausible` 对结构化异常值添加保留标记。
- 当前缺口：
  - staged 均衡问题仍继承通用 `ANSWER_MAX_TOKENS=8000`，长尾解码没有按用途收口。
  - 普通 `health_query` 返回恢复数据缺失、过期、冲突或 plausibility warning 时不会触发模型升档。
  - 最终合成没有确定性的恢复数据降级指令，模型仍可能在证据不足时建议高强度训练。
- 性能基线：同一代码路径下，简单档上限 2000 token；均衡和高风险档均为 8000 token。仓库性能治理规定 AI 分析目标 5 秒、最大 30 秒；本切片把 staged 均衡档完整回答 P95 ≤ 30 秒作为产品预算，先从限制无必要长尾解码入手，不关闭分析思考。
- 并发与分支：2026-08-31 开工时 `main == origin/main`（`4a478eb7`）；开放 PR 未触及本切片文件。工作树存在上一已确认 Mobile UI 任务改动，本切片不覆盖、不暂存这些文件。

## G1 · 准入裁决

- request：优化复杂回答完整耗时，并在恢复数据质量不足时自动升档和收紧运动建议。
- classification：`existing_core_loop_performance_and_safety_behavior`。
- first_user_fit：依赖可穿戴恢复数据决定当天训练的高强度工作者。
- core_loop_step：`wearable facts -> HealthTwin / data quality -> Safety gate -> advice -> action`。
- first_class_objects：`HealthTwin`、`SafetyGuardian`、`LeverageAction`。
- target_surface / source_of_truth：Backend Agent；owner-scoped `wearable_router` snapshot 与实际只读工具结果。
- safety_level：`medical_boundary`；不诊断、不处方、不把缺失数据解释为安全许可。
- autonomy_tier：无写入。
- success_metric：staged 均衡档回答预算收口；恢复数据降级必升 `high_stakes`；建议明确数据缺口且不得建议冲刺、间歇、大重量或其他高强度训练。
- non_goals：不新增数据库、不改变记录写入、不展示 chain-of-thought、不修改用药/诊断规则、不对真实健康数据做模拟器写入。
- smallest_end_to_end_slice：恢复/运动建议问题 -> 读取工具 -> 确定性质量判定 -> 模型升档 + 保守合成约束 -> 完整回答和可观测元数据。
- spec_required：`yes`。
- **裁决：PASS。** 用户已明确要求继续实施并给出三档验收范围，视为本切片 G1 确认。

## G2 · 可行性与安全压测

- 复用现有 owner-scoped wearable router，不在 prompt 前额外加载全量健康上下文。
- 只在恢复/运动建议语境、且实际恢复读结果暴露质量问题时触发；普通步数查询和非运动问题不升档。
- 失败方向固定为保守：数据质量判定自身失败时不伪装为完整；对恢复/运动建议按降级处理。
- 模型升级只改变答案模型质量档，不扩大工具权限、数据范围或写权限。
- 回退：`STAGED_RESPONSE_MODE=off` 恢复旧路由；恢复数据 guard 可移除而不迁移数据。
- **裁决：PASS。** 用户已确认“自动提升模型 + 更保守建议”的安全方向。

## S2 / S3 · 规格与规划

- Feature spec：`docs/specs/active/2026-08-31-complex-latency-recovery-safety-routing.md`。
- Health Harness run：`docs/_generated/harness-runs/c038061c7b15.jsonl`（本地生成物，不提交）。
- 实现顺序：先 RED 测试；再按档回答预算；再接恢复质量判定、升档和保守指令；最后跑 LLM 变更闸、独立安全评审和三档模拟器验收。
- 无 API / DB / Mobile schema 变化；done meta 只增加内容无关的恢复 guard 状态与原因码。

## S4 · 研发任务

- [x] T1 失败测试：staged balanced 使用有界回答 token；flag off 与高风险保持原质量预算。
- [x] T2 失败测试：缺失、过期、冲突、plausibility warning 触发恢复数据降级。
- [x] T3 失败测试：降级后答案模型升到 high_stakes，并注入禁止高强度的确定性指令。
- [x] T4 后端定向/受影响回归、LLM live change gate、安全复审。
- [x] T5 iOS Simulator 简单、均衡、高风险三档验收。

## G3 · 测试

- 后端受影响集合：恢复 guard、状态事件、进度事件和任务路由共 280 个用例；首次全跑暴露“继续用这个训练计划吗”承接语优先级回归，修正后对应 38 个承接语参数化/端到端用例通过，并再次全跑。
- Mobile SSE/状态消费：`chatStream` 与 `agentTurnState` 共 51 个用例通过；`useChatEngine` 的“上下文承接语不被 thinking 心跳覆盖”用例通过。
- live LLM regression：invariants 12/12、health_agent_core 50/50、orchestrator 5/5、trajectory contract 12/12、goldens 9/9。
- 模拟器使用仅含合成账号、无真实健康数据的临时 SQLite fixture；它证明 UI/SSE/路由和文案闭环，不替代 PostgreSQL 生产语义或线上 P95。

### iOS Simulator 三档验收（单次冒烟）

| 档位 | 问题 | 首阶段 | 后端完整耗时 | 模型/结果 |
|---|---|---:|---:|---|
| 简单 | 今天走了多少步？ | 服务端 32ms；模拟器约 1.5s 可见 | 3892ms | `casual` / `qwen3.6-flash`，正常完成，无思考泄露 |
| 均衡 | 20 分钟久坐晚间拉伸方案 | 服务端 108ms；模拟器约 1.7s 可见 | 26075ms | `balanced` / `qwen3.7-plus`，低于 30s 单次预算，无思考泄露 |
| 高风险 | 昨晚睡眠 + 今天间歇跑 | 服务端 47ms；模拟器约 2.6s 可见 | 23919ms | `high_stakes` / `qwen3.8-max`；`missing_core_signal + read_failed`，明确不建议间歇跑，只给低强度替代 |

单次冒烟全部低于 30 秒；P95 仍需生产同批真实请求的持续观测，不能由三次本地运行外推。

## G4 · 安全评审

- 独立安全评审结论：GO。恢复建议分类、guard fail-closed、非 fast 模型地板、回退阻断、内容无关元数据和缺数保守文案均通过；后续仅调整承接语分类，不改变安全路径。
- 发布候选复审结论：`330aedbda` **NO-GO**，原因是 Mobile 长按菜单的半截回答导出旁路；阻断修复与回归已完成，最终 GO 以修复后固定提交的复审结论为准。
- 修复后固定提交 `14078c987` 复审结论：**GO**，无剩余发布阻断。

## G5 / G6 · 发布与上线验证

- 2026-08-31 用户明确要求完成后进行 OTA，并已在本任务链路授权合并到 `main` 和部署到线上。
- 本切片的性能与恢复安全路由为 Backend 行为，必须先通过 `deploy.sh -b` 发布；Mobile UI 变更再按 `scripts/mobile-ota.sh production` 发布。OTA 不冒充 Backend 部署。
- **裁决：READY。** 本地回归、LLM gate、修复后独立安全复审与三档模拟器验收已通过；上线状态仍以发布工具回执和线上读回为准。

## 2026-09-01 · Agent 交互质量可靠性门禁

- 后续统一计划：`docs/plans/2026-08-31-agent-interaction-quality-reliability.md`。
- 新增脱敏 20 回合 / 100 展示面合成回放门禁；只验证契约和阈值逻辑，不把合成时延冒充生产 P95。
- 回放覆盖内容规范化、终态一致、写回执声明、只读/图片去重、输出预算与医疗剂量边界。
