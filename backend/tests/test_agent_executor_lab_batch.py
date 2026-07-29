"""query_lab_indicators 批量查询回归 —— 性能优化:模型一次查 N 个指标而非 N 次调用。

单指标(name)shape 向后兼容不变;批量(names=[...])返回 by_name 分组。
"""
import asyncio
import json
from datetime import date, timedelta

from app.models.family_health import MedicalIndicator
from app.services.agent_executor import AgentExecutor


def _ind(uid, name, value, unit, d, **kw):
    return MedicalIndicator(user_id=uid, name=name, name_en=kw.get("name_en"), value=value,
                            unit=unit, record_date=d, is_abnormal=kw.get("is_abnormal", False),
                            reference_high=kw.get("reference_high"))


def _run(coro):
    return asyncio.run(coro)


def _lab(db, uid, **args):
    ex = AgentExecutor(db)
    ex._current_user_id = uid
    return json.loads(_run(ex._exec_query_lab_indicators("http://x", {}, args)))


def _seed(db, uid):
    r = date.today() - timedelta(days=20)
    db.add_all([
        _ind(uid, "低密度脂蛋白", 3.8, "mmol/L", r, name_en="LDL", is_abnormal=True, reference_high=3.4),
        _ind(uid, "谷丙转氨酶", 42, "U/L", r, name_en="ALT"),
        _ind(uid, "促甲状腺激素", 2.1, "mIU/L", r, name_en="TSH"),
    ])
    db.commit()


def test_single_name_backward_compat(db):
    _seed(db, 1)
    out = _lab(db, 1, name="LDL")
    assert "batch" not in out                 # 单指标不走批量 shape
    assert out["count"] == 1
    assert out["items"][0]["name_en"] == "LDL"


def test_batch_names_grouped(db):
    _seed(db, 2)
    out = _lab(db, 2, names=["LDL", "ALT", "TSH"])
    assert out["batch"] is True
    assert out["count"] == 3
    assert set(out["by_name"].keys()) == {"LDL", "ALT", "TSH"}
    assert out["by_name"]["LDL"]["items"][0]["name_en"] == "LDL"
    assert out["by_name"]["ALT"]["count"] == 1
    assert out["queried"] == ["LDL", "ALT", "TSH"]


def test_batch_dedup_preserves_order(db):
    _seed(db, 3)
    out = _lab(db, 3, names=["LDL", "LDL", "ALT", " "])  # 重复 + 空 → 去重去空保序
    assert out["queried"] == ["LDL", "ALT"]
    assert out["count"] == 2


def test_batch_missing_indicator_zero_not_error(db):
    _seed(db, 4)
    out = _lab(db, 4, names=["LDL", "不存在的指标XYZ"])
    assert out["by_name"]["LDL"]["count"] == 1
    assert out["by_name"]["不存在的指标XYZ"]["count"] == 0
    assert "hint" in out["by_name"]["不存在的指标XYZ"]


def test_batch_cap_at_20_flags_truncated(db):
    _seed(db, 5)
    out = _lab(db, 5, names=[f"IND{i}" for i in range(25)])  # 25 > 20
    assert len(out["queried"]) == 20
    assert out["truncated"] is True


def test_batch_bp_name_bridges_to_blood_pressure(db):
    _seed(db, 6)
    out = _lab(db, 6, names=["LDL", "收缩压"])
    assert out["by_name"]["收缩压"].get("metric_key") == "blood_pressure"


def test_empty_names_list_falls_back_to_all(db):
    _seed(db, 7)
    out = _lab(db, 7, names=[])  # 空列表 → 走单指标(name 也空)= 返回全部
    assert "batch" not in out
    assert out["count"] >= 1  # 返回最近异常/全部项


def test_batch_names_stringified_json_recovered(db):
    """弱模型兜底:names 被吐成字符串化 JSON 数组也能识别为批量。"""
    _seed(db, 8)
    out = _lab(db, 8, names='["LDL","ALT"]')  # 字符串而非 list
    assert out["batch"] is True
    assert out["queried"] == ["LDL", "ALT"]


def test_batch_names_garbage_string_falls_back(db):
    """names 是不可解析的垃圾字符串 → fail-safe 落回单指标(不崩)。"""
    _seed(db, 9)
    out = _lab(db, 9, names="not a json array")
    assert "batch" not in out  # 落回单指标路径
