"""TTS 文本规范化 — CosyVoice 把 '3.6千米' 念成 '3 6千米' 漏掉点, 这层修.

只测纯函数, 不打 DashScope.
"""
from app.services.tts.cosyvoice import _normalize_for_tts


def test_decimal_distance():
    assert _normalize_for_tts("跑了 3.6 千米") == "跑了 3点6 千米"


def test_decimal_no_space():
    assert _normalize_for_tts("3.6千米") == "3点6千米"


def test_multiple_decimals():
    assert _normalize_for_tts("配速 5.30, 心率 142.5") == "配速 5点30, 心率 142点5"


def test_version_number_also_normalized():
    # IP / 版本号也按 "点" 念, 比 "省略" 强
    assert _normalize_for_tts("v1.0.2 已上线") == "v1点0点2 已上线"


def test_sentence_end_period_kept():
    # 句尾点号不应被替换 (前后不是数字)
    assert _normalize_for_tts("今天恢复优先级: 高.") == "今天恢复优先级: 高."


def test_decimal_after_chinese():
    # "第3.5期" 这种也希望念出来 — 数字之间, 替换
    assert _normalize_for_tts("第3.5期") == "第3点5期"


def test_no_digits_no_change():
    assert _normalize_for_tts("早上好, 今天天气不错") == "早上好, 今天天气不错"


def test_integer_with_period_at_end():
    # "跑了 5." 这种残缺串不动 (后面不是数字)
    assert _normalize_for_tts("跑了 5.") == "跑了 5."
