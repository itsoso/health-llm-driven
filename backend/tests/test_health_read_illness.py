"""Canonical illness query: semantic filters, chronology and owner isolation."""
import json
import logging
import uuid
from datetime import date, timedelta

from sqlalchemy.exc import OperationalError

from app.models.illness import IllnessEpisode
from app.models.user import User
from app.services import health_read


def _make_user(db) -> User:
    token = uuid.uuid4().hex[:8]
    user = User(
        username=f"illness_query_{token}",
        email=f"illness_query_{token}@example.com",
        hashed_password="x",
        name="Illness Query Test User",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _episode(db, user_id: int, name: str, days_ago: int, **overrides) -> IllnessEpisode:
    episode = IllnessEpisode(
        user_id=user_id,
        name=name,
        start_date=date.today() - timedelta(days=days_ago),
        end_date=overrides.pop("end_date", None),
        status=overrides.pop("status", "resolved"),
        severity=overrides.pop("severity", 3),
        notes=overrides.pop("notes", None),
        **overrides,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    return episode


def test_illness_read_filters_owner_keyword_window_and_orders_latest(db):
    current_user = _make_user(db)
    other_user = _make_user(db)
    newer = _episode(
        db,
        current_user.id,
        "口腔溃疡",
        10,
        status="active",
        severity=4,
        notes="右侧",
    )
    older = _episode(
        db,
        current_user.id,
        "复发性口腔溃疡",
        40,
        status="resolved",
        end_date=date.today() - timedelta(days=35),
    )
    _episode(db, current_user.id, "口腔溃疡", 220)
    _episode(db, current_user.id, "感冒", 5)
    other = _episode(db, other_user.id, "口腔溃疡", 1)

    out = health_read.canonical_read(
        db,
        current_user.id,
        "illness",
        days=183,
        keyword="口腔溃疡",
    )
    rows = json.loads(out)

    assert [row["id"] for row in rows] == [newer.id, older.id]
    assert other.id not in {row["id"] for row in rows}
    assert rows[0] == {
        "id": newer.id,
        "name": "口腔溃疡",
        "start_date": newer.start_date.isoformat(),
        "end_date": None,
        "status": "active",
        "severity": 4,
        "notes": "右侧",
    }


def test_illness_read_returns_honest_no_match_and_requires_user(db):
    current_user = _make_user(db)
    _episode(db, current_user.id, "感冒", 3)

    no_match = health_read.canonical_read(
        db,
        current_user.id,
        "illness",
        days=183,
        keyword="口腔溃疡",
    )
    no_user = health_read.canonical_read(
        db,
        None,
        "illness",
        days=183,
        keyword="口腔溃疡",
    )

    assert "未找到" in no_match
    assert "口腔溃疡" in no_match
    assert "Error" in no_user
    assert "user_id" in no_user


def test_illness_read_includes_all_episode_statuses(db):
    current_user = _make_user(db)
    for index, status in enumerate(("active", "improving", "resolved"), start=1):
        _episode(db, current_user.id, "口腔溃疡", index, status=status)

    out = health_read.canonical_read(
        db,
        current_user.id,
        "illness",
        days=30,
        keyword="口腔溃疡",
    )
    rows = json.loads(out)

    assert {row["status"] for row in rows} == {"active", "improving", "resolved"}


def test_illness_read_without_window_searches_full_history_directly(db):
    current_user = _make_user(db)
    old = _episode(db, current_user.id, "口腔溃疡", 400)
    future = _episode(db, current_user.id, "口腔溃疡", -1)

    out = health_read.canonical_read(
        db,
        current_user.id,
        "illness",
        keyword="口腔溃疡",
    )
    rows = json.loads(out)

    assert [row["id"] for row in rows] == [old.id]
    assert future.id not in {row["id"] for row in rows}


def test_illness_read_sanitizes_database_errors(db, monkeypatch, caplog):
    keyword = "口腔溃疡"

    def fail_query(*args, **kwargs):  # noqa: ARG001
        raise OperationalError(
            "SELECT * FROM illness_episodes WHERE name ILIKE %(keyword)s",
            {"keyword": f"%{keyword}%"},
            RuntimeError("database unavailable"),
        )

    monkeypatch.setattr(db, "query", fail_query)
    with caplog.at_level(logging.ERROR, logger="app.services.health_read"):
        out = health_read.read_illness_episodes(db, 42, keyword=keyword)

    assert out == "Error: 病症记录查询暂时失败，请稍后重试。"
    assert keyword not in out
    assert keyword not in caplog.text
    assert "SELECT" not in caplog.text
    assert "OperationalError" in caplog.text
