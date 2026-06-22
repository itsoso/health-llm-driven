"""Regression coverage for the Owner-approved latest model whitelist."""

from app.services.llm import model_registry as reg


EXPECTED_MODELS = {
    "qwen3.7-plus": ("text_generation", "reasoning", "vision_understanding"),
    "qwen3.7-max": ("text_generation", "reasoning"),
    "qwen3.6-plus": ("text_generation", "reasoning", "vision_understanding"),
    "qwen3.6-flash": ("text_generation", "reasoning", "vision_understanding"),
    "qwen-image-2.0": ("image_generation",),
    "qwen-image-2.0-pro": ("image_generation",),
    "wan2.7-image": ("image_generation",),
    "wan2.7-image-pro": ("image_generation",),
    "deepseek-v4-pro": ("text_generation", "reasoning"),
    "deepseek-v4-flash": ("text_generation", "reasoning"),
    "deepseek-v3.2": ("text_generation", "reasoning"),
    "kimi-k2.7-code": ("text_generation", "reasoning", "vision_understanding"),
    "kimi-k2.6": ("text_generation", "reasoning", "vision_understanding"),
    "kimi-k2.5": ("text_generation", "reasoning", "vision_understanding"),
    "glm-5.2": ("text_generation",),
    "glm-5.1": ("text_generation",),
    "glm-5": ("text_generation",),
    "minimax-m2.5": ("text_generation", "reasoning"),
}

IMAGE_ONLY = {
    "qwen-image-2.0",
    "qwen-image-2.0-pro",
    "wan2.7-image",
    "wan2.7-image-pro",
}

TOP_CHAT_MODELS = {
    "qwen3.7-plus",
    "qwen3.7-max",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "kimi-k2.7-code",
    "glm-5.2",
    "minimax-m2.5",
}

HIDDEN_CHAT_VARIANTS = {
    "qwen3.6-plus",
    "qwen3.6-flash",
    "deepseek-v3.2",
    "kimi-k2.6",
    "kimi-k2.5",
    "glm-5.1",
    "glm-5",
}

LOW_VERSION_MODELS = {
    "qwen2.5",
    "qwen3.5",
    "qwen-vl-max",
    "deepseek-v3",
    "deepseek-v3.1",
    "kimi-k2",
    "kimi-k2.4",
    "glm-4",
    "glm-4.5",
    "minimax-m1",
}


def test_owner_latest_models_are_registered_with_capabilities():
    by_id = {m.id: m for m in reg.MODELS}

    for model_id, capabilities in EXPECTED_MODELS.items():
        entry = by_id.get(model_id)
        assert entry is not None, f"{model_id} is not registered"
        assert entry.model == model_id if model_id != "minimax-m2.5" else entry.model == "MiniMax-M2.5"
        for capability in capabilities:
            assert capability in entry.capabilities


def test_image_generation_models_are_not_chat_selectable():
    by_id = {m.id: m for m in reg.MODELS}
    chat_ids = {m.id for m in reg.list_models(only_available=False)}

    for model_id in IMAGE_ONLY:
        assert by_id[model_id].chat_selectable is False
        assert "image_generation" in by_id[model_id].capabilities
        assert model_id not in chat_ids


def test_only_top_tokenplan_chat_models_are_chat_selectable():
    chat_ids = {m.id for m in reg.list_models(only_available=False)}

    assert TOP_CHAT_MODELS.issubset(chat_ids)
    assert chat_ids.isdisjoint(HIDDEN_CHAT_VARIANTS)


def test_low_version_models_are_not_registered():
    registered = {m.id for m in reg.MODELS}
    assert registered.isdisjoint(LOW_VERSION_MODELS)
