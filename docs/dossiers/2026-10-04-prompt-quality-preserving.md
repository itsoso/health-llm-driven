# Prompt 优化与效果回归验证

| 字段 | 值 |
| --- | --- |
| 状态 | rejected |
| 当前阶段 | 已拒绝写入说明精简；评测及撤回验证完成 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

日期：2026-10-04。状态：候选优化已否决并撤出运行路径；评测设施与撤回验证已完成。未提交、推送或部署。

## 范围与基线

承接用户“继续优化，并且确保优化之后不影响效果”。已 fetch origin/main `f201d85b4f0d726b09ff0f8b16acf403d70f3e57`；沿用隔离工作树 HEAD `a8853dea1207163aaa412974dddfbc050ce3eeea`，两者运行时代码一致，仅发布 dossier 不同。保留前轮优化和原共享目录改动。本轮使用 implementation + safety，ledger 为 `docs/_generated/harness-runs/1a9709044391.jsonl`。

上一轮输入分段审计表明，工具说明是主要输入来源之一。本轮评估了 health_record 的跨类型示例精简候选：明确本人、单次、封闭全句、毫升/ml 数量，且服务端已有一致的 simple_health_record/water 目标时，provider 只带公共头及完整 water 示例。保留外层安全说明、record_type 说明、所有参数/枚举/required、工具集合及 Pi 原始 schema。当前注册表说明出现未知布局或特化版本时保持原样。以上是已否决候选的设计，不是最终应用行为。

目标编译器本身不能证明输入只有一个目标，因此增加全句约束，重新校验 owner、原始输入、数量、日期与 goal。复合任务、他人、临床问题、附件、引用、待确认/待执行写操作、失败修复轮、额外上下文均保留完整材料。自然倒装句“记录我今天喝了350毫升水”目前没有 typed goal，也保持原样。该优化不扩大 Laya 或 LLM 的权限，不跳过模型、执行网关、幂等和写入回执。

`domain_prompt_optimization` 的默认值仍是 false。关闭它可撤回 provider 内容优化。本轮未修改生产配置。

## 真实回归与撤回

首次 17 个固定合成样本的 max 对照中，三个实际改变输入的饮水样本参数正确。随后 flash 对照发现真实退化：“记录喝水0.5升”原版生成 amount=500，精简版却追问具体毫升数。因此先否决升/L 的投影，将实验收窄至显式毫升/ml；未加入新的提示暗示或升级模型来掩盖问题。

原始失败保留在 [flash 首次失败](../reviews/2026-10-04-record-prompt-rejected-flash.json)；[max 原始全样本](../reviews/2026-10-04-record-prompt-initial-max.json) 也完整保留，不覆盖旧结果。

全样本评测另有两类检查器误报：加粗的“6.5”以及“不能”分段回答/“不足以计算 ODI”。已以原始响应添加失败测试，再限定修复文本匹配；肯定说法、错误数值和伪造 ODI 仍失败。原始报告重评分另存，不重新采样挑结果。

原版“昨晚睡眠”有一次返回 days=1，不符合固定日期范围契约。该样本两侧请求完全相同，不能归因本轮精简；仍保留为未解决的基础模型日期提案问题，不能将整份报告称为全绿。服务端实际查询窗口解析另有邻近测试，但本次 provider 回放不执行工具，不能替这一次提案证明真实执行结果。

## 评测架构与边界

新增 `backend/eval/prompt_projection_quality.py` 与 `scripts/benchmark_record_prompt_projection.py`：冻结合成输入、日期与工具结果，默认只构造请求，显式参数才调用 API。对照走真实 AgentExecutor provider 出口；两组都保留此前优化，强制只有 health_record.data.description 可以不同。工具决策检查完整目标、具体参数、日期、权限和 schema；答案检查数值、数据缺失、失败写入不可声称成功等确定性契约。

评测器不执行模型提议的工具，不写真实健康数据。它保留临床质量、自由文本语义完整性、实际持久化 Unknown。请求完全相同却响应不同的样本标识为 unchanged_control；不能把采样波动算作精简造成的回归，也不能自动算通过。

收益只引用真实 API prompt_tokens；字符数、缓存与单次耗时不冒充生产账单或 P95。最终对照与独立复审见下方结果。

## 验证证据

- 关联回归：783 passed；日志 `/tmp/reva-record-regression.log`，JUnit `/tmp/reva-record-regression.xml`。
- 升/L 撤回先写失败测试，确认原实现失败后收窄；撤回后的最终关联验证为 387 passed（`/tmp/reva-record-final-verification.xml`），覆盖候选隔离、真实 provider、Pi、原有范围投影和快速路由。
- [既有 LLM 回归闸](../reviews/2026-10-04-record-prompt-live-gate.json)：invariants、health_agent_core、orchestrator 与 trajectory 均通过。orchestrator 均分 0.94；不将其当作统计非劣证明。
- System Map 已重新生成，统一漂移检查通过；executor Ruff 11 项均与远端基线一致，无新增发现。

停止条件：任一实际改变输入的候选产生错参数、漏目标、多余追问、安全/权限差异即拒绝该范围；同请求波动或基线失败单独保留。扩大覆盖或生产启用前，需要新的同批质量证据、目标 revision CI 和发布授权。

## 最终实验结论：不接入运行路径

[收窄后的 flash 对照](../reviews/2026-10-04-record-prompt-narrowed-flash.json) 继续发现退化：350毫升、250ml 两个输入，原版均正确记录，候选却再次询问已知信息。[同批 max 对照](../reviews/2026-10-04-record-prompt-narrowed-max.json) 的四个被精简样本通过，不能抵消 flash 失败。候选输入约减少 10.77%，但这项收益被否决，不计为交付效果。

因此完整撤销本轮 AgentExecutor 的 record 投影接线、状态和触发条件；没有新增可启用该候选的生产开关。正式 provider 对这些写入请求继续发送完整说明，即使开启已有 domain_prompt_optimization 也不裁剪写入示例。此前读查询、历史、Laya 等优化保持原状。

候选移入 `backend/eval/experimental_record_projection.py`，只有显式运行评测脚本时，才注入脚本内单独的 executor 实例；生产目录无引用。新增流式/非流式 provider 和真实 Pi 检查，覆盖即使残留旧实验 flag 也不能启用候选；脚本隔离测试验证类方法及评测前后应用请求完全一致。

新增的可复用成果是固定合成对照评测、质量判定及真实失败回归，覆盖数量/单位、日期、多目标、缺参、否定、医疗边界、数据缺失与写入回执。[旧 max 结果重新评分](../reviews/2026-10-04-record-prompt-rescored-max.json) 保留原评分和请求散列：只修正三条误报，日期基线失败保留，整体仍为 failed_contracts。所有真实实验响应和失败均保留。

本轮不声明新增长期输入 token 降幅，也不声明统计意义的普遍效果不变。实际做到的是在代码进入生产前，用真实模型对照发现并拒绝影响效果的压缩。

## 最终独立裁决与交付

独立复审：撤回及评测隔离 GO，候选质量继续 NO-GO。生产目录无实验模块、record投影函数或触发 flag 的引用。Executor SHA256 精确恢复前轮已审版本 `e958a7b42e0cedb47e463f61347e9761bd71ed61c8bd1ad2c8e2768894e1083a`。独立 provider/benchmark 验证 33 passed，日志 `/tmp/reva-record-withdrawal-independent.log`；与本轮 387 项检查重叠，不相加计覆盖。

迁移到离线模块后，六组 baseline/candidate 请求散列与此前真实 API 对照完全相同，未通过改样本抹掉失败。System Map 最终重生成及漂移闸通过；新增代码 Ruff 与 diff-check 通过。综合证据见 [验证清单](../reviews/2026-10-04-record-prompt-quality-evidence.json)。

完成范围是可复用的合成质量对照、已见退化的回归保护和候选撤回；无新增生产 token 收益，无提交、推送或部署。扩展输入压缩需另一个通过同批模型质量对照的方案，不能仅凭静态测试或强模型通过即放行。
