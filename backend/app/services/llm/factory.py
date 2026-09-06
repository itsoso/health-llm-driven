"""LLM Provider 工厂 - 根据配置创建对应的 LLM Provider 实例"""
import logging
from typing import Optional

from app.config import settings
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# 单例缓存
_provider_instance: Optional[LLMProvider] = None


def create_llm_provider(provider_type: Optional[str] = None) -> LLMProvider:
    """
    根据配置创建 LLM Provider 实例.

    优先级:
    1. model_registry 当前 active model (admin 切换的)
    2. settings.llm_provider 默认值

    Args:
        provider_type: 强制指定 provider, None = 走优先级
    """
    # 优先用 admin 切换过的活跃 model
    if provider_type is None:
        from app.services.llm.model_registry import get_active_model_id, get_model
        active = get_active_model_id()
        if active:
            entry = get_model(active)
            if entry:
                logger.info(f"[LLM Factory] 用 admin 选定模型 {entry.id} (provider={entry.provider})")
                return _create_from_entry(entry)
        provider_type = getattr(settings, "llm_provider", "tokenplan")

    provider_type = provider_type.lower().strip()
    logger.info(f"[LLM Factory] 创建 provider: {provider_type}")

    if provider_type == "openai":
        return _create_openai_provider()
    elif provider_type == "tokenplan":
        return _create_tokenplan_provider()
    elif provider_type == "ollama":
        return _create_ollama_provider()
    else:
        raise ValueError(
            f"未知的 LLM provider 类型: {provider_type!r}，"
            f"支持的类型: openai, ollama, tokenplan"
        )


def _create_from_entry(entry) -> LLMProvider:
    """根据 ModelEntry 创建 provider — 模型级路由."""
    from app.services.llm.providers.openai_provider import OpenAIProvider

    if entry.provider == "openai-proxy":
        provider = OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=entry.model,
        )
        provider.provider_name = "openai-proxy"
        return provider
    if entry.provider == "tokenplan":
        provider = OpenAIProvider(
            api_key=settings.tokenplan_api_key,
            base_url=settings.tokenplan_base_url,
            model=entry.model,
        )
        provider.provider_name = "tokenplan"
        return provider
    if entry.provider == "moonshot":
        if not settings.moonshot_api_key:
            raise ValueError("MOONSHOT_API_KEY 未配置, 无法用 Kimi")
        provider = OpenAIProvider(
            api_key=settings.moonshot_api_key,
            base_url=settings.moonshot_base_url,
            model=entry.model,
        )
        provider.provider_name = "moonshot"
        return provider
    if entry.provider == "zhipu":
        if not settings.zhipu_api_key:
            raise ValueError("ZHIPU_API_KEY 未配置, 无法用 GLM")
        provider = OpenAIProvider(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            model=entry.model,
        )
        provider.provider_name = "zhipu"
        return provider
    if entry.provider == "langbridge-proxy":
        if not settings.langbridge_gateway_api_key:
            raise ValueError("LANGBRIDGE_GATEWAY_API_KEY 未配置, 无法用商用模型 gateway")
        if not settings.langbridge_gateway_base_url:
            raise ValueError("LANGBRIDGE_GATEWAY_BASE_URL 未配置")
        provider = OpenAIProvider(
            api_key=settings.langbridge_gateway_api_key,
            base_url=settings.langbridge_gateway_base_url,
            model=entry.model,
        )
        provider.provider_name = "langbridge-proxy"
        return provider
    raise ValueError(f"unknown entry.provider: {entry.provider}")


def _create_openai_provider() -> LLMProvider:
    """创建 OpenAI provider，兼容遗留配置"""
    from app.services.llm.providers.openai_provider import OpenAIProvider

    # 新配置优先，回退到遗留配置
    api_key = getattr(settings, "llm_openai_api_key", None) or settings.openai_api_key
    base_url = getattr(settings, "llm_openai_base_url", None) or settings.openai_base_url
    model = getattr(settings, "llm_openai_model", None) or settings.openai_model

    return OpenAIProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def _create_tokenplan_provider() -> LLMProvider:
    """阿里云 TokenPlan (兼容 OpenAI 协议). 国内直连, 套餐固定."""
    from app.services.llm.providers.openai_provider import OpenAIProvider

    api_key = settings.tokenplan_api_key
    base_url = settings.tokenplan_base_url
    model = settings.tokenplan_model

    if not api_key:
        raise ValueError("TOKENPLAN_API_KEY 未配置")
    logger.info(f"[LLM Factory] TokenPlan: model={model} base={base_url[:50]}")
    provider = OpenAIProvider(api_key=api_key, base_url=base_url, model=model)
    provider.provider_name = "tokenplan"
    return provider


def _create_ollama_provider() -> LLMProvider:
    """创建 Ollama provider"""
    from app.services.llm.providers.ollama_provider import OllamaProvider

    base_url = getattr(settings, "llm_ollama_base_url", "http://localhost:11434")
    model = getattr(settings, "llm_ollama_model", "llama3")

    return OllamaProvider(
        base_url=base_url,
        model=model,
    )


# Vision provider 单例
_vision_provider_instance: Optional[LLMProvider] = None


def get_vision_provider() -> LLMProvider:
    """
    获取 Vision Provider 单例

    如果配置了独立的 vision API key，使用独立 provider（如 DashScope/Qwen）；
    否则回退到通用 LLM provider。
    """
    global _vision_provider_instance
    if _vision_provider_instance is None:
        vision_api_key = getattr(settings, "llm_vision_api_key", None)
        vision_base_url = getattr(settings, "llm_vision_base_url", None)
        vision_model = getattr(settings, "llm_vision_model", "qwen3-vl-flash")

        if vision_api_key:
            from app.services.llm.providers.openai_provider import OpenAIProvider
            _vision_provider_instance = OpenAIProvider(
                api_key=vision_api_key,
                base_url=vision_base_url,
                model=vision_model,
            )
            logger.info(f"[LLM Factory] Vision provider: {vision_model} @ {vision_base_url}")
        else:
            _vision_provider_instance = get_llm_provider()
            logger.info("[LLM Factory] Vision provider: 回退到通用 LLM provider")
    return _vision_provider_instance


def get_llm_provider() -> LLMProvider:
    """
    获取 LLM Provider 单例

    首次调用时创建实例并缓存，后续调用返回同一实例。
    包装顺序 (从内到外): real → usage_tracker → pii_scrub
    确保 usage_tracker 记录的是脱敏后 prompt, 真实调用前 PII 已 redact.

    Returns:
        LLMProvider 实例
    """
    global _provider_instance
    if _provider_instance is None:
        from app.services.llm.usage_tracker import wrap_provider
        from app.services.llm.pii_scrub import wrap_provider_pii_scrub
        _provider_instance = wrap_provider_pii_scrub(
            wrap_provider(create_llm_provider())
        )
    return _provider_instance


def reset_llm_provider() -> None:
    """
    重置 LLM Provider 单例（用于测试或配置变更后重新创建）
    """
    global _provider_instance
    _provider_instance = None
    logger.info("[LLM Factory] Provider 单例已重置")


def create_provider_for_model_id(model_id: str) -> LLMProvider:
    """Create a wrapped provider for an explicit registered model id."""

    from app.services.llm.model_registry import get_model
    from app.services.llm.usage_tracker import wrap_provider
    from app.services.llm.pii_scrub import wrap_provider_pii_scrub

    entry = get_model(model_id)
    if not entry:
        raise ValueError(f"未注册的 model_id: {model_id}")
    raw = _create_from_entry(entry)
    logger.info(f"[LLM Factory] 用请求指定模型 {model_id} (provider={entry.provider})")
    return wrap_provider_pii_scrub(wrap_provider(raw))


def create_provider_for_extraction(model_id: str) -> LLMProvider:
    """便宜快模型抽取档 provider,创建失败 **fail-soft** 回退默认 provider。

    纯抽取/判重类调用点(memory / dialog / directive / kb-judge / action-card)用它把默认
    强模型降档到便宜 flash 档。`model_id` 未注册 / provider env 缺失 → create_provider_for_model_id
    抛 ValueError,这里记 WARNING 并回退到 `get_llm_provider()`(= 这些调用点原本的 provider
    路径),绝不因降档配置错误而中断业务。回退是可观测的(WARNING 日志),不是静默吞掉。
    """
    try:
        return create_provider_for_model_id(model_id)
    except Exception as exc:  # noqa: BLE001 — 降档配置错误必须 fail-soft 回退强模型, 不断业务
        logger.warning(
            "[LLM Factory] 抽取档模型 %s 创建失败, fail-soft 回退默认 provider: %s",
            model_id,
            exc,
        )
        return get_llm_provider()


def create_provider_for_user(user_id: int, db, task_tier: str | None = None) -> LLMProvider:
    """用户级 LLM 偏好 (2026-05-13).

    优先级: 任务分级路由(flag 开+传 tier)> user_profile.llm_model_id
            > admin global (set_active_model_id) > settings 默认.
    每次都新建 (不缓存), 确保用户切换立刻生效. 包了 usage_tracker + pii_scrub.

    Args:
        user_id: 用户 ID
        db: SQLAlchemy session
        task_tier: 可选任务档(high_stakes/balanced/casual)。仅当 settings.task_tiered_routing
            为真且匹配到可用模型时生效;否则忽略 = 零行为变更(成本/延迟路由,Tier 4)。
    """
    from app.config import settings
    from app.services.llm.usage_tracker import wrap_provider
    from app.services.llm.pii_scrub import wrap_provider_pii_scrub
    from app.services.ai_consent import is_disclosed_model, is_disclosed_destination

    # 0. 任务分级路由(flag 门控;失败/无匹配静默回退到下面的既有逻辑)
    if task_tier and getattr(settings, "task_tiered_routing", False):
        try:
            from app.services.llm.model_registry import get_model
            from app.services.llm.task_routing import pick_model_id_by_tier
            tier_model = pick_model_id_by_tier(task_tier)
            if tier_model:
                entry = get_model(tier_model)
                if entry and is_disclosed_model(entry):
                    raw = _create_from_entry(entry)
                    logger.info(f"[LLM Factory] user={user_id} 任务路由 tier={task_tier} model={tier_model}")
                    return wrap_provider_pii_scrub(wrap_provider(raw))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[LLM Factory] user={user_id} 任务路由失败, 回退既有: {e}")

    # 1. 用户偏好
    try:
        from app.models.user_profile import UserProfile
        from app.services.llm.model_registry import get_model
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        model_id = getattr(profile, "llm_model_id", None) if profile else None
        if model_id:
            entry = get_model(model_id)
            if entry and is_disclosed_model(entry):
                try:
                    raw = _create_from_entry(entry)
                    logger.info(f"[LLM Factory] user={user_id} 用偏好 model={model_id}")
                    return wrap_provider_pii_scrub(wrap_provider(raw))
                except ValueError as e:
                    # env 缺 (例如选了 kimi 但 MOONSHOT_API_KEY 没配) → 降级
                    logger.warning(f"[LLM Factory] user={user_id} 偏好 {model_id} env 缺, 降级: {e}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[LLM Factory] 读 user={user_id} 偏好失败, 降级: {e}")

    # 2. 降级到全局 (admin 切换 / settings 默认)
    provider = get_llm_provider()
    if not is_disclosed_destination(getattr(provider, "base_url", None)):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail={"code": "ai_recipient_not_disclosed", "message": "系统默认 AI 服务尚未完成数据使用披露，暂不可用"})
    return provider
