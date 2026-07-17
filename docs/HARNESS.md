# LLM Harness — 设计与方法论

> **这是「产品 LLM Harness」** —— 讲*健康 AI agent 怎么造*(source-aware path / verification before write / tool schema / memory 注入 / streaming)。它**不是**"编码 agent(Claude Code/Cursor)怎么在本仓库干活"的操作工具架 —— 那个的入口是 `CLAUDE.md`,设计见 `docs/design-agent-operating-harness.md`。**两者名字像,职责无关,别混。**

本文档沉淀本项目里"如何让 LLM 为健康场景稳定输出"的工程设计。代码散落在 `backend/app/orchestrator/`, `backend/app/services/agent_executor.py`, `backend/app/services/llm/`, `backend/app/twin/`, `backend/app/services/tool_schema_registry.py`，本文档把这些放进一张图。

写作原则：**先讲我们怎么做，再标注业界对应做法**。让设计有可追溯依据，但不被术语带跑。

## 业界参考词典

下面是本文档里沿用或对照的业界术语。每条都映射到我们具体在哪一节用：

| 业界术语 | 来源 | 我们在哪用 |
|---|---|---|
| **Augmented LLM** (LLM + 检索 + 工具 + 记忆) | [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) | Twin (§7) + Memory 注入 (§4) + Tool schema (§3) 三件合起来就是我们的 augmented LLM |
| **Workflow vs Agent** (固定路径 vs 自主循环) | 同上 | siri fast path / push pipeline 是 workflow；orchestrator + specialist 是 agent loop |
| **ACI (Agent-Computer Interface)** | 同上 | §3 Tool schema 加厚 = 投资 ACI |
| **Poka-yoke 工具设计** (设计上让 LLM 不容易犯错) | 同上 | §3 例子值 + side-effect 标注 + type 分支 schema |
| **Orchestrator-workers** | 同上 + [Anthropic — Multi-Agent Research](https://www.anthropic.com/engineering/multi-agent-research-system) | `app/orchestrator/orchestrator.py` lead + specialist 子 agent |
| **Evaluator-optimizer** | Anthropic | `app/orchestrator/cross_review.py` + `arbitration.py` 是这个 pattern |
| **Verification is the bottleneck** | [Karpathy](https://karpathy.bearblog.dev/) | §2 写库前 confirm |
| **Context engineering / Context rot** | [Anthropic — Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | §4 + §7 + 新增 §10 |
| **Just-in-time retrieval** | 同上 | §4 hybrid stage 按 query 检索而非全量预注入 |
| **Compaction / Tool result clearing** | 同上 | 我们当前缺，列入 §11 todo |
| **Strict mode** (JSON Schema 严格匹配) | [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling) | §3 Tool schema 当前未启用，列入 §11 todo |
| **Function calling 模式 AUTO/ANY/NONE** | [Google Gemini Function Calling](https://ai.google.dev/gemini-api/docs/function-calling) | §3 我们用 AUTO（让模型自选），高风险路径未来可考虑 ANY |
| **Compositional / Parallel function calling** | OpenAI / Gemini | §1 specialist 之间是 parallel；agent_executor 多轮工具是 compositional |
| **LLM-as-judge** | Anthropic 多 agent 文 + 业界 eval 主流 | §11 我们当前没有自动 eval，列入 todo |

## 一句话原则

> **Verification is the bottleneck.** 让 LLM 多输出文本便宜，让 LLM 少出错贵；Harness 的工作不是让模型更强，是把可错环节限定在能验证的范围内。

具体落到 7 条设计原则：

1. **Source-aware** — Siri / Web / Voice / Push 不同入口，prompt / latency budget / 输出格式都不一样
2. **Verification before write** — 高确定性数值（体重/血压/疾病）写库前必须 LLM 复述+用户确认
3. **Tool schema 描述加厚** — 给 LLM 解释*为什么*选这个参数，不只是 type（对应 Anthropic 的 ACI / Poka-yoke）
4. **Memory 注入分 stage 可观测** — 4 stage 每个独立 ok/chars/count/error，写 audit
5. **Provider failover** — 主 LLM 失败走模型注册表内的可用 provider，不让用户看见故障
6. **Streaming + 按句 TTS** — 不等整段，第一句出来就播
7. **Prompt blob from Twin** — 数据先固化成 HealthTwin schema，再格式化为 prompt 段；不让 prompt 直接拼数据库行

业界还有几条我们认同但尚未完整落地的，统一放 §11 缺口。

---

## 1. Source-aware 路径

**业界对应**：Anthropic 把"系统按预定路径走"叫 *workflow*，"LLM 在循环里自己决定"叫 *agent*。两者不是非此即彼，要按场景混用。我们就是这么做的：siri / push 是 workflow（路径写死），orchestrator + specialist 是 agent loop。Anthropic 的核心建议是 *"start with the simplest solution; add complexity only when it demonstrably improves outcomes"* — siri 走 fast path 就是把 workflow 用足，不为了"agent 化"硬上多步循环。

不同入口对延迟、格式、上下文深度的需求差几个数量级：

| Source | latency budget | 输出格式 | 路径 | 实现位置 |
|---|---|---|---|---|
| `siri` | 3–5 秒 | 口语化短句, 无 markdown, 数字口语化, ≤250 字 | **fast path / workflow**: 只跑 Twin + LLM, 跳过 specialist / arbitration / cross-review | `_run_orchestrator_fast` / `_stream_orchestrator_fast` |
| `voice-chat` | 流式 SSE, 按句出 TTS | 自然口语，可以稍长 | 标准 orchestrator + 按句切 chunk → TTS | `mobile/app/voice-chat.tsx` |
| `web` / `chat` | 8–15 秒 | markdown，数字突出，章节加竖线 | **agent loop**: orchestrator + specialist + arbitration | `app/orchestrator/orchestrator.py` |
| `push` (Open-Loop / Coach) | 异步，10s+ ok | 短句, deep_link, 故事化（"为什么 + 做什么"） | trust-loop pipeline (workflow) | `app/services/notification/` |

**判断在哪里分叉**：`OrchestratorRequest.source` 在请求入口就决定。

```python
# app/orchestrator/orchestrator.py
if req.source == "siri":
    return await _run_orchestrator_fast(db, user_id, req)
```

**反模式**：
- ❌ 在 specialist 内部根据 source 调整输出 → 路径已经走过重负载，没省到
- ❌ Siri 走完整 orchestrator 然后裁剪输出 → 用户已经超时退出 Siri

---

## 2. Verification before write（Karpathy 启发）

**业界对应**：
- Karpathy 反复强调 *generation 便宜，verification 不便宜* — 不要让 LLM 自主完成错了没法静默修正的操作。
- Google Gemini 官方建议："For high-impact actions (e.g., placing orders), confirm with the user before executing."
- OpenAI 函数调用最佳实践把这归到 "Avoid exposing destructive operations without confirmation loops" + "Use idempotency keys for state-changing operations"。
- Anthropic 把这归到 "Pause for human feedback at checkpoints or blockers" + "stopping conditions"。

我们的实现把它落到代码层：写库类操作分两档：

| 类别 | 例子 | 策略 |
|---|---|---|
| **低风险** | 饮水、补剂打卡、运动开始 | 直接执行，不需确认 |
| **高确定性** | 体重、血压、血糖、疾病/症状 | 写库前 LLM 必须复述 + 用户确认 |

**实现**：`app/services/agent_executor.py::_confirm_or_describe`

```python
def _confirm_or_describe(args: dict, data: dict, *, preview: str) -> str | None:
    """L8 (Karpathy 'verification is the bottleneck'):
    高确定性 health_record 写库前强制 LLM 复述给用户确认.

    第一次调用 (无 confirmed flag): 返回 [NEEDS_CONFIRMATION] 提示, 不写库.
    LLM 看到提示会复述给用户, 用户答'是的' → LLM 重新调用 + confirmed=true.
    """
    confirmed = (
        args.get("confirmed") is True or args.get("confirm") is True
        or data.get("confirmed") is True or data.get("confirm") is True
    )
    data.pop("confirmed", None)
    data.pop("confirm", None)
    if confirmed:
        return None
    return (
        f"[NEEDS_CONFIRMATION] 我准备记录: {preview}. "
        f"请向用户复述并问一次'是这样吗？', "
        f"用户确认后**重新调用** health_record 并在 data 里加 confirmed=true."
    )
```

**调用方**：

```python
# weight / blood_pressure / illness 三类
check = _confirm_or_describe(args, data, preview=", ".join(preview_bits))
if check is not None:
    return check  # tool_result 直接返回 [NEEDS_CONFIRMATION] 给 LLM
# 否则继续写库
```

**为什么要 LLM 复述而不是 UI 弹窗确认**：
- UI 弹窗要每个 type 单独写组件
- LLM 复述能自然融进对话流，"我记一下你血压 138/92，对吗？"
- 复述同时校对了 LLM 自己解析得对不对（用户说"血压 138 / 92 心率 72"，LLM 把 72 当舒张压就会被复述暴露）

**已应用 type**: `weight`, `blood_pressure`, `illness`。新增高确定性 type 必须接入。

---

## 3. Tool Schema 描述加厚

**业界对应**（这一节业界共识最强）：

- **Anthropic ACI 原则**：Tool 是 Agent-Computer Interface，要"像给 junior dev 写 docstring 一样"写描述。Anthropic 自报花在 ACI 上的时间比花在主 prompt 上的多。一个工具描述重写 + 测试 agent 把任务完成时间降低了 **40%**（来自 Multi-Agent Research 文章）。
- **Anthropic Poka-yoke 原则**：tool schema 设计上让 LLM 难犯错（例：要求绝对路径而非相对路径，避免 escaped string，避免要求 LLM 数行号/字符）。
- **OpenAI**：snake_case + verb-noun 命名（`get_weather` / `send_email`）；用 `enum` 替代 free-string；嵌套越深越不可靠；同一会话内**工具数量 < 20**（>20 用 routing 或 retrieval 子集化）；详细描述在哪些情况*不*调用此工具。
- **Google Gemini**："descriptions must be clear and specific"；用 `enum` 不用 free string（"improves accuracy"）；活跃工具集 10–20 上限；嵌套深 schema 在 `ANY` 模式可能被拒；不要用 `dict[str: int]` 这种 free-form map。
- **Strict mode** (OpenAI `gpt-4o-2024-08-06+`) / **VALIDATED mode** (Gemini)：保证 schema 严格匹配，代价是所有 fields 必须 required + `additionalProperties: false`。
- **tool_choice 强制**：OpenAI 的 `tool_choice` / Gemini 的 `tool_config: ANY`，我们当前没用，但适合"这一步必须走某个工具"的场景（见 §11 缺口）。

**反模式**：

```python
{
  "name": "dimension",
  "type": "string",
  "description": "数据维度"  # ❌ LLM 还是猜
}
```

**正确做法**（`backend/app/services/tool_schema_registry.py`）：

```python
{
    "name": "health_query",
    "description": """查询用户的健康数据. 根据用户问题选对 dimension 是关键.
    [然后列出每种 dimension 适用场景的判断指南]""",
    "parameters": {
        ...
        "dimension": {
            "description": "数据维度. 见 function description 里的选择指南",
        },
        "days": {
            "description": "查询最近几天. 昨天=1, 最近/本周=7, 本月=30",
        },
        "indicator": {
            "description": "具体指标名 (仅 medical_exam / genetic). 例: HCY, LDL, HbA1c, MTHFR, APOE",
        },
    }
}
```

**加厚原则**：
1. **示例值 > 类型描述** — 写 "昨天=1, 本周=7" 比写 "天数(int)" 让 LLM 选得准
2. **何时不用 > 何时用** — `health_query` 和 `health_analysis` 容易混，描述里直接对比"区别在于…"（OpenAI 官方建议 "specify when NOT to call a function"）
3. **type 默认值约定** — `data` 字段的 schema 按 `type` 分支讲清，避免 LLM 把 `weight` 的 `value` 写成 `kg` 字符串
4. **side effects 要说** — 写库 / 触发推送 / 影响疾病追踪都要在 description 里点出，让 LLM 自己升级谨慎度
5. **enum > free string** — 选择有限的字段（type、dimension、analysis_type）必须用 `enum`，业界共识

**别在后端做容错适配**：用户/AI 调错路径时，**修 schema 不修 router**。后端不该兜 LLM 的错（与 Agent Skills 原则一致）。

**当前未启用，但应该启用的**：
- OpenAI strict mode (`"strict": true` + `additionalProperties: false`) — 强约束 LLM 输出 JSON 严格匹配 schema，TokenPlan 接的 OpenAI 兼容协议应该支持，需验证
- 工具数量监控 — 当前 `tool_schema_registry` 5 个工具远低于 20 上限，安全；新加工具时记得查这条

---

## 4. Memory 注入：4 Stage 可观测

**业界对应**：Anthropic 在 [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 里把 prompt 工程"升级"成 *context engineering*：把进入上下文的 token 当稀缺资源管。我们的 `_inject_memory` 实现了其中两类技术：

- **Just-in-time retrieval**：hybrid stage 按 query 实时检索，不把所有 facts 预置到 prompt。Anthropic："agents hold lightweight references and load data dynamically at runtime"。
- **Hybrid retrieval**：directives + case_timeline 是预先拉的（高频确定性），hybrid stage 是按需的（低频长尾）。Anthropic 的 Claude Code 也是这种混合：`CLAUDE.md` 预置 + `grep`/`head` 按需。

**Anthropic 还推荐但我们当前缺的**（见 §11）：
- **Compaction** — 接近 context limit 时把对话压缩重启
- **Tool result clearing** — 把老的 tool_call output 截掉
- **Structured note-taking** — agent 写 NOTES.md 持久化超出 context 的状态（Claude Plays Pokémon 用这个跨数千步保留地图）

**实现**：`app/orchestrator/orchestrator.py::_inject_memory`

每次调用注入 4 个独立 stage，每个独立成功/失败：

| Stage | 内容 | 失败时影响 |
|---|---|---|
| `conversation` | 通用对话记忆（过敏/医嘱/偏好） | 失去人格化，但不影响 specialist 判断 |
| `case_timeline` | 当前 finding 关联 metric 的近 N 次历史 | specialist 看不到趋势上下文 |
| `directives` | 医生/用户硬性指令（必须遵循） | **严重** — specialist 可能给出违反医嘱的建议 |
| `hybrid` | BM25 + Graph + RRF 融合检索（LLM Wiki v2） | 失去长尾事实回忆 |

**每 stage trace**：

```python
trace["stages"][name] = {
    "ok": bool, "chars": int, "count": int, "error": str | None
}
```

**写 audit**：`agent_type='memory_injection'`，给 observability dashboard 聚合。

**Why 这么设计**：
- 之前一个 try/except 包整段，22 次失败被静默吞 — 用户感觉"AI 不记得我"，没数据查
- 现在每 stage 独立，dashboard 看到 `directives.ok` 突然掉 → 立刻能定位是 directive_parser 出问题
- 主 audit (`log_orchestrator_run`) 也带 `memory_referenced` 字段，靠 `memory_reference_detector` 检查回答里是不是真用上了注入的记忆 — 注入≠用上

**关键文件**：
- 注入：`app/orchestrator/orchestrator.py::_inject_memory`
- 引用检测：`app/services/memory_reference_detector.py`
- audit 聚合：`app/services/observability_service.py::G. Memory Injection (T1.1)`

---

## 5. Provider Failover

**业界对应**：OpenAI / Anthropic 文档都建议"return informative errors back to the model so it can self-correct" — 但这个是模型层。我们这里的 failover 是**provider 层**：主 provider 整个挂掉时切到备份。Anthropic 在多 agent 文里也用类似 retry + checkpoint 思路应对长循环里的 transient 失败。

**实现**：`app/orchestrator/orchestrator.py::_call_llm`

```python
async def _call_llm(system_prompt, user_prompt) -> str:
    text = await _try(None)            # 默认 provider (TokenPlan / OpenAI)
    if not text:
        text = await _try("tokenplan")  # 显式兜底到注册表内 provider
    return text or ""
```

**Provider 优先级**（见 `app/services/llm/factory.py`）：
1. `tokenplan` — 阿里云 OpenAI 兼容套餐，国内直连低延迟，**当前生产默认**
2. `openai` — 配 API key 时可用
3. `ollama` — 本地开发

**两个失败模式都要兜**：
- 网络层失败（超时/5xx）→ raise → catch 走 fallback
- 业务层"成功但空"（content 是空串）→ return None → 走 fallback

**LLM 调用超时**：60s → 120s（commit `7425dca`），原因是 specialist 链调用偶发慢，60s 直接超时丢推理。

**TokenPlan provider 切换**：admin 可在 `/admin/llm-provider` ping + 切换（见 `e298dda`）。

---

## 6. Streaming + 按句 TTS

**问题**：voice-chat 等整段 LLM 输出再播 → 用户感觉延迟 5-10s。

**方案**（commit `76cd7a9`）：
1. backend `provider.chat(stream=True)` → 按 chunk yield
2. mobile 侧累积 chunk → 检测句尾（`。！？\n`）→ 切句 → 推 TTS
3. 句还没完时 partial 显示在 UI（避免首屏空白）

**关键文件**：
- backend stream：`app/orchestrator/orchestrator.py::_stream_llm` / `_stream_orchestrator_fast`
- mobile：`mobile/app/voice-chat.tsx`（按句切 + TTS 队列）
- 历史踩坑：`useEffect` deps 含 state/submit 导致 listener 重挂覆盖，partial events 全丢（commit `dc63950`）

**TTS 后端**：阿里云 CosyVoice v2 / v3.5-plus，声音复刻。`app/services/tts/`。

---

## 7. Twin → Prompt Blob

**业界对应**：Anthropic context engineering 文章把这归到 "system prompts at the right altitude" — 不要堆 raw 数据，也不要泛泛说"你是健康助理"。Twin 是中间层：固化 schema + freshness 标签 + 异常优先 = high-signal token。Anthropic："find the smallest set of high-signal tokens that maximize the likelihood of the desired outcome"，正是这个意思。

**为什么不直接 dump 数据库行给 LLM**：
- DB schema 含字段名、null、time zone — LLM 解读容易跑偏
- 不同 specialist 关心不同切片，重复格式化代码会发散
- 数据陈旧度（freshness）必须显式表达，不然 LLM 把 30 天前血压当当前值

**方案**：先把数据固化成 `HealthTwin` schema (`app/twin/schema.py`)，再用 `twin_to_prompt_blob` 格式化（`app/twin/formatter.py`）：

```python
def twin_to_prompt_blob(twin: HealthTwin, max_abnormal: int = 5, max_genes: int = 8) -> str:
    """把 HealthTwin 转成 LLM 可读 markdown blob.
    - freshness 用 '今天/3 天前/已过期' 描述, 不给 raw timestamp
    - abnormal 优先, 正常值省略, 减少 token
    - 基因只列与当前 finding 相关的 max_genes 个
    """
```

**Freshness 显式语言化**（`_age_label`）：

| 时间差 | 标签 |
|---|---|
| 0-1 天 | "今天" / "昨天" |
| 2-7 天 | "3 天前" |
| 7-30 天 | "上周" / "本月" |
| > 30 天 | "已过期" |

LLM 看到"已过期"会主动说"建议你重新测一下"，看到 raw timestamp 会当当前值用。

---

## 7.5. Coach Persona — 语气切换 (P3-1, 2026-05-11)

**问题**: 同一份 specialist 输出 + 同一份 Twin, 不同用户期望的语气差极远。爱看数据的工程师要"减到 5g/天",慢性病老人要"少放点盐"。一个 prompt 服所有人 = 谁都不满意。

**实现**: `app/orchestrator/orchestrator.py::_build_persona_addendum`

`User.coach_persona` 三档:

| 档 | 风格 | 关键指令 |
|---|---|---|
| `strict_coach` | 严厉教练 | 直接命令式, "立刻/必须/今天就", 最多 1 个行动, 借口被数据反驳 |
| `gentle_advisor` (默认) | 温和顾问 | 共情开场, 解释 why, 2-3 个可选行动, 缓冲词允许 |
| `data_driven` | 数据派 | 每条带数字阈值, 禁"适量/规律"模糊词, metric→action→expected change 三段 |

**注入位置**: 末尾追加在 system_prompt 第 12 条, 不改前 11 条规则 (信任校准/冲突仲裁/Trust Loop/显式归因 全部保留)。siri fast path 不走 persona (已有自己的口语化规则)。

**为什么不用 LLM 选 persona**: 用户偏好稳定 (一选三个月不会换), 让 LLM 每次推理 = 浪费 token + 不一致。让用户在 Settings 里显式选, prompt 拼接零成本。

**API**:
- `GET /api/v1/users/me/coach-persona` → `{coach_persona}`
- `PATCH /api/v1/users/me/coach-persona` body `{coach_persona}` 三档之一

**反模式**:
- ❌ 在 specialist 内部根据 persona 改输出 — specialist 是确定性裁决, 不该看 persona
- ❌ 加 persona-specific specialist (如 "StrictCoachAlertSpecialist") — 维护爆炸, 1 specialist × 3 persona = 3 倍代码

---

## 7.6. Starter polish — rules-cast-facts → LLM 改写 → 确定性 verify gate (2026-07)

**问题**: 首页对话起手 chip 由 21 条确定性规则生成 (`conversation_starters._build_candidates`), 内容正确但措辞生硬 ("今天恢复评分 40，帮我安排轻负荷或休息日方案")。想让措辞更自然, 又绝不能让 LLM 编造规则没说过的数字/实体/医嘱。

**做法**: RULES 仍是唯一事实源, LLM 只改写措辞, 一道**确定性** verify gate 拒掉 LLM 编造的内容, 回退到规则模板文本。**fail-safe = 规则文本, 永远。**

```
RULES → cast facts → LLM 改写 → verify gate → serve
                                    ↓ reject
                                 规则模板文本
```

**self-grounding 锚点**: facts 直接从模板文本抽 (数字/单位), 不重构 21 个 generator。凡模板文本里已出现的数字/实体都是规则批准的 —— verify gate 就拿"两条源文本的并集"当锚点集。

**verify_polished 四道** (`app/services/starter_polish.py`, 纯函数, 硬单测):
- **number anchoring**: 输出里每个数字串 (含小数/百分号) 必须逐字出现在源文本, 否则拒。
- **red-word denylist**: 剂量/mg/毫克/停药/加量/减量/换药/服用/每天吃/处方 —— 源文本没出现就拒 (源里有 = 规则已经说了, 放行)。
- **form check**: 必须以 ？/? 结尾, 或不含祈使标记 (应该/必须/立即去); 裸命令句拒。
- **length**: strip 后 6..40 字, 越界拒。
- synthesis 合并项额外: `combines` 必须是输入 key, 且文本对两条源文本的并集过全部上面四道。

**弱模型 JSON 防御** (glm/minimax 教训): 剥 code fence → 弯引号归一 → `json.loads`, 失败再正则抠 `[...]` 数组; 任何解析失败 → 返回 None (调用方回退规则)。**永不抛到 endpoint。**

**cache + progressive enhancement**: `signals_hash = sha256(sorted [key+text])[:16]`, Redis key `starter_polish:{user_id}:{hash}` TTL 6h。命中 → 服务润色文本; miss → 立即服务规则文本 + FastAPI `BackgroundTasks` 后台 warm (endpoint 是 sync `def`, 用 framework-native BackgroundTasks 而非线程/celery)。响应加 `polished: true/false` (additive, 移动端 Pydantic extra-safe) 便于日志里量化 adoption。

**flag / 模型**: `STARTER_LLM_POLISH_ENABLED`(默认 True)+ `STARTER_LLM_POLISH_MODEL_ID=deepseek-v4-flash`(fast 档 + 可靠 + 纯文本, 最便宜)。flag 关 / redis down / provider error → 与纯规则行为**字节一致**。usage 记账走 wrap_provider + `set_caller("starter_polish")`, 免费接上。

**反模式**:
- ❌ 让 LLM 直接产 chip (无锚点 = 编造数字, 健康场景直接说错)。
- ❌ 把 verify 建成"LLM 自评" (judge 只 advisory); 这里 gate 是确定性纯函数。
- ❌ 同步等 LLM 阻塞 endpoint; 起手 chip 是启动关键路径, 必须立即返回规则文本。

---

## 8. 路由：什么时候走 Orchestrator vs Skill

**业界对应**：Anthropic 把 *routing*（分类后分流）列为五大 workflow pattern 之一，建议"separation of concerns and building more specialized prompts"。我们用正则做 router 而不是 LLM 做 router 是个有意识的取舍 — Anthropic 也强调 *"start with the simplest solution"*。

**实现**：`app/services/agent_executor.py::_needs_skill`

```python
_NEEDS_SKILL_RE = re.compile(
    r"记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|"
    r"早餐|午餐|晚餐|加餐|夜宵|早饭|午饭|晚饭|"
    r"固化到|钉到首页|保存到首页|加到计划|"
    r"大卡|kcal|热量.*记|记.*热量"
)
```

**判定**：
- 命中 = 用户想"记录/写库"，走 AgentExecutor tool-calling
- 不命中 = 查询/分析/对话，走 AgentExecutor 或 Orchestrator（specialist + arbitration）
- 含图片/文件 = 走 AgentExecutor vision/file 路径

**为什么用正则不用 LLM 路由**：
- 正则零延迟、可预测、可回归测试
- LLM 路由要再多一次调用 → 加 1-2s
- 错判时纠错路径清晰：加关键词到正则

**新增动词时**：直接改 `_NEEDS_SKILL_RE`，跑 `pytest tests/test_smoke.py` 看回归。

---

## 9. 审计与可观测

每条 orchestrator 调用必须写 audit（`app/agents/audit.py`）：

| audit_type | 内容 | 用途 |
|---|---|---|
| `orchestrator_run` | 主调用：输入/输出/specialist 列表/memory_trace/memory_referenced | 还原决策 + reasoning trace |
| `memory_injection` | 4 stage 的命中详情 | dashboard 反查"AI 真的记得吗" |
| `cross_review` | specialist 间检测到的冲突 | 衡量裁决频率 |
| `llm_arbitration` | LLM 仲裁的 winner / confidence | 可信度评估 |
| `safety_guardian` | safety hook 检测到的 alert + 上下文 | reasoning trace 反查 |
| `client_event` (mobile) | 挂载/打开/click 5 类事件 | 行为率 → suggestion |

**反查接口**：
- `/safety/{audit_id}` / `/specialist/{audit_id}` — explainer 拼 trace, 不调 LLM
- mobile `ExplainSheet` / `ExplainButton` 直接展开

---

## 10. 多 Agent 与 Sub-agent 设计取舍

我们的 orchestrator + 10 specialist 是 **orchestrator-workers** pattern 的实现 — Anthropic Multi-Agent Research 文章里的核心架构。但他们的经验里有几个我们必须警惕的失败模式：

### Anthropic 报告的多 agent 失败模式

| 失败模式 | Anthropic 现象 | 我们的对策 / 现状 |
|---|---|---|
| **Token 成本爆炸** | 多 agent 系统用 *15× chat 单次 token*，只有"高价值任务"才划算 | 我们 specialist 跑在 Twin blob 上（已压缩），且 siri fast path 直接跳过；普通查询不会触发 10 个 specialist 全跑 |
| **Coordination 爆炸** | 早期 agent 给简单查询 spawn 50 个子 agent | 我们 specialist 注册表是静态的，`applies_to(intent, twin)` 决定是否跑 — 不是 LLM 自由 spawn |
| **Duplicate work** | 模糊 delegation 导致子 agent 重复劳动 | specialist 之间靠 `SpecialistContext`（如 readiness_zone）显式传，不靠 LLM 协调 |
| **Synchronous bottleneck** | Lead 等所有子 agent，无 mid-flight steering | 我们当前也是同步等 — 列入 §11 |
| **Compounding errors** | Stateful 长循环出错时不能简单 restart | 我们 specialist 是无状态的，重跑没副作用；但写库类操作（agent_executor）有 — 靠 §2 verification 兜 |
| **Source bias** | Agent 偏 SEO 内容 | 我们 KnowledgeLibrarian 默认走 reviewed System KB V2（本地 DB + reviewed artifacts），来源固定且有 review gate；legacy Chroma/RAG 默认关闭 |

### Anthropic 报告的多 agent 收益（我们已得到的）

- **并行 + context 隔离**：specialist 跑在自己的 Twin partition 上，不污染主 prompt（Anthropic："subagents enable compression via parallel context windows and separation of concerns"）
- **专业化 prompt**：每个 specialist 自己的 prompt 比一个大 prompt 准（Anthropic 内部 eval：多 agent + Opus lead/Sonnet 子 agent 比单 agent Opus **多 90.2%**）
- **可观测 / 可解释**：每 specialist 单独写 audit，reasoning trace 能反查（mobile ExplainSheet）

### 决策规则

**新加 specialist 之前问 3 个问题**：

1. 这个判断**确定性强吗**？强 → 写规则进 SafetyGuardian，不要起 specialist
2. 它**复用 Twin 的哪个 partition**？答不上来 → 数据没准备好，不该上 specialist 层
3. 它的输出**会被 LLM 合成消费**还是**直接展示**？前者就是 specialist，后者写普通 service 就够

**反模式**：把"我希望 LLM 多想想"包装成 specialist。Anthropic："start simple — single LLM call with retrieval and in-context examples"。

---

## 11. Eval、缺口与 todo

业界主流的 LLM 工程 stack 里，下面几项我们当前**没有**或**只有一半**，列出来诚实标记：

### 11.1 LLM-as-judge eval 套件 ✅(两层,2026-07-17 R3 补齐行为层)

**业界做法**：Anthropic 在 multi-agent 文里把 LLM-as-judge 列为最 scalable 的 eval 方式 — 一个 rubric prompt 出 0.0–1.0 分 + pass/fail，配合 ~20 个 representative queries 就能复现 30% → 80% 的差异。

**我们现状(两层分工)**：
- **质量层**:`backend/evals/comparative/`(16 题六家族 battery + LLM judge + cadence 例行,
  只读打生产)——评"答案好不好"。
- **行为层**:`backend/evals/behavior/xiaoba_core.yaml`(22 题七家族)+
  `tests/test_behavior_battery.py`——断言意图分类/确认档位/工具子集/卡片门控/兜底话术/
  remember 医疗硬闸/快路由上下文这些**确定性层**,零 LLM 零网络,CI 阻断常跑。
  三条历史 regression(卡片误发/兜底饮食偏见/食物抱怨误记)编入回溯校准。
- **流程强制**:改 prompt/路由的增量(R1 compaction / R5 渐进披露)翻 flag 前:
  行为 battery 全绿 + comparative battery 无回退。

### 11.2 OpenAI Strict Mode ❌

**业界做法**：`"strict": true` + `additionalProperties: false` 让 LLM 输出 100% 匹配 schema。

**我们现状**：tool_schema_registry 没启用 strict。TokenPlan 兼容协议是否支持需先验证。

**Todo**：试 `health_record` 一个工具开启 strict，跑回归看是否减少 schema 错误（最直接收益是减少 `data` 字段缺字段的兜底分支）。

### 11.3 Compaction / Tool result clearing ❌

**业界做法**：Anthropic 推荐接近 context limit 时压缩对话；tool_call 老 output 丢弃。我们 voice-chat 长对话场景已经会触到这条边界。

**我们现状**：`memory_extractor` 在对话结束时抽事实写 memory_facts（✅ 部分实现 *structured note-taking*），但**没有运行中的 compaction** — 单次对话内 turn 数多了仍会积累。

**Todo**：voice-chat 加 turn count 阈值，到 N turn 自动压缩；或对话退出时不只抽 facts 也抽"未解决任务"。

### 11.4 Force tool_choice ⚠️

**业界做法**：OpenAI `tool_choice: {"type": "function", "function": {"name": "X"}}` / Gemini `tool_config: ANY`，强制 LLM 必须走某个工具。

**我们现状**：全用 AUTO，靠 prompt 说"必须调 health_record"。

**Todo**：体重/血压等高风险记录路径，识别意图后强制 tool_choice，避免 LLM "决定先聊一句不调工具"。

### 11.5 Mid-flight steering ❌

**业界做法**：Anthropic Multi-Agent 文里指出 lead agent 同步等所有子 agent 是 bottleneck，理想是子 agent 出第一批结果时 lead 能调整剩下的。

**我们现状**：specialist 全部跑完才进 LLM 合成。

**Todo**：暂时不优先 — specialist 数量少（~10 个 / 单次 ~3-5 个 applies）成本可控。等 specialist 增多再考虑。

### 11.6 Deep eval 的 source bias / hallucination 测试 ❌

**业界做法**：Anthropic 强调 "human testing still catches hallucinations, edge cases, and source bias automation misses"。

**我们现状**：只有用户实测反馈（已在 `feedback_supplement_analysis.md` / `feedback_gene_analysis_errors.md` 累积）。

**Todo**：把这些反馈编进 11.1 的 eval rubric — 比如"基因解读不能把 FADS1/SOD2/GPX1 误判为风险"作为强校验。

---

## 不要做的事

- ❌ **直接把 DB row dump 给 LLM** — 走 Twin
- ❌ **JSON 输出依赖 LLM 自觉** — 用 tool_call 结构化，不靠 prompt 让它"返回 JSON"
- ❌ **后端兜 LLM 调错路径** — 修 tool schema / Skill 定义，不加别名 router
- ❌ **同步等 LLM 整段返回再处理** — 流式 + 按句切
- ❌ **noop fallback 静默成功** — native module 不可用要么抛错要么返回明显 sentinel（`-1` / `'native-unavailable'`），不能 `return 0` 让上层以为成功
- ❌ **memory 注入用一个大 try/except** — 每 stage 独立 ok/error，否则故障静默
- ❌ **写库类操作不复述** — 高确定性数值必须 `_confirm_or_describe`
- ❌ **不同 source 跑同一条路径** — Siri 必须 fast path

---

## 新加 Harness 能力的 checklist

每加一个新能力（新 specialist / 新 source / 新 tool / 新 memory stage），同 PR 必须：

- [ ] 是否需要 source-aware 分支？（latency budget 是不是和现有 source 一样？）
- [ ] 写库的话，是否接 `_confirm_or_describe`？（业界 = high-impact action confirmation loop）
- [ ] tool schema 是否包含示例值 + side effects 说明？enum 字段是否用了 `enum`？
- [ ] 工具数量是否仍 ≤ 20？（OpenAI / Gemini 共识上限）
- [ ] 是否写 audit？反查接口是否能拼出 reasoning trace？
- [ ] 新 specialist 是否回答了 §10 的"3 个问题"？
- [ ] 是否更新本文档（`docs/HARNESS.md`）？

文档漂移检查：本文档列出的"实现位置"路径每周快速走查一次，与代码不一致时立刻修文档（不修代码）。

---

## 业界文献索引

整理时实际读过、写本文档时引用的来源：

- **Anthropic — [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)** (2024-12)
  augmented LLM、workflow vs agent、5 个 workflow pattern、ACI、Poka-yoke。本文档结构骨架来自这里。
- **Anthropic — [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)** (2025)
  orchestrator-workers 实战、多 agent 失败模式、tool 重写降 40% 完成时间、token 15× 成本。§10 取自此。
- **Anthropic — [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)** (2025)
  context rot、just-in-time retrieval、compaction、structured note-taking、sub-agent。§4 / §7 / §11.3 取自此。
- **OpenAI — [Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)**
  strict mode、parallel/compositional、tool_choice、descriptions 写法、< 20 tools 上限。§3 取自此。
- **OpenAI — [Structured Outputs Guide](https://platform.openai.com/docs/guides/structured-outputs)**
  strict mode 的 schema 限制（必须 required + additionalProperties: false）。§3 / §11.2 取自此。
- **Google Gemini — [Function Calling docs](https://ai.google.dev/gemini-api/docs/function-calling)**
  AUTO / VALIDATED / ANY / NONE 模式、enum 提升准确性、10–20 tool 上限、`thought_signature` 处理。§3 / §11.4 取自此。
- **Andrej Karpathy — "verification is the bottleneck"** ([blog](https://karpathy.bearblog.dev/) + 多次推文)
  generation cheap / verification expensive、autonomy slider、"decade of agents"。§2 / L9 autonomy slider 取自此。
- **Anthropic — [Model Context Protocol](https://modelcontextprotocol.io/)**
  我们的 MCP server (`mcp-server/`) 的协议基础。

更新约定：新引一篇业界文，加到本节，并在文档对应章节加 inline 链接。

---

## 历史决策与坑

| 时间 | 决策/坑 | 出处 |
|---|---|---|
| 2026-06-28 | 体检/化验 chat 路径(agent_executor)补 `knowledge_search` RAG 工具(接 dedao wiki chroma,fail-honest 区分"不可用"vs"零命中"防编造引用)+ `lab_plausibility` 输入合理性闸(SpO2 53% 类录入错误:语义=核实不抑制,危急值绝不忽略)+ R4 prompt 硬化(补剂非处方化/改善须标"相关非因果"/结构发现不下"无需处理"/⚠️值先核实再处置) | 本次 |
| 2026-05-05 | weight / BP / illness 写库前必须 confirm | `b0926af`, `8522c75` |
| 2026-05-05 | tool schema 描述加厚（dimension/type 选择指南） | `5179678` |
| 2026-05-05 | memory_extractor 接 messages 数组（不是 string） | `738ddf0` |
| 2026-05-05 | voice-chat 关闭后自动抽 facts 写 memory_facts | `7d85e86` |
| 2026-05-04 | LLM 调用 read 超时 60s → 120s | `7425dca` |
| 2026-05-04 | mobile/voice 切流式 + 按句 TTS | `76cd7a9` |
| 2026-05-04 | TokenPlan provider + admin 切换 | `e298dda` |
| 2026-05-04 | observability T1.1: memory 4 stage 命中率 | `d6db34d` |
| 2026-05-04 | orchestrator audit 加 memory_trace + 引用检测 | `02e12b9` |
| 2026-05-03 | source=siri 走 fast 路径，3-5 秒返回 | `8a24fc7` |
| 2026-05-03 | siri prompt 口语化合成 | `dd27fa3` |
| 2026-05-04 | partial events 丢失根因（useEffect deps） | `dc63950` |
