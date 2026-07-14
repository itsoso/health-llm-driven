"""GenUI 单晚/整晚血氧曲线 (intra-night) — 检测 + 构建 + 诚实兜底。

bug 修回归: 「绘制昨晚整晚血氧曲线」曾被误判成近半年月度趋势 (答非所问)。
"""
from datetime import date, time

import pytest

from app.models.daily_health import SpO2Sample
from app.models.user import User
from app.services.genui.chart_builder import (
    _parse_target_night,
    build_nocturnal_spo2_curve,
    detect_chart_requests,
    detect_nocturnal_curve_request,
)

TODAY = date(2026, 7, 14)


# ──────────────────────────── 检测 ────────────────────────────

def test_detect_explicit_date_and_cue():
    assert detect_nocturnal_curve_request(
        "绘制昨天晚上 2026 7 13 整晚的血氧曲线", today=TODAY
    ) == ("spo2", date(2026, 7, 13))


def test_detect_relative_zuowan():
    assert detect_nocturnal_curve_request("画一下昨晚整晚血氧曲线", today=TODAY) == (
        "spo2",
        date(2026, 7, 13),
    )


def test_detect_jinwan_is_today():
    assert detect_nocturnal_curve_request("今晚血氧整晚曲线", today=TODAY) == (
        "spo2",
        date(2026, 7, 14),
    )


def test_detect_qianwan_is_two_days_ago():
    assert detect_nocturnal_curve_request("前晚整晚血氧曲线", today=TODAY) == (
        "spo2",
        date(2026, 7, 12),
    )


def test_no_cue_is_not_nocturnal():
    # 无单晚线索 → None → fall through 到区间趋势 (不误吞普通血氧趋势请求)
    assert detect_nocturnal_curve_request("血氧曲线", today=TODAY) is None
    assert detect_nocturnal_curve_request("绘制近半年血氧趋势", today=TODAY) is None


def test_half_year_trend_still_goes_to_trend_detector():
    # 关键: 近半年趋势请求既不被 nocturnal 吞, 也仍被 detect_chart_requests 命中
    assert detect_nocturnal_curve_request("绘制近半年血氧趋势", today=TODAY) is None
    assert detect_chart_requests("绘制近半年血氧趋势") == [("spo2", "6m")]


def test_non_spo2_nocturnal_is_none():
    # 目前只做血氧 intra-night; 「昨晚心率曲线」不走本分支
    assert detect_nocturnal_curve_request("昨晚整晚心率曲线", today=TODAY) is None


def test_parse_month_day_infers_year():
    # 7月13日 (今天 7/14) → 今年
    assert _parse_target_night("7月13日整晚血氧", TODAY) == date(2026, 7, 13)
    # 12月31日 (晚于今天) → 去年
    assert _parse_target_night("12月31日整晚血氧", TODAY) == date(2025, 12, 31)


# ──────────────────────────── 构建 ────────────────────────────

def _seed(db, user_id, record_date, samples, source="garmin"):
    """samples: list[(hour, minute, value)]"""
    for h, m, v in samples:
        db.add(SpO2Sample(
            user_id=user_id, record_date=record_date,
            sample_time=time(h, m), spo2_value=v, source=source,
        ))
    db.commit()


@pytest.fixture
def user(db):
    u = User(username="noct", email="noct@test.com", hashed_password="x", name="N")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_curve_from_next_day_morning_record(db, user):
    """整夜数据常挂醒来次日 record_date: evening=7/13 但密集采样在 7/14 晨; 当日白天点(<18h)剔除。"""
    # 7/13 只有 3 个零散白天点 (均 <18:00, 都在窗外, 应剔除)
    _seed(db, user.id, date(2026, 7, 13), [(9, 0, 97), (14, 0, 96), (16, 0, 95)])
    # 7/14 有一整夜密集采样 (01:00-06:00, 每 15 分钟, 含一次低谷)
    night = []
    for h in range(1, 7):
        for mm in (0, 15, 30, 45):
            v = 88 if (h == 3 and mm == 30) else 95  # 03:30 低谷
            night.append((h, mm, v))
    _seed(db, user.id, date(2026, 7, 14), night)

    block = build_nocturnal_spo2_curve(db, user.id, date(2026, 7, 13))
    assert block is not None
    assert block["component"] == "line_chart"
    assert block["title"] == "7月13日整晚血氧"
    assert block["unit"] == "%"
    # x 轴是时刻 (HH:MM), 不是月份
    assert all(":" in lbl for lbl in block["x"])
    assert "月" not in "".join(block["x"])
    # 低谷 88 <92 → 标红 warn
    lo_ann = next(a for a in block["annotations"] if "最低" in a["label"])
    assert lo_ann["kind"] == "warn"
    # 只数窗内 24 点 (7/13 白天 3 点被剔除)
    assert "24" in block["data_note"]


def test_window_excludes_previous_night(db, user):
    """[安全评审回归] 相邻夜都密: 前一夜(挂 7/13 晨, 均值85)绝不冒充所问夜(挂 7/14 晨, 均值97)。

    早先按 record_date 样本数 argmax 会挑中更密的前一夜 → 答非所问。绝对时间窗修复后,
    7/13 晨(00:00-07:00, 在 7/13 18:00 之前)全部窗外剔除, 只留 7/14 晨的所问夜。
    """
    prev = [(h, mm, 85) for h in range(0, 7) for mm in (0, 20, 40)]  # 21 点, 更密
    _seed(db, user.id, date(2026, 7, 13), prev)
    asked = [(h, mm, 95 if (h == 3 and mm == 0) else 97) for h in range(1, 7) for mm in (0, 30)]  # 12 点, 含轻微起伏
    _seed(db, user.id, date(2026, 7, 14), asked)

    block = build_nocturnal_spo2_curve(db, user.id, date(2026, 7, 13))
    assert block is not None
    pts = block["series"][0]["points"]
    assert all(p >= 95 for p in pts), f"应只含所问夜(~97), 不含前一夜(85): {pts}"
    assert "12" in block["data_note"]  # 只数窗内 12 点
    # 全 ≥95 → 最低桶不标红 (避免正常夜 over-alarm)
    lo_ann = next(a for a in block["annotations"] if "最低" in a["label"])
    assert lo_ann["kind"] == "good"


def test_epoch_ms_absolute_time_wins_over_record_date(db, user):
    """有 epoch_ms 时按绝对时刻定位: 名义 sample_time 在窗外(7/14 22:xx)也能靠 epoch 落进窗内(7/13 22:xx)。"""
    from datetime import datetime as _dt
    base = _dt(2026, 7, 13, 22, 0)  # 所问夜傍晚 22:00, 在窗内 [7/13 18:00, 7/14 12:00]
    for i in range(15):
        epoch = int(base.timestamp() * 1000) + i * 60000  # 每分钟一点
        db.add(SpO2Sample(
            user_id=user.id, record_date=date(2026, 7, 14),  # 名义挂次日
            sample_time=time(22, i),  # combine(7/14,22:xx)=窗外; 靠 epoch_ms 才落进窗内
            spo2_value=96, source="garmin", epoch_ms=epoch,
        ))
    db.commit()
    block = build_nocturnal_spo2_curve(db, user.id, date(2026, 7, 13))
    assert block is not None  # 若误用 combine(7/14,22:xx) 会全落窗外 → None
    assert block["x"][0].startswith("22:")


def test_too_few_samples_returns_none_not_trend(db, user):
    """诚实兜底: 该夜无逐分钟血氧 → None (调用方绝不回退月度趋势)。"""
    _seed(db, user.id, date(2026, 7, 14), [(3, 0, 95), (3, 30, 94)])  # 仅 2 点
    assert build_nocturnal_spo2_curve(db, user.id, date(2026, 7, 13)) is None


def test_out_of_range_values_filtered(db, user):
    """值域 sanity: <50 或 >100 的脏值被过滤, 不进曲线。"""
    night = [(h, mm, 95) for h in range(1, 7) for mm in (0, 20, 40)]  # 18 个有效点 (≥12)
    night += [(2, 15, 3), (4, 15, 250)]  # 脏值 (<50 / >100)
    _seed(db, user.id, date(2026, 7, 14), night)
    block = build_nocturnal_spo2_curve(db, user.id, date(2026, 7, 13))
    assert block is not None
    for pt in block["series"][0]["points"]:
        assert 50 <= pt <= 100
