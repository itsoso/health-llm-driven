# Agent 感知时延优化计划：TTFT、可交互与关键内容优先

> 日期：2026-09-01
> 范围：Agent 对话链路，独立于 CI / release skill 性能工作。
> 原则：先补真实用户视角量测，再按瀑布消除最大的串行等待；医疗安全、写回执和证据边界不降级。

## 1. 目标不是“更早吐一个字节”

本计划同时优化六个不同指标，避免把通用 loading、空 token 或内部状态误记成用户收益。

| 指标 | 起点 → 终点 | 用户价值 |
|---|---|---|
| `local_feedback_ms` | 点击发送 → 本地消息/取消入口可见 | 确认操作已生效 |
| `server_accepted_ms` | 点击发送 → 服务端持久化确认 | 确认请求不会丢失 |
| `first_semantic_progress_ms` | 点击发送 → 首个与当前任务有关的真实阶段/依据 | 不再面对无信息等待 |
| `time_to_interactive_ms` | 点击发送 → 首个可取消、确认、编辑或执行的控件可用 | 用户可以继续行动 |
| `time_to_key_content_ms` | 点击发送 → 首个足以回答问题或支持决策的证据、读数、回执或结论 | 最核心的体验指标 |
| `provider_ttft_ms` | 模型请求发出 → 首个模型正文 token | 只用于定位模型侧延迟 |

终态继续记录 `total_ms`，但不允许用更短的终态掩盖关键内容更晚到达。所有指标按 `action_type × has_image × route × model_tier × outcome` 分层观察，并至少输出 `n/p50/p95/p99`。

### 初始发布目标

这些是第一轮验收目标，不是未经基线验证的承诺；拿到 7 天有效样本后重新校准。

| 路径 | 本地反馈 P95 | 持久化确认 P95 | 关键内容 P95 | 总耗时 P95 |
|---|---:|---:|---:|---:|
| 确定性读数/明确写入 | ≤100ms | ≤1s | ≤3s | ≤5s |
| 常规健康问答 | ≤100ms | ≤1s | ≤8s | ≤20s |
| 图片确认 | ≤100ms | ≤2.5s | ≤8s（可确认结果） | ≤20s |
| 复杂报告 | ≤100ms | ≤1s | ≤10s（首个证据/结论段） | ≤30s |

## 2. 当前证据与缺口

- 现有生产样本记录了平均总时延 42.2s、P50 26.3s、P95 99.4s，首个有用反馈中位数 15.9s；因此问题首先在关键内容和长尾，不是几十毫秒的 Python 微优化。
- Qwen 真网探针中，隐藏推理开启时首正文约 35.8s，关闭时约 1.6s，512 token 推理预算约 11.0s；说明模型推理策略是大杠杆，但医疗质量闸未过前不能直接全局关闭。
- 已有 pre-LLM 日志显示普通回合 P50 约 217ms；P90 约 3.0s 主要由图片路径拉高。普通文本回合不应优先做高风险并行重构。
- Mobile 已上报 `local_feedback/server_accepted/first_useful/write_verified` 的端到端毫秒值，但 `client_events_stats` 目前只计事件数，没有分位数或路径分层。
- Executor 的 `end_to_end_ttft_ms` 从 Executor 内部开始计时，漏掉 API 鉴权、附件处理、准入、回放/预生成判断和容量预留，名称比实际口径更宽。
- Mobile 首 token 使用 80ms 批处理，后续流式更平滑，但首个可见正文会额外等待 0–80ms。
- 已有快路、固定工具子集、思考流展示、确定性写回执、GenUI/starter 预生成、prompt-cache 观测和模型分层；新方案应建立在这些能力上，不重复造轮子。

## 3. 顺序与发布闸

### Phase A — 先让瀑布可信（P0，零行为变化）

1. 在 `client_events_stats` 聚合现有 Agent 里程碑，输出：
   - 全局及 `action_type × has_image` 的 `n/p50/p95/p99`；
   - 每个 phase 的样本数，避免把缺失事件当成快速事件；
   - 拒绝负数、布尔值和超过协议上限的脏数据。
2. 把 API route-entry 的 monotonic 时间传到 Executor，新增 `api_admission_ms`，并保持现有字段兼容。
3. 将模型阶段拆成 `provider_request_start / first_reasoning / first_content / tool_args_complete / first_tool_result`；区分首个状态、首个依据、首张卡片和首个正文。
4. Mobile 把当前 `first_useful` 拆成：
   - `first_semantic_progress`：任务相关但不一定能回答问题；
   - `first_key_content`：读数、证据、验证回执、可确认卡片或正文结论；
   - `first_interactive`：控件真正可操作。
5. 只记录枚举、布尔和时长，不记录正文、健康值、图片、URL、用户标识或原始 turn id。

验收：离线测试全绿；线上连续 7 天或每个主路径至少 100 个有效样本；缺失率单独展示。没有基线前不宣称 TTFT 已改善。

### Phase B — 让第一件有价值的东西先到（P1，低风险）

1. Mobile 首个 token / 首张卡片立即 flush，只有后续 token 继续 80ms 合批。
2. `request_persisted` 后立即发送便宜、确定、任务相关的阶段，例如“已读取最近 7 天数据”，而不是泛化的“正在处理”。阶段必须来自真实执行状态。
3. 只读路径：工具结果一到，先发送确定性读数/证据卡片，再做叙事合成。
4. 写路径：verified receipt 是关键内容；回执到达即发送，解释文本后置。任何未验证写入仍 fail-closed。
5. 图片路径：上传、识别、待确认分别计时；识别结果先变成可编辑确认卡，不等待长叙事。

验收：关键内容 P95 明显下降；错误写入、假成功、无依据进度事件均为 0；答案质量不低于基线。

### Phase C — 消除大段串行等待（P2，中风险）

只在 Phase A 瀑布证明该阶段占比足够大时启动。

1. 扩展确定性查询直出：饮水、体重、睡眠、步数、血压等无歧义读数不进入二次 LLM 合成。
2. 稳定 prompt 最长公共前缀，将动态内容放在尾部；以 provider 返回的 `cached_tokens` 和 TTFT 同时验收。
3. 按路由设置推理策略：简单读写使用快模型/低推理，常规健康问答使用评测通过的预算，高风险与复杂分析保留强推理。任何降档先过双基线质量与安全 eval。
4. 多个独立只读工具可并发；写工具保持串行。SQLAlchemy Session 不跨协程并发共享，读任务使用独立 session 或预先冻结的快照。
5. 连接池复用、异步流泵和 provider priority tier 仅在网络/排队阶段被量测为显著时启用。

验收：按路径比较 baseline/candidate 的 P50/P95/P99、缓存命中率、模型调用轮数、token、成本和质量；不能只报平均值。

### Phase D — 专门打长尾（P3，高约束）

Jeff Dean 的核心提示是关注尾延迟和跨服务放大：一个回合串联或 fan-out 多个组件时，单组件的小概率慢请求会变成用户的常见慢回合。因此：

1. 给每个阶段设 deadline 和剩余预算，超时后返回可恢复的部分结果，不让一个辅助步骤吞掉整个回合。
2. 仅对幂等、只读、可取消的 provider 请求做 p95 后 hedging；先限制为约 2–5% 的额外请求量，胜者返回后取消另一份。
3. 写工具、可能产生副作用的调用、昂贵多模型分析绝不 hedge。
4. fan-out 数量有上限；用隔离并发池和 admission control，防止一个深报告拖慢所有普通回合。
5. 每次发布都看 P99 和超时率，平均值变快但 P99 变差视为回归。

参考：Dean 与 Barroso 的 [The Tail at Scale](https://barroso.org/publications/TheTailAtScale.pdf) 展示了延迟触发备份请求在低额外负载下改善极端尾部的做法；这里仅借鉴其只读、可取消场景，不扩展到写操作。

### Phase E — 传输层最后评估

当前 SSE 已能流式传输。只有当 Phase A 证明连接建立/API-to-first-byte 占 TTFT 的 15–20% 以上，或语音需要真正双工，才评估 WebSocket。OpenAI 公布的 agentic WebSocket 工作流案例报告约 45% TTFT 改善，但那是特定工作流结果，不能直接外推到本项目；若瓶颈在模型隐藏推理，换协议不会解决。[案例](https://openai.com/index/speeding-up-agentic-workflows-with-websockets/)

## 4. 性能判断准则

- 优先减少一次模型/网络往返，其次减少串行等待，再考虑函数级微优化。Jeff Dean 的数量级思维意味着：本地内存/函数开销通常远小于跨网络模型调用。[延迟数量级参考](https://www.cs.cmu.edu/~15721-f24/slides/01-Introduction.pdf)
- prompt 越长通常 TTFT 越高；公共前缀稳定、动态内容后置，并用真实 cache hit 验收。[Gemini 长上下文建议](https://ai.google.dev/gemini-api/docs/long-context?authuser=19) [缓存建议](https://ai.google.dev/gemini-api/docs/generate-content/caching?hl=en)
- 推理强度必须按任务和 eval 选择；长任务应先给简短、真实的用户可见 preamble/进度，但不能伪造“正在查询”。[OpenAI 模型与延迟建议](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5)
- “首个有用”不能由 generic spinner、纯标点、空 delta 或尚未验证的写入满足。

## 5. 第一批实现切片

按以下顺序独立提交、独立验收：

1. `agent milestone percentile aggregation`：聚合现有客户端里程碑；纯观测、最小风险。
2. `end-to-end latency clock`：补 API entry 与 provider 阶段时钟，校正 `end_to_end` 命名/口径。
3. `semantic/key/interactive milestones`：拆分客户端指标并补缺失率。
4. `first artifact immediate flush`：首 token/卡片立即渲染。
5. 根据 7 天瀑布，在确定性查询直出、推理预算、缓存前缀、只读并发中只选择收益最大的一个进入 A/B。

每个切片必须先写失败测试，运行相关 Backend/Mobile 回归，并在提交后等待 CI 全绿。涉及模型行为的切片额外执行 agent live eval、安全不变量和回执一致性闸。

## 6. 2026-09-03 实施进展

本轮只完成本地实现和验证，不继承历史发布授权，不执行 commit、push、部署、OTA 或送审。

- [x] 将客户端里程碑扩展为 `first_semantic_progress`、`first_content_painted`、`first_key_content`、`first_interactive`、`citations_received` 和 `citations_painted`；所有事件仍只含枚举、时长和布尔值。
- [x] 里程碑终点改为 React Native surface 的首次 `onLayout`，不再把 SSE 收到或 state 更新当成“用户已经看到”。
- [x] 首个正文 token 或首张内联卡在同一次 state update 中立即落 UI；80ms 合批只用于后续 token。
- [x] 受支持的只读工具结果到达后，先流出确定性 GenUI 卡片，再继续叙事合成；医疗建议缓冲路径不提前释放健康内容。
- [x] 确定性查询直出改成 `off / shadow / on`；默认 `off`，`shadow` 只记录 eligibility 和候选字符数，不改变回答，未知值回落 `off`。
- [x] 周报聚合新增关键内容、可交互和引用实际绘制的 p50/p95/p99；保留 `citations_visible` 仅用于历史数据兼容。
- [ ] API admission/provider 子阶段时钟尚未补齐，继续列为 Phase A 后续切片。
- [ ] 7 天或主路径 100 个有效样本尚未形成，不能宣称线上 P95 已改善。
- [ ] live orchestrator gate 因本机没有 TokenPlan/OpenAI 凭证未执行成功；离线 invariants、health-agent core、trajectory contract 和 golden trace 已通过。

发布前停止条件保持不变：live LLM gate、固定提交独立安全复审、主干 CI 和同批请求基线任一缺失，均不得把本地实现标成可发布或已提速。
