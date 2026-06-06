# -*- coding: utf-8 -*-
"""抗衰主动 Agent(Phase2 W1)回归。

纯逻辑(diff/find)无 DB;evaluate_user 用内存 DB + 两条快照。
钉:改善/回升/持平判定 + 阈值打扰 + 指标优先级 + 缺值不打扰 + 取快照算变化。
"""
from datetime import datetime, timedelta

from app.services.longevity_watch import (
    NOTABLE_YEARS,
    diff_biological_age,
    find_change_in_snapshots,
)


def _twin(phenotypic_age=None, fitness_age=None):
    return {
        "labs": {"phenotypic_age": phenotypic_age},
        "physiological": {"vo2max_fitness_age": fitness_age},
    }


def test_diff_improved_notable():
    c = diff_biological_age(_twin(phenotypic_age=47.0), _twin(phenotypic_age=44.0))
    assert c.kind == "improved" and c.notable is True
    assert c.delta_years == -3.0
    assert c.metric == "phenotypic_age" and c.label == "身体年龄"
    assert "年轻" in c.message and "诊断" in c.message  # 正反馈 + 边界


def test_diff_regressed_gentle():
    c = diff_biological_age(_twin(phenotypic_age=44.0), _twin(phenotypic_age=47.0))
    assert c.kind == "regressed" and c.notable is True
    assert c.delta_years == 3.0
    assert "不用慌" in c.message  # 温和不报警化


def test_diff_stable_not_notable():
    c = diff_biological_age(_twin(phenotypic_age=47.0), _twin(phenotypic_age=47.3))
    assert c.kind == "stable" and c.notable is False
    assert abs(c.delta_years) < NOTABLE_YEARS


def test_diff_prefers_phenoage_over_fitness():
    c = diff_biological_age(
        _twin(phenotypic_age=50.0, fitness_age=40),
        _twin(phenotypic_age=45.0, fitness_age=39),
    )
    assert c.metric == "phenotypic_age"  # 优先血检


def test_diff_fitness_age_fallback():
    c = diff_biological_age(_twin(fitness_age=45), _twin(fitness_age=41))
    assert c.metric == "fitness_age" and c.kind == "improved"
    assert c.label == "体能年龄"


def test_diff_none_when_no_comparable():
    assert diff_biological_age(_twin(), _twin()) is None
    assert diff_biological_age(_twin(phenotypic_age=47.0), _twin()) is None  # 缺一边


def test_find_change_picks_latest_and_prev():
    # newest-first;最新 44, 上一条 47 → improved
    snaps = [_twin(phenotypic_age=44.0), _twin(phenotypic_age=47.0), _twin(phenotypic_age=48.0)]
    c = find_change_in_snapshots(snaps)
    assert c.curr == 44.0 and c.prev == 47.0 and c.kind == "improved"


def test_find_change_skips_identical_then_uses_next():
    # 最新两条相同(同次体检重复快照)→ 跳过, 用再上一条
    snaps = [_twin(phenotypic_age=44.0), _twin(phenotypic_age=44.0), _twin(phenotypic_age=47.0)]
    c = find_change_in_snapshots(snaps)
    assert c is not None and c.curr == 44.0 and c.prev == 47.0


def test_find_change_none_when_single():
    assert find_change_in_snapshots([_twin(phenotypic_age=44.0)]) is None
    assert find_change_in_snapshots([]) is None


def test_evaluate_user_with_db(db):
    """两条快照(47→44)→ evaluate_user 返回 improved 变化。"""
    from app.models.twin_snapshot import TwinSnapshot
    from app.tasks.longevity_watch import evaluate_user

    t0 = datetime(2026, 3, 1)
    db.add(TwinSnapshot(user_id=1, schema_version="1", content_hash="h1",
                        purpose="manual", quality_grade="B", sources=["labs"],
                        twin_json=_twin(phenotypic_age=47.0), created_at=t0))
    db.add(TwinSnapshot(user_id=1, schema_version="1", content_hash="h2",
                        purpose="manual", quality_grade="B", sources=["labs"],
                        twin_json=_twin(phenotypic_age=44.0), created_at=t0 + timedelta(days=84)))
    db.commit()

    change = evaluate_user(db, 1)
    assert change is not None
    assert change.kind == "improved" and change.curr == 44.0 and change.prev == 47.0


def test_evaluate_user_none_when_single_snapshot(db):
    from app.models.twin_snapshot import TwinSnapshot
    from app.tasks.longevity_watch import evaluate_user
    db.add(TwinSnapshot(user_id=2, schema_version="1", content_hash="x",
                        purpose="manual", quality_grade="C", sources=["labs"],
                        twin_json=_twin(phenotypic_age=44.0), created_at=datetime(2026, 5, 1)))
    db.commit()
    assert evaluate_user(db, 2) is None
