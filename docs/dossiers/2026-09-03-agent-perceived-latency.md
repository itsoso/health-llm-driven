# Dossier: Agent 感知时延第一批优化

| 字段 | 值 |
|---|---|
| slug | `agent-perceived-latency` |
| 创建日期 | 2026-09-03 |
| 当前阶段 | 本地候选 `b9063c441` 已固定；G4、live LLM gate 与 push pending |
| 状态 | candidate_committed_pending_review |
| 负责 | Codex / product / backend / mobile |
| 计划 | `docs/plans/2026-09-01-agent-perceived-latency.md` |

## S0 / G1 · 需求与准入

目标是缩短 TTFT、可交互时间和关键内容时间，优先减少用户无信息等待。该切片优化既有 Agent 对话核心循环，不新增诊断、处方、健康写入权限、数据库对象或外部数据范围。

- 关键内容：真实只读工具结果生成的卡片、可核对引用/依据、已验证写回执。
- 非关键内容：通用 spinner、空 token、纯标点、未验证写入声明。
- 成功度量：按路径观察 `n/p50/p95/p99`，线上基线形成前不宣称性能改善。
- **G1：PASS。** 属于既有核心循环性能与可观测性修正，安全边界不扩大。

## S2 / S3 · 决策与顺序

1. 先把 receipt、state update 与真实 paint 拆开。
2. 再移除首 token 的 80ms 人为等待。
3. 只读工具完成后先给确定性卡片，叙事后置。
4. 查询短路先提供 `shadow`，不直接改变默认线上行为。
5. 并发、hedging、模型降档等高风险优化等真实瀑布和长尾样本后再选。

## S5 · 实现

- Backend/Mobile 事件协议增加真实绘制、关键内容、交互和引用 receipt/paint 里程碑；载荷保持内容无关。
- ChatBubble 在 progress、正文、只读卡片、引用、依据和写回执首次布局时回传 paint；同类 surface 每条消息只记一次。
- 第一段流内容立即更新 assistant message，后续流内容继续 80ms 合批。
- `metric_table`、饮食/睡眠汇总和用药列表可在只读 tool result 后立即流出；最终消息仍持久化相同可信 fence，模型伪造 fence 继续被清洗。
- 医疗建议和其他 buffered 路径不提前发送 GenUI；失败/中断仍清除提前引用。
- `deterministic_query_reply` 支持 `off / shadow / on`，默认 `off`；旧布尔配置兼容，未知值 fail-closed。

## G3 · 本地验证

- TDD RED：新里程碑 schema、paint 回调、首 token 立即显示、提前 GenUI 和 query shadow 用例先失败。
- Backend 受影响集合：180 passed（SQLite 测试库；没有数据库语义变化，不作为 PostgreSQL 生产证据）。
- Mobile 相关集合：215 passed；TypeScript `tsc --noEmit` PASS；Expo lint 0 error（90 条仓库既有 warning）。
- `git diff --check` PASS。
- LLM 离线门禁：invariants 12/12、health-agent core 50/50、trajectory contract 12/12、golden trace 9/9 PASS。
- live orchestrator 5 个用例因本机未配置 `TOKENPLAN_API_KEY` / OpenAI 凭证未能运行，门禁状态保持 failed/pending，不能当成模型质量通过。
- System Map、mobile nav 与 doc drift：PASS。
- **G3：CONDITIONAL。** 确定性与跨端契约证据已绿；live LLM 证据仍缺。

## G4 · 安全与隐私

- 提前卡片只来自已完成、只读且受支持的工具结果；不会从模型文本提取健康数值。
- 健康建议 verifier/buffered 路径不提前释放卡片或正文；写工具不进入本切片短路。
- 客户端里程碑不含正文、健康值、URL、用户标识或原始 turn id。
- query `shadow` 不改变回答；`on` 仍要求只读、全覆盖且无安全后缀，否则回落正常合成。
- **G4：PENDING。** 需要对固定提交做独立 safety/privacy review，不能沿用历史评审。

## G5 / G6 · 发布与线上验证

- 2026-09-05 经用户授权固定本地候选提交 `b9063c441`；尚未 push、部署或 Store/OTA 发布，当前 TestFlight Build 261 不含本轮代码。
- 发布前还需 live LLM gate、独立 G4、目标 revision CI-mode 集成闸和上线后同批请求分位数验证。
- **裁决：NOT STARTED。**

## 回退

- query rollout 可切回 `off`；未知值自动回落 `off`。
- GenUI 继续受既有 capability 与 kill switch 控制；关闭后恢复叙事路径。
- 新客户端 paint 指标不改变服务端回答；旧 `citations_visible` 数据仍可被聚合读取。
