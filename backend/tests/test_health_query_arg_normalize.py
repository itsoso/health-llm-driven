"""health_query 参数容错归一。钉:模型把 dimension 猜成 type/query_type=lab_results 时也能修正。

实测 bug 回归:Claude-Opus-4.7 `health_query(type=lab_results, days=7)` /
`health_query(query_type=lab_results, time_range=14d)` → 应归一到 dimension='medical_exam'。
"""

from app.services.agent_executor import _normalize_health_query_args as norm


def test_type_alias_lab_results_to_medical_exam():
    # 截图里的真实失败调用 1
    a = norm({"type": "lab_results", "days": 7})
    assert a["dimension"] == "medical_exam" and a["days"] == 7


def test_query_type_alias_and_time_range():
    # 真实失败调用 2:query_type + time_range="14d"
    a = norm({"query_type": "lab_results", "time_range": "14d"})
    assert a["dimension"] == "medical_exam" and a["days"] == 14


def test_chinese_and_other_aliases():
    assert norm({"dimension": "化验"})["dimension"] == "medical_exam"
    assert norm({"type": "gene"})["dimension"] == "genetic"
    assert norm({"category": "血压"})["dimension"] == "blood_pressure"
    assert norm({"type": "meds"})["dimension"] == "medication"


def test_correct_args_passthrough():
    # 已经对的不动
    a = norm({"dimension": "medical_exam", "indicator": "HCY", "days": 30})
    assert a == {"dimension": "medical_exam", "indicator": "HCY", "days": 30}


def test_unknown_dimension_preserved():
    # 不认识的值原样留给下游(不臆造)
    assert norm({"dimension": "sleep"})["dimension"] == "sleep"
    assert norm({"dimension": "某未知维度"})["dimension"] == "某未知维度"


def test_empty_and_none_safe():
    assert norm({}) == {}
    assert norm({"dimension": ""}).get("dimension") in (None, "")  # 空不崩


def test_dimension_wins_over_alias():
    # 同时有 dimension 和 type → dimension 优先,不被覆盖
    a = norm({"dimension": "sleep", "type": "lab_results"})
    assert a["dimension"] == "sleep"


def test_unknown_payload_fields_are_not_forwarded_to_health_query():
    a = norm(
        {
            "dimension": "sleep",
            "days": 30,
            "record_type": "symptom",
            "data": {"description": "模型自造字段"},
        }
    )
    assert a == {"dimension": "sleep", "days": 30}


def test_supported_legacy_aliases_are_derived_before_schema_projection():
    a = norm(
        {
            "type": "medical_records",
            "query": "膝关节MRI",
            "created_days": 3,
            "created_since": "2026-08-01",
        }
    )
    assert a == {
        "dimension": "medical_exam",
        "keyword": "膝关节MRI",
        "uploaded_days": 3,
        "uploaded_since": "2026-08-01",
    }


# ──── MRI 假阴回归(prod 实锤:Claude-4.7 内联 JSON + medical_records) ────


def test_medical_records_and_imaging_aliases_normalize_to_medical_exam():
    from app.services.agent_executor import _normalize_health_query_args

    for raw in (
        "medical_records",
        "medical_record",
        "imaging",
        "mri",
        "核磁",
        "磁共振",
        "ct",
        "xray",
        "ultrasound",
        "影像",
        "影像报告",
        "检查报告",
    ):
        out = _normalize_health_query_args({"type": raw})
        assert out["dimension"] == "medical_exam", raw


def test_uploaded_range_alias_normalizes_to_uploaded_days():
    a = norm({"type": "medical_records", "uploaded_range": "近1天"})
    assert a["dimension"] == "medical_exam"
    assert a["uploaded_days"] == 1


def test_claude_inline_params_payload_recovers_end_to_end():
    # prod 日志原始形状:{"tool":..,"params":{...}} —— 恢复层曾只认 parameters/arguments
    from app.services.agent_executor import (
        _extract_inline_tool_call,
        _normalize_health_query_args,
    )

    text = '我先查一下你的膝关节MRI相关记录。\n{"tool":"health_query","params":{"type":"medical_records","keyword":"膝关节MRI"}}'
    tools = [{"function": {"name": "health_query"}}]
    call = _extract_inline_tool_call(text, tools)
    assert call is not None
    import json as _json

    args = _json.loads(call["function"]["arguments"])
    assert args.get("type") == "medical_records"  # params 容器被解开,参数不再丢失
    normalized = _normalize_health_query_args(args)
    assert normalized["dimension"] == "medical_exam"


def test_anthropic_style_input_container_also_recovers():
    from app.services.agent_executor import _extract_inline_tool_call
    import json as _json

    text = '{"name":"health_query","input":{"dimension":"medical_exam"}}'
    call = _extract_inline_tool_call(text, [{"function": {"name": "health_query"}}])
    assert call is not None
    assert _json.loads(call["function"]["arguments"])["dimension"] == "medical_exam"
