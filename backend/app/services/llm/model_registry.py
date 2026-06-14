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
  - openclaw     : 走 OPENCLAW_BASE_URL
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
    reliable_tool_calling: bool = True
    # ↑ 该模型做 function-calling 是否可靠 (吐合规的 tool_calls, 而非把工具调用
    #   写成文本 / 弯引号 JSON / [claim:] 泄漏)。False = 经验上不稳, 需要工具的
    #   agent 回合会门控回退到可靠模型 (见 agent_executor._resolve_chat_provider)。
    #   纯文本分析/问答不受影响。拿不准时保守标 True。


# 注册表 — 加新模型只改这里
MODELS: List[ModelEntry] = [
    # ──── 阿里百炼 TokenPlan (国内直连, 套餐固定计费) ────
    # 全部走同一 base_url (token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1,
    # OpenAI 协议兼容) + 同一 TOKENPLAN_API_KEY, 只换 model 字段。
    # 2026-06-11: 按 Owner 选择,对话 picker 只保留下面 5 个套餐模型 + langbridge 商用 3 个;
    # 其余 (qwen3.6-plus/flash, deepseek-v4-flash, deepseek-v3.2, kimi-k2.5, glm-5,
    # openai-proxy gpt-4o*, moonshot kimi-k2) 下线。用户旧偏好若指向已删 id 会优雅降级到
    # 默认 (见 factory.create_provider_for_user)。
    ModelEntry(
        id="qwen3.7-max",
        label="Qwen3.7 Max 推理 · 阿里",
        provider="tokenplan",
        model="qwen3.7-max",
        speed_tier="reasoning",
        note="千问旗舰推理, 深度强 (套餐内)",
        requires_env=("TOKENPLAN_API_KEY",),
    ),
    ModelEntry(
        id="deepseek-v4-pro",
        label="DeepSeek V4 Pro 推理 · 阿里直连",
        provider="tokenplan",
        model="deepseek-v4-pro",
        speed_tier="reasoning",
        note="V4 旗舰推理, 中文强 (套餐内)",
        requires_env=("TOKENPLAN_API_KEY",),
    ),
    ModelEntry(
        id="kimi-k2.6",
        label="Kimi K2.6 · 月之暗面 (阿里直连)",
        provider="tokenplan",
        model="kimi-k2.6",
        speed_tier="balanced",
        note="推理 + 视觉, 长上下文, 现进套餐",
        requires_env=("TOKENPLAN_API_KEY",),
    ),
    ModelEntry(
        id="glm-5.1",
        label="GLM-5.1 · 智谱 (阿里直连)",
        provider="tokenplan",
        model="glm-5.1",
        speed_tier="balanced",
        note="智谱新版, 文本生成 (套餐内); 工具调用不稳 (历史 bug #147/#161)",
        requires_env=("TOKENPLAN_API_KEY",),
        reliable_tool_calling=False,
    ),
    ModelEntry(
        id="minimax-m2.5",
        label="MiniMax M2.5 · 阿里直连",
        provider="tokenplan",
        model="MiniMax-M2.5",
        speed_tier="reasoning",
        note="推理模型, 通过 TokenPlan 套餐; 工具调用经验不稳",
        requires_env=("TOKENPLAN_API_KEY",),
        reliable_tool_calling=False,
    ),

    # OpenClaw 已从可选 LLM 通道下线 (2026-06: 无用户使用, 主链路走 tokenplan/langbridge)。
    # 注意: OpenClawService/models 仍在为 Siri / 微信 bot / /agent 会话持久化服务, 那是另一回事。

    # ──── 商用模型 (经 browser-llm-orchestrator LangBridge gateway) ────
    # 透明走 https://base.executor.life/api/llm , OpenAI 协议兼容, 支持 vision.
    # 切换粒度 = user_profile.llm_model_id, admin 也可用 set_active_model_id 全局切.
    ModelEntry(
        id="claude-opus-4.7",
        label="Claude Opus 4.7 · 商用",
        provider="langbridge-proxy",
        model="commercial/Claude-Opus-4.7",
        speed_tier="reasoning",
        note="多模态 / 推理强 / 经 LangBridge",
        requires_env=("LANGBRIDGE_GATEWAY_API_KEY",),
    ),
    ModelEntry(
        id="gpt-5.5",
        label="GPT-5.5 · 商用",
        provider="langbridge-proxy",
        model="commercial/GPT-5.5",
        speed_tier="balanced",
        note="多模态 / 工具调用 / 经 LangBridge",
        requires_env=("LANGBRIDGE_GATEWAY_API_KEY",),
    ),
    ModelEntry(
        id="gemini-3.1-pro",
        label="Gemini 3.1 Pro · 商用",
        provider="langbridge-proxy",
        model="commercial/Gemini-3.1-Pro-Preview",
        speed_tier="reasoning",
        note="多模态 / 长上下文 / 经 LangBridge",
        requires_env=("LANGBRIDGE_GATEWAY_API_KEY",),
    ),
]


def get_model(model_id: str) -> Optional[ModelEntry]:
    for m in MODELS:
        if m.id == model_id:
            return m
    return None


def list_models(only_available: bool = False) -> List[ModelEntry]:
    """返回模型列表. only_available=True 时过滤掉 env 缺失的."""
    if not only_available:
        return list(MODELS)
    from app.config import settings
    out: List[ModelEntry] = []
    for m in MODELS:
        ok = all(_env_present(e, settings) for e in m.requires_env)
        if ok:
            out.append(m)
    return out


def _env_present(env_name: str, settings) -> bool:
    """env 名映射到 settings 字段."""
    mapping = {
        "OPENAI_API_KEY": "openai_api_key",
        "TOKENPLAN_API_KEY": "tokenplan_api_key",
        "OPENCLAW_API_KEY": "openclaw_api_key",
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


def pick_reliable_tool_model_id(
    near_speed_tier: Optional[str] = None,
    only_available: bool = True,
) -> Optional[str]:
    """选一个 reliable_tool_calling=True 的可用模型 id, 优先贴近 near_speed_tier。

    无任何可靠+可用模型时返回 None (调用方维持现状, 依赖兜底解析)。
    """
    models = [m for m in list_models(only_available=only_available) if m.reliable_tool_calling]
    if not models:
        return None
    if near_speed_tier:
        order = _RELIABLE_FALLBACK_SPEED_ORDER.get(near_speed_tier, (near_speed_tier,))
        for target in order:
            for m in models:
                if m.speed_tier == target:
                    return m.id
    return models[0].id
