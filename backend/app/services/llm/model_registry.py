"""
LLM 模型注册表 — 单一真相源, 给 admin UI 列出可选, 给 factory 解析 provider.

每个 entry 描述: provider 类型 + 实际模型名 + 显示标签 + 速度档.

speed_tier:
  - fast       : 1-3s, 用于工具调用 / 简短回答
  - balanced   : 3-8s, 通用对话
  - reasoning  : 10s+, 深度分析 (qwen3.6-plus / o1 系)

provider:
  - openai-proxy : 走 OPENAI_BASE_URL (代理), 用 OPENAI_API_KEY
  - tokenplan    : 走 TOKENPLAN_BASE_URL (阿里百炼), 用 TOKENPLAN_API_KEY
  - moonshot     : 月之暗面官方 API (需独立 KIMI_API_KEY, 暂未配置)
  - zhipu        : 智谱 GLM 官方 API (需独立 ZHIPU_API_KEY, 暂未配置)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelEntry:
    id: str               # 唯一标识, 也是 admin UI / 切换时传的 key
    label: str            # 显示给用户
    provider: str         # 上面 provider 枚举之一
    model: str            # 真正传给 API 的 model 字段
    speed_tier: str       # fast / balanced / reasoning
    note: str = ""        # 可选: 一句话特点
    requires_env: tuple[str, ...] = ()   # 这个 model 需要哪些 env 才能用
    capabilities: tuple[str, ...] = ("text_generation",)
    chat_selectable: bool = True
    reliable_tool_calling: bool = True
    # ↑ 该模型做 function-calling 是否可靠 (吐合规的 tool_calls, 而非把工具调用
    #   写成文本 / 弯引号 JSON / [claim:] 泄漏)。False = 经验上不稳, 需要工具的
    #   agent 回合会门控回退到可靠模型 (见 agent_executor._resolve_chat_provider)。
    #   纯文本分析/问答不受影响。拿不准时保守标 True。
    supports_streaming: bool = True
    # ↑ 该模型是否真流式 (逐 token SSE)。False = 上游整段一次性返回 (ttft≈total),
    #   例如 langbridge-proxy 经万擎公网转发的商用模型: 网关无 SSE, 整段答案一次到。
    #   agent_executor 在答案轮据此发一条 thinking 状态 detail, 让 mac 端如实显示
    #   「需等待完整回答」而非误导性的 token 滚动。拿不准时保守标 True (走正常滚动)。
    supports_thinking_budget: bool = False
    # ↑ 该模型是否接受 DashScope/qwen 的思考控制参数 (enable_thinking / thinking_budget,
    #   经 extra_body 顶层放置)。True 才允许 agent_executor 在合成轮给思考阶段封顶
    #   (SYNTHESIS_THINKING_BUDGET, 砍 in-call TTFT)。fail-closed 默认 False: 只对
    #   **真网络探针验证过**该参数的模型置 True (见 scripts/probe_qwen_thinking_budget.py),
    #   未验证模型置 True 会让端点 400 打死合成轮。拿不准时保守留 False。
    supports_forced_tool_choice: bool = False
    # ↑ 该模型是否接受 named-function tool_choice(须与 enable_thinking=false 成对:
    #   qwen 系 thinking 模式下 tool_choice=object/required 会 400)。fail-closed 默认
    #   False: 只对真网探针验证过的模型置 True(scripts/probe_tool_choice_strict.py,
    #   2026-07-17 双模型 PASS 且参数合法)。R2 记录轮 force 只对 True 模型生效。
    supports_explicit_cache: bool = False
    # ↑ 该模型是否支持 DashScope compatible-mode 的显式上下文缓存 (Anthropic 式
    #   cache_control ephemeral 断点)。True 才允许 agent_executor 在 flag 开时给该模型
    #   的请求在 append-only 边界注入缓存断点 (LLM_EXPLICIT_PROMPT_CACHE, 让合成轮跳过
    #   重复 prefill 整条 system)。fail-closed 默认 False: 只对**真网络探针验证过**
    #   cache_control 生效 (usage.prompt_tokens_details.cached_tokens 透传 + TTFT 下降) 的
    #   DashScope 模型置 True (见 scripts/probe_explicit_cache.py)。未验证模型置 True 有被
    #   端点拒/忽略无效断点的风险。拿不准时保守留 False。


# 注册表 — 加新模型只改这里
MODELS: List[ModelEntry] = [
    # ──── 阿里百炼 TokenPlan (国内直连, 套餐固定计费) ────
    # 全部走同一 base_url (token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1,
    # OpenAI 协议兼容) + 同一 TOKENPLAN_API_KEY, 只换 model 字段。
    # 2026-06-22: Owner 指定新版白名单。仅每个品牌最高级对话模型进入 chat picker;
    # lower chat variants 和 image-only 模型只进目录,不进 picker。
    ModelEntry(
        id="qwen3.7-plus",
        label="Qwen3.7 Plus · 千问",
        provider="tokenplan",
        model="qwen3.7-plus",
        # 2026-07-13 真网探针: enable_thinking=false 14-15.7s→2.2-2.4s (-85%), 正文长度不变
        # (rank11 段落调用实测被 intent 分层路由到本模型, 无此 flag 则 fail-closed 不折控制)。
        supports_thinking_budget=True,
        speed_tier="balanced",
        note="文本生成 / 推理 / 视觉理解",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning", "vision_understanding"),
    ),
    ModelEntry(
        id="qwen3.7-max",
        label="Qwen3.7 Max · 千问",
        provider="tokenplan",
        model="qwen3.7-max",
        speed_tier="reasoning",
        note="文本生成 / 推理",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning"),
        # 探针实证 (probe_qwen_thinking_budget.py, 2026-07-12): enable_thinking=false /
        # thinking_budget=N 经 extra_body 顶层放置生效, 合成轮 TTFT 从 ~36s 塌到 ~1.6s
        # (关思考) / ~11s (封顶 512)。仅本模型验证过 → 其它 qwen 需各自跑探针再置 True。
        supports_thinking_budget=True,
        # 探针实证 (probe_explicit_cache.py, 2026-07-13): cache_control 被接受,
        # callB cached_tokens=7282 钉死命中 (flash 隐式基线为 0,显式=纯增益)。
        supports_explicit_cache=True,
        # 探针实证 (probe_tool_choice_strict.py, 2026-07-17): enable_thinking=false 下
        # named tool_choice PASS 且参数合法。
        supports_forced_tool_choice=True,
    ),
    ModelEntry(
        id="qwen3.6-plus",
        label="Qwen3.6 Plus · 千问",
        provider="tokenplan",
        model="qwen3.6-plus",
        speed_tier="balanced",
        note="文本生成 / 推理 / 视觉理解",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning", "vision_understanding"),
        chat_selectable=False,
    ),
    ModelEntry(
        id="qwen3.6-flash",
        label="Qwen3.6 Flash · 千问",
        provider="tokenplan",
        model="qwen3.6-flash",
        speed_tier="fast",
        note="文本生成 / 推理 / 视觉理解",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning", "vision_understanding"),
        chat_selectable=False,
        # 探针实证 (probe_explicit_cache.py, 2026-07-13): cache_control 被接受,
        # callB cached_tokens=7282 钉死命中 (flash 隐式基线为 0,显式=纯增益)。
        supports_explicit_cache=True,
        # 探针实证 (probe_tool_choice_strict.py, 2026-07-17): 同上双模型 PASS。
        supports_forced_tool_choice=True,
    ),
    ModelEntry(
        id="qwen-image-2.0",
        label="Qwen Image 2.0 · 千问",
        provider="tokenplan",
        model="qwen-image-2.0",
        speed_tier="balanced",
        note="图片生成",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("image_generation",),
        chat_selectable=False,
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="qwen-image-2.0-pro",
        label="Qwen Image 2.0 Pro · 千问",
        provider="tokenplan",
        model="qwen-image-2.0-pro",
        speed_tier="reasoning",
        note="图片生成",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("image_generation",),
        chat_selectable=False,
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="wan2.7-image",
        label="Wan2.7 Image · 万相",
        provider="tokenplan",
        model="wan2.7-image",
        speed_tier="balanced",
        note="图片生成",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("image_generation",),
        chat_selectable=False,
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="wan2.7-image-pro",
        label="Wan2.7 Image Pro · 万相",
        provider="tokenplan",
        model="wan2.7-image-pro",
        speed_tier="reasoning",
        note="图片生成",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("image_generation",),
        chat_selectable=False,
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="deepseek-v4-pro",
        label="DeepSeek V4 Pro",
        provider="tokenplan",
        model="deepseek-v4-pro",
        speed_tier="reasoning",
        note="文本生成 / 推理",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning"),
    ),
    ModelEntry(
        id="deepseek-v4-flash",
        label="DeepSeek V4 Flash",
        provider="tokenplan",
        model="deepseek-v4-flash",
        speed_tier="fast",
        note="文本生成 / 推理",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning"),
    ),
    ModelEntry(
        id="deepseek-v3.2",
        label="DeepSeek V3.2",
        provider="tokenplan",
        model="deepseek-v3.2",
        speed_tier="balanced",
        note="文本生成 / 推理",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning"),
        chat_selectable=False,
    ),
    ModelEntry(
        id="kimi-k2.7-code",
        label="Kimi K2.7 Code · 月之暗面",
        provider="tokenplan",
        model="kimi-k2.7-code",
        speed_tier="reasoning",
        note="文本生成 / 推理 / 视觉理解",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning", "vision_understanding"),
    ),
    ModelEntry(
        id="kimi-k2.6",
        label="Kimi K2.6 · 月之暗面",
        provider="tokenplan",
        model="kimi-k2.6",
        speed_tier="balanced",
        note="文本生成 / 推理 / 视觉理解",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning", "vision_understanding"),
        chat_selectable=False,
    ),
    ModelEntry(
        id="kimi-k2.5",
        label="Kimi K2.5 · 月之暗面",
        provider="tokenplan",
        model="kimi-k2.5",
        speed_tier="balanced",
        note="文本生成 / 推理 / 视觉理解",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning", "vision_understanding"),
        chat_selectable=False,
    ),
    ModelEntry(
        id="glm-5.2",
        label="GLM-5.2 · 智谱AI",
        provider="tokenplan",
        model="glm-5.2",
        speed_tier="balanced",
        note="文本生成",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation",),
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="glm-5.1",
        label="GLM-5.1 · 智谱AI",
        provider="tokenplan",
        model="glm-5.1",
        speed_tier="balanced",
        note="文本生成; 工具调用不稳 (历史 bug #147/#161)",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation",),
        chat_selectable=False,
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="glm-5",
        label="GLM-5 · 智谱AI",
        provider="tokenplan",
        model="glm-5",
        speed_tier="fast",
        note="文本生成; 工具调用不稳",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation",),
        chat_selectable=False,
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="minimax-m2.5",
        label="MiniMax M2.5",
        provider="tokenplan",
        model="MiniMax-M2.5",
        speed_tier="reasoning",
        note="文本生成 / 推理; 工具调用经验不稳",
        requires_env=("TOKENPLAN_API_KEY",),
        capabilities=("text_generation", "reasoning"),
        reliable_tool_calling=False,
    ),

    # ──── 商用模型 (经 browser-llm-orchestrator LangBridge gateway) ────
    # 透明走 https://base.executor.life/api/llm , OpenAI 协议兼容, 支持 vision.
    # 切换粒度 = user_profile.llm_model_id, admin 也可用 set_active_model_id 全局切.
    # supports_streaming=False: 经万擎公网转发的商用模型在网关侧无 SSE, 整段答案
    # 一次性返回 (ttft≈total)。agent_executor 答案轮据此发 thinking 状态 detail,
    # 让 mac 端如实提示「整段生成, 需等待完整回答」而非误导性 token 滚动。
    ModelEntry(
        id="claude-opus-4.7",
        label="Claude Opus 4.7 · 商用",
        provider="langbridge-proxy",
        model="commercial/Claude-Opus-4.7",
        speed_tier="reasoning",
        note="多模态 / 推理强 / 经 LangBridge",
        requires_env=("LANGBRIDGE_GATEWAY_API_KEY",),
        supports_streaming=False,
    ),
    ModelEntry(
        id="gpt-5.5",
        label="GPT-5.5 · 商用",
        provider="langbridge-proxy",
        model="commercial/GPT-5.5",
        speed_tier="balanced",
        note="多模态 / 工具调用 / 经 LangBridge",
        requires_env=("LANGBRIDGE_GATEWAY_API_KEY",),
        supports_streaming=False,
    ),
    ModelEntry(
        id="gemini-3.1-pro",
        label="Gemini 3.1 Pro · 商用",
        provider="langbridge-proxy",
        model="commercial/Gemini-3.1-Pro-Preview",
        speed_tier="reasoning",
        note="多模态 / 长上下文 / 经 LangBridge",
        requires_env=("LANGBRIDGE_GATEWAY_API_KEY",),
        supports_streaming=False,
    ),
]


def get_model(model_id: str) -> Optional[ModelEntry]:
    for m in MODELS:
        if m.id == model_id:
            return m
    return None


def list_models(only_available: bool = False, include_non_chat: bool = False) -> List[ModelEntry]:
    """返回 chat 可选模型列表.

    include_non_chat=True 时也返回图片生成等非聊天模型;only_available=True 时过滤 env 缺失的。
    """
    models = [m for m in MODELS if include_non_chat or m.chat_selectable]
    if not only_available:
        return list(models)
    from app.config import settings
    out: List[ModelEntry] = []
    for m in models:
        ok = all(_env_present(e, settings) for e in m.requires_env)
        if ok:
            out.append(m)
    return out


def _env_present(env_name: str, settings) -> bool:
    """env 名映射到 settings 字段."""
    mapping = {
        "OPENAI_API_KEY": "openai_api_key",
        "TOKENPLAN_API_KEY": "tokenplan_api_key",
        "MOONSHOT_API_KEY": "moonshot_api_key",
        "ZHIPU_API_KEY": "zhipu_api_key",
        "LANGBRIDGE_GATEWAY_API_KEY": "langbridge_gateway_api_key",
    }
    field = mapping.get(env_name)
    if not field:
        return False
    return bool(getattr(settings, field, None))


# 当前活跃模型 — 进程内可变, 重启失效 (持久化要靠 .env)
# 由 admin 切换 API 设置, get_active_model 读取
_active_model_id: Optional[str] = None


def get_active_model_id() -> Optional[str]:
    """返回当前选中模型 id; None 表示走 settings.llm_provider 默认行为."""
    return _active_model_id


def set_active_model_id(model_id: Optional[str]) -> None:
    """admin 切换模型. None 表示恢复默认."""
    global _active_model_id
    _active_model_id = model_id


# ──── 工具调用能力门控 ────
# 当一个 agent 回合需要工具, 但当前选中模型 reliable_tool_calling=False 时,
# 由调用方 (agent_executor) 用下面的 helper 选一个可靠模型回退, 从源头减少
# 弱模型吐坏工具调用 (#147/#161 的兜底解析仍保留作为安全网)。

# 回退优先级: 先同 speed_tier 找可靠模型, 再按 speed_tier 邻近降级, 最后任意可靠模型。
_RELIABLE_FALLBACK_SPEED_ORDER = {
    "fast": ("fast", "balanced", "reasoning"),
    "balanced": ("balanced", "reasoning", "fast"),
    "reasoning": ("reasoning", "balanced", "fast"),
}


def is_reliable_tool_caller(model_id: Optional[str]) -> bool:
    """model_id 对应模型是否可靠做 function-calling。未知 id 保守返回 True (不门控)。"""
    if not model_id:
        return True
    entry = get_model(model_id)
    if entry is None:
        return True
    return entry.reliable_tool_calling


def _reliable_tool_models(only_available: bool) -> List[ModelEntry]:
    """内部工具/回退路由的候选集: 可靠工具调用 + 能生成文本的模型。

    必须 include_non_chat=True: 最快的可靠工具模型 (qwen3.6-flash) 故意
    chat_selectable=False (不许用户当答案模型选), 但内部工具决策轮/回退要能用到它。
    默认的 list_models() 会把它滤掉 → 快路由永远拿不到最快档, 只能落到次快的
    deepseek-v4-flash (~7s vs qwen3.6-flash evaled ~1-2.6s), 白白丢一半收益。

    能力护栏 "text_generation" in capabilities: include_non_chat=True 会同时放进
    图片生成模型 (qwen-image / wan 系, image_generation-only)。这些既非文本模型、
    也已标 reliable_tool_calling=False, 但这里显式再钉一道 —— 即使有谁误把某个
    图片模型标成 reliable_tool_calling=True, 也绝不会被工具路由选中。
    """
    return [
        m
        for m in list_models(only_available=only_available, include_non_chat=True)
        if "text_generation" in m.capabilities and m.reliable_tool_calling
    ]


def pick_reliable_tool_model_id(
    near_speed_tier: Optional[str] = None,
    only_available: bool = True,
) -> Optional[str]:
    """选一个 reliable_tool_calling=True 的可用模型 id, 优先贴近 near_speed_tier。

    无任何可靠+可用模型时返回 None (调用方维持现状, 依赖兜底解析)。
    """
    models = _reliable_tool_models(only_available)
    if not models:
        return None
    if near_speed_tier:
        order = _RELIABLE_FALLBACK_SPEED_ORDER.get(near_speed_tier, (near_speed_tier,))
        for target in order:
            for m in models:
                if m.speed_tier == target:
                    return m.id
    return models[0].id


# ──── 快模型路由 (延迟优化: 简单记录/查询回合走最快的可靠工具调用模型) ────
# speed_tier 从快到慢的枚举顺序, 用于"选最快的可靠工具调用模型"。
_SPEED_TIER_ORDER = ("fast", "balanced", "reasoning")


def pick_fast_tool_model_id(only_available: bool = True) -> Optional[str]:
    """选**最快**的 reliable_tool_calling=True 可用工具调用模型 id, 供简单回合快路由。

    候选集来自 _reliable_tool_models (include_non_chat=True + text_generation 护栏):
    最快档就是 chat_selectable=False 的 qwen3.6-flash —— 它不许当用户答案模型,
    但内部快路由要能用到它 (否则只能落到次快的 deepseek-v4-flash, 丢一半延迟收益)。

    为什么必须 reliable_tool_calling=True: 简单记录/查询回合几乎一定要调工具
    (health_record/health_query/health_manage), 不会调工具的快模型会直接把这类
    回合搞坏 (吐文本冒充成功=静默丢数据)。所以先按 speed_tier (fast→balanced→
    reasoning) 找, 每档里只考虑 reliable_tool_calling 的模型, 命中最快那档的第一个。

    无任何可靠+可用工具调用模型时返回 None (调用方维持现状, 不做快路由)。
    """
    models = _reliable_tool_models(only_available)
    if not models:
        return None
    for tier in _SPEED_TIER_ORDER:
        for m in models:
            if m.speed_tier == tier:
                return m.id
    return models[0].id
