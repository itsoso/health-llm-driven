# PRD — Agent Harness 增量重构

> 状态：草案 v1（Phase 1 产物）· 2026-06-03
> 范围：后端 LLM Agent Harness 架构（增量演进）+ 为后续「跨端统一设计语言」定义能力面
> 关联：`docs/HARNESS.md`（现行方法论与 §11 缺口）、`docs/design-agent-operating-harness.md`、本次多模型综合（`agent_executor._run_multi_model_stream`）
> 下游：本 PRD → 设计文档（架构详设）→ Claude Design 跨端 UI → 多界面落地

---

## 0. 一句话

把现在「能跑但叠了太多补丁」的健康 Agent harness，**增量**收敛成一条**可观测、可评测、分层（取数 / 分析 / 综合）的执行主干**，并对外暴露一组**稳定的能力面（capability surface）**，让跨端统一设计语言有明确契约可渲染。

---

## 1. 背景与问题陈述

### 1.1 现状（已实现，能跑）
- **三条入口/执行路径并存**：
  1. `needsSkill` 正则命中 → OpenClaw Gateway（skill 写库，带 vision）
  2. 不命中 → Orchestrator（11 specialist + Twin + LLM 仲裁合成）
  3. 统一 `agent/stream` → `AgentExecutor.run_stream`（单模型工具循环 + fast-record + source-aware + 多模型综合）
- `HealthTwin`（14 分区）→ prompt blob；`model_registry` 多 provider（tokenplan / langbridge 商用三强 / openclaw / openai-proxy）；memory 4-stage 注入；`_confirm_or_describe` 写前复述；audit 旁路。
- 本 session 新增：**多模型综合**（lead 带工具 + 商用三强分析 + Claude 综合）。

### 1.2 痛点（重构动机）
| # | 痛点 | 证据 |
|---|---|---|
| P1 | **执行主干臃肿易碎** | `run_stream` ≈ 600+ 行，叠了 fast-record / inline-card / 多模型 / system-KB evidence / 兜底分支；改一处怕碰全局（本 session 多次 JSON 泄漏类回归即出自此） |
| P2 | **三条路径职责重叠、路由脆** | OpenClaw vs Orchestrator vs AgentExecutor 边界靠正则 + 历史约定；记录/分析/查询的归属对新人不透明 |
| P3 | **模型角色未分层** | 取数（机械工具调用）和分析（高质量推理）用同一个贵模型；多模型综合是「bolt-on」而非主干能力 |
| P4 | **评测缺位** | HARNESS.md §11.1：无 LLM-as-judge eval 套件，prompt/模型改动靠人肉回归，质量回归不可量化 |
| P5 | **结构化与可靠性缺口** | §11.2 无 strict mode、§11.4 全 AUTO tool_choice、§11.3 无运行中 compaction —— 长对话/高风险写库可靠性靠 prompt 兜 |
| P6 | **能力面无稳定契约** | 各端（mac/web/mobile）各自消费 SSE 事件 + 各画各的；没有一份「harness 对外能力 = 模式 / 事件 / 证据 / 可解释性」的契约，跨端设计语言无从对齐 |

### 1.3 不做什么（非目标）
- ❌ 推翻现有结构重写（本次=**增量**，保留能跑的 Twin / safety rules / specialist / provider 层）
- ❌ 改 Twin schema、安全规则引擎、部署链路（属 frozen core）
- ❌ 本 PRD 不含具体 UI 视觉（留给下游 Claude Design 阶段）；本 PRD 只定义**能力面契约**供其消费

---

## 2. 目标与成功指标

### 2.1 目标
1. **一条执行主干**：把记录/查询/分析/多模型统一到一个分层 pipeline，路由作为薄前置层，而非三套并行实现。
2. **模型角色分层**：Router/Gatherer（便宜快，工具）→ Analyst（按需单模型或商用三强 panel）→ Synthesizer（强模型综合）。把本 session 的多模型从 bolt-on 升为主干的一个「分析档位」。
3. **可评测**：建 `backend/evals/` + LLM-as-judge runner，prompt/模型/路由改动有跑分门禁。
4. **可靠性补缺**：高风险写库走 force tool_choice + strict mode 试点；长对话加 compaction。
5. **稳定能力面**：产出一份《Harness Capability Surface》契约（模式 / SSE 事件 / 证据卡 / 来源归因 / 可解释性 / 延迟预算），作为跨端设计语言的输入。

### 2.2 成功指标（可量化）
| 指标 | 现状(基线待测) | 目标 |
|---|---|---|
| Eval 套件评分（~20 representative queries，LLM-as-judge 0–1） | 无 | 建立基线，重构后不低于基线 |
| `run_stream` 主体行数 | ~600+ | 主干 ≤ 250；其余拆为可单测的阶段函数 |
| 工具参数 schema 错误率（`data` 缺字段兜底触发次数 / 100 turn） | 待测 | ↓ ≥ 50%（strict + tool_choice 试点路径） |
| 单轮成本（多模型分析档） | 4× 商用调用 | 取数转便宜模型后 ↓ ≥ 30% |
| 路径归属可解释性 | 正则 + 口口相传 | 一张路由决策表 + 每轮 audit 标 `route`/`tier` |
| 跨端能力面契约 | 无 | 1 份文档 + 版本号，三端引用 |

---

## 3. 设计原则（沿用 + 新增）

沿用 HARNESS.md 7 原则（source-aware / verify-before-write / 厚 tool schema / memory 分 stage / provider failover / streaming+TTS / Twin→blob）。本次新增 3 条：

8. **分层模型角色（Layered model roles）** — 取数≠分析≠综合，各用合适档位的模型；贵模型只花在验证瓶颈处（呼应「verification is the bottleneck」）。
9. **Eval-driven** — 没有 eval 的 prompt/路由改动不合入；rubric 把已知错误（如基因 FADS1/SOD2 误判风险）编成强校验。
10. **能力面优先于界面（Capability surface first）** — 先定义 harness 对外暴露什么（模式/事件/证据），再让各端设计语言渲染；不让某端的 UI 反向决定 harness 行为。

---

## 4. 目标架构（增量）

```
                ┌─────────────── Router (薄, 正则 fast-path + 升级判定) ───────────────┐
   用户输入 ──▶ │  record? → 写库快路径   |   simple Q? → 单模型   |   deep? → 多模型档    │
                └───────────────────────────────┬───────────────────────────────────────┘
                                                 ▼
         ┌────────── Execution Spine (统一主干, 分阶段可单测) ──────────┐
         │  1) Gather  — Qwen3.x(便宜快) 工具循环: query/record 只执行一次 │
         │  2) Analyze — 单模型 或 商用三强 panel(analysis-only, 并发)      │
         │  3) Synthesize — 强模型综合(共识/补充/分歧) + 证据卡 + 来源归因  │
         │  贯穿: Twin blob · memory 4-stage · verify-before-write · audit │
         └───────────────────────────────────────────────────────────────┘
                                                 ▼
              SSE 能力面: route/tier · stage 进度 · tool_result · token · 证据卡 · done(model/sources)
```

### 4.1 路由层（薄前置，增量）
- 保留正则 fast-path（零延迟、可回归）；新增**显式档位**：`fast_record` / `single` / `multi_model`（对应 mac「多模型综合」模式）。
- 路由结果写进 audit（`route`, `tier`），让 P2/P6 的「归属不透明」变可观测。
- 不引入 LLM 路由（沿用 §8 取舍）；仅在正则不确定时按保守默认（分析档）。

### 4.2 执行主干：Gather → Analyze → Synthesize
- **Gather（取数）**：默认 `qwen3.7-max`（套餐内、便宜、工具调用够用）跑工具循环，query/record **只执行一次**（避免 panel 重复写库）。产出 `gathered_data_context`。
- **Analyze（分析）**：
  - `single` 档：一个模型直接出分析（多数日常查询）。
  - `multi_model` 档：商用三强（Claude Opus 4.7 / GPT-5.5 / Gemini 3.1 Pro）在同一 `gathered_data_context` 上**并发** analysis-only。
- **Synthesize（综合）**：强模型（Claude Opus 4.7）合成「共识 / 各模型补充 / 分歧」，单档时退化为直出。
- 把现 `_run_multi_model_stream` 重构为这条主干的 `multi_model` 实例；`run_stream` 单模型路径重构为 `single` 实例 —— **两者共用 Gather/Analyze/Synthesize 阶段函数**，消除 P1 的巨型函数与 P3 的 bolt-on。

### 4.3 可靠性补缺（§11）
- **Strict mode 试点**（§11.2）：`health_record` 单工具开 `strict:true`（先验证 TokenPlan/LangBridge 兼容），降 schema 兜底分支（指标见 §2.2）。
- **Force tool_choice**（§11.4）：体重/血压/血糖等高风险写库，识别意图后强制工具，杜绝「先聊一句不调工具」。
- **Compaction**（§11.3）：长对话（voice/连续 turn）到阈值压缩历史 + 丢弃旧 tool output。

### 4.4 评测（§11.1）
- `backend/evals/`：~20 条 representative query（rhinitis / sleep / recovery / safety / 基因 / 多模型综合各几条），每条带 expected-behavior rubric。
- LLM-as-judge runner：输出 0–1 分 + pass/fail；把已知错误反馈（`feedback_*`）编成强校验项。
- 接入 CI（非阻塞先跑分对比，成熟后设门禁）。

---

## 5. Harness Capability Surface（供跨端设计语言消费）

> 这是本 PRD 给下游 UI 阶段的**契约**。跨端统一设计语言围绕这些能力设计组件，而非各端各猜。

| 能力 | 内容 | UI 渲染含义 |
|---|---|---|
| **模式/档位** | `fast_record` / `single` / `multi_model` | 模型/模式选择器；多模型档显示 panel 进度 |
| **阶段进度** | Gather→Analyze→Synthesize 的 stage 事件 | 「正在查数据 / 三方分析 / 综合中」进度态 |
| **流式 token** | 增量答案 | 主回答区流式渲染 |
| **工具活动** | `tool_call` / `tool_result`(含 record_type/data) | 工具活动 chip、记录回执卡 |
| **证据卡** | system-KB evidence、inline cards、来源归因 `sources_used` | 证据/来源区，可展开 |
| **可解释性** | audit `route`/`tier`/specialist trace（反查接口） | 「AI 用了什么数据/为什么」展开面 |
| **延迟预算** | 各 source（Siri/Web/Voice/Push）不同 | 加载骨架 / 占位策略 |
| **多模型结果** | 共识 / 各模型观点 / 分歧 结构 | 综合报告的结构化分区展示 |

输出物：`docs/specs/harness-capability-surface.md`（带版本号），三端引用。

---

## 6. 分阶段交付（增量、可回滚）

| 阶段 | 内容 | 产出 | 风险 |
|---|---|---|---|
| **P0 评测基线** | 建 `backend/evals/` + judge runner，跑现状基线 | 基线分数 + runner | 低（只读） |
| **P1 模型分层** | 取数转 `qwen3.7-max`，多模型升为主干 `multi_model` 档（即上条「Qwen 取数 + 三强分析」） | 重构 `_run_multi_model_stream` | 中（需部署 + eval 守门） |
| **P2 主干收敛** | 抽 Gather/Analyze/Synthesize 阶段函数，`run_stream` 瘦身复用 | `run_stream` ≤250 行 | 中高（碰核心，靠 eval+单测兜） |
| **P3 可靠性补缺** | strict 试点 / 高风险 force tool_choice / compaction | 三个独立小 PR | 中 |
| **P4 能力面契约** | 写 `harness-capability-surface.md` + audit 加 route/tier | 契约文档 | 低 |
| **P5 跨端 UI** | Claude Design 出统一设计语言 + 关键界面，再各端落地 | .pen + 设计文档 + 各端实现 | 大（独立后续） |

每阶段：单测 + eval 不回归 + 灰度（先 mac 自用）→ 部署。

---

## 7. 风险与回滚
- **碰核心 run_stream**（P2）：每步保留旧路径开关；eval 守门；可单提交回滚。
- **取数模型降级影响质量**（P1）：eval 对比 Qwen-gather vs Claude-gather；漏取由综合者显式标「数据缺口」。
- **strict mode 兼容性**（P3）：先单工具单 provider 验证再铺开。
- **成本/延迟**（multi_model）：仅 `deep` 档触发；档位对用户透明（能力面已暴露）。

## 8. 开放问题（待决）
1. `single` 档默认模型：Qwen3.7 Max（便宜）还是用户当前选择？
2. 多模型档是否允许 agent **自主**升级（难题自动触发）vs 仅手动选「多模型综合」？
3. compaction 阈值与策略（按 turn 数 / token 数）。
4. eval rubric 的「金标准」由谁标注 / 多久更新。

## 9. 下一步
1. 评审本 PRD（开放问题 §8 拍板）。
2. Phase 2：架构详设文档（阶段函数接口、数据结构、迁移步骤）。
3. Phase 3：Claude Design 跨端统一设计语言 + 关键界面（消费 §5 能力面）。
4. Phase 4：各端整合落地。
