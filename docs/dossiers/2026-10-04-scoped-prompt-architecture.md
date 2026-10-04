# 任务范围驱动的 Prompt 架构优化

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 本地验证完成，分支交接；未发布 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 范围准入

裁决：PASS。范围是用户授权的既有体验、路由和上下文传输优化及其分支交接，不新增产品入口、健康对象、用户数据权限或自动发布行为。权限、质量地板、写入回执和安全输出边界继续由原系统负责；失败候选不得进入运行路径。本文记录本地实现与证据，不代表全量 CI、生产效果或发布准入。

日期：2026-10-04。状态：本轮实现、本地验证与独立安全复审通过；未提交、推送或部署。

## 基线与授权

承接用户“继续其他部分的优化，从架构层也做下分析，输入 token 普遍很大”及“可以，按照你说的来”。本轮范围是工具说明按任务裁剪、历史预算与保真、可证明完整的报告复用。

已 fetch；远端 main 为 `f201d85b4f0d726b09ff0f8b16acf403d70f3e57`。隔离工作树 HEAD 为 `a8853dea1207163aaa412974dddfbc050ce3eeea`，两者运行时代码一致，差异仅发布 dossier。原共享目录的未提交改动保持原状；本工作树保留前几轮优化。

Router：implementation + safety。沿用单一 harness ledger：`docs/_generated/harness-runs/b992d9b915cd.jsonl`。生产开关不变，commit/push/merge/deploy 均不在本轮授权内。

## 架构判断与实现

输入膨胀来自每轮传递内容的范围：通用工具说明包含当前任务不会使用的维度；已完成长答被反复放入历史；综合分析可能在内层产出完整报告后，再由外层模型复述一次。继续压缩自然语言提示本身无法统一解决这些来源。

工具说明现在由同用户的服务端 OwnedReadScope 驱动，只投影实际注册 health_query / health_query_batch 的说明。工具集合、参数 schema、枚举、required 与网关权限不变；不认识的维度、特化 schema 或描述漂移保持原样。投影位于实际 provider 出口，流式和非流式都覆盖。

历史服务继续向 Pi 和业务解析器返回完整原文，另提供不可变 provider references。只有已完成、无待办/回执/卡片状态的旧助手长答完全重复时才引用，最近助手回复与所有用户原话保留。实际发送前再次验证原文仍在同一请求更早位置；原文消失或变动就不压缩。16,000 字符是诊断软预算，不是假装保证的硬上限。后台摘要保留窗口与请求窗口不一致时，使用本会话真实缓存切点并补回间隔原文；这项修复可能增加输入，不能算作节省。

报告复用采用进程内回执，工具 JSON 无权授权。仅双开关开启、首次对话的封闭单一报告请求、唯一工具执行可进入。绑定用户、run、工具调用和完整 Pi 用户帧；真实正常生成、真实安全验证、证据完整、无卡片/冲突/引用/回退才可 seal。通过 Pi 的 model response 接口交付，Pi 正常结束后仍走医疗边界、输出质量、事件和持久化。默认关闭；shadow 保持普通模型流程，不存候选全文。上游 error/status 不再被工具结果投影丢弃。

## 同批真实 API 对照

见 [API 证据](../reviews/2026-10-04-scoped-prompt-api-evidence.json)。仅固定合成数据，无真实健康载荷，4 次 API 请求，qwen3.8-max，temperature=0，max_tokens=300。

| 场景 | 基线输入 token | 优化输入 token | 降幅 |
| --- | ---: | ---: | ---: |
| sleep+spo2 工具说明 | 3554 | 2620 | 26.28% |
| 完全重复的历史长答 | 5715 | 3174 | 44.46% |

两侧查询维度、日期范围一致；历史回顾保留日期和过敏信息及“不代表再次执行”边界。候选历史包含 2048 cached tokens。以上是对应请求的 API prompt_tokens，不是全体请求平均降幅、生产账单节省或延迟改善；没有执行回放中的模型工具调用。

## 验证与质量底线

- 新行为先做失败测试；provider、真实 Pi 循环及真实工具网关均有接线验证。
- 关联回归：776 passed，日志 `/tmp/reva-scoped-regression.log`，JUnit `/tmp/reva-scoped-regression.xml`。
- 真实 LLM 闸：invariants 12/12、health_agent_core 50/50、orchestrator 5/5，后者 score 0.96；trajectory contract 和 golden 均通过。临时 SQLite 的 usage 日志表缺失告警不影响闸结果；API A/B 独立从 provider usage 取真值。
- System Map 已重新生成，统一漂移闸通过。Ruff 现有 11 项与远端基线相同，无新增发现。
- 独立复审发现 wrapped provider 内部恢复可隐藏失败并错归因，已要求失败发生时使活跃回执失效；该项修复完成与复审证据见下方最终裁决。

质量底线：不丢用户原话、未完成任务或安全状态；不改变工具权限；不把缓存/HTTP JSON、截断、降级或验证异常当成已完成报告。普通非重复长历史仍可能超过软预算，不能宣称已全面控制输入上限。

回退：关闭 domain_prompt_optimization 可恢复普通 provider 内容；关闭 orchestrator_synthesis_passthrough 可恢复外层合成。禁止用宽泛字符串匹配扩大复用覆盖。生产启用前还需目标 revision 的 CI、发布授权和真实流量分段验证。

## 最终裁决

独立安全复审：本地实现 GO。发现的隐藏 provider 回退已在共享异常边界使回执失效；新增真实 primary failure → fallback success 的回归，原恢复与用量日志保持正常。来源、组织、期刊和专家归因采用更保守的复用否决规则；“根据你近一周的数据”等封闭个人数据短语保留，同段外部归因仍阻止复用。该规则不等于语义引文核验。

最后 module + hooks + actual Pi 联合验证及独立复验均为 **173 passed**，独立日志 `/tmp/reva-delivery-independent-complete-final.log`。共享交付护栏注入拒绝时，实际 token 拼接与数据库回复一致且 completion_status 为 error；正常复用的 inner model 归因、跨用户/回合/工具拒绝、取消清理和回退拒绝均覆盖。另有 wrapper/usage 与交付增量回归 81 passed；这些套件与 776 项关联回归有重叠，不相加冒充独立覆盖量。

最终证据：[架构验证 JSON](../reviews/2026-10-04-scoped-prompt-architecture-evidence.json)。本裁决不授权发布或默认开启报告复用。下一生产阶段应对同一批真实请求检查输入分段、缓存命中、总调用次数、长尾延迟与答案质量，不能把本轮固定合成样本降幅推广到全量请求。
