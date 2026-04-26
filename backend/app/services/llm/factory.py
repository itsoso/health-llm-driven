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
    根据配置创建 LLM Provider 实例

    优先使用新配置字段（llm_provider / llm_*），不存在时回退到遗留配置
    （openai_api_key、openclaw_base_url 等）。

    Args:
        provider_type: 指定 provider 类型 ("openai" | "ollama" | "openclaw")，
                       None 则从 settings.llm_provider 读取

    Returns:
        对应的 LLMProvider 实例

    Raises:
        ValueError: 未知的 provider 类型
    """
    if provider_type is None:
        provider_type = getattr(settings, "llm_provider", "openclaw")

    provider_type = provider_type.lower().strip()
    logger.info(f"[LLM Factory] 创建 provider: {provider_type}")

    if provider_type == "openai":
        return _create_openai_provider()
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
            f"支持的类型: openclaw, openai, ollama"
        )


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

    Returns:
        LLMProvider 实例
    """
    global _provider_instance
    if _provider_instance is None:
        from app.services.llm.usage_tracker import wrap_provider
        _provider_instance = wrap_provider(create_llm_provider())
    return _provider_instance


def reset_llm_provider() -> None:
    """
    重置 LLM Provider 单例（用于测试或配置变更后重新创建）
    """
    global _provider_instance
    _provider_instance = None
    logger.info("[LLM Factory] Provider 单例已重置")
