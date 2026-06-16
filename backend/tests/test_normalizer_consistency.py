"""护栏: 两个 name→code 归一化器必须一致,防止"相似指标"在上传管线里串味。

仓库有两条归一化路径:
  - `exam_packages.normalize_item_name`  —— 体检导入 → medical_indicators 双写时用
  - `biomarkers.definitions.resolve_code` —— medical_indicators → biomarker_observations 时用
若两者对同一名字给出不同 canonical code,某条上传路径就会把指标归错(历史教训:
「糖化血红蛋白A1」总糖化被当标准 A1c、「血红蛋白」g/L 被当糖化)。本测试锁死二者
对易撞车指标的一致性 —— 任何一边漂移都会让 CI 红。
"""
import pytest

from app.services.exam_packages import normalize_item_name
from app.biomarkers.definitions import resolve_code, REGISTRY


# 易撞车分析物: 名字互为子串, 必须分流到各自 code
COLLISION_PRONE = {
    "糖化血红蛋白A1c": "glucose_hba1c",
    "糖化血红蛋白A1c测定": "glucose_hba1c",
    "糖化血红蛋白": "glucose_hba1c",
    "HbA1c": "glucose_hba1c",
    "糖化血红蛋白A1": "glucose_hba1_total",
    "HbA1": "glucose_hba1_total",
    "血红蛋白": "hemoglobin",
    "血色素": "hemoglobin",
    "Hb": "hemoglobin",
}


@pytest.mark.parametrize("name,expected", COLLISION_PRONE.items())
def test_both_normalizers_agree_on_collision_prone(name, expected):
    exam_code = normalize_item_name(name)[0]
    bio_code = resolve_code(name)
    assert exam_code == expected, f"exam normalize_item_name({name!r})={exam_code!r} != {expected!r}"
    assert bio_code == expected, f"biomarker resolve_code({name!r})={bio_code!r} != {expected!r}"


def test_three_analytes_are_distinct():
    """糖化A1 / 标准A1c / 血红蛋白 三者 code 互不相同(别再挤一起)。"""
    codes = {resolve_code("糖化血红蛋白A1"), resolve_code("糖化血红蛋白A1c"), resolve_code("血红蛋白")}
    assert codes == {"glucose_hba1_total", "glucose_hba1c", "hemoglobin"}


# 更广的回归: 这些名字两个归一化器都应识别且一致
BROAD = [
    "糖化血红蛋白A1c", "糖化血红蛋白A1", "糖化血红蛋白", "血红蛋白", "Hb", "HbA1c", "HbA1",
]


@pytest.mark.parametrize("name", BROAD)
def test_no_divergence_when_both_recognize(name):
    """当两边都给出落在 biomarker REGISTRY 的非空 code 时, 必须相等(漂移即红)。"""
    exam_code = normalize_item_name(name)[0]
    bio_code = resolve_code(name)
    if exam_code and bio_code and exam_code in REGISTRY:
        assert exam_code == bio_code, (
            f"两归一化器对 {name!r} 漂移: exam={exam_code!r} biomarker={bio_code!r}"
        )
