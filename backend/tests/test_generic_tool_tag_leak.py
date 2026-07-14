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

import pytest

from app.services.agent_executor import (
    _strip_xml_tool_markers,
    _is_botched_text_tool_call,
    _extract_inline_tool_call,
    _GENERIC_TOOL_TAG_LEAK_RE,
    _starts_like_bare_registered_tool_call,
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


def test_recovers_exact_bare_registered_python_call():
    """整条回复只有已注册函数签名时应恢复执行,不能把机器语法展示给用户。"""
    call = _extract_inline_tool_call(
        "health_manage(record_type='diet', operation='delete')",
        HEALTH_TOOLS,
        user_message="删除最后一餐，重复记录了",
    )

    assert call is not None
    assert call["function"]["name"] == "health_manage"
    assert json.loads(call["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "delete",
    }


def test_does_not_execute_bare_python_call_embedded_in_prose():
    """只允许整条机器调用恢复;教程或解释里的函数签名保持普通文本。"""
    assert _extract_inline_tool_call(
        "示例写法是 health_manage(record_type='diet', operation='delete')。",
        HEALTH_TOOLS,
    ) is None


def test_does_not_recover_bare_delete_without_matching_user_write_intent():
    raw = "health_manage(record_type='diet', operation='delete', record_id=74)"

    assert _extract_inline_tool_call(raw, HEALTH_TOOLS, user_message="如何删除一餐？") is None
    assert _extract_inline_tool_call(raw, HEALTH_TOOLS, user_message="不要删除最后一餐") is None
    assert _extract_inline_tool_call(raw, HEALTH_TOOLS, user_message="请展示调用示例") is None


@pytest.mark.parametrize("raw", [
    '[工具调用: health_manage(record_type="diet", operation="delete", record_id=74)]',
    '<invoke name="health_manage"><parameter name="record_type">diet</parameter>'
    '<parameter name="operation">delete</parameter><parameter name="record_id">74</parameter></invoke>',
    '<tool>health_manage {"record_type":"diet","operation":"delete","record_id":74}</tool>',
    '{"name":"health_manage","parameters":{"record_type":"diet","operation":"delete","record_id":74}}',
])
def test_all_textual_tool_formats_share_the_same_write_intent_gate(raw):
    assert _extract_inline_tool_call(raw, HEALTH_TOOLS, user_message="如何删除一餐？") is None
    assert _extract_inline_tool_call(raw, HEALTH_TOOLS, user_message="不要删除这条记录") is None


def test_suppresses_a_bare_registered_call_while_it_is_still_streaming():
    assert _starts_like_bare_registered_tool_call("health_man", HEALTH_TOOLS)
    assert _starts_like_bare_registered_tool_call("health_manage(", HEALTH_TOOLS)
    assert not _starts_like_bare_registered_tool_call("h", HEALTH_TOOLS)
    assert not _starts_like_bare_registered_tool_call("health advice", HEALTH_TOOLS)
    assert not _starts_like_bare_registered_tool_call("今天建议先休息", HEALTH_TOOLS)


# ── Finding 1:fenced ``` 块 / 行内 `code` span 里的工具语法(即便形如调用)绝不剥 ─────
# 讲解工具语法的示例、贴 KB 片段等会把 tool-call 形状的 `<tool>` 放进代码区;此前门控只在
# "标签后无调用形状"时豁免,一旦示例里带 `example(1)` / `{"name":...}` 就被 mangle 且吃穿闭合
# 围栏继续吞后文。修复:`_apply_outside_code_spans` 把代码区整体豁免(镜像 _leaks_tool_result_json)。
def test_no_touch_code_fence_with_toolshaped_content():
    """围栏块里 `<tool>example(1)</tool>` 形如调用 → 整块豁免,不吃穿闭合 ``` 吞后文。"""
    txt = "示例:\n```xml\n<tool>demo</tool>\n<tool>example(1)</tool>\n```\n以上是配置。"
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_code_fence_with_json_toolcall():
    txt = '讲解:\n```json\n<tool_call>{"name":"health_query","arguments":{"dimension":"diet"}}</tool_call>\n```\n就是这样。'
    assert _strip_xml_tool_markers(txt) == txt


def test_no_touch_inline_code_tool_syntax():
    """行内 `code` span 里的 `<tool_call>{...}</tool_call>` 元讲解 → 保留。"""
    txt = '系统内部会生成 `<tool_call>{"name":"health_query"}</tool_call>` 这样的结构。'
    assert _strip_xml_tool_markers(txt) == txt


def test_real_leak_after_fence_still_stripped():
    """Finding 1 的对侧:真泄漏若恰好跟在围栏块后,仍照剥(只豁免代码区,不豁免其后散文)。"""
    txt = '```json\n{"a":1}\n```\n好的<tool>{"name":"health_query"}'
    assert _strip_xml_tool_markers(txt) == '```json\n{"a":1}\n```\n好的'


def test_botched_ignores_fenced_example():
    """围栏/行内代码里的工具语法不算"该重试的畸形调用" → 不触发重提示门。"""
    fenced = '讲解:\n```\n<tool>health_query(dimension="diet")</tool>\n```'
    assert _is_botched_text_tool_call(fenced, HEALTH_TOOLS) is False
    inline = '系统会生成 `<tool_call>{"name":"health_query"}</tool_call>` 结构'
    assert _is_botched_text_tool_call(inline, HEALTH_TOOLS) is False


def test_botched_still_fires_on_leak_after_fence():
    txt = '```\nx\n```\n好的<tool>{"name":"health_query"}'
    assert _is_botched_text_tool_call(txt, HEALTH_TOOLS) is True


# 已知限度(接受):**裸散文**(无围栏/无行内代码)里的元讲解含字面工具语法,与真泄漏在
# 语法层不可区分 → 仍被剥。缓解 = 用代码区包起来(见上面 inline_code / code_fence 用例即保留)。
# 健康产品几乎不会裸讲工具语法,故接受;此测试把该边界钉成"有意为之",防被误当回归。
def test_bare_prose_meta_explanation_is_stripped_known_limitation():
    txt = '系统内部会生成 <tool_call>{"name":"health_query"}</tool_call> 这样的结构。'
    assert _strip_xml_tool_markers(txt) == "系统内部会生成 这样的结构。"


# ── Finding 2:JSON 对象体止于配平 `}` → 不吞尾随**英文**散文(中文本就被 CJK 挡住)─────
# `[^<一-鿿]` 止于 `<`/CJK 但不止于英文,故 blob 后同一行的英文子句被吞。修复:JSON 体加
# `{}` 到 stop set,收在配平括号处,尾随英文由外层循环在非调用形状处自然停下而保留。
def test_blob_then_english_suffix_preserved():
    txt = 'Okay. <tool>{"name":"health_query"} your blood pressure is fine'
    assert _strip_xml_tool_markers(txt) == "Okay. your blood pressure is fine"


def test_blob_balanced_json_then_english():
    txt = '<tool>{"name":"health_query","arguments":{"dimension":"diet"}} here is your data'
    assert _strip_xml_tool_markers(txt) == "here is your data"


def test_founder_still_empty_after_finding2_change():
    """Finding 2 的 `{}` stop 不得破坏主修复:founder 残缺/嵌套 blob 仍剥净为空。"""
    assert _strip_xml_tool_markers(_FOUNDER) == ""


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
    # Finding 2 后 JSON 体在 }/{ 处收尾→外层循环重入,深嵌套/多对象不得退化。
    _GENERIC_TOOL_TAG_LEAK_RE.sub("", "<tool>" + "{" * 1000 + "}" * 1000)
    _GENERIC_TOOL_TAG_LEAK_RE.sub("", "<tool>" + '{"k":1}' * 800)
