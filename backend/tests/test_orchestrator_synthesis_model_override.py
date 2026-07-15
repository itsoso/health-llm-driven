"""深报告合成模型覆盖(2026-07-15, D 组换快)。

orchestrator._call_llm 主路径:settings.orchestrator_synthesis_model_id 非空时按该
model_id 建 provider(绕过 per-user/task_tier);默认空 → 存量行为。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import app.orchestrator.orchestrator as orch


def _fake_provider(text="综合报告", model="fake"):
    p = MagicMock()
    p.model = model
    p.chat = AsyncMock(return_value={"content": text})
    return p


def test_override_set_routes_to_model_id(monkeypatch):
    monkeypatch.setattr(
        orch.settings, "orchestrator_synthesis_model_id", "deepseek-v4-flash",
        raising=False,
    )
    calls = {}

    def fake_for_model(mid):
        calls["model_id"] = mid
        return _fake_provider(model=mid)

    def fake_for_user(*a, **k):  # 不应被调用
        calls["for_user"] = True
        return _fake_provider()

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", fake_for_model, raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", fake_for_user, raising=False,
    )
    # 深报告 mega 合成显式开 allow_synthesis_override=True → 用覆盖模型
    out = asyncio.run(orch._call_llm("sys", "user", allow_synthesis_override=True))
    assert calls.get("model_id") == "deepseek-v4-flash", "覆盖非空+显式开 → 用 create_provider_for_model_id"
    assert "for_user" not in calls, "覆盖生效时不再走 per-user 选择"
    assert "综合报告" in out or out  # 正常返回合成文本


def test_override_not_applied_without_explicit_flag(monkeypatch):
    # settings 非空但调用方**未开** allow_synthesis_override(= Siri/仲裁/段落路径)→ 绝不覆盖
    monkeypatch.setattr(
        orch.settings, "orchestrator_synthesis_model_id", "deepseek-v4-flash",
        raising=False,
    )
    calls = {}
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda mid: calls.setdefault("model_id", mid) or _fake_provider(model=mid),
        raising=False,
    )
    import app.services.llm as _llm
    monkeypatch.setattr(
        _llm, "get_llm_provider",
        lambda: calls.setdefault("default", True) or _fake_provider(),
        raising=False,
    )
    asyncio.run(orch._call_llm("sys", "user"))  # 默认 allow_synthesis_override=False
    assert "model_id" not in calls, "未开显式开关(Siri/仲裁) → 即使 settings 非空也不覆盖"


def test_override_empty_keeps_existing_behavior(monkeypatch):
    monkeypatch.setattr(
        orch.settings, "orchestrator_synthesis_model_id", "", raising=False,
    )
    calls = {}

    def fake_for_model(mid):  # 不应被调用
        calls["model_id"] = mid
        return _fake_provider(model=mid)

    def fake_get_default():
        calls["default"] = True
        return _fake_provider()

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", fake_for_model, raising=False,
    )
    # _user_pref_ctx 无值 → 走 get_llm_provider 默认路径
    monkeypatch.setattr(orch, "_user_pref_ctx", orch._user_pref_ctx)  # no-op, ctx 默认 None
    import app.services.llm as _llm
    monkeypatch.setattr(_llm, "get_llm_provider", fake_get_default, raising=False)
    out = asyncio.run(orch._call_llm("sys", "user"))
    assert "model_id" not in calls, "空覆盖 → 绝不用 create_provider_for_model_id"
