"""health_query 化验维度 (medical_exam) 读 MedicalIndicator 表的回归测试.

P0: 之前 medical_exam 走原始 /medical-exams/me HTTP, 经 _api_get 截断成前 10 条 →
化验项查空/不全. 现改读归一化 MedicalIndicator 表 (与 Twin fetch_latest_labs 同源).
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.family_health import MedicalIndicator
from app.models.medical_exam import MedicalExam
from app.services.agent_executor import AgentExecutor


def _make_indicator(user_id, name, value, unit, record_date, **kw):
    return MedicalIndicator(
        user_id=user_id,
        name=name,
        name_en=kw.get("name_en"),
        value=value,
        unit=unit,
        record_date=record_date,
        is_abnormal=kw.get("is_abnormal", False),
        reference_low=kw.get("reference_low"),
        reference_high=kw.get("reference_high"),
    )


def _run(coro):
    return asyncio.run(coro)


def _exec(db, user_id, **args):
    ex = AgentExecutor(db)
    ex._current_user_id = user_id
    return _run(ex._exec_health_query("http://x", {}, {"dimension": "medical_exam", **args}))


def test_no_indicator_returns_indicator_list_with_latest(db):
    from datetime import timedelta
    uid = 1
    recent = date.today() - timedelta(days=30)
    db.add_all([
        _make_indicator(uid, "低密度脂蛋白", 3.8, "mmol/L", recent,
                        name_en="LDL", is_abnormal=True, reference_high=3.4),
        _make_indicator(uid, "同型半胱氨酸", 15.0, "umol/L", recent,
                        name_en="HCY", is_abnormal=True, reference_high=10.0),
        _make_indicator(uid, "空腹血糖", 5.2, "mmol/L", recent,
                        name_en="FBG"),
    ])
    db.commit()

    out = _exec(db, uid)  # 无 indicator
    assert "低密度脂蛋白" in out
    assert "同型半胱氨酸" in out
    assert "空腹血糖" in out
    assert "3 项化验指标" in out
    # 异常项被标注
    assert "偏高" in out


def test_no_indicator_takes_latest_per_indicator(db):
    from datetime import timedelta
    uid = 2
    today = date.today()
    db.add_all([
        _make_indicator(uid, "低密度脂蛋白", 4.0, "mmol/L", today - timedelta(days=300), name_en="LDL"),
        _make_indicator(uid, "低密度脂蛋白", 3.2, "mmol/L", today - timedelta(days=10), name_en="LDL"),
    ])
    db.commit()
    out = _exec(db, uid)
    # 只出现最新值 3.2, 不是旧值 4.0
    assert "3.2" in out
    assert "1 项化验指标" in out


def test_with_indicator_returns_time_series(db):
    from datetime import timedelta
    uid = 3
    today = date.today()
    db.add_all([
        _make_indicator(uid, "低密度脂蛋白", 4.0, "mmol/L", today - timedelta(days=300), name_en="LDL"),
        _make_indicator(uid, "低密度脂蛋白", 3.5, "mmol/L", today - timedelta(days=150), name_en="LDL"),
        _make_indicator(uid, "低密度脂蛋白", 3.2, "mmol/L", today - timedelta(days=10), name_en="LDL"),
        _make_indicator(uid, "空腹血糖", 5.2, "mmol/L", today - timedelta(days=10), name_en="FBG"),
    ])
    db.commit()
    ex = AgentExecutor(db)
    ex._current_user_id = uid
    out = _run(ex._exec_health_query("http://x", {}, {
        "dimension": "medical_exam", "indicator": "LDL",
    }))
    # 三条 LDL 时间序列都在, 不被截断
    assert "4.0" in out and "3.5" in out and "3.2" in out
    # 不混入其它指标
    assert "空腹血糖" not in out
    assert "3 条" in out


def test_indicator_match_by_english_name(db):
    from datetime import timedelta
    uid = 4
    db.add(_make_indicator(uid, "同型半胱氨酸", 15.0, "umol/L", date.today() - timedelta(days=30), name_en="HCY"))
    db.commit()
    ex = AgentExecutor(db)
    ex._current_user_id = uid
    out = _run(ex._exec_health_query("http://x", {}, {
        "dimension": "medical_exam", "indicator": "HCY",
    }))
    assert "同型半胱氨酸" in out
    assert "15.0" in out


def test_many_indicators_not_truncated(db):
    """20+ 项化验指标不应被截断丢失 (旧 _api_get 截前 10 条的 bug)."""
    from datetime import timedelta
    uid = 5
    recent = date.today() - timedelta(days=30)
    db.add_all([
        _make_indicator(uid, f"指标{i:02d}", float(i), "x", recent)
        for i in range(25)
    ])
    db.commit()
    out = _exec(db, uid)
    assert "25 项化验指标" in out
    # 全部 25 项都在 (尤其第 11 项及之后, 旧逻辑会丢)
    for i in range(25):
        assert f"指标{i:02d}" in out


def test_user_isolation(db):
    """只返回当前用户的指标."""
    from datetime import timedelta
    recent = date.today() - timedelta(days=30)
    db.add_all([
        _make_indicator(1, "用户1的LDL", 3.0, "mmol/L", recent, name_en="LDL"),
        _make_indicator(2, "用户2的LDL", 9.9, "mmol/L", recent, name_en="LDL"),
    ])
    db.commit()
    out = _exec(db, 1)
    assert "用户1的LDL" in out
    assert "用户2的LDL" not in out
    assert "9.9" not in out


def test_no_data_friendly_message(db):
    out = _exec(db, 999)
    assert "未找到" in out


def test_days_window_widened_for_low_freq_labs(db):
    """化验是低频数据: 即便 days=7, 3 个月前的化验也要能查到 (窗口被放宽到>=365)."""
    uid = 6
    db.add(_make_indicator(uid, "低密度脂蛋白", 3.2, "mmol/L",
                           date.today() - timedelta(days=90)))
    db.commit()
    out = _exec(db, uid, days=7)  # days 太小, 但化验维度应放宽
    assert "低密度脂蛋白" in out


def test_stale_indicator_marked_old(db):
    """>180 天的化验应标注 (较旧·约N天前),避免 LLM 当现值给建议(safety NIT)。"""
    uid = 1
    old = date.today() - timedelta(days=200)
    recent = date.today() - timedelta(days=10)
    db.add_all([
        _make_indicator(uid, "陈年指标", 1.0, "x", old),
        _make_indicator(uid, "近期指标", 2.0, "y", recent),
    ])
    db.commit()
    out = _exec(db, uid)
    # 陈旧项带标记,近期项不带
    assert "较旧" in out
    chen_line = next(l for l in out.splitlines() if "陈年指标" in l)
    jin_line = next(l for l in out.splitlines() if "近期指标" in l)
    assert "较旧" in chen_line
    assert "较旧" not in jin_line


def test_recent_uploaded_medical_exams_are_listed_by_created_at(db):
    uid = 7
    db.add_all([
        MedicalExam(
            user_id=uid,
            exam_date=date(2026, 7, 1),
            exam_type="other",
            overall_assessment="左膝关节内外侧盘状半月板考虑，并半月板水平损伤。",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ),
        MedicalExam(
            user_id=uid,
            exam_date=date(2025, 8, 27),
            exam_type="comprehensive",
            overall_assessment="年度体检旧报告。",
            created_at=datetime.now(timezone.utc) - timedelta(days=20),
        ),
    ])
    db.commit()

    out = _exec(db, uid, uploaded_days=1)
    assert "最近上传/导入的体检/影像报告" in out
    assert "左膝关节内外侧盘状半月板" in out
    assert "年度体检旧报告" not in out


def test_medical_exam_query_includes_latest_report_summaries(db):
    uid = 8
    db.add(MedicalExam(
        user_id=uid,
        exam_date=date(2026, 6, 30),
        exam_type="other",
        overall_assessment="右膝关节内侧半月板后角损伤，关节腔少量积液。",
        created_at=datetime.now(timezone.utc),
    ))
    db.add(_make_indicator(uid, "右膝关节腔及髌上囊", None, "", date.today(), is_abnormal=True))
    db.commit()

    out = _exec(db, uid)
    assert "最近检查报告摘要" in out
    assert "右膝关节内侧半月板后角损伤" in out
    assert "右膝关节腔及髌上囊" in out


def test_medical_exam_keyword_with_mri_modality_matches_body_part_summary(db):
    uid = 9
    db.add(MedicalExam(
        user_id=uid,
        exam_date=date(2026, 7, 1),
        exam_type="other",
        overall_assessment="左膝关节内外侧盘状半月板考虑，并半月板水平损伤。",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()

    out = _exec(db, uid, keyword="膝关节MRI")
    assert "左膝关节内外侧盘状半月板" in out


def test_medical_exam_keyword_keeps_report_summary_when_indicator_rows_match(db):
    uid = 10
    db.add(MedicalExam(
        user_id=uid,
        exam_date=date(2026, 7, 1),
        exam_type="other",
        overall_assessment="左膝关节半月板信号异常，建议结合骨科查体评估。",
        created_at=datetime.now(timezone.utc),
    ))
    db.add(_make_indicator(uid, "左膝关节腔及髌上囊", None, "", date.today(), is_abnormal=True))
    db.commit()

    out = _exec(db, uid, keyword="膝关节MRI")
    assert "相关检查报告摘要" in out
    assert "左膝关节半月板信号异常" in out
    assert "左膝关节腔及髌上囊" in out
