"""补剂"在服 vs 在库"分段(2026-07-03 红参 case)。

is_active 定义数 = 补剂库存量,不是当前摄入;在服 = 近 14 天有 taken 打卡。
防 LLM 把 24 种库存说成"你目前有 24 种补剂,再加 X 会增加负担"。
"""
from datetime import date, timedelta

from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.twin import _collectors
from app.twin.builder import build_twin
from app.twin.formatter import twin_to_prompt_blob


def _seed(db):
    u = User(name="u", email="seg@test.com", hashed_password="x")
    db.add(u); db.flush()
    defs = []
    for name in ("MitoQ", "肌酸", "陈年鱼油"):
        d = SupplementDefinition(user_id=u.id, name=name, is_active=True)
        db.add(d); db.flush(); defs.append(d)
    today = date.today()
    # MitoQ:3 天前打卡(在服);肌酸:今天打卡(在服);陈年鱼油:20 天前(窗口外=未在服)
    db.add(SupplementRecord(user_id=u.id, supplement_id=defs[0].id, record_date=today - timedelta(days=3), taken=True))
    db.add(SupplementRecord(user_id=u.id, supplement_id=defs[1].id, record_date=today, taken=True))
    db.add(SupplementRecord(user_id=u.id, supplement_id=defs[2].id, record_date=today - timedelta(days=20), taken=True))
    db.commit()
    return u


def test_collector_segments_taking_vs_registered(db):
    u = _seed(db)
    out = _collectors.fetch_supplement_today(db, u.id)
    assert out["total_active_count"] == 3          # 库存量不变(安全规则仍用全量)
    assert out["taking_recent_count"] == 2         # 只有窗口内打卡的算在服
    assert set(out["taking_recent_names"]) == {"MitoQ", "肌酸"}
    assert out["taking_window_days"] == 14


def test_prompt_blob_separates_taking_from_registered(db):
    u = _seed(db)
    twin = build_twin(db, u.id, use_cache=False)
    blob = twin_to_prompt_blob(twin)
    assert "在服 2 种" in blob
    assert "登记 3 种" in blob
    assert "不应计入当前摄入负担" in blob
    # 未在服的不出现在"在服"名单里
    assert "陈年鱼油" not in blob.split("不应计入")[0].split("在服")[-1][:120]


def test_registered_only_library_says_not_taking(db):
    u = User(name="u2", email="seg2@test.com", hashed_password="x")
    db.add(u); db.flush()
    db.add(SupplementDefinition(user_id=u.id, name="库存维C", is_active=True))
    db.commit()
    out = _collectors.fetch_supplement_today(db, u.id)
    assert out["taking_recent_count"] == 0
    twin = build_twin(db, u.id, use_cache=False)
    blob = twin_to_prompt_blob(twin)
    assert "无打卡记录" in blob and "不代表正在服用" in blob
