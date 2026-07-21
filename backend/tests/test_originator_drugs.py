"""原研药精选表查询。钉:通用名/品牌/含规格都能命中;表外返回 None(不猜);端点鉴权。"""
import operator

import pytest

from app.services import originator_drugs
from app.services.originator_drugs import find_originator


def test_medication_aliases_canonicalize_generic_and_brand_names():
    aliases = originator_drugs.medication_aliases()

    assert aliases["替普瑞酮"] == "替普瑞酮"
    assert aliases["施维舒"] == "替普瑞酮"
    assert aliases["伊托必利"] == "伊托必利"
    assert aliases["盐酸伊托必利"] == "伊托必利"
    assert aliases["加斯清"] == "伊托必利"
    assert aliases["盐酸西替利嗪"] == "西替利嗪"


def test_medication_aliases_are_read_only():
    aliases = originator_drugs.medication_aliases()

    with pytest.raises(TypeError):
        operator.setitem(aliases, "伪造品牌", "替普瑞酮")


def test_lookup_by_generic_name():
    o = find_originator("阿托伐他汀")
    assert o is not None and o["brand"] == "立普妥" and "辉瑞" in o["manufacturer"]


def test_lookup_by_brand_alias():
    assert find_originator("立普妥")["generic"] == "阿托伐他汀"
    assert find_originator("Lipitor")["brand"] == "立普妥"  # 英文别名


def test_lookup_strips_spec_and_dosage_form():
    # 含钠/肠溶胶囊/规格 → 仍命中泮托拉唑
    o = find_originator("泮托拉唑钠肠溶胶囊 40mg")
    assert o is not None and o["generic"] == "泮托拉唑"


def test_lookup_brand_in_name():
    # 用户处方上的品牌名(泮立苏)→ 映射到泮托拉唑原研
    assert find_originator("泮立苏")["generic"] == "泮托拉唑"
    # 沃克本身就是伏诺拉生的原研
    o = find_originator("富马酸伏诺拉生片 20mg")
    assert o["brand"] == "沃克" and "武田" in o["manufacturer"]


def test_unknown_drug_returns_none_not_guess():
    # 表外的药必须返回 None,不能编
    assert find_originator("某不存在的中药复方颗粒") is None
    assert find_originator("") is None
    assert find_originator("匹伐他汀") is None  # 故意未收录(原研中文名存疑)→ None,而非乱答


def test_expanded_table_entries():
    # 扩表后的高频条目(含用户在用药)
    assert find_originator("阿奇霉素")["brand"] == "希舒美"
    assert find_originator("盐酸西替利嗪片 10mg")["brand"] == "仙特明"
    assert find_originator("糠酸莫米松鼻喷雾剂")["brand"] == "内舒拿"
    assert find_originator("伊托必利")["brand"] == "加斯清"
    assert find_originator("谐畅动力")["generic"] == "盐酸伊托必利"  # 国产品牌 → 原研
    assert find_originator("替尔泊肽")["brand"] == "穆峰达"
    o = find_originator("硫酸氢氯吡格雷片 75mg")
    assert o is not None and o["brand"] == "波立维"
    assert find_originator("优甲乐")["generic"] == "左甲状腺素钠"
    assert find_originator("montelukast")["brand"] == "顺尔宁"


def test_endpoint_requires_auth(client):
    r = client.post("/api/v1/prescriptions/recognize")
    assert r.status_code in (401, 403)
    r2 = client.get("/api/v1/prescriptions/originator?name=阿托伐他汀")
    assert r2.status_code in (401, 403)
