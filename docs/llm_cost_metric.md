# LLM Token 成本 & Eval 度量体系

_最后更新: 2026-04-30_

## 一、现状（已建成，不要重做）

基础设施在 4 天前就 ship 了（2026-04-26 起有真实数据），但外部没人知道，容易重复造轮子。

| 组件 | 位置 | 状态 |
|---|---|---|
| 数据模型 | `app/models/llm_usage.py:LlmUsageLog` | ✅ 已部署到 PG `llm_usage_logs` |
| 埋点中间件 | `app/services/llm/usage_tracker.py` | ✅ `wrap_provider` + `set_caller` + tiktoken 估算 + 价格表 |
| 自动注入 | `app/services/llm/factory.py:150` | ✅ `get_llm_provider()` 返回前自动 wrap |
| 业务标注 | 82 处 `set_caller(...)` 调用 | ⚠️ 38 个不同的 caller，但日常只有 4 个活跃 |
| 查询 API | `app/api/llm_usage.py:GET /llm-usage/summary` | ✅ 支持 by_caller / by_model / by_day 聚合 |
| 生产数据 | 4 天 25 行 27K tokens | ✅ 数据在流 |

### 真实 LLM 调用面（澄清误解）

此前以为有 "23 处 LLM 调用" — 错误。**10 个 Specialist 都是纯规则/结构化**（`applies_to` + `run` 从 Twin 产 `SpecialistFinding`，不调 LLM）。`memory_extractor.py` 是正则抽取，不是 LLM。`cross_review.py` 也不是 LLM。

实际 LLM 调用只在**服务层**：

| 业务链路 | 调用点 | 是否已埋点 |
|---|---|---|
| Orchestrator 合成 | `orchestrator.synthesis` / `.stream` | ✅ |
| Safety 解释 | `safety.explain` | ✅ |
| Daily Briefing AI 叙事 | `daily_briefing.ai_narrative` | ✅ |
| Insight v2 pattern mining | `insight.llm_pattern_mining` | ✅ |
| Health Analysis 三链路 | `health_analysis.analyze_issues` / `.structured` / `.personalized_advice` | ✅ |
| Health Trend | `health_trend.analyze` | ✅ |
| 饮食识别 | `food_recognition.*` | ✅ |
| 基因 / 化验 OCR | `genetic.*` / `medical_*` / `vision.*` / `family_health.exam_*` | ✅ |
| Workout 分析 | `workout_analysis.enhance` | ✅ |
| RAG / 知识增强 | `rag_pipeline.*` | ✅ |
| Agent Loop / Executor | `agent_executor.run_stream` / `agent_loop.run` | ✅ |
| Smart Plan / Period Goal | `smart_plan.generate` / `period_goal.generate` | ✅ |
| Intervention Assessment | `intervention_assessment.assess_card` | ✅ |
| Directive Parser | `directive_parser` | ✅ |
| PDF 解析 | `pdf_parser.extract_exam` | ✅ |

## 二、已知缺陷（P0，先修）

### 缺陷 1：`model='unknown'`，cost=0

**现象**：线上 25 行全部 `model='unknown'`，因此所有价格查表失败，`cost_usd=0`，成本完全看不到。

**根因**（`usage_tracker.py:151`）：
```python
actual_model = model or getattr(provider, "default_model", "unknown")
```
- `model` 参数：调用方基本都不传
- `getattr(provider, "default_model")`：OpenClaw/OpenAI provider 类没挂这个属性

**修法**：查 provider 真实模型名所在属性（例如 `self.model` / `self._model` / `self.client.model`），统一暴露为 `provider.model_name`，并在 `factory.py` 给各 provider 实例设一次。

### 缺陷 2：`caller='unknown'` 占 56%

**现象**：每天 22:00-22:01 固定跑 4 次 small LLM 调用（137-197 tokens），另外 2 次大调用 11K tokens — 全部没 caller。

**根因**：某个 Celery 定时任务漏了 `set_caller(...)`。嫌疑人：`app/tasks/notifications.py` 的 evening_insights 或 anomaly_check。

**修法**：grep 22:00-22:30 触发的 celery task，补 `set_caller`。

### 缺陷 3：流式调用不追踪

`usage_tracker.py:135-138` 有意跳过 `stream=True`（怕破坏 AsyncIterator 语义）。但 `orchestrator.stream` 是真实高频调用点。短期可接受；中期用 `chat_completion_stream` 包装在流结束时累计记录。

## 三、Golden Set / Eval 体系（P1，从零建）

### 目标

1. **防 regression**：改 prompt / 换模型 / 升级 provider 前，跑 Golden Set 看关键指标有没有退步
2. **可归因**：出问题了能定位到哪个 agent / 哪种 case 坏掉
3. **可量化模型对比**：gpt-4o-mini vs Claude 3.5 vs OpenClaw 谁在什么场景更划算

### 选型（基于 Agent 调研）

**主方案：自写 ~350 行 harness + Langfuse self-host**

| 维度 | 选择 | 理由 |
|---|---|---|
| 主 | 自写 Python harness | 已有 `LlmUsageLog` 表承接 token 成本；我们不用 LangChain；350 行能覆盖需求 |
| 辅 | Langfuse(Docker 私有化) | Trace + Dataset + UI 三合一，非工程师也能维护 Golden Set |
| CI | GitHub Actions | 直接跑 pytest 风格 |

**备用：promptfoo**。如果自写 harness 出问题，YAML 配置 + CLI 一天起步，但没 obs。

**不选**：LangSmith（绑 LangChain）、Braintrust（贵）、OpenAI Evals（需代理）、DSPy（重）、ragas（偏 RAG）。

### Golden Set 三大 Suite

| Suite | 什么 case | Scorer | Ground Truth 来源 |
|---|---|---|---|
| `suite_safety` | "用户 BP 185/110 + 吃美托洛尔" → 预期触发 hypertension_urgent 告警 | `exact_match` 命中集合 | 手工标注 30 case + Safety Guardian 规则复算 |
| `suite_orchestrator` | "我最近总是睡不好, 怎么办" → 预期回答包含 readiness_zone + 2+ specialist finding + 不要出现虚假事实 | `llm_judge` 打 1-5 分 + 关键词必含检查 | 手工标注 20 case |
| `suite_insight` | 输入 30 天 fact+garmin+diet+anomaly → 预期 insight.evidence_refs 全部来自输入 | `grounding_check`（复用 `insight_generator.py` 里的 evidence 校验）+ confidence 边界检查 | 合成数据 20 case |

**可选 Suite 2.0**：`suite_kg_extract`（chat → triples），`suite_doctor_weekly`（Garmin 周数据 → 报告关键段落必含）。

### 组件设计（自写 harness）

```
backend/eval/
├── __init__.py
├── models.py              # GoldenCase / EvalResult / SuiteReport (Pydantic)
├── runner.py              # run_suite(name, baseline=None) → SuiteReport
├── scorers/
│   ├── exact_match.py     # 集合命中
│   ├── llm_judge.py       # gpt-4o-mini 打分 rubric
│   ├── grounding.py       # evidence_refs 溯源校验
│   └── keywords.py        # 必含/必不含关键词
├── datasets/
│   ├── safety.yaml        # 30 case
│   ├── orchestrator.yaml  # 20 case
│   └── insight.yaml       # 20 case
├── baselines/
│   └── main.json          # 上一次 main 分支的分数 — 作为 regression 参照
└── cli.py                 # python -m eval run --suite safety
```

**CI 集成**：PR 到 main 时跑 3 个 suite，若分数低于 baseline 任何一项 > 5%（硬阈值可调），标红不阻塞合并（软 gate，避免 flaky）。

**评分公式**：
```
suite_score = (accuracy * 0.6) + (1 - cost_usd_ratio) * 0.2 + (1 - latency_ratio) * 0.2
```
其中 `cost_usd_ratio` 和 `latency_ratio` 从 `llm_usage_logs` 同期 P50 归一化 — 让 Golden Set 既看质量也看成本。

## 四、落地顺序

| 阶段 | 工作 | 预估 | 交付 |
|---|---|---|---|
| A | 修 `model=unknown` + 补 `unknown` caller + 线上观察 1 天 | 2h | 线上 cost_usd 开始非 0 |
| B | 自写 eval harness 骨架 (runner + models + exact_match scorer + suite_safety 10 case) | 1 天 | `python -m eval run --suite safety` 能跑 |
| C | 补 suite_orchestrator + llm_judge scorer | 1 天 | 3 suite 齐全 |
| D | suite_insight + grounding scorer + baseline 对比 | 0.5 天 | regression 报告 |
| E | CI 接入（GitHub Actions 软 gate） | 0.5 天 | PR 自动评 |
| F（可选，后置）| Langfuse self-host + traces 接入 + dataset UI | 1-2 天 | 非工程师可维护 Golden Set |

总工期 A-E **约 3 天**，F 再加 1-2 天。和之前"Token 监控从零做 2 天"的估算相比，实际因为基础设施已有，省了 2 天。

## 五、决策点（需要 review）

1. **是否先干 A（修缺陷）再干 B-E（Eval）？** 推荐是 — 否则 eval 出来的 cost 也是 0。
2. **Eval suite case 数量** — 30/20/20 够不够？过少会过拟合，过多人工标注负担大。建议 v1 就这样，跑 2 周看是否需要扩。
3. **Langfuse 部署** — 是否在 ECS 同机跑？会多吃 1GB 内存（Clickhouse + Postgres）。可以先不上，等 B-E 跑通再评估。
4. **模型对比**（gpt-4o-mini vs Claude 3.5 vs 本地 Qwen）— 加不加到 harness 里？建议加到 runner 的 `--model` 参数，但 v1 只跑默认模型；对比 v2 再做。
