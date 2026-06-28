"""血常规(CBC)深度评估。钉:_history/趋势;红细胞系同向偏高(两项才触发、单项不触发、
性别感知)、中性-淋巴倒置;prompt blob 无数据返回空;R4 措辞(复查/评估,无诊断/处方/剂量)。"""
from datetime import date

from sqlalchemy import text

from app.services.chronic_trends import compute_trend
from app.services.blood_routine import (
    assess_blood_routine,
    blood_routine_prompt_blob,
    cbc_analyte_of,
    _history,
)


def _seed(db, user_id, name, value, d, unit=""):
    db.execute(text(
        "INSERT INTO medical_indicators (user_id, name, value, unit, record_date) "
        "VALUES (:u, :n, :v, :unit, :d)"
    ), {"u": user_id, "n": name, "v": value, "unit": unit, "d": d})
    db.commit()


# ── 纯趋势 / _history ──
def test_history_picks_matching_rows(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 150, date(2024, 1, 1), "g/L")
    _seed(db, user.id, "血红蛋白", 173, date(2026, 1, 1), "g/L")
    h = _history(db, user.id, "hemoglobin")
    assert [v for _, v in h] == [150.0, 173.0]  # 按 record_date 升序
    t = compute_trend(h)
    assert t is not None and t.direction == "rising"


# ── 锚定白名单 helper:positive control 无假阴 + 复合名全拒(防 under-alarm)──
def test_cbc_analyte_of_positive_controls():
    assert cbc_analyte_of("血红蛋白") == "hemoglobin"
    assert cbc_analyte_of("血红蛋白浓度") == "hemoglobin"
    assert cbc_analyte_of("HGB") == "hemoglobin"
    assert cbc_analyte_of("血红蛋白测定") == "hemoglobin"   # 良性后缀仍匹配
    assert cbc_analyte_of("血红蛋白(g/L)") == "hemoglobin"  # 单位括号被剥
    assert cbc_analyte_of("血小板") == "platelet"
    assert cbc_analyte_of("血小板计数") == "platelet"
    assert cbc_analyte_of("PLT") == "platelet"
    assert cbc_analyte_of("白细胞") == "wbc"
    assert cbc_analyte_of("白细胞计数") == "wbc"
    assert cbc_analyte_of("WBC") == "wbc"


def test_cbc_analyte_of_rejects_compound_names():
    # 这些都含规范名子串, 但带额外 token → 锚定 ^...$ 失配 → None (绝不当成 feeder)
    for n in (
        "网织红细胞血红蛋白含量", "还原血红蛋白", "血红蛋白A2", "胎儿血红蛋白", "血红蛋白电泳",
        "糖化血红蛋白", "糖化血红蛋白A1c",
        "平均血小板体积", "血小板分布宽度", "大血小板比率", "血小板压积",
        "白细胞酯酶", "尿白细胞", "白细胞介素6",
        "红细胞", "红细胞平均体积", "红细胞分布宽度",
    ):
        assert cbc_analyte_of(n) is None, f"{n} 不应被当成 CBC feeder"


# ── ADVERSARIAL: blood_routine 抗「残余」子串污染 (黑名单漏的复合名) ──
def test_hgb_excludes_reticulocyte_a2_hba1c_mch(client, db):
    """残余 under-alarm: 网织红细胞血红蛋白含量(33)/血红蛋白A2(2.5)/还原血红蛋白 等
    黑名单漏的复合名, record_date 更晚。锚定白名单后 HGB 必须仍是 173。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    uid = user.id
    _seed(db, uid, "血红蛋白", 150, date(2024, 1, 1), "g/L")     # 真 HGB
    _seed(db, uid, "血红蛋白", 173, date(2026, 1, 1), "g/L")     # 真 HGB latest
    _seed(db, uid, "网织红细胞血红蛋白含量", 33, date(2026, 3, 1), "pg")  # 残余污染(更晚)
    _seed(db, uid, "还原血红蛋白", 50, date(2026, 4, 1), "g/L")          # 残余污染(更晚)
    _seed(db, uid, "血红蛋白A2", 2.5, date(2026, 5, 1), "%")             # 残余污染(最晚)
    _seed(db, uid, "糖化血红蛋白", 5.4, date(2026, 6, 1), "%")           # HbA1c(最最晚)
    _seed(db, uid, "平均血红蛋白量", 30.5, date(2026, 7, 1), "pg")        # MCH(最最最晚)

    a = assess_blood_routine(db, uid, sex="男")
    assert a["hgb_latest"] == 173.0, f"HGB 被残余复合名污染: {a['hgb_latest']}"
    assert a["trends"]["hgb"]["n"] == 2
    assert a["trends"]["hgb"]["last_value"] == 173.0


def test_red_cell_elevation_still_fires_with_founder_values(client, db):
    """founder 真值 HGB173/HCT54 + 一堆残余复合名污染源(更晚)→ red_cell_elevation 仍触发。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    uid = user.id
    _seed(db, uid, "血红蛋白", 173, date(2026, 1, 1), "g/L")
    _seed(db, uid, "红细胞压积", 54, date(2026, 1, 1), "%")
    # 更晚的复合名污染源(若漏过白名单会把 HGB 压到 <170 → 静默不触发)
    _seed(db, uid, "网织红细胞血红蛋白含量", 33, date(2026, 5, 1), "pg")
    _seed(db, uid, "血红蛋白A2", 2.5, date(2026, 6, 1), "%")
    a = assess_blood_routine(db, uid, sex="男")
    assert "red_cell_elevation" in {f["code"] for f in a["flags"]}, "残余污染压制了安全 flag"


def test_platelet_excludes_mpv_pdw_plcr(client, db):
    """血小板: 裸「血小板」会吞 平均血小板体积(MPV)/血小板分布宽度(PDW)/大血小板比率(P-LCR)。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    uid = user.id
    _seed(db, uid, "血小板计数", 230, date(2026, 1, 1), "10^9/L")   # 真 PLT
    _seed(db, uid, "平均血小板体积", 10.5, date(2026, 3, 1), "fL")   # MPV(更晚)
    _seed(db, uid, "血小板分布宽度", 16, date(2026, 4, 1), "%")      # PDW(更晚)
    _seed(db, uid, "大血小板比率", 30, date(2026, 5, 1), "%")        # P-LCR(最晚)

    a = assess_blood_routine(db, uid, sex="男")
    assert a["plt_latest"] == 230.0, f"PLT 被 MPV/PDW/P-LCR 污染: {a['plt_latest']}"
    # 只有一条真 PLT(其余复合名被锚定拒绝)→ 不足 2 点, 趋势为 None(不臆测)
    assert a["trends"]["plt"] is None


def test_wbc_excludes_esterase_urine_interleukin(client, db):
    """白细胞: 裸「白细胞」会吞 白细胞酯酶/尿白细胞/白细胞介素6。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    uid = user.id
    _seed(db, uid, "白细胞计数", 6.5, date(2026, 1, 1), "10^9/L")   # 真 WBC
    _seed(db, uid, "白细胞酯酶", 1, date(2026, 3, 1), "")           # 尿干化学(更晚)
    _seed(db, uid, "尿白细胞", 25, date(2026, 4, 1), "/uL")         # 尿沉渣(更晚)
    _seed(db, uid, "白细胞介素6", 8.2, date(2026, 5, 1), "pg/mL")   # IL-6(最晚)

    a = assess_blood_routine(db, uid, sex="男")
    assert a["wbc_latest"] == 6.5, f"WBC 被 酯酶/尿白细胞/IL-6 污染: {a['wbc_latest']}"


def test_rbc_does_not_grab_hct_mcv_rdw(client, db):
    """RBC 不吞 红细胞压积/平均红细胞体积(MCV)/红细胞分布宽度(RDW)。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    uid = user.id
    _seed(db, uid, "红细胞计数", 5.8, date(2026, 1, 1), "10^12/L")  # 真 RBC
    _seed(db, uid, "红细胞压积", 54, date(2026, 3, 1), "%")          # HCT 污染(更晚)
    _seed(db, uid, "平均红细胞体积", 92, date(2026, 4, 1), "fL")     # MCV 污染(更晚)
    _seed(db, uid, "红细胞分布宽度", 13, date(2026, 5, 1), "%")      # RDW 污染(最晚)

    a = assess_blood_routine(db, uid, sex="男")
    assert a["rbc_latest"] == 5.8, f"RBC 被污染: {a['rbc_latest']}"
    # HCT 走自己专属 pattern,应正确取到 54(不被 RBC 抢)
    assert a["hct_latest"] == 54.0


# ── 无数据 ──
def test_no_data(db):
    a = assess_blood_routine(db, 999, sex="男")
    assert a["available"] is False


def test_prompt_blob_empty_without_data(db):
    assert blood_routine_prompt_blob(db, 999, sex="男") == ""


# ── 红细胞系整体偏高:两项同向才触发 ──
def test_red_cell_elevation_fires_when_both_high_male(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 173, date(2026, 1, 1), "g/L")    # > 170 男
    _seed(db, user.id, "红细胞压积", 54, date(2026, 1, 1), "%")     # > 50 男
    a = assess_blood_routine(db, user.id, sex="男")
    assert a["available"] is True
    codes = {f["code"] for f in a["flags"]}
    assert "red_cell_elevation" in codes


def test_red_cell_elevation_not_fired_when_only_hgb_high(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 173, date(2026, 1, 1), "g/L")    # > 170
    _seed(db, user.id, "红细胞压积", 46, date(2026, 1, 1), "%")     # < 50 → 不佐证
    a = assess_blood_routine(db, user.id, sex="男")
    codes = {f["code"] for f in a["flags"]}
    assert "red_cell_elevation" not in codes


def test_red_cell_elevation_not_fired_when_only_hct_high(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 160, date(2026, 1, 1), "g/L")    # < 170
    _seed(db, user.id, "红细胞压积", 54, date(2026, 1, 1), "%")     # > 50
    a = assess_blood_routine(db, user.id, sex="男")
    codes = {f["code"] for f in a["flags"]}
    assert "red_cell_elevation" not in codes


def test_red_cell_elevation_sex_aware_female_lower_threshold(client, db):
    """女性阈值更低(HGB>150 & HCT>45)→ 男性不触发的值在女性触发。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 158, date(2026, 1, 1), "g/L")    # >150 女, <170 男
    _seed(db, user.id, "红细胞压积", 47, date(2026, 1, 1), "%")     # >45 女, <50 男
    a_female = assess_blood_routine(db, user.id, sex="女")
    assert "red_cell_elevation" in {f["code"] for f in a_female["flags"]}
    a_male = assess_blood_routine(db, user.id, sex="男")
    assert "red_cell_elevation" not in {f["code"] for f in a_male["flags"]}


def test_unknown_sex_uses_male_conservative_threshold(client, db):
    """性别未知 → 男性(更高)阈值,保守少报:女性会触发的临界值在 None 下不触发。"""
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 158, date(2026, 1, 1), "g/L")
    _seed(db, user.id, "红细胞压积", 47, date(2026, 1, 1), "%")
    a = assess_blood_routine(db, user.id, sex=None)
    assert "red_cell_elevation" not in {f["code"] for f in a["flags"]}


# ── 中性/淋巴比例倒置 ──
def test_neutrophil_lymphocyte_inversion(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "中性粒细胞百分比", 42, date(2026, 1, 1), "%")  # < 50
    _seed(db, user.id, "淋巴细胞百分比", 48, date(2026, 1, 1), "%")    # > 40
    a = assess_blood_routine(db, user.id, sex="男")
    assert "neutrophil_lymphocyte_inversion" in {f["code"] for f in a["flags"]}


def test_inversion_not_fired_when_within_range(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "中性粒细胞百分比", 60, date(2026, 1, 1), "%")  # 正常
    _seed(db, user.id, "淋巴细胞百分比", 30, date(2026, 1, 1), "%")
    a = assess_blood_routine(db, user.id, sex="男")
    assert "neutrophil_lymphocyte_inversion" not in {f["code"] for f in a["flags"]}


# ── ADVERSARIAL: collector 锚定白名单 —— 残余复合名(更晚)不得污染 feeder 字段 ──
def test_collector_cbc_anchored_no_conflation(client, db):
    """fetch_latest_labs 锚定白名单:晚于真值的复合名(网织血红蛋白/A2/MCH/MCHC/HbA1c +
    MPV/PDW/P-LCR + 白细胞酯酶/尿白细胞)都不得污染 hemoglobin/platelet/wbc/rbc。
    旧黑名单会漏网织/A2/MPV/酯酶 → twin.labs.hemoglobin 变 33/2.5 → red_cell 静默不触发。"""
    from tests.conftest import create_authenticated_user
    from app.twin._collectors import fetch_latest_labs
    from app.twin.schema import LabsContext
    user, _ = create_authenticated_user(db)
    uid = user.id
    # 真值(早)
    _seed(db, uid, "血红蛋白", 173, date(2026, 1, 1), "g/L")
    _seed(db, uid, "红细胞压积", 54, date(2026, 1, 1), "%")
    _seed(db, uid, "红细胞计数", 5.8, date(2026, 1, 1), "10^12/L")
    _seed(db, uid, "血小板计数", 230, date(2026, 1, 1), "10^9/L")
    _seed(db, uid, "白细胞计数", 6.5, date(2026, 1, 1), "10^9/L")
    _seed(db, uid, "中性粒细胞百分比", 42, date(2026, 1, 1), "%")
    _seed(db, uid, "淋巴细胞百分比", 48, date(2026, 1, 1), "%")
    # 真 MCH/MCHC(早) —— 也要被正确归到自己字段
    _seed(db, uid, "平均血红蛋白量", 30.5, date(2026, 1, 1), "pg")
    _seed(db, uid, "平均血红蛋白浓度", 340, date(2026, 1, 1), "g/L")
    # 残余复合名污染源(全部更晚 —— 若漏过白名单会因 record_date desc 抢占 feeder)
    _seed(db, uid, "网织红细胞血红蛋白含量", 33, date(2026, 3, 1), "pg")
    _seed(db, uid, "血红蛋白A2", 2.5, date(2026, 4, 1), "%")
    _seed(db, uid, "糖化血红蛋白A1c", 5.4, date(2026, 5, 1), "%")
    _seed(db, uid, "平均血小板体积", 10.5, date(2026, 3, 1), "fL")
    _seed(db, uid, "血小板分布宽度", 16, date(2026, 4, 1), "%")
    _seed(db, uid, "大血小板比率", 30, date(2026, 5, 1), "%")
    _seed(db, uid, "白细胞酯酶", 1, date(2026, 3, 1), "")
    _seed(db, uid, "尿白细胞", 25, date(2026, 4, 1), "/uL")
    _seed(db, uid, "白细胞介素6", 8.2, date(2026, 5, 1), "pg/mL")

    out = fetch_latest_labs(db, uid)
    assert out.get("hemoglobin") == 173.0, f"HGB 被残余复合名污染: {out.get('hemoglobin')}"
    assert out.get("hematocrit") == 54.0
    assert out.get("rbc") == 5.8
    assert out.get("platelet") == 230.0, f"PLT 被 MPV/PDW/P-LCR 污染: {out.get('platelet')}"
    assert out.get("wbc") == 6.5, f"WBC 被 酯酶/尿白细胞/IL-6 污染: {out.get('wbc')}"
    assert out.get("neutrophil_pct") == 42.0
    assert out.get("lymphocyte_pct") == 48.0
    assert out.get("mch") == 30.5
    assert out.get("mchc") == 340.0

    # mirror builder._fill_collectors 映射循环 —— 落到正确字段且互不串
    L = LabsContext()
    for key, val in out.items():
        if hasattr(L, key) and getattr(L, key, None) is None:
            setattr(L, key, val)
    assert (L.hemoglobin, L.hematocrit, L.rbc, L.platelet, L.wbc) == (173.0, 54.0, 5.8, 230.0, 6.5)
    assert (L.mch, L.mchc, L.neutrophil_pct) == (30.5, 340.0, 42.0)
    assert L.hemoglobin != L.mch and L.hemoglobin != L.mchc and L.mch != L.mchc


# ── R4 安全措辞:不出现诊断/处方/剂量祈使,出现复查/评估 ──
def test_r4_wording(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _seed(db, user.id, "血红蛋白", 173, date(2026, 1, 1), "g/L")
    _seed(db, user.id, "红细胞压积", 54, date(2026, 1, 1), "%")
    blob = blood_routine_prompt_blob(db, user.id, sex="男")
    assert blob  # 有数据 + flag → 非空
    assert "非诊断" in blob
    text_all = blob + " ".join(f["message"] for f in assess_blood_routine(db, user.id, sex="男")["flags"])
    # 不下诊断标签 / 不开处方 / 不给剂量
    for forbidden in ("确诊", "诊断为", "处方", "服用", "mg", "毫克", "每日", "剂量"):
        assert forbidden not in text_all, f"R4 违规: 出现 '{forbidden}'"
    # 应是复查 / 评估框架
    assert "复查" in text_all and "评估" in text_all
