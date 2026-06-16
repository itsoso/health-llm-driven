"""补剂时段「一键完成」数据 (依从性重构: 24 checkbox → 4 时段动作)。

锁住 _build_slots 给每个时段输出 total / taken_count / pending_count /
pending_ids / all_taken —— 客户端据此把整段补剂压成一个动作, 用 pending_ids
一次 POST /supplements/records/batch 完成。仅补剂; 药物不在此列 (禁默认完成)。
"""
from types import SimpleNamespace

from app.services.daily_supplement_guide import _build_slots


def _supp(id, name, timing, dosage="", category="", description=""):
    return SimpleNamespace(
        id=id, name=name, timing=timing, dosage=dosage,
        category=category, description=description, sort_order=0,
    )


def _record(taken):
    return SimpleNamespace(taken=taken, taken_time=None)


def _slot_by_timing(slots, timing):
    return next(s for s in slots if s["timing"] == timing)


def test_pending_ids_and_counts():
    supps = [
        _supp(1, "维生素D", "morning"),
        _supp(2, "鱼油", "morning"),
        _supp(3, "镁", "bedtime"),
    ]
    taken = {1: _record(True)}  # 早晨只打卡了 1 个
    slots = _build_slots(supps, taken, ctx={})

    morning = _slot_by_timing(slots, "morning")
    assert morning["total"] == 2
    assert morning["taken_count"] == 1
    assert morning["pending_count"] == 1
    assert morning["pending_ids"] == [2]      # 只剩鱼油待完成
    assert morning["all_taken"] is False

    bedtime = _slot_by_timing(slots, "bedtime")
    assert bedtime["pending_ids"] == [3]
    assert bedtime["all_taken"] is False


def test_all_taken_slot():
    supps = [_supp(1, "维生素D", "morning"), _supp(2, "鱼油", "morning")]
    taken = {1: _record(True), 2: _record(True)}
    slots = _build_slots(supps, taken, ctx={})

    morning = _slot_by_timing(slots, "morning")
    assert morning["taken_count"] == 2
    assert morning["pending_count"] == 0
    assert morning["pending_ids"] == []
    assert morning["all_taken"] is True


def test_none_taken_slot_pending_all():
    supps = [_supp(1, "镁", "bedtime"), _supp(2, "甘氨酸", "bedtime")]
    slots = _build_slots(supps, {}, ctx={})

    bedtime = _slot_by_timing(slots, "bedtime")
    assert bedtime["pending_ids"] == [1, 2]
    assert bedtime["pending_count"] == 2
    assert bedtime["all_taken"] is False


def test_missing_timing_defaults_to_morning():
    supps = [_supp(1, "复合维生素", None)]
    slots = _build_slots(supps, {}, ctx={})
    assert _slot_by_timing(slots, "morning")["pending_ids"] == [1]
