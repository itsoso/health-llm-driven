"""extract_from_briefing_entry: only known health metrics become is_value facts.

Regression for the "AI 画像" garbage-memory bug — the briefing regex used to mine
ANY "{label} {number}" (genetic/supplement fragments like "AA 9" / "上午补充 500"),
which then self-reinforced daily to confidence 1.0.
"""
from types import SimpleNamespace


def test_briefing_extractor_keeps_metrics_drops_fragments(db):
    from app.models.user import User
    from app.models.memory_fact import MemoryFact
    from app.services.memory_extractor import extract_from_briefing_entry

    user = User(username="mx", email="mx@test.com", hashed_password="x", name="m")
    db.add(user)
    db.commit()
    db.refresh(user)

    # objective embeds real vitals + the garbage genetic/supplement fragments
    entry = SimpleNamespace(
        id=1,
        user_id=user.id,
        created_by="briefing",
        objective=(
            "HRV 72 ms，静息心率 52 bpm，体重 70.5 kg。"
            "AA 9。基因提示 9。上午补充 500。动脉粥样硬化风险相关 4。ml 2。"
        ),
        assessment="",
        plan="",
    )

    extract_from_briefing_entry(db, entry)

    subjects = [
        f.subject
        for f in db.query(MemoryFact)
        .filter(MemoryFact.user_id == user.id, MemoryFact.predicate == "is_value")
        .all()
    ]

    # 真指标保留
    assert any("hrv" in s.lower() for s in subjects), subjects
    assert any("体重" in s for s in subjects), subjects
    # 垃圾碎片被白名单挡掉 —— 一条都不该进
    for junk in ("AA", "基因提示", "上午补充", "动脉粥样硬化风险相关", "ml"):
        assert junk not in subjects, f"garbage fact leaked: {junk} in {subjects}"
