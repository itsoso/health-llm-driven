"""内联工具调用:MiniMax 经代理吐的 XML/`<invoke>` 格式的恢复 + 剥离(F1 止血)。

生产实锤(2026-07-05 20:19:24 journalctl 原文):MiniMax 把工具调用吐成 Anthropic 风格 XML
而非结构化 tool_calls:
    <invoke name="health_query">
    <parameter name="dimension">diet</parameter>
    <parameter name="days">7</parameter>
    </invoke>
    </minimax:tool_call>
JSON + 括号两张网都漏 → 工具没执行(零数据)+ 原始 XML 语法泄漏给用户。客户端截图还出现过
同一 invoke 重复两次、闭标签 `</minimax:tool_call>` 悬空无开标签的变体。

覆盖:
- 生产原文 → 恢复出 health_query(dimension=diet, days=7 且 days 为 int)
- 双 invoke 变体 → 取第一个已注册工具
- 孤立闭标签 / 整块剥净,不泄漏原始语法
- 未注册工具名不吞
- 既有 JSON / 括号格式回归零变化
"""
import json

from app.services.agent_executor import (
    _extract_inline_tool_call,
    _extract_xml_tool_call,
    _extract_bracket_tool_call,
    _strip_xml_tool_markers,
    _strip_bracket_tool_markers,
    _coerce_param_by_schema,
)
from app.services.tool_schema_registry import HEALTH_TOOLS

# 生产实锤 payload,一字未改(前导 \n + 悬空 </minimax:tool_call>)。
_PROD_PAYLOAD = (
    '\n<invoke name="health_query">\n'
    '<parameter name="dimension">diet</parameter>\n'
    '<parameter name="days">7</parameter>\n'
    '</invoke>\n'
    '</minimax:tool_call>'
)

_ALLOWED = {"health_query", "health_record", "health_manage"}


# ── 恢复 ────────────────────────────────────────────────────────────────

def test_prod_payload_recovered_via_inline_entrypoint():
    """生产原文经统一入口 _extract_inline_tool_call 恢复(与三张网共用的函数)。"""
    call = _extract_inline_tool_call(_PROD_PAYLOAD, HEALTH_TOOLS)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    args = json.loads(call["function"]["arguments"])
    assert args["dimension"] == "diet"
    # days 声明为 integer → coerce 成 int 7,不是字符串 "7"(镜像括号分支数值 coercion)。
    assert args["days"] == 7
    assert isinstance(args["days"], int)


def test_prod_payload_recovered_via_xml_helper():
    call = _extract_xml_tool_call(_PROD_PAYLOAD, HEALTH_TOOLS, _ALLOWED)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    args = json.loads(call["function"]["arguments"])
    assert args == {"dimension": "diet", "days": 7}


def test_days_coerced_by_schema_integer_type():
    """days 是 integer schema → 字符串 "7" 必须变 int(422 float→int 教训)。"""
    props = {}
    for t in HEALTH_TOOLS:
        if t["function"]["name"] == "health_query":
            props = t["function"]["parameters"]["properties"]
            break
    assert _coerce_param_by_schema("7", props.get("days")) == 7
    assert isinstance(_coerce_param_by_schema("7", props.get("days")), int)
    # dimension 是 string enum → 保持字符串。
    assert _coerce_param_by_schema("diet", props.get("dimension")) == "diet"
    # schema 缺失该参数 → 内容形状推断兜底(裸数字→int,裸标识符→str)。
    assert _coerce_param_by_schema("42", None) == 42
    assert _coerce_param_by_schema("comprehensive", None) == "comprehensive"


def test_double_invoke_takes_first_registered():
    """同一 invoke 重复两次(客户端截图变体)→ 取第一个已注册工具,只恢复一次。"""
    dup = _PROD_PAYLOAD + _PROD_PAYLOAD
    call = _extract_inline_tool_call(dup, HEALTH_TOOLS)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    args = json.loads(call["function"]["arguments"])
    assert args == {"dimension": "diet", "days": 7}


def test_unregistered_invoke_name_not_swallowed():
    """未注册工具名的 <invoke> 不恢复成调用(保持可见,镜像 menu_share 守卫)。"""
    txt = (
        '<invoke name="definitely_not_a_tool">\n'
        '<parameter name="x">1</parameter>\n'
        '</invoke>'
    )
    assert _extract_xml_tool_call(txt, HEALTH_TOOLS, _ALLOWED) is None
    assert _extract_inline_tool_call(txt, HEALTH_TOOLS) is None


def test_first_invoke_unregistered_second_registered():
    """第一个 invoke 未注册、第二个已注册 → 跳过未注册的,恢复第二个。"""
    txt = (
        '<invoke name="bogus"><parameter name="a">1</parameter></invoke>\n'
        '<invoke name="health_query"><parameter name="dimension">sleep</parameter></invoke>'
    )
    call = _extract_xml_tool_call(txt, HEALTH_TOOLS, _ALLOWED)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    assert json.loads(call["function"]["arguments"]) == {"dimension": "sleep"}


# ── 剥离(重试用尽 / 未恢复兜底,绝不泄漏原始语法)────────────────────────

def test_strip_full_invoke_block_and_orphan_tag():
    out = _strip_xml_tool_markers(_PROD_PAYLOAD)
    assert "<invoke" not in out
    assert "</invoke" not in out
    assert "minimax:tool_call" not in out
    assert "<parameter" not in out
    assert out == ""  # 整条就是工具语法 → 剥净后为空(交给空回复重试链)


def test_strip_orphan_closing_tag_only():
    """悬空无开标签的 </minimax:tool_call>(客户端截图变体)也剥净。"""
    txt = "这是给你的回答。\n</minimax:tool_call>"
    out = _strip_xml_tool_markers(txt)
    assert "minimax:tool_call" not in out
    assert "这是给你的回答。" in out


def test_strip_preserves_prose_around_block():
    txt = (
        "我帮你查一下今天的饮食 🍜\n"
        '<invoke name="health_query"><parameter name="dimension">diet</parameter></invoke>\n'
        "稍等。"
    )
    out = _strip_xml_tool_markers(txt)
    assert "<invoke" not in out and "health_query" not in out
    assert "我帮你查一下今天的饮食" in out
    assert "稍等。" in out


def test_strip_noop_when_no_xml_markers():
    txt = "普通回答,没有任何工具语法。"
    assert _strip_xml_tool_markers(txt) == txt


# ── 既有格式回归(JSON / 括号零变化)────────────────────────────────────

def test_json_format_regression_unchanged():
    """裸 JSON 工具调用仍走 JSON 分支恢复,不受 XML 分支影响。"""
    txt = '{"name":"health_query","parameters":{"dimension":"sleep","days":3}}'
    call = _extract_inline_tool_call(txt, HEALTH_TOOLS)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    args = json.loads(call["function"]["arguments"])
    assert args == {"dimension": "sleep", "days": 3}


def test_bracket_format_regression_unchanged():
    """括号签名格式仍恢复,XML 分支不干扰(它以 `<` 开头,与 `[`/`{` 不冲突)。"""
    txt = '已记录 [工具调用: health_query(dimension=medical_exam, days=30)]'
    call = _extract_inline_tool_call(txt, HEALTH_TOOLS)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    args = json.loads(call["function"]["arguments"])
    assert args["dimension"] == "medical_exam"
    assert args["days"] == 30


def test_xml_strip_does_not_touch_bracket_or_json_text():
    """XML strip 只动 XML 标记,不误伤括号 / JSON / menu_share 文本。"""
    bracket_txt = '[工具调用: health_query(dimension=diet)]'
    assert _strip_xml_tool_markers(bracket_txt) == bracket_txt
    menu_txt = '今晚吃这些 ```menu_share\n{"title":"晚餐"}\n```'
    assert _strip_xml_tool_markers(menu_txt) == menu_txt


def test_bracket_strip_does_not_touch_xml_text():
    """反向:括号 strip 不动 XML 块(两条剥离链各管各的格式)。"""
    xml_txt = '<invoke name="health_query"><parameter name="dimension">diet</parameter></invoke>'
    assert _strip_bracket_tool_markers(xml_txt) == xml_txt


def test_plain_text_not_recovered_as_toolcall():
    """普通回答不含任何工具语法 → 不恢复、不剥离。"""
    txt = "你今天的睡眠评分是 82 分,深睡占比不错。"
    assert _extract_inline_tool_call(txt, HEALTH_TOOLS) is None
    assert _strip_xml_tool_markers(txt) == txt
