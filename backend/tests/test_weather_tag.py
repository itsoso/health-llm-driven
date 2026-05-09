"""#67: weather_tag util — 抽 plan title 前缀 / 实际天气匹配 / 剥前缀."""
from app.utils.weather_tag import (
    extract_weather_tag,
    weather_text_matches_tag,
    strip_tag_prefix,
)


def test_extract_rain_tag():
    assert extract_weather_tag("雨天力量维护日") == "rain"
    assert extract_weather_tag("阴雨日轻松走") == "rain"
    assert extract_weather_tag("雷雨日室内瑜伽") == "rain"


def test_extract_other_tags():
    assert extract_weather_tag("雪天减量") == "snow"
    assert extract_weather_tag("晴天长跑") == "sun"
    assert extract_weather_tag("大晴天郊外骑行") == "sun"
    assert extract_weather_tag("雾霾日室内训练") == "fog"
    assert extract_weather_tag("大风日避开海边") == "wind"
    assert extract_weather_tag("雷暴日休息") == "thunder"


def test_extract_no_prefix():
    assert extract_weather_tag("力量维护日") is None
    assert extract_weather_tag("") is None
    assert extract_weather_tag("跑步30分钟") is None


def test_match_rain_keyword():
    assert weather_text_matches_tag("中雨", "rain") is True
    assert weather_text_matches_tag("雷阵雨", "rain") is True
    assert weather_text_matches_tag("多云", "rain") is False
    assert weather_text_matches_tag("晴", "rain") is False


def test_match_empty_inputs():
    assert weather_text_matches_tag("", "rain") is False
    assert weather_text_matches_tag("中雨", None) is False
    assert weather_text_matches_tag("中雨", "") is False


def test_strip_prefix_rain():
    assert strip_tag_prefix("雨天力量维护日", "rain") == "力量维护日"
    assert strip_tag_prefix("雷雨日室内瑜伽", "rain") == "室内瑜伽"
    # 不带前缀 → 原文返回
    assert strip_tag_prefix("力量维护日", "rain") == "力量维护日"


def test_strip_separator_chars():
    assert strip_tag_prefix("雨天: 力量维护日", "rain") == "力量维护日"
    assert strip_tag_prefix("雨天 - 力量维护日", "rain") == "力量维护日"
    assert strip_tag_prefix("雨天，力量维护日", "rain") == "力量维护日"


def test_strip_no_tag():
    assert strip_tag_prefix("雨天力量维护日", None) == "雨天力量维护日"
    assert strip_tag_prefix("", "rain") == ""


def test_end_to_end_keep_when_match():
    """晴天 title + 实际晴 → 不剥."""
    title = "晴天长跑"
    tag = extract_weather_tag(title)  # 'sun'
    actual = "晴"
    if not weather_text_matches_tag(actual, tag):
        title = strip_tag_prefix(title, tag)
    assert title == "晴天长跑"


def test_end_to_end_strip_when_mismatch():
    """晴天 title + 实际下雨 → 剥成 "长跑"."""
    title = "晴天长跑"
    tag = extract_weather_tag(title)  # 'sun'
    actual = "中雨"
    if not weather_text_matches_tag(actual, tag):
        title = strip_tag_prefix(title, tag)
    assert title == "长跑"
