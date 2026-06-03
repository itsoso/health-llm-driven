"""TwinSnapshot 版本化测试 (Personal Health OS P1, G1)."""
import datetime
import uuid


def _mk_user(db):
    from app.models.user import User
    u = User(
        username=f"ts_{uuid.uuid4().hex[:8]}",
        email=f"ts_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="测试",
        birth_date=datetime.date(1985, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_snapshot_dedupe_and_latest(db):
    u = _mk_user(db)
    from app.twin.snapshots import snapshot_twin, latest_snapshot, get_snapshot

    twin = {"meta": {"data_sources": ["garmin", "labs", "diet"]}, "physiological": {"rhr": 51}}
    s1 = snapshot_twin(db, u.id, twin, purpose="plan")
    assert s1.id is not None
    assert s1.content_hash
    assert s1.quality_grade == "B"  # 3 sources → B
    assert s1.sources == ["garmin", "labs", "diet"]

    # 内容相同 → 去重, 复用同一快照
    s2 = snapshot_twin(db, u.id, twin, purpose="plan")
    assert s2.id == s1.id

    # 内容变化 → 新快照
    twin2 = {"meta": {"data_sources": ["garmin", "labs", "diet"]}, "physiological": {"rhr": 60}}
    s3 = snapshot_twin(db, u.id, twin2, purpose="report")
    assert s3.id != s1.id

    assert latest_snapshot(db, u.id).id == s3.id
    assert latest_snapshot(db, u.id, purpose="plan").id == s1.id
    assert get_snapshot(db, s1.id).id == s1.id


def test_snapshot_accepts_pydantic_like_twin(db):
    u = _mk_user(db)
    from app.twin.snapshots import snapshot_twin

    class FakeTwin:
        def model_dump(self, mode=None):
            return {"meta": {"data_sources": ["a", "b", "c", "d", "e"]}}

    s = snapshot_twin(db, u.id, FakeTwin(), purpose="manual")
    assert s.quality_grade == "A"  # 5 sources → A
    assert s.sources == ["a", "b", "c", "d", "e"]
    assert s.twin_json["meta"]["data_sources"] == ["a", "b", "c", "d", "e"]


def test_invalid_purpose_falls_back_to_manual(db):
    u = _mk_user(db)
    from app.twin.snapshots import snapshot_twin
    s = snapshot_twin(db, u.id, {"meta": {"data_sources": []}}, purpose="bogus")
    assert s.purpose == "manual"
    assert s.quality_grade == "D"  # 0 sources → D


def test_dedupe_false_forces_new_snapshot(db):
    u = _mk_user(db)
    from app.twin.snapshots import snapshot_twin
    twin = {"meta": {"data_sources": ["garmin"]}}
    a = snapshot_twin(db, u.id, twin, purpose="manual")
    b = snapshot_twin(db, u.id, twin, purpose="cycle_baseline", dedupe=False)
    assert b.id != a.id
    assert b.purpose == "cycle_baseline"
