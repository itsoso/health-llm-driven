"""原研药精选表查询。钉:通用名/品牌/含规格都能命中;表外返回 None(不猜);端点鉴权。"""
from app.services.originator_drugs import find_originator


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
    assert find_originator("阿奇霉素") is None  # 未收录 → None,而非乱答


def test_endpoint_requires_auth(client):
    r = client.post("/api/v1/prescriptions/recognize")
    assert r.status_code in (401, 403)
    r2 = client.get("/api/v1/prescriptions/originator?name=阿托伐他汀")
    assert r2.status_code in (401, 403)
