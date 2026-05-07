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


# 注册表 — 加新模型只改这里
MODELS: List[ModelEntry] = [
    # ──── OpenAI 代理 (现 default, 国内访问被代理 CDN 加速) ────
    ModelEntry(
        id="gpt-4o-mini",
        label="GPT-4o mini · 代理",
        provider="openai-proxy",
        model="gpt-4o-mini",
        speed_tier="fast",
        note="便宜快, 工具调用首选",
        requires_env=("OPENAI_API_KEY",),
    ),
    ModelEntry(
        id="gpt-4o",
        label="GPT-4o · 代理",
        provider="openai-proxy",
        model="gpt-4o",
        speed_tier="balanced",
        note="质量好, 复杂分析",
        requires_env=("OPENAI_API_KEY",),
    ),

    # ──── 阿里百炼 TokenPlan (国内直连, 套餐固定计费) ────
    # 当前套餐 (2026-05-07) 支持的模型: qwen3.6-plus / deepseek-v3.2 / glm-5 /
    # MiniMax-M2.5 + qwen-image / wan2.7-image (图像生成, 暂不接).
    # 全部走同一个 base_url + 同一个 API Key, 只换 model 字段.
    # qwen-turbo/plus/max 不在套餐里, 保留是 fallback 提示 (运行时若被选会走 base_url 默认报错).
    ModelEntry(
        id="qwen3.6-plus",
        label="Qwen3.6 Plus 推理 · 阿里",
        provider="tokenplan",
        model="qwen3.6-plus",
        speed_tier="reasoning",
        note="thinking 模型, 慢但深度强 (10-50s)",
        requires_env=("TOKENPLAN_API_KEY",),
    ),
    ModelEntry(
        id="deepseek-v3.2",
        label="DeepSeek V3.2 · 阿里直连",
        provider="tokenplan",
        model="deepseek-v3.2",
        speed_tier="reasoning",
        note="推理模型, 中文强, 套餐内",
        requires_env=("TOKENPLAN_API_KEY",),
    ),
    ModelEntry(
        id="glm-5",
        label="GLM-5 · 智谱 (阿里直连)",
        provider="tokenplan",
        model="glm-5",
        speed_tier="balanced",
        note="国产质量好, 通过 TokenPlan 套餐",
        requires_env=("TOKENPLAN_API_KEY",),
    ),
    ModelEntry(
        id="minimax-m2.5",
        label="MiniMax M2.5 · 阿里直连",
        provider="tokenplan",
        model="MiniMax-M2.5",
        speed_tier="reasoning",
        note="推理模型, 通过 TokenPlan 套餐",
        requires_env=("TOKENPLAN_API_KEY",),
    ),

    # ──── Kimi (不在 TokenPlan 套餐, 需独立 Moonshot Key) ────
    ModelEntry(
        id="kimi-k2",
        label="Kimi K2 · 月之暗面 (需独立 Key)",
        provider="moonshot",
        model="kimi-k2-turbo-preview",
        speed_tier="balanced",
        note="长上下文 200k. 需配 MOONSHOT_API_KEY",
        requires_env=("MOONSHOT_API_KEY",),
    ),

    # ──── OpenClaw (内部) ────
    ModelEntry(
        id="openclaw-main",
        label="OpenClaw · 内部",
        provider="openclaw",
        model="openclaw:main",
        speed_tier="balanced",
        note="内部网关, 多模型聚合",
        requires_env=("OPENCLAW_API_KEY",),
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
