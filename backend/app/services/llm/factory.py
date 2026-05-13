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
        provider_type = getattr(settings, "llm_provider", "openclaw")

    provider_type = provider_type.lower().strip()
    logger.info(f"[LLM Factory] 创建 provider: {provider_type}")

    if provider_type == "openai":
        return _create_openai_provider()
    elif provider_type == "tokenplan":
        return _create_tokenplan_provider()
    elif provider_type == "ollama":
        return _create_ollama_provider()
    elif provider_type == "openclaw":
        try:
            return _create_openclaw_provider()
        except Exception as e:
            logger.warning(f"[LLM Factory] OpenClaw 创建失败，回退到 OpenAI: {e}")
            return _create_openai_provider()
    else:
        raise ValueError(
            f"未知的 LLM provider 类型: {provider_type!r}，"
            f"支持的类型: openclaw, openai, ollama, tokenplan"
        )


def _create_from_entry(entry) -> LLMProvider:
    """根据 ModelEntry 创建 provider — 模型级路由."""
    from app.services.llm.providers.openai_provider import OpenAIProvider

    if entry.provider == "openai-proxy":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=entry.model,
        )
    if entry.provider == "tokenplan":
        return OpenAIProvider(
            api_key=settings.tokenplan_api_key,
            base_url=settings.tokenplan_base_url,
            model=entry.model,
        )
    if entry.provider == "moonshot":
        if not settings.moonshot_api_key:
            raise ValueError("MOONSHOT_API_KEY 未配置, 无法用 Kimi")
        return OpenAIProvider(
            api_key=settings.moonshot_api_key,
            base_url=settings.moonshot_base_url,
            model=entry.model,
        )
    if entry.provider == "zhipu":
        if not settings.zhipu_api_key:
            raise ValueError("ZHIPU_API_KEY 未配置, 无法用 GLM")
        return OpenAIProvider(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            model=entry.model,
        )
    if entry.provider == "openclaw":
        return _create_openclaw_provider()
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
    return OpenAIProvider(api_key=api_key, base_url=base_url, model=model)


def _create_ollama_provider() -> LLMProvider:
    """创建 Ollama provider"""
    from app.services.llm.providers.ollama_provider import OllamaProvider

    base_url = getattr(settings, "llm_ollama_base_url", "http://localhost:11434")
    model = getattr(settings, "llm_ollama_model", "llama3")

    return OllamaProvider(
        base_url=base_url,
        model=model,
    )


def _create_openclaw_provider() -> LLMProvider:
    """创建 OpenClaw provider，兼容遗留配置"""
    from app.services.llm.providers.openclaw_provider import OpenClawProvider

    # 新配置优先，回退到遗留配置
    base_url = getattr(settings, "llm_openclaw_base_url", None) or settings.openclaw_base_url
    api_key = getattr(settings, "llm_openclaw_api_key", None) or settings.openclaw_api_key
    model = getattr(settings, "llm_openclaw_model", None) or settings.openclaw_model

    # 多模型分析配置（可选）
    analyze_url = getattr(settings, "llm_openclaw_analyze_url", None)
    analyze_api_key = getattr(settings, "llm_openclaw_analyze_api_key", None)
    kim_user_id = getattr(settings, "llm_openclaw_kim_user_id", None)

    return OpenClawProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        analyze_url=analyze_url,
        analyze_api_key=analyze_api_key,
        kim_user_id=kim_user_id,
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
        vision_model = getattr(settings, "llm_vision_model", "qwen-vl-max")

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


def create_provider_for_user(user_id: int, db) -> LLMProvider:
    """用户级 LLM 偏好 (2026-05-13).

    优先级: user_profile.llm_model_id > admin global (set_active_model_id) > settings 默认.
    每次都新建 (不缓存), 确保用户切换立刻生效. 包了 usage_tracker + pii_scrub.

    Args:
        user_id: 用户 ID
        db: SQLAlchemy session
    """
    from app.services.llm.usage_tracker import wrap_provider
    from app.services.llm.pii_scrub import wrap_provider_pii_scrub

    # 1. 用户偏好
    try:
        from app.models.user_profile import UserProfile
        from app.services.llm.model_registry import get_model
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        model_id = getattr(profile, "llm_model_id", None) if profile else None
        if model_id:
            entry = get_model(model_id)
            if entry:
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
    return get_llm_provider()
