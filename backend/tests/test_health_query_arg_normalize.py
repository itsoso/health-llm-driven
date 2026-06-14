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
