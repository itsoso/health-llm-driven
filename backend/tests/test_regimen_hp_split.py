"""用药方案按 Hp 状态分流(锚点用户活检 HP- 暴露的真实缺陷)。

钉:① 新增 Hp 阴性 PPI 愈合模板(无根除抗生素)② 根除模板标 positive
③ templates_for_hp_status 正确分流 ④ API hp_status 过滤 ⑤ 愈合模板可实例化。
"""
from app.services import regimen_templates as rt


def test_ppi_healing_template_exists_no_antibiotics():
    t = rt.get_template("gu_ppi_healing_8w")
    assert t is not None
    assert t["hp_status"] == "negative"
    names = rt.phase_med_names(t["phases"], 0)
    joined = " ".join(names)
    assert "PPI" in joined
    assert "阿莫西林" not in joined and "克拉霉素" not in joined  # Hp- 不上根除抗生素


def test_eradication_templates_tagged_positive():
    for tid in ("hp_bismuth_quad_14d", "hp_triple_14d"):
        assert rt.get_template(tid)["hp_status"] == "positive"


def test_templates_for_hp_status_routing():
    neg = {t["template_id"] for t in rt.templates_for_hp_status("negative")}
    pos = {t["template_id"] for t in rt.templates_for_hp_status("positive")}
    allt = {t["template_id"] for t in rt.templates_for_hp_status(None)}
    assert neg == {"gu_ppi_healing_8w"}
    assert "hp_bismuth_quad_14d" in pos and "gu_ppi_healing_8w" not in pos
    assert allt >= neg | pos          # None = 全部


def test_api_filters_by_hp_status(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.get("/api/v1/medication/regimen-templates?hp_status=negative", headers=h)
    assert r.status_code == 200, r.text
    tids = {t["template_id"] for t in r.json()["templates"]}
    assert tids == {"gu_ppi_healing_8w"}
    # 全部
    r2 = client.get("/api/v1/medication/regimen-templates", headers=h)
    assert len({t["template_id"] for t in r2.json()["templates"]}) >= 3


def test_healing_template_instantiates_no_critical(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/medication/regimens", headers=h,
                    json={"template_id": "gu_ppi_healing_8w"})
    assert r.status_code == 200, r.text   # 纯 PPI,无撞药 CRITICAL
    assert r.json()["blocked"] is False
    assert r.json()["regimen"]["current_phase_name"] == "愈合期"
