# Agent Harness 自由度升级(对标 OpenClaw/Hermes 五项)

status: approved (founder 2026-07-07「1 2 3 4 5 都做,按顺序和优先级」)
owner: Claude + Codex 协作;每 slice 独立可上线,集成闸后合批部署

## 背景与原则

对标结论:OpenClaw/Hermes 赢在 harness 自由度,我们赢在领域确定性。
本计划把"自由度里不破坏确定性的五样"搬进来。硬约束不变:
- **R4**:LLM 永不发不可逆写;一切新能力先经确定性代码/确认门
- **fail-loud**:每个新降级点必须可观测,禁止静默兜底
- **复杂度预算**:优先复用既有接缝(interruption_budget / proactive_coordinator /
  memory_facts API / health_query_dimensions 均已存在),删>加

优先级 = 价值排序;实施 = 双轨并行(A 轨后端重、B 轨产品面),每 slice 绿了即合。

---

## Slice 1 · 单推理工具管道(P0,后端)

**偷什么**:Hermes 的 Programmatic Tool Calling 把多步工具管道折叠成单次推理。
**不偷什么**:`execute_code` 任意代码执行 —— 安全面不可接受。

**适配设计:`health_query_batch` 声明式批查询计划(零代码执行)**
- 新工具 `health_query_batch`:LLM 一次产出 JSON plan =
  `{queries: [{dimension, days, agg?}], compare?: {a, b, op}}`(≤6 条子查询)
- 后端确定性执行:逐条走既有 `health_query` 数据面(复用
  `health_query_dimensions.normalize_health_query_args` 的别名归一 + fail-loud
  未知维度),聚合/对比在 Python 里做,一次性把结构化结果回灌
- 效果:多指标问题("对比我这周和上周的睡眠+HRV+步数")从 3-4 轮 LLM 往返
  → 1 轮。生产实测 prompt:output=24:1、每轮 p50 11-14s,少两轮 ≈ 省 ~6k token + 20-30s
- 守门:
  - plan 校验 fail-loud(未知 dimension/agg → 报错列合法值,不静默跳过,
    与 health_query 跨模型三层防御同款)
  - 子查询全部只读;工具注册 `confirm: none`(查询类)
  - eval:`smoke` 真网用例 ×3(多指标对比/趋势+当前值/跨月),加进 eval cadence

**验收**:①MRI 式多指标问题 1 轮完成(meta.tools_used 佐证);②未知维度
fail-loud;③golden 对话回归绿;④时延对比记录进 dossier。

## Slice 2 · 情境心跳(P1,后端)

**偷什么**:OpenClaw 30min heartbeat 的"该为用户做点什么吗"。
**不偷什么**:每 30min 一次 LLM 自检(贵 + 不可控)。v1 **零 LLM**。

**设计:确定性触发器心跳**
- 新 celery beat `contextual-heartbeat`:白天(08-22 用户时区)每 30min
- 每 tick:读 Twin 增量(带 5min 缓存,不重建)→ 跑一组确定性触发规则:
  - 饮水缺口(15:00 后 <40% 目标)
  - 用药窗错过 >30min(读 medication timing)
  - recheck 到期(为 Wave-1 recheck 排程预留同一出口)
  - 久坐(可穿戴步数 2h 无增量,工作时段)
- 命中 → 候选提示 → **全部经 `interruption_budget` + `proactive_coordinator`
  既有门**(打扰预算是硬闸,不是建议)→ push 或折进下次简报
- 遥测:`heartbeat_considered/emitted/suppressed_by_budget`(fail-loud:
  规则抛错计入 failed_rules 并告警,不静默)

**验收**:①tick 在预算耗尽时 0 push(对抗测试);②每条规则正反例;
③suppressed 计数可查;④founder 实测一天不觉打扰。

## Slice 3 · 程序性记忆/配方(P2,后端+移动)

**偷什么**:Hermes"从完成的任务里沉淀可复用技能"。
**不偷什么**:agent 自写代码。配方 = **确定性重放的工具序列**,不是程序。

**设计**
- 模型 `ProcedureRecipe(user_id, name, trigger_phrases[], steps=[{tool,
  args_template}], created_from_conversation_id, use_count)`
- v1 入口:**手动**——一轮对话完成 ≥2 个写类工具后,结果卡出现"存为配方"
  (自动检测重复模式留 v2,防过度设计)
- 执行:用户说触发短语 → 意图层精确匹配(先于 LLM,类似 fast-path)→
  逐步重放,**每步确认策略沿用该 kind 既有 confirm tier**(R4 完好:
  配方不绕任何确认门,typed_only/never_auto 原样生效)
- args_template 只允许既有槽位(日期=今天等确定性填充),禁止 LLM 现场改参

**验收**:①存/触发/重放全链路;②配方步骤的确认门与直接调用完全一致
(对抗测试:配方里塞 never_auto kind 仍要求确认);③误触发率——触发短语
精确匹配不做模糊。

## Slice 4 · 统一任务账本(P3,后端+移动)

**偷什么**:OpenClaw Task Brain 的"一张账本管所有后台活"。

**设计**
- 只读聚合 service `task_ledger_service.build_ledger(user_id)`:
  union(write_intents pending/recent, desktop_jobs active, agenda 未来 48h,
  heartbeat 最近 emitted, recipes 已存)→ 统一 shape
  `{kind, title, status, when, source}`
- `GET /api/v1/agent/tasks`;移动端 ⋯ 菜单「小巴的任务」→ 对话页内联面板
  (agent-native,复用今日面板同款内联模式,不跳页)
- v1 只读;取消/重试操作留 v2

**验收**:①五源都有数据时账本完整且去重;②空态诚实("暂无进行中任务");
③内联展开不跳页。

## Slice 5 · 记忆透明可纠(P4,移动为主 —— 后端已就位)

**现状**:`memory_facts` API 已有 GET /me(按置信度)、dismiss("这条不对"
软删)、reinforce、supersede、矛盾检测。**缺的只是可见面。**

**设计**
- mobile `/memory` 屏改版:"小巴以为你…"列表(事实 + 置信度 + 来源轮次
  跳转)+ 每条「不对」(dismiss)/「确认」(reinforce)双动作
- 矛盾检测结果浮出:两条冲突事实并排让用户裁决(supersede)
- 简报记忆过度抽取的历史坑 → 列表按 effective_confidence 排序 + 低置信
  折叠,防"满屏噪音事实"

**验收**:①dismiss 后该事实不再进 prompt(端到端验证);②裁决冲突走
supersede;③OTA 可发(纯 JS)。

---

## 实施次序与节奏

| 波次 | 内容 | 轨道 |
|---|---|---|
| Wave A(先行) | Slice 1(最大杠杆)‖ Slice 5(最小,先拿动量) | A 轨 Claude ‖ B 轨 agent |
| Wave B | Slice 2 ‖ Slice 4 | 后端 ‖ 全栈 |
| Wave C | Slice 3(依赖 1 的工具注册面稳定) | 全栈 |

每 slice:实现 → 单测+对抗测试 → 集成闸(合跑,查 main 真色)→ deploy -b
(+OTA 若含移动)。安全敏感点(Slice 1 工具注册、Slice 3 确认门)过
safety-privacy-reviewer。
