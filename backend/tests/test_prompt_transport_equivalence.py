"""Byte contracts for a faster scan of validated tool JSON; no timing assertions."""
import copy
import importlib.util
import json
from pathlib import Path
import random

import pytest

from app.services.llm.prompt_transport import compact_tool_json


def baseline(messages):
    path = Path(__file__).parent / "fixtures/prompt_transport_7d934b3.py"
    spec = importlib.util.spec_from_file_location("frozen_prompt_transport", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compact_tool_json(messages)


def test_numeric_and_duplicate_key_lexemes_are_exact():
    raw = '\t{ "v": -0.0000E+019, "v": 1.2300e-9999, "big": ' + '9' * 6000 + ', "s": "two  spaces\\u0020\\n" }\r\n'
    expected = '{"v":-0.0000E+019,"v":1.2300e-9999,"big":' + '9' * 6000 + ',"s":"two  spaces\\u0020\\n"}'
    message = {"role": "tool", "content": raw, "tool_call_id": "synthetic", "extension": {"keep": True}}
    result = compact_tool_json([message])
    assert result == [{**message, "content": expected}]
    assert message["content"] == raw
    assert result[0]["extension"] is message["extension"]


def test_deterministic_string_corpus_matches_serializer_and_frozen_baseline():
    rng = random.Random(20261004)
    alphabet = ['a', '中', '🙂', ' ', '\t', '\n', '\r', '"', '\\', '/', '\x00', '\x1f', '\u2028', '\u00a0']
    for index in range(768):
        values = [''.join(rng.choices(alphabet, k=index % 73)), '\\' * (index % 19) + '"',
                  {"key": "literal \\u0020", "n": index, "null": None, "ok": True}]
        ascii_only = bool(index % 2)
        raw = json.dumps(values, ensure_ascii=ascii_only, indent=index % 5)
        expected = json.dumps(values, ensure_ascii=ascii_only, separators=(',', ':'))
        messages = [{"role": "tool", "content": raw}]
        assert compact_tool_json(messages)[0]["content"] == expected
        assert compact_tool_json(messages) == baseline(messages)
        assert compact_tool_json(compact_tool_json(messages)) == compact_tool_json(messages)


@pytest.mark.parametrize("text", [
    '{ "v": NaN }', '{ "v": -Infinity }', '{ "v": Infinity }',
    '{ "v": 01 }', '{ "v": +1 }', '{ "v": 1, }',
    '{ "v": "raw\nline" }', r'{ "v": "bad\qescape" }',
    '{ "v": 1 } trailing', '\u00a0{ "v": 1 }',
    pytest.param('[' * 1500, id='unfinished-deep-array'),
    pytest.param('{ "v": "' + '\\\\' * 10000, id='unfinished-long-string'),
])
def test_invalid_and_too_deep_results_retain_original_message(text):
    message = {"role": "tool", "content": text}
    result = compact_tool_json([message])
    assert result[0] is message
    assert result == baseline([message])


def test_non_tool_arguments_and_multimodal_contents_keep_identity():
    messages = [{"role": role, "content": '{ "keep": "two  spaces" }'}
                for role in ('system', 'user', 'assistant')]
    messages += [{"role": "tool", "content": [{"type": "text", "text": '{ "v": 1 }'}]},
                 {"role": "tool", "content": None},
                 {"role": "tool", "content": '"JSON scalar  string"'},
                 {"role": "assistant", "tool_calls": [{"function": {"arguments": '{ "v": 1 }'}}]}]
    before = copy.deepcopy(messages)
    result = compact_tool_json(messages)
    assert all(actual is original for actual, original in zip(result, messages))
    assert messages == before


def test_decoder_recursion_error_retains_opaque_message(monkeypatch):
    def recursion_limit(*args, **kwargs):
        raise RecursionError("synthetic decoder limit")

    monkeypatch.setattr(json, "loads", recursion_limit)
    message = {"role": "tool", "content": '[ [ [ 0 ] ] ]'}
    assert compact_tool_json([message])[0] is message


@pytest.mark.parametrize("value", ['report  text\n' * 50000, '\\"\n\t' * 50000])
def test_long_strings_keep_all_characters_and_escapes(value):
    raw = json.dumps({"text": value}, indent=2)
    messages = [{"role": "tool", "content": raw}]
    assert compact_tool_json(messages) == baseline(messages)
    assert compact_tool_json(messages)[0]["content"] == json.dumps({"text": value}, separators=(',', ':'))
