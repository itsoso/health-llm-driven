"""凝血酶原时间 (PT) 与中性粒细胞绝对值 (NEUT) 纳入 biomarker 注册表。

2026-09-30: 体检里偏低的 PT / 中性粒细胞从未进入归一化层 (注册表外)。同名「中性粒细胞」既有
10E9/L 绝对值也有 % 百分比 —— 只收绝对值; 凝血酶时间 / APTT / INR / 活动度 / 对照值 / 嗜酸嗜碱都不是。
数值均为合成值。
"""
import pytest

from app.biomarkers.definitions import resolve_code
from app.biomarkers.normalize import normalize_observation
from tests.test_medical_exam_biomarker_ingest import _confirm, _observations
from tests.test_medical_exams import _create_user


@pytest.mark.parametrize("name", ["凝血酶原时间", "PT", "PT(秒)", "凝血酶原时间(PT)", "Prothrombin time"])
def test_prothrombin_time_names_resolve(name):
    assert resolve_code(name) == "PT"


@pytest.mark.parametrize("name", [
    "凝血酶时间", "TT", "活化部分凝血活酶时间", "APTT", "APTT对照", "PT对照", "凝血酶原时间对照",
    "PT-INR", "国际标准化比值", "INR", "凝血酶原活动度", "PTA", "凝血酶原时间比值", "异常凝血酶原",
    "PTH", "甲状旁腺激素",
])
def test_non_prothrombin_time_names_rejected(name):
    assert resolve_code(name) != "PT"


@pytest.mark.parametrize("name", [
    "中性粒细胞", "中性粒细胞绝对值", "中性粒细胞计数", "中性粒细胞数", "NEUT#", "NEUT", "ANC",
])
def test_neutrophil_count_names_resolve(name):
    assert resolve_code(name) == "NEUT"


@pytest.mark.parametrize("name", [
    "中性粒细胞(%)", "中性粒细胞%", "中性粒细胞百分比", "中性粒细胞比例", "中性粒细胞比率", "NEUT%",
    "中性粒细胞/淋巴细胞比值", "嗜酸性粒细胞", "嗜碱性粒细胞", "嗜酸性粒细胞绝对值", "抗中性粒细胞胞浆抗体",
    "ANCA", "中性粒细胞碱性磷酸酶", "中性粒细胞明胶酶相关脂质运载蛋白", "杆状核中性粒细胞", "分叶核中性粒细胞",
    "脑脊液中性粒细胞",
])
def test_non_neutrophil_count_names_rejected(name):
    assert resolve_code(name) != "NEUT"


@pytest.mark.parametrize("unit", ["10E9/L", "10^9/L", "×10^9/L", "x10^9/L", "10*9/L", "×10⁹/L", None])
def test_neutrophil_count_units(unit):
    obs = normalize_observation("中性粒细胞", 1.6, unit)
    assert obs is not None and obs.code == "NEUT"
    assert obs.normalized_value == 1.6 and obs.flag == "low" and obs.is_risk is True


def test_neutrophil_per_microlitre_converts():
    obs = normalize_observation("中性粒细胞绝对值", 1600, "/μL")
    assert obs is not None and obs.normalized_value == 1.6


def test_neutrophil_percentage_under_bare_name_rejected():
    """同名「中性粒细胞」的百分比: 单位 % 是异量纲; 缺单位时 55 这种量级也不是绝对值。"""
    assert normalize_observation("中性粒细胞", 55, "%") is None
    assert normalize_observation("中性粒细胞", 55, None) is None


@pytest.mark.parametrize("unit", ["秒", "s", "sec", None])
def test_prothrombin_time_units(unit):
    obs = normalize_observation("凝血酶原时间", 15.2, unit)
    assert obs is not None and obs.code == "PT"
    assert obs.normalized_value == 15.2 and obs.flag == "high" and obs.is_risk is True


def test_prothrombin_time_rejects_other_dimension():
    assert normalize_observation("凝血酶原时间", 95, "%") is None  # 活动度串项


def test_confirm_import_ingests_pt_and_neutrophil_count_only(client, db):
    user, headers = _create_user(db)
    items = [
        {"item_name": "凝血酶原时间", "value": 12.4, "unit": "秒", "is_abnormal": "normal"},
        {"item_name": "凝血酶时间", "value": 17.1, "unit": "秒", "is_abnormal": "normal"},
        {"item_name": "活化部分凝血活酶时间", "value": 30.2, "unit": "秒", "is_abnormal": "normal"},
        {"item_name": "中性粒细胞", "value": 1.6, "unit": "10E9/L", "is_abnormal": "low"},
        {"item_name": "中性粒细胞(%)", "value": 41.0, "unit": "%", "is_abnormal": "normal"},
        {"item_name": "嗜酸性粒细胞", "value": 0.2, "unit": "10E9/L", "is_abnormal": "normal"},
    ]

    resp = _confirm(client, headers, items)

    assert resp.status_code == 200, resp.text
    assert _observations(db, user.id) == {("PT", 12.4), ("NEUT", 1.6)}
