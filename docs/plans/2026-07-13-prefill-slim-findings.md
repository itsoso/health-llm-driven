# 工具轮/合成轮 prefill 瘦身 — 勘查结论 + 落地计划(2026-07-13)

> 起因:founder「Agent 对话时间太长」。本文是对「工具决策轮 ~14k prefill」的实地勘查结论。
> **核心校准:prod 上最大的 prefill+模型 杠杆已经在跑,剩下的主要是成本优化(缓存稳定性),不是延迟。**

## prod 现状(已核实)

- `TASK_TIERED_ROUTING=true` — 建议/分析回合的**首个工具决策轮**已降 qwen3.6-flash + lite 栈(无分析 blob/无 KB/无 memory),34s→1-2s。**已上线。**
- `LLM_EXPLICIT_PROMPT_CACHE=true` — qwen3.7-max/qwen3.6-flash 都 `supports_explicit_cache=True`,`_maybe_apply_prompt_cache_markers` 无条件调,`mark_system + mark_history_prefix`。**已上线。**
- 合成轮:full ~14k 栈 + qwen3.7-max,**隐式缓存命中仅 ~29%**。

## 为什么缓存只命中 29%(根因)

`mark_system` 断点缓存**整条 system**,但 system 里混了**每回合变**的内容:
- **`时间: HH:MM`**(`health_context_lite_service.py:181`)—— 分钟每回合变,且落在 21.7k 字符 tool schema **之前**;这几十字节一变,其后整条 system + tool schema 全 cache-miss。**单枪匹马阻止 27k 字符静态头跨回合缓存。**
- **memory 双重注入 bug** —— `build_lite_health_context`(:274,lite/full 都调)和 `_build_system_prompt`(:6311,full 块)各注入一次 limit=5 记忆 → 同批记忆进 prompt 两遍 + 一次冗余 DB 往返;且 decayed_score 随 now 漂序,持续打碎前缀。
- 滚动分析 blob(肝/CBC/疗程/干预/效应)在 system 前缀内,慢变。

## 本次已改(safe,已提交)

1. **memory 双重注入去重**(`agent_executor.py:6309`)—— 删 full 块里的重复注入;记忆仍由 `build_lite_health_context` 注一次(自带「用户历史记忆:」标签)。零信息损失,省一份记忆文本 + 一次 DB 往返。**无 flag(纯 bug 修)。**
2. **`时间: HH:MM` → `H点(时段)`**(`health_context_lite_service.py:181`)—— 降精度到小时,5min TTL 窗内恒稳定;精确时间戳仍由工具侧 datetime.now() 负责。预估隐式命中 29%→~50-65%。**低风险,直接改。**

## 关键量级(实测)

| 块 | 大小 | 稳定性 |
|---|---|---|
| 全量 tool schema(15 工具) | 21,690 字符 ≈ 5.4k tok | **byte-stable**(可缓存) |
| big-3 子集 | 10,784 字符 | 故意固定(缓存友好) |
| base 静态规则头 | ~6k 字符 ≈ 1.5k tok | byte-stable |
| build_lite 基础画像 | ~800-1200 tok | 会话内 5min 缓存,含 HH:MM(已修) |
| 分析 blob(仅 full) | 数百~上千 tok | 全易变 |

## 反直觉结论:缓存打通后别再裁 tool schema

命中的全量 21.7k schema 按 ~10% 计价 ≈ 542 有效 tok,**比未缓存的 10.8k big-3 子集(2,696 tok)还便宜 5×**。动态裁剪把 byte-stable schema 变成变字节、每回合冷 encode,net 负收益。**优先「缓存全量 byte-stable schema」而非「动态裁剪」。**

## 延迟 vs 成本的诚实校准

合成轮时间是 **decode-dominated**(qwen3.7-max ~12-13 tok/s 写 1800-5200 字符 = 45-130s)。缓存命中只降 **prefill encode(~1-3s)+ 成本(~5×)**,**几乎不动 decode**。所以:
- **#2 prefill 缓存工作 = 成本优化 + 少量延迟**,near-zero-risk,值得做但不是延迟大杠杆。
- **合成轮延迟的真杠杆 = 减少无效重复**:GenUI-first metric_table 由确定性卡片承载数字，正文只做结论、趋势、风险边界和行动，不逐行复述卡片；正文不再设置 500 字硬上限，避免深度建议被截断。**1a(点亮已建好但暗置的 metric_table cap)** 仍通过减少重复来降低 decode，但不牺牲完整性。

## 未做的更大杠杆(按 节省/风险 排,留待评估)

- **Lever B — 稳前缀重排**:把 memory / 实时快照 / 滚动 blob 整体移到 last_user 之后的 turn-tail append-only 消息(复用 KB 已用的 `turn_context_parts` 机制),让 system 只剩 byte-stable 头。叠加 HH:MM 修复后活跃会话命中 ~70-90%。**中等重构、需过 invariant_judge + cadence eval。**
- **`tool_round_lite_context` flag**:把「剥 blob/KB/memory」从「换 flash 模型 + 砍历史」里解耦,让 near-zero-risk 的剥上下文维度对**所有**工具决策轮独立生效(保强模型 + 保历史)。prod 已开 tiered_routing,收益部分已兑现。
- **`tool_schema_compact` flag**:压 5 大工具 description 冗余(byte-stable,全回合含合成轮生效,省 ~600 tok);红线=不删 health_record 的单位锚点/worked-example(弱快模型靠它填参,「饮水2000」教训)。
- **`mark_static_preamble`**:静态前缀实测 918-1278 est token,贴 DashScope ≥1024 下限,须先 probe 证实命中再开。

## 质量护栏(任何工具轮瘦身上线前)

- **smoke_fast_tool_model.py 式真网 eval**:固定 advice/analysis 回合,断言工具选对率 ≥ 全量栈基线。
- 跟进消歧集([[feedback_fast_path_drops_followup_context]])。
- 参数填充 eval(护 description 压缩,「饮水2000」不被记成默认值)。
