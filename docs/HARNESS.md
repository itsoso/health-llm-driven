# LLM Harness — 设计与方法论

本文档沉淀本项目里"如何让 LLM 为健康场景稳定输出"的工程设计。代码散落在 `backend/app/orchestrator/`, `backend/app/services/agent_executor.py`, `backend/app/services/llm/`, `backend/app/twin/`, `backend/app/services/tool_schema_registry.py`，本文档把这些放进一张图。

## 一句话原则

> **Verification is the bottleneck.** 让 LLM 多输出文本便宜，让 LLM 少出错贵；Harness 的工作不是让模型更强，是把可错环节限定在能验证的范围内。

具体落到 7 条设计原则：

1. **Source-aware** — Siri / Web / Voice / Push 不同入口，prompt / latency budget / 输出格式都不一样
2. **Verification before write** — 高确定性数值（体重/血压/疾病）写库前必须 LLM 复述+用户确认
3. **Tool schema 描述加厚** — 给 LLM 解释*为什么*选这个参数，不只是 type
4. **Memory 注入分 stage 可观测** — 4 stage 每个独立 ok/chars/count/error，写 audit
5. **Provider failover** — 主 LLM 失败兜底走 OpenClaw，不让用户看见故障
6. **Streaming + 按句 TTS** — 不等整段，第一句出来就播
7. **Prompt blob from Twin** — 数据先固化成 HealthTwin schema，再格式化为 prompt 段；不让 prompt 直接拼数据库行

---

## 1. Source-aware 路径

不同入口对延迟、格式、上下文深度的需求差几个数量级：

| Source | latency budget | 输出格式 | 路径 | 实现位置 |
|---|---|---|---|---|
| `siri` | 3–5 秒 | 口语化短句, 无 markdown, 数字口语化, ≤250 字 | **fast path**: 只跑 Twin + LLM, 跳过 specialist / arbitration / cross-review | `_run_orchestrator_fast` / `_stream_orchestrator_fast` |
| `voice-chat` | 流式 SSE, 按句出 TTS | 自然口语，可以稍长 | 标准 orchestrator + 按句切 chunk → TTS | `mobile/app/voice-chat.tsx` |
| `web` / `chat` | 8–15 秒 | markdown，数字突出，章节加竖线 | 标准 orchestrator (specialist + arbitration) | `app/orchestrator/orchestrator.py` |
| `push` (Open-Loop / Coach) | 异步，10s+ ok | 短句, deep_link, 故事化（"为什么 + 做什么"） | trust-loop pipeline | `app/services/notification/` |

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

写库类操作分两档：

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
2. **何时不用 > 何时用** — `health_query` 和 `health_analysis` 容易混，描述里直接对比"区别在于…"
3. **type 默认值约定** — `data` 字段的 schema 按 `type` 分支讲清，避免 LLM 把 `weight` 的 `value` 写成 `kg` 字符串
4. **side effects 要说** — 写库 / 触发推送 / 影响疾病追踪都要在 description 里点出，让 LLM 自己升级谨慎度

**别在后端做容错适配**：用户/AI 调错路径时，**修 schema 不修 router**。后端不该兜 LLM 的错（与 OpenClaw Skills 原则一致）。

---

## 4. Memory 注入：4 Stage 可观测

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

**实现**：`app/orchestrator/orchestrator.py::_call_llm`

```python
async def _call_llm(system_prompt, user_prompt) -> str:
    text = await _try(None)            # 默认 provider (TokenPlan / OpenAI)
    if not text:
        text = await _try("openclaw")  # 兜底 OpenClaw
    return text or ""
```

**Provider 优先级**（见 `app/services/llm/factory.py`）：
1. `tokenplan` — 阿里云 OpenAI 兼容套餐，国内直连低延迟，**当前生产默认**
2. `openclaw` — fallback，function calling 不支持但能保证有回答
3. `openai` — 配 API key 时可用
4. `ollama` — 本地开发

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

## 路由：什么时候走 Orchestrator vs Skill

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
- 命中 = 用户想"记录/写库"，走 OpenClaw skill（function calling）
- 不命中 = 查询/分析/对话，走 Orchestrator（specialist + arbitration）
- 含图片/文件 = 强制走 skill 路径（OpenClaw 有 vision）

**为什么用正则不用 LLM 路由**：
- 正则零延迟、可预测、可回归测试
- LLM 路由要再多一次调用 → 加 1-2s
- 错判时纠错路径清晰：加关键词到正则

**新增动词时**：直接改 `_NEEDS_SKILL_RE`，跑 `pytest tests/test_smoke.py` 看回归。

---

## 审计与可观测

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
- [ ] 写库的话，是否接 `_confirm_or_describe`？
- [ ] tool schema 是否包含示例值 + side effects 说明？
- [ ] 是否写 audit？反查接口是否能拼出 reasoning trace？
- [ ] 是否更新本文档（`docs/HARNESS.md`）？

文档漂移检查：本文档列出的"实现位置"路径每周快速走查一次，与代码不一致时立刻修文档（不修代码）。

---

## 历史决策与坑

| 时间 | 决策/坑 | 出处 |
|---|---|---|
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
