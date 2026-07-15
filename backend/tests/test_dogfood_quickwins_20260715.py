"""2026-07-15 dogfood 复盘 A 组 quick wins 回归。

覆盖:
- A1: health_record record_type enum 含 'event'(修 schema 漂移,回收裸陈述记录)
- A2: HealthKit 同步意图检测(修"后台拉取 Apple Health"结构性谎报)
- A4: LLM 客户端硬超时默认(消无界 LLM 轮冻结)
"""
from app.services.agent_executor import _is_healthkit_sync_intent
from app.services.tool_schema_registry import get_health_tools


# ──── A1: event 进 health_record enum ────

def test_health_record_enum_includes_event():
    tools = get_health_tools(["health_record"])
    assert tools, "health_record 工具应存在"
    enum = tools[0]["function"]["parameters"]["properties"]["record_type"]["enum"]
    assert "event" in enum, "record_type enum 必须含 'event'(否则模型无法记行程/事件)"
    # 与 health_manage 对齐(dispatch/别名早已支持 event,只 record 侧漏)
    for t in get_health_tools(["health_manage"]):
        assert "event" in t["function"]["parameters"]["properties"]["record_type"]["enum"]


# ──── A2: HealthKit 同步意图检测 ────

def test_healthkit_intent_positive():
    for text in (
        "同步 apple healthkit 数据",
        "同步 apple health",
        "帮我同步苹果健康",
        "sync my HealthKit",
        "把 Apple Health 的数据同步过来",
        "苹果健康数据同步一下",
    ):
        assert _is_healthkit_sync_intent(text), f"应识别为 HealthKit 意图: {text!r}"


def test_healthkit_intent_negative():
    # Garmin / 通用同步 / 空 → 不误判为 HealthKit(仍走 garmin_sync 或原路径)
    for text in (
        "帮我同步",
        "帮我同步 garmin",
        "同步Garmin数据",
        "为什么无法同步 garmin",
        "记录喝水300毫升",
        "",
        None,
    ):
        assert not _is_healthkit_sync_intent(text), f"不应误判为 HealthKit: {text!r}"


# ──── A4: LLM 客户端硬超时默认 ────

def test_apply_client_defaults_injects_timeout_and_retries():
    from app.services.llm.providers import openai_provider as op

    out = op._apply_client_defaults({"api_key": "x", "base_url": "https://y"})
    assert "timeout" in out, "必须注入硬超时(消无界 LLM 轮冻结)"
    assert out["max_retries"] == 1, "max_retries 收到 1(不再 ×3 放大冻结)"
    # read 帽 ≥ 当日最慢合法 llm_ms(88s)+ 余量,不误杀正常慢合成
    import httpx

    assert isinstance(out["timeout"], httpx.Timeout)
    assert out["timeout"].read >= 100.0
    assert out["timeout"].connect <= 15.0
    # 不改 caller 原 dict
    src = {"api_key": "x"}
    op._apply_client_defaults(src)
    assert "timeout" not in src and "max_retries" not in src


def test_apply_client_defaults_respects_caller_override():
    from app.services.llm.providers import openai_provider as op

    out = op._apply_client_defaults(
        {"api_key": "x", "timeout": 5.0, "max_retries": 0}
    )
    assert out["timeout"] == 5.0, "caller 显式 timeout 优先"
    assert out["max_retries"] == 0, "caller 显式 max_retries 优先"
