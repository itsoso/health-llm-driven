"""Safety 化验输入完整性 + 确定性回归 (2026-09-30 incident)。

背景: fetch_medical_exam_abnormal 曾 LIMIT 10 且只按 record_date desc 排序(无 tie-breaker)。
一次 112 项体检 + 图片上传落在同一 record_date → 进 Safety 的 10 条异常是 PostgreSQL 任意挑的,
eGFR<60 / ALT·AST 被截掉即漏报。kidney_function_decline 还没有 twin.labs.egfr 兜底。

不变量(加层不减层): 输入从「任意 10 条子集」扩成「完整最新检查」后, 任何子集上会触发的告警,
在完整集合上必须仍触发且严重度不降(规则须对同次检查的超集单调)。
"""

import logging
import random
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.schema import Severity
from app.twin.schema import HealthTwin, LabsContext, TwinMeta

LATEST = date.today() - timedelta(days=3)
OLDER = LATEST - timedelta(days=60)


def _user(db):
    from app.models.user import User

    user = User(
        username=f"lw_{uuid.uuid4().hex[:6]}", email=f"lw_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="lab window", birth_date=date(1980, 1, 1),
        gender="男", is_active=True, is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add(db, user_id, name, value, *, day=LATEST, abnormal=True):
    from app.models.family_health import MedicalIndicator

    db.add(MedicalIndicator(
        user_id=user_id, name=name, value=value, record_date=day,
        is_abnormal=abnormal, source="pdf_import",
    ))
    db.flush()


def _fillers(db, user_id, prefix, n, day=LATEST):
    for i in range(n):
        _add(db, user_id, f"{prefix}异常项{i:02d}", 1.0 + i, day=day)


def _twin(flagged, **labs):
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    twin.labs = LabsContext(flagged_abnormal=flagged, **labs)
    return twin


def _alerts(twin):
    return {a.rule_id: a for a in evaluate_safety(twin).alerts}


# ─────────────────────── collector: 完整 + 确定 ───────────────────────


class TestAbnormalWindowCollector:
    def test_latest_exam_returned_complete_and_ordered(self, db):
        """最新日 27 条异常全部返回, 按 (record_date desc, id desc), 关键项不在前 10 也在。"""
        from app.twin._collectors import fetch_medical_exam_abnormal

        user = _user(db)
        _fillers(db, user.id, "A", 12)
        _add(db, user.id, "估算肾小球滤过率", 45.0)
        _add(db, user.id, "谷丙转氨酶", 250.0)
        _add(db, user.id, "谷草转氨酶", 210.0)
        _fillers(db, user.id, "B", 12)
        _fillers(db, user.id, "OLD", 5, day=OLDER)
        db.commit()

        items, meta = fetch_medical_exam_abnormal(db, user.id)
        names = [it["item_name"] for it in items]

        assert len(items) == 27  # 最新日完整; 最新日已 ≥10 条 → 不混入更旧日期
        assert {it["exam_date"] for it in items} == {LATEST}
        assert {"估算肾小球滤过率", "谷丙转氨酶", "谷草转氨酶"} <= set(names)
        assert names.index("谷丙转氨酶") >= 10  # 确实不在确定性顺序的前 10 条
        assert names[0] == "B异常项11" and names[-1] == "A异常项00"  # id desc
        assert meta["exam_date"] == LATEST
        assert fetch_medical_exam_abnormal(db, user.id)[0] == items  # 重复调用逐项一致

    def test_short_latest_exam_keeps_whole_older_exam(self, db):
        """最新日只有 3 条 → 旧 LIMIT 10 会跨进上一次检查并任意截断;
        新窗口把被触及的上一次检查整日纳入 (⊇ 任何旧截断结果)。"""
        from app.twin._collectors import fetch_medical_exam_abnormal

        user = _user(db)
        _fillers(db, user.id, "NEW", 3)
        _fillers(db, user.id, "PREV", 15, day=OLDER)
        _fillers(db, user.id, "ANCIENT", 4, day=OLDER - timedelta(days=90))
        db.commit()

        items, _ = fetch_medical_exam_abnormal(db, user.id)
        dates = [it["exam_date"] for it in items]
        assert len(items) == 18
        assert dates == sorted(dates, reverse=True)
        assert OLDER - timedelta(days=90) not in dates  # 未被前 10 条触及的日期不纳入

    def test_hard_cap_truncates_loudly(self, db, monkeypatch, caplog):
        from app.twin import _collectors

        user = _user(db)
        _fillers(db, user.id, "X", 30)
        db.commit()
        monkeypatch.setattr(_collectors, "ABNORMAL_WINDOW_MAX_ROWS", 20)

        with caplog.at_level(logging.WARNING):
            items, _ = _collectors.fetch_medical_exam_abnormal(db, user.id)
        assert len(items) == 20
        assert [it["item_name"] for it in items][0] == "X异常项29"  # 截断也确定: 保留最新 id
        assert any("truncated" in r.getMessage() for r in caplog.records)


# ─────────────────────── 端到端: DB → Twin → Safety ───────────────────


class TestLatestExamEndToEnd:
    def test_egfr_and_liver_beyond_first_ten_still_alert(self, db):
        from app.twin import build_twin

        user = _user(db)
        _fillers(db, user.id, "A", 12)
        _add(db, user.id, "估算肾小球滤过率", 45.0)
        _add(db, user.id, "谷丙转氨酶", 250.0)
        _add(db, user.id, "谷草转氨酶", 210.0)
        _fillers(db, user.id, "B", 12)
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        alerts = _alerts(twin)
        assert alerts["labs.egfr_decline"].severity == Severity.MEDIUM
        assert alerts["labs.liver_enzyme_pattern"].severity == Severity.CRITICAL

    def test_unflagged_low_egfr_alerts_via_canonical_value(self, db):
        """化验单没标异常的 eGFR 45(实验室不标/OCR 丢标) → twin.labs.egfr 兜底告警。"""
        from app.twin import build_twin

        user = _user(db)
        _fillers(db, user.id, "A", 12)
        _add(db, user.id, "估算肾小球滤过率", 45.0, abnormal=False)
        db.commit()

        twin = build_twin(db, user_id=user.id, use_cache=False)
        assert twin.labs.egfr == 45.0
        assert "labs.egfr_decline" in _alerts(twin)


# ─────────────────────── kidney: canonical 兜底 ─────────────────────


class TestKidneyCanonicalFallback:
    def test_fallback_when_no_flagged_egfr(self):
        alert = _alerts(_twin([], egfr=25.0))["labs.egfr_decline"]
        assert alert.severity == Severity.HIGH
        assert alert.data_citation["egfr"] == 25.0

    def test_fallback_when_flagged_egfr_not_numeric(self):
        flagged = [{"item_name": "eGFR", "value": "见备注", "exam_date": LATEST}]
        assert "labs.egfr_decline" in _alerts(_twin(flagged, egfr=50.0))

    def test_canonical_lower_than_flagged_wins(self):
        """flagged eGFR 85(按 >90 参考标异常) 但最新 canonical 50 → 取更差值, 不被遮蔽。"""
        flagged = [{"item_name": "eGFR", "value": 85, "exam_date": LATEST}]
        assert _alerts(_twin(flagged, egfr=50.0))["labs.egfr_decline"].data_citation["egfr"] == 50.0

    def test_normal_canonical_no_alert(self):
        assert "labs.egfr_decline" not in _alerts(_twin([], egfr=92.0))


# ─────────────────────── 单调性 + 顺序无关 ───────────────────────────


def _realistic_latest_exam():
    """同一天一次大体检的异常项(含会做子串遮蔽的比值/衍生项), 按 id asc 列出。"""
    rows = [
        ("谷丙转氨酶(ALT)", 250), ("谷草转氨酶(AST)", 210), ("AST/ALT", 0.84),
        ("γ-谷氨酰转移酶(GGT)", 180), ("低密度脂蛋白胆固醇(LDL-C)", 5.2),
        ("LDL-C/HDL-C", 3.5), ("估算肾小球滤过率(eGFR)", 42), ("eGFR(MDRD)", 58),
        ("尿酸", 560), ("尿酸/肌酐", 0.4), ("淋巴细胞百分比", 46), ("异型淋巴细胞百分比", 3),
        ("中性粒细胞百分比", 44), ("糖化血红蛋白A1c", 7.4), ("总胆红素", 25),
        ("甘油三酯", 2.6), ("癌胚抗原", 6.1), ("血小板压积", 0.31),
    ]
    items = [
        {"item_name": n, "value": v, "unit": None, "exam_date": LATEST, "_id": i}
        for i, (n, v) in enumerate(rows, start=1)
    ]
    return sorted(items, key=lambda it: it["_id"], reverse=True)  # collector 顺序: id desc


def _family(rule_id):
    return "labs.hba1c" if rule_id.startswith("labs.hba1c") else rule_id


def _severity_by_family(flagged):
    out = {}
    for a in evaluate_safety(_twin(flagged)).alerts:
        fam = _family(a.rule_id)
        out[fam] = max(out.get(fam, Severity.INFO), a.severity)
    return out


class TestSupersetMonotonic:
    def test_any_ten_item_subset_never_outranks_complete_exam(self):
        full = _realistic_latest_exam()
        full_sev = _severity_by_family(full)
        rng = random.Random(20260930)
        for _ in range(400):
            subset = sorted(rng.sample(full, 10), key=lambda it: it["_id"], reverse=True)
            for fam, sev in _severity_by_family(subset).items():
                assert fam in full_sev, f"{fam} fires on a 10-item subset but not on the full exam"
                assert full_sev[fam] >= sev, f"{fam} downgraded {sev} → {full_sev[fam]}"

    def test_complete_exam_picks_real_analytes_not_ratios(self):
        alerts = _alerts(_twin(_realistic_latest_exam()))
        assert alerts["labs.liver_enzyme_pattern"].severity == Severity.CRITICAL
        assert alerts["labs.ldl_high"].severity == Severity.HIGH
        assert alerts["labs.egfr_decline"].data_citation["egfr"] == 42
        assert alerts["labs.uric_acid_high"].data_citation["raw"] == 560

    def test_rule_outcomes_independent_of_list_order(self):
        full = _realistic_latest_exam()
        expected = {(a.rule_id, a.severity) for a in evaluate_safety(_twin(full)).alerts}
        rng = random.Random(7)
        for _ in range(50):
            shuffled = full[:]
            rng.shuffle(shuffled)
            got = {(a.rule_id, a.severity) for a in evaluate_safety(_twin(shuffled)).alerts}
            assert got == expected

    def test_older_exam_value_never_overrides_latest(self):
        """同指标跨两次检查: 取最新检查的值, 不拿旧的更差值升级(不因扩窗而误报陈旧数据)。"""
        flagged = [
            {"item_name": "低密度脂蛋白胆固醇", "value": 4.2, "exam_date": LATEST},
            {"item_name": "低密度脂蛋白胆固醇", "value": 5.6, "exam_date": OLDER},
        ]
        alert = _alerts(_twin(flagged))["labs.ldl_high"]
        assert alert.data_citation["ldl"] == 4.2 and alert.severity == Severity.MEDIUM


# ─────────────────────── prompt blob 仍有界 ───────────────────────────


def test_prompt_blob_abnormal_line_stays_bounded():
    from app.twin.formatter import twin_to_prompt_blob

    many = [{"item_name": f"异常指标{i:03d}", "value": i, "exam_date": LATEST} for i in range(200)]
    blob_many = twin_to_prompt_blob(_twin(many))
    blob_five = twin_to_prompt_blob(_twin(many[:5]))
    assert blob_many == blob_five  # 默认 max_abnormal=5: 200 条与 5 条产出完全一致
    line = next(ln for ln in blob_many.splitlines() if ln.startswith("异常项"))
    assert line.count(",") == 4
