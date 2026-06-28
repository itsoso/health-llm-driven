"""lenient_loads —— 救 LLM 吐的非法 JSON(体检报告上传 HTTP400 的修复)。

铁律回归:
- 合法 JSON 零行为变化(快路径)。
- key 位置的弯引号/全角/裸 key/尾逗号/控制字符 → 修复后解析成功。
- 截断的 JSON → 仍抛 json.JSONDecodeError(调用方 pdf_parser 靠它判"截断→分次导入"而非"格式错误")。
- 只补 key 引号,绝不给中文 value 误加引号。
"""
import json

import pytest

from app.services.json_lenient import lenient_loads


def test_valid_json_passes_through():
    assert lenient_loads('{"summary": "正常", "n": 3}') == {"summary": "正常", "n": 3}


def test_dict_or_list_passthrough():
    assert lenient_loads({"a": 1}) == {"a": 1}
    assert lenient_loads([1, 2]) == [1, 2]


def test_bare_key_repaired():
    # 实测报错形态:`Expecting property name enclosed in double quotes`(裸 key)
    out = lenient_loads('{"a": 1, summary: "x", b_2: 2}')
    assert out == {"a": 1, "summary": "x", "b_2": 2}


def test_smart_double_quote_on_key_repaired():
    # 全角/弯引号当 key 分隔符 → 严格解析在 key 位置失败
    raw = '{“summary”: "肝功能正常", "ok": true}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)  # 证明严格会炸
    assert lenient_loads(raw) == {"summary": "肝功能正常", "ok": True}


def test_fullwidth_colon_and_comma_repaired():
    raw = '{"a"：1，"b"：2}'
    assert lenient_loads(raw) == {"a": 1, "b": 2}


def test_trailing_comma_nested_repaired():
    raw = '{"items": [{"x": 1,}], "k": 2,}'
    assert lenient_loads(raw) == {"items": [{"x": 1}], "k": 2}


def test_control_char_in_string_repaired():
    raw = '{"note": "line1\x07line2"}'  # 裸控制字符(响铃)在字符串里 → 非法
    assert lenient_loads(raw)["note"] == "line1line2"


def test_code_fence_stripped():
    assert lenient_loads('```json\n{"a": 1}\n```') == {"a": 1}


def test_chinese_value_not_quote_mangled():
    # 不能把中文 value 当裸 key 误加引号
    out = lenient_loads('{"diagnosis": 脂肪肝}'.replace("脂肪肝", '"脂肪肝"'))
    assert out == {"diagnosis": "脂肪肝"}
    # 合法中文值原样
    assert lenient_loads('{"d": "脂肪肝 轻度"}') == {"d": "脂肪肝 轻度"}


def test_truncated_json_still_raises():
    # 截断(超 max_tokens 被切)→ 必须仍抛 JSONDecodeError,pdf_parser 据此给"分次导入"指引
    raw = '{"summary": "很长的报告", "items": [{"name": "ALT", "value":'
    with pytest.raises(json.JSONDecodeError):
        lenient_loads(raw)


def test_unrepairable_raises_original_error():
    # 修不动 → 抛原始严格异常(不假装成功)
    with pytest.raises(json.JSONDecodeError):
        lenient_loads("not json at all {{{")
