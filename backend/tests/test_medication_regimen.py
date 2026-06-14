"""用药自动驾驶 P1a:方案模板引擎 + 一键实例化 + 引入即 DDI 预检闸门。

钉:① 模板纯数据(深拷贝隔离)② 实例化建当前阶段药品(带时点+regimen_id)
③ DDI 闸门:引入克拉霉素 × 已有他汀 → 出 ddi 告警(HIGH,不阻断但带回)
④ CRITICAL(SSRI×MAOI)→ 422 阻断不写库 ⑤ override_safety 可强行录入。
"""
import pytest

from app.services import regimen_templates
from app.models.medication import Medication, MedicationRegimen


# ── 模板引擎(纯函数)────────────────────────────────────
def test_list_templates_has_hp():
    ids = {t["template_id"] for t in regimen_templates.list_templates()}
    assert "hp_bismuth_quad_14d" in ids
    assert "hp_triple_14d" in ids


def test_get_template_is_deepcopy():
    a = regimen_templates.get_template("hp_bismuth_quad_14d")
    a["phases"][0]["meds"][0]["dosage"] = "改了"
    b = regimen_templates.get_template("hp_bismuth_quad_14d")
    assert b["phases"][0]["meds"][0]["dosage"] != "改了"  # 没污染模块级常量
    assert regimen_templates.get_template("不存在") is None


def test_phase_med_names():
    tpl = regimen_templates.get_template("hp_bismuth_quad_14d")
    names = regimen_templates.phase_med_names(tpl["phases"], 0)
    assert any("克拉霉素" in n for n in names)
    assert any("阿莫西林" in n for n in names)
    assert regimen_templates.phase_med_names(tpl["phases"], 99) == []


# ── 实例化(API)──────────────────────────────────────
def test_instantiate_creates_phase0_meds_with_timing(client, auth_user_and_headers, db):
    user, h = auth_user_and_headers
    r = client.post("/api/v1/medication/regimens", headers=h,
                    json={"template_id": "hp_bismuth_quad_14d", "start_on": "2026-06-15"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["blocked"] is False
    reg = body["regimen"]
    assert reg["current_phase_name"] == "根除期"
    assert reg["expected_end_on"] == "2026-08-10"  # 2026-06-15 + (14+42) 天

    # 当前阶段 4 种药已建,带时点 + regimen_id
    meds = db.query(Medication).filter(Medication.regimen_id == reg["id"]).all()
    assert len(meds) == 4
    ppi = next(m for m in meds if "PPI" in m.name)
    assert ppi.timing_relation == "before_meal_30"
    amox = next(m for m in meds if "阿莫西林" in m.name)
    assert amox.timing_relation == "after_meal"
    # 愈合期(单 PPI)此刻不应建 —— 只实例化当前阶段;4 种里不含「times_per_day=1 的单独 PPI 愈合行」
    assert sum(1 for m in meds if "PPI" in m.name) == 1  # 根除期只有 1 个 PPI 条目


def test_disclaimer_returned(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.get("/api/v1/medication/regimen-templates", headers=h)
    assert r.status_code == 200
    assert "医生" in r.json()["disclaimer"]


# ── DDI 闸门 ────────────────────────────────────────
def _add_med(db, user_id, name):
    db.add(Medication(user_id=user_id, name=name, is_active=True, times_per_day=1))
    db.commit()


def test_ddi_gate_surfaces_statin_clarithromycin(client, auth_user_and_headers, db):
    user, h = auth_user_and_headers
    _add_med(db, user.id, "阿托伐他汀")  # 已在吃他汀
    r = client.post("/api/v1/medication/regimens", headers=h,
                    json={"template_id": "hp_bismuth_quad_14d"})  # 含克拉霉素(CYP3A4 抑制)
    assert r.status_code == 200, r.text  # HIGH 不阻断
    cats = {a["category"] for a in r.json()["safety_alerts"]}
    assert "ddi" in cats  # 他汀×克拉霉素 相互作用被检出并带回


def test_ddi_gate_blocks_critical(client, auth_user_and_headers, db):
    user, h = auth_user_and_headers
    _add_med(db, user.id, "舍曲林")  # 已在吃 SSRI
    # 自定义方案含 MAOI → SSRI×MAOI = CRITICAL
    phases = [{"name": "测试", "duration_days": 7, "meds": [
        {"name": "苯乙肼", "dosage": "15mg", "times_per_day": 1, "timing_relation": "after_meal"}
    ]}]
    r = client.post("/api/v1/medication/regimens", headers=h,
                    json={"phases": phases, "name": "撞药测试"})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["reason"] == "critical_drug_interaction"
    # 阻断 → 没写库
    assert db.query(MedicationRegimen).filter(MedicationRegimen.user_id == user.id).count() == 0


def test_override_safety_allows_critical(client, auth_user_and_headers, db):
    user, h = auth_user_and_headers
    _add_med(db, user.id, "舍曲林")
    phases = [{"name": "测试", "duration_days": 7, "meds": [
        {"name": "苯乙肼", "dosage": "15mg", "times_per_day": 1, "timing_relation": "after_meal"}
    ]}]
    r = client.post("/api/v1/medication/regimens", headers=h,
                    json={"phases": phases, "name": "知情强录", "override_safety": True})
    assert r.status_code == 200, r.text
    # 仍把 CRITICAL 告警带回(知情),但已写库
    assert any(a["severity"]["value"] == 4 for a in r.json()["safety_alerts"])
    assert db.query(MedicationRegimen).filter(MedicationRegimen.user_id == user.id).count() == 1
