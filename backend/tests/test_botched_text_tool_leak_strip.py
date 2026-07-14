"""通用"工具调用写成文本"畸形泄漏剥离 — founder 2026-07-14「列出饮食记录」。

弱模型(qwen 经代理)把 tool call 吐成 `call {name: health_query, arguments: {dimension:…}}`
嵌套畸形(非 <tool> 族),既有 strip/recover 不认。通用检测: 前导块含 调用语法+注册工具名。
"""
from app.services.agent_executor import _strip_botched_text_tool_leak as strip


def test_strips_founder_nested_call_leak():
    leak = ("call {name: health_query, arguments: {dimension:{name: health_query, "
            "arguments: {dimension:call {name: health_query, arguments: {dimension:"
            "<call:health_query{dimension: diet}\n\n今日饮食如下：")
    assert strip(leak).startswith("今日饮食")


def test_strips_angle_call_variant():
    assert strip("<call:health_query{dimension: diet}\n\n今日饮食：").startswith("今日饮食")


def test_strips_brace_name_variant():
    assert strip('{name: health_manage, arguments: {record_type: water}}\n\n结果：').startswith("结果")


def test_leak_before_reva_ui_fence():
    t = 'call {name: health_query, arguments: {dimension: diet}}\n```reva-ui\n{...}'
    assert strip(t).startswith("```reva-ui")


def test_does_not_strip_normal_prose():
    t = "今日饮食明细：早餐 400kcal，午餐 350kcal。"
    assert strip(t) == t


def test_does_not_strip_tool_name_mention_without_call_syntax():
    # 讨论工具名但无 call{/arguments: 语法 → 保留(散文不含调用语法)
    t = "health_query 是查询健康数据的工具，你可以直接问我要哪类数据。"
    assert strip(t) == t


def test_does_not_strip_medical_disclaimer():
    t = "建议就医。涉及用药请咨询医生。"
    assert strip(t) == t


def test_strip_empty_result_falls_back_to_original():
    # 整条都是畸形泄漏、剥后为空 → 返回原文(不吞整条, 交给空回复重试链)
    t = "call {name: health_query, arguments: {dimension: diet}}"
    assert strip(t)  # 非空
