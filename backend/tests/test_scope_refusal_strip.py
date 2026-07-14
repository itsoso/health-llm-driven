"""剥掉弱模型幻觉的"我只负责记录查询、无法分析"自我设限开场白 — founder 2026-07-14。

prompt 压不住变体(模型换措辞),故确定性剥离。极特异正则(三要素同句)不误伤合法免责。
"""
from app.services.agent_executor import _strip_scope_refusal_preamble as strip


def test_strips_real_variant_1_router():
    t = "抱歉，我是健康记录工具路由器，无法为您提供健康分析和长建议。如需记录、修改或删除健康数据，请随时告诉我。\n\n今日饮水明细："
    assert strip(t).startswith("今日饮水明细")


def test_strips_real_variant_2_ascii_question():
    # 结尾是 ASCII ? (非全角？) — 曾漏判
    t = "抱歉，我仅负责健康数据的记录与查询，无法提供健康分析与建议，请问您需要记录或查询什么数据?\n\n今日饮水："
    assert strip(t).startswith("今日饮水")


def test_strips_stray_lt_prefix():
    t = "<抱歉，我是健康记录工具路由器，无法为您提供健康分析和长建议。今日饮水明细如下："
    assert strip(t).startswith("今日饮水明细")


def test_does_not_strip_legit_medical_disclaimer():
    # R4 合法免责("请咨询医生")不含 记录/查询+无法+分析 三要素 → 保留
    t = "你的血压偏高，建议就医。涉及用药请咨询医生后再调整。"
    assert strip(t) == t


def test_does_not_strip_genuine_out_of_scope_decline():
    # 真·超范围婉拒(无"记录/查询…无法…分析"自限组合)→ 保留
    t = "我无法帮你预订医院挂号，这需要你自己在医院 App 操作。"
    assert strip(t) == t


def test_does_not_strip_capability_limitation():
    # 对抗: "只能查询…无法分析更早的" 是合法**能力/数据范围**说明(非角色自限)→ 保留。
    # 开场锚定 角色自限(是…路由器/工具、只/仅负责), 不吃"我只能查询"。
    t = "我只能查询最近7天的数据，无法分析更早的趋势。"
    assert strip(t) == t


def test_does_not_strip_normal_answer():
    t = "今日饮水明细：10:31 300ml，12:17 200ml。"
    assert strip(t) == t


def test_strip_empty_falls_back_to_original():
    # 极端: 整条就是自限句、剥后为空 → 返回原文, 不吞掉整条回复
    t = "我仅负责记录与查询，无法提供分析。"
    out = strip(t)
    assert out  # 非空(要么剥后有残留, 要么兜底返回原文)
