"""冻结的 2026-09 补剂 taken 缺省回填:只修审计出的那批行,人群漂移即 fail-closed。"""
from datetime import date, time

import pytest

from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.services.supplement_taken_repair import (
    RECORD_IDS,
    USER_ID,
    repair_supplement_taken,
)


def _user(db, user_id):
    user = User(id=user_id, username=f"u{user_id}", email=f"u{user_id}@example.com",
                name=f"u{user_id}", hashed_password="x", is_active=True, is_approved=True)
    db.add(user)
    db.flush()
    return user


def _record(db, user_id, record_id, record_date, *, taken=False, notes=None, taken_time=None):
    supp = SupplementDefinition(user_id=user_id, name=f"补剂{record_id}", is_active=True)
    db.add(supp)
    db.flush()
    db.add(SupplementRecord(id=record_id, user_id=user_id, supplement_id=supp.id,
                            record_date=record_date, taken=taken, notes=notes,
                            taken_time=taken_time))


@pytest.fixture
def audited(db):
    """审计人群 + 对照组(合法取消勾选 / 4 月更正行 / 已服 / 他人同形行)。"""
    _user(db, USER_ID)
    _user(db, USER_ID + 1)
    for i, record_id in enumerate(RECORD_IDS):
        _record(db, USER_ID, record_id, date(2026, 9, 4 + i % 12), notes="当日服用")
    _record(db, USER_ID, 5001, date(2026, 5, 2))                                   # 取消勾选
    _record(db, USER_ID, 5002, date(2026, 4, 3), notes="【更正】误记")                 # 刻意未服
    _record(db, USER_ID, 5003, date(2026, 9, 20), taken=True, taken_time=time(7, 30))
    _record(db, USER_ID + 1, 5004, date(2026, 9, 9), notes="他人备注")
    db.commit()
    return db


def _taken(db):
    taken = {r.id: r.taken for r in db.query(SupplementRecord).all()}
    db.rollback()  # 结束只读事务:修复须自开事务(PostgreSQL SERIALIZABLE 必须是首条语句)
    return taken


def test_population_is_frozen_to_the_audited_rows():
    assert USER_ID == 3
    assert RECORD_IDS == (1088, 1089, 1090, 1091, 1092, 1093, 1094, 1098,
                          1099, 1100, 1101, 1102, 1103, 1104, 1105, 1106)


def test_repair_refuses_to_join_an_open_transaction(audited):
    audited.query(SupplementRecord).count()

    with pytest.raises(RuntimeError, match="own transaction"):
        repair_supplement_taken(audited, apply=True)

    audited.rollback()
    assert all(taken is False for record_id, taken in _taken(audited).items() if record_id in RECORD_IDS)


def test_dry_run_counts_population_and_writes_nothing(audited):
    before = _taken(audited)

    assert repair_supplement_taken(audited, apply=False) == len(RECORD_IDS)

    audited.expire_all()
    assert _taken(audited) == before


def test_apply_marks_only_audited_rows_taken(audited):
    before = _taken(audited)

    assert repair_supplement_taken(audited, apply=True) == len(RECORD_IDS)

    audited.expire_all()
    after = _taken(audited)
    assert all(after[record_id] is True for record_id in RECORD_IDS)
    assert {k: v for k, v in after.items() if k not in RECORD_IDS} == {
        k: v for k, v in before.items() if k not in RECORD_IDS
    }
    repaired = audited.query(SupplementRecord).filter(SupplementRecord.id.in_(RECORD_IDS)).all()
    assert {(r.notes, r.taken_time) for r in repaired} == {("当日服用", None)}


@pytest.mark.parametrize("drift", ["already_taken", "extra_candidate", "missing_row"])
def test_population_drift_fails_closed(audited, drift):
    if drift == "already_taken":
        audited.get(SupplementRecord, RECORD_IDS[0]).taken = True
    elif drift == "extra_candidate":
        _record(audited, USER_ID, 5005, date(2026, 9, 28), notes="新备注")
    else:
        audited.delete(audited.get(SupplementRecord, RECORD_IDS[-1]))
    audited.commit()
    before = _taken(audited)

    with pytest.raises(RuntimeError, match="population changed"):
        repair_supplement_taken(audited, apply=True)

    audited.rollback()
    audited.expire_all()
    assert _taken(audited) == before
