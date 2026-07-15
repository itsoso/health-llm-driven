"""快照卡分析轮门控(2026-07-14 founder 截图:问"上周睡眠不好吗"却贴今晚单晚快照)。

原则:单日快照卡只在直接单指标速查(卡即答案)出现;分析轮(LLM 正文已自带
表格/多段分析)整类压掉 —— 不再关键词错配窗口、不与更好的正文重复。
"""
from app.services.inline_cards import (
    build_cards,
    _SNAPSHOT_CARD_TYPES,
    _DRAFT_KIND_BY_CARD,
)
from app.api.agent import _answer_owns_its_visualization as owns


def test_answer_owns_visualization_signal():
    md_table = "对照\n| 日期 | 评分 | HRV |\n|---|---|---|\n| 7/5 | 42 | 40 |\n| 7/7 | 67 | 37 |"
    assert owns(md_table, ["health_query"]) is True          # 含 markdown 表 → 分析
    assert owns("最近偏低。", ["health_analysis"]) is True     # 深分析工具 → 分析
    assert owns("你昨晚睡了8小时,评分75。", ["health_query"]) is False  # 一句话速查
    assert owns("评分75。", None) is False
    assert owns("", None) is False


def test_snapshot_cards_suppressed_on_analysis_turn(db):
    # 睡眠关键词的分析问句本会出 sleep 快照(有数据时);分析轮标志一开, 整类被压。
    q = "上周我也吃过，出现过睡眠不好的情况吗"
    normal = {c["type"] for c in build_cards(db, 1, q)}
    gated = {c["type"] for c in build_cards(db, 1, q, suppress_snapshot_cards=True)}
    # 压制后不含任何快照卡类型
    assert not (gated & _SNAPSHOT_CARD_TYPES), f"分析轮仍出快照卡: {gated & _SNAPSHOT_CARD_TYPES}"
    # 压制只针对快照类:非快照卡(如草稿/图表)不受该 flag 影响(此 query 无草稿,断言子集关系)
    assert (gated - _SNAPSHOT_CARD_TYPES) == (normal - _SNAPSHOT_CARD_TYPES)


def test_draft_cards_survive_snapshot_gating(db):
    # 快照门控绝不误伤记录草稿(不同类,不同职责)。
    q = "加餐吃了一个油桃"
    gated = build_cards(db, 1, q, suppress_snapshot_cards=True)
    assert any(c["type"] == "diet_draft" for c in gated), "草稿卡不属快照类, 不应被快照门控压掉"


def test_snapshot_types_disjoint_from_draft_types():
    # 契约:快照类与草稿类不重叠(两套门控互不干扰)。
    assert not (_SNAPSHOT_CARD_TYPES & set(_DRAFT_KIND_BY_CARD.keys()))
