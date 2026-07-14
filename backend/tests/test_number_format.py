"""展示用数字精度规范 (AGENTS.md §14): 整数→整数, 小数→最多 2 位去尾零。

回归 founder bug: 动态卡片 sleep 的 duration_h 显示 6.166666666666667 (15 位)。
"""
import math

from app.services.genui.table_builder import _fmt_num
from app.utils.number_format import format_card_numbers, format_display_number


def test_float_capped_at_two_decimals():
    assert format_display_number(6.166666666666667) == 6.17
    assert format_display_number(0.855) in (0.85, 0.86)  # 四舍五入到 2 位
    assert format_display_number(-6.166666) == -6.17


def test_integer_stays_integer():
    assert format_display_number(58) == 58
    assert format_display_number(58.0) == 58
    assert format_display_number(221) == 221
    assert isinstance(format_display_number(58.0), int)


def test_trailing_zeros_stripped():
    assert format_display_number(71.4) == 71.4
    assert format_display_number(6.10) == 6.1
    assert format_display_number(6.20) == 6.2


def test_non_numbers_and_specials_untouched():
    assert format_display_number(True) is True  # bool 不当数字处理
    assert format_display_number(False) is False
    assert format_display_number("6.1666") == "6.1666"
    assert format_display_number(None) is None
    assert format_display_number(math.inf) == math.inf
    assert math.isnan(format_display_number(math.nan))


def test_founder_sleep_card_dict():
    """founder 截图那张 sleep 动态卡片的 data → 规范后 duration_h 变 6.17, 整数不变。"""
    raw = {"awake_min": 6, "deep_min": 58, "duration_h": 6.166666666666667, "light_min": 221}
    out = format_card_numbers(raw)
    assert out == {"awake_min": 6, "deep_min": 58, "duration_h": 6.17, "light_min": 221}


def test_format_card_numbers_recurses_nested():
    raw = {
        "a": 1.23456,
        "nested": {"b": 9.0, "c": [3.14159, 5, "x"]},
        "s": "keep",
        "flag": True,
    }
    out = format_card_numbers(raw)
    assert out["a"] == 1.23
    assert out["nested"]["b"] == 9 and isinstance(out["nested"]["b"], int)
    assert out["nested"]["c"] == [3.14, 5, "x"]
    assert out["s"] == "keep"
    assert out["flag"] is True


def test_format_card_numbers_does_not_mutate_input():
    """不可变输入: 返回新对象, 原 dict 不动 —— 保证从同一 data 构建的写入 payload 不被降精度。"""
    raw = {"duration_h": 6.166666666666667, "nested": {"x": 1.23456}}
    out = format_card_numbers(raw)
    assert raw["duration_h"] == 6.166666666666667  # 原值未变
    assert raw["nested"]["x"] == 1.23456
    assert out["duration_h"] == 6.17  # 新对象已规范
    assert out is not raw and out["nested"] is not raw["nested"]


def test_table_builder_fmt_num_rounds():
    assert _fmt_num(6.166666666666667) == "6.17"
    assert _fmt_num(350.0) == "350"
    assert _fmt_num(58, "ms") == "58 ms"
    assert _fmt_num(71.44, "kg") == "71.44 kg"
    assert _fmt_num(None) is None
