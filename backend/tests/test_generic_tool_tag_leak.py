"""通用 `<tool>` 伪标签工具调用泄漏:展示剥离 + 重提示门(F 止血,补 origin/main 未接线的死代码)。

生产实锤(founder 截图 2026-07-14,mac app,qwen3.7-max/qwen3.6-flash 工具轮):弱模型把工具
调用吐成 `<tool>` 伪标签 + 残缺/嵌套 JSON/签名混合的**文本**,而非结构化 tool_calls。既非
`<invoke>` 也非 `<minimax:tool_call>`,前两张网都漏,原文一字未改:

    <tool> {"name": "health_manage", "arguments": {"record_type<tool> {"name<tool> {"name":health_manage(record_type='diet', operation='list', date='today', meal_type='breakfast')

`_XML_TOOLCALL_PREFIX_RE` 已在流式期抑制逐 token live 泄漏;但 `_GENERIC_TOOL_TAG_LEAK_RE`
一度被定义却无人消费(死代码)—— 最终/持久化文本(full_reply / message.meta / reload)仍会
把整段 blob 作为一整块回显 + 落库。本测试锁死两条接线:
  · `_strip_xml_tool_markers` —— 展示兜底剥净畸形 blob(恢复不出结构化调用时);
  · `_is_botched_text_tool_call` —— 认出该 blob → 重提示模型用结构化 function calling 重试。

安全边界(误伤防线):门控要求 `<tool>` 标签后**紧跟**工具调用形状(`{` / 另一 tool 标签 /
`name(`),故文档里的 `<tool>example</tool>`、代码块、`<toolbar>`、散文里的 `<` 全部不动。
"""
import json

from app.services.agent_executor import (
    _strip_xml_tool_markers,
    _is_botched_text_tool_call,
    _extract_inline_tool_call,
    _GENERIC_TOOL_TAG_LEAK_RE,
    _maybe_generic_tool_tag,
    _XML_TOOLCALL_PREFIX_RE,
)
from app.services.tool_schema_registry import HEALTH_TOOLS

# founder 截图原文,一字未改。
_FOUNDER = (
    '<tool> {"name": "health_manage", "arguments": {"record_type<tool> '
    '{"name<tool> {"name":health_manage(record_type=\'diet\', operation=\'list\', '
    'date=\'today\', meal_type=\'breakfast\')'
)

TOOLS = [{"function": {"name": "health_manage"}}, {"function": {"name": "health_query"}}]


# ── 展示剥离:畸形 blob 从最终/持久化文本剥净(恢复不出结构化调用时的兜底)────────
def test_strip_founder_exact_blob_to_empty():
    """founder 原文整段就是畸形工具语法 → 剥净后为空(交给空回复重试链,绝不泄漏)。"""
    out = _strip_xml_tool_markers(_FOUNDER)
    assert out == ""
    assert "<tool" not in out
    assert "health_manage(" not in out


def test_strip_wellformed_tool_tag_blob():
    assert _strip_xml_tool_markers('<tool_call>{"name":"health_query"}</tool_call>') == ""
    assert _strip_xml_tool_markers('<function_call>{"name":"health_query"}') == ""


def test_strip_signature_only_tag():
    assert _strip_xml_tool_markers("<tool>health_manage(record_type='diet')</tool>") == ""


def test_strip_preserves_prose_preamble():
    """短前言 + 尾部畸形 blob → 只剥 blob,保前言。"""
    txt = "好的,我帮你查一下今天的早餐。<tool> {\"name\":health_manage(record_type='diet')"
    assert _strip_xml_tool_markers(txt) == "好的,我帮你查一下今天的早餐。"


def test_strip_stops_at_cjk_prose_after_blob():
    """blob 后紧跟中文散文 → JSON 片段止于 CJK,绝不吞散文。"""
    txt = '<tool>{"name":"health_query","arguments":{"dimension":"diet"}}好的这是你的饮食'
    assert _strip_xml_tool_markers(txt) == "好的这是你的饮食"


def test_strip_two_blobs_keep_prose_between():
    txt = '第一段。<tool>{"name":"health_query"}中间<tool>{"name":"health_manage"}结尾。'
    assert _strip_xml_tool_markers(txt) == "第一段。中间结尾。"


def test_strip_tag_with_attributes_and_unclosed():
    assert _strip_xml_tool_markers('<tool name="health_query">{"arguments":{"dimension":"diet"}}') == ""
    assert _strip_xml_tool_markers('<tool {"name":"health_query","arguments":{') == ""


def test_strip_cjk_value_in_json_fully_consumed():
    """JSON 值含中文(带引号)整体消费,不残留。"""
    assert _strip_xml_tool_markers('<tool>{"name":"health_record","arguments":{"food_name":"米饭"}}') == ""


# ── 误伤防线:文档/代码块/普通散文里的 `<tool>` / `<` 一律不动 ──────────────────
def test_no_touch_doc_tag_without_toolcall_shape():
    txt = "在 HTML 里,<tool>example</tool> 不是合法标签。"
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_code_fence_with_tool_tag():
    txt = "示例代码:\n```xml\n<tool>demo</tool>\n```"
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_toolbar_word():
    txt = "页面顶部的 <toolbar> 区域展示导航。"
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_plain_comparisons_and_calls():
    txt = "如果 x < 5 那么 f(x) 会增大,收缩压 120 < 130 正常。"
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_menu_share_block():
    txt = '今晚吃这些 ```menu_share\n{"title":"晚餐"}\n```'
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_plain_answer():
    txt = "你今天的睡眠评分是 82 分,深睡占比不错。"
    assert _strip_xml_tool_markers(txt) == txt


# ── 既有格式回归:invoke / minimax 剥离仍生效,不受新分支影响 ─────────────────
def test_invoke_regression_still_stripped():
    txt = '<invoke name="health_query"><parameter name="dimension">diet</parameter></invoke>'
    assert _strip_xml_tool_markers(txt) == ""


# ── 重提示门:认出畸形 blob → 重试(拿真数据);普通文本不误判 ─────────────────
def test_botched_detects_founder_blob():
    assert _is_botched_text_tool_call(_FOUNDER, HEALTH_TOOLS) is True


def test_botched_detects_markdown_list_regression():
    assert _is_botched_text_tool_call("拉补剂库。\n\nTool calls:\n- health_query", HEALTH_TOOLS) is True


def test_botched_no_false_positive():
    # 标记词但无已注册工具名
    assert _is_botched_text_tool_call("Tool calls: 暂无需要调用的", HEALTH_TOOLS) is False
    # 普通回答
    assert _is_botched_text_tool_call("你的补剂库有 6 项。", HEALTH_TOOLS) is False
    # 文档里的 <tool> 标签但没工具调用形状/没注册工具名
    assert _is_botched_text_tool_call("<tool>example</tool> 是什么", HEALTH_TOOLS) is False


# ── well-formed <tool> JSON 仍优先被恢复成真调用(先执行,不走剥离)──────────────
def test_wellformed_tool_tag_json_recovered_as_call():
    """`<tool>{"name":..}` 的合法 JSON 已被 _extract_inline_tool_call 恢复成真 tool_call。"""
    call = _extract_inline_tool_call('<tool>{"name":"health_query","arguments":{"dimension":"diet"}}</tool>', HEALTH_TOOLS)
    assert call is not None
    assert call["function"]["name"] == "health_query"
    assert json.loads(call["function"]["arguments"]) == {"dimension": "diet"}


# ── 流式期前缀抑制:`<tool` 家族一出现即抑制 live 下发;`<toolbar`/`<` 不误伤 ─────
def test_streaming_prefix_suppresses_tool_family():
    for s in ("<tool", "好的<tool>", "<tool_call", "<function_call", "<invoke", "<minimax:tool_call"):
        assert _XML_TOOLCALL_PREFIX_RE.search(s), s


def test_streaming_prefix_no_false_positive():
    for s in ("<toolbar", "血压 < 120", "普通回答 f(x)", "<toolkit>"):
        assert not _XML_TOOLCALL_PREFIX_RE.search(s), s


# ── ReDoS 冒烟:病态输入必须线性返回(各分支首字符互斥)──────────────────────
def test_no_catastrophic_backtracking():
    _GENERIC_TOOL_TAG_LEAK_RE.sub("", "<tool>" + '{"a":"b",' * 800 + "x" * 800)
    _GENERIC_TOOL_TAG_LEAK_RE.sub("", "<tool>" + "a(" * 500)
