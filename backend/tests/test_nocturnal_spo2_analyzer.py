"""P1b 事件检测算法测试。

用合成数据喂 _detect_events，验证：
- 平稳夜（无事件）
- 经典 OSA（多次 ≥4% 下降集中 REM）
- 小幅波动（< 阈值，不应计入）
- 短暂下降（< 10s，不应计入）
"""
from datetime import datetime, timedelta
from app.services.sleep.nocturnal_spo2_analyzer import _detect_events, DROP_THRESHOLD_PCT


def _seq(ts_start: datetime, values, interval_sec=60):
    """生成 (ts, spo2) 序列。"""
    return [(ts_start + timedelta(seconds=i * interval_sec), v) for i, v in enumerate(values)]


class TestDetectEvents:
    def test_flat_night_no_events(self):
        # 8 小时 95% 平线
        ts = datetime(2026, 4, 23, 23, 0)
        samples = _seq(ts, [95] * 480)
        events = _detect_events(samples)
        assert events == []

    def test_classic_osa_pattern(self):
        """基线 95，中间一次下降到 88（-7%）持续 2min → 1 个事件。"""
        ts = datetime(2026, 4, 23, 23, 0)
        # 前 10 分钟建基线
        values = [95] * 10 + [93, 90, 88, 89, 92] + [95] * 10
        samples = _seq(ts, values)
        events = _detect_events(samples)
        assert len(events) == 1
        ev = events[0]
        assert ev.min_spo2 == 88
        assert ev.drop_magnitude >= 4.0

    def test_small_fluctuation_ignored(self):
        """基线 95，仅降到 93（-2%）→ 不应计入。"""
        ts = datetime(2026, 4, 23, 23, 0)
        values = [95] * 10 + [94, 93, 94, 95] + [95] * 10
        samples = _seq(ts, values)
        events = _detect_events(samples)
        assert events == []

    def test_short_dip_ignored(self):
        """基线 95，单点降到 88 后立刻恢复（1min 总时长 < 10s？不 - 1min = 60s，会记入）。
        重点是 duration_seconds 必须 >= 10。
        """
        # 为了构造 < 10s 的下降，我们用 5s 间隔
        ts = datetime(2026, 4, 23, 23, 0)
        samples = [(ts + timedelta(seconds=i * 5), v) for i, v in enumerate([95] * 30 + [88, 95] + [95] * 30)]
        events = _detect_events(samples)
        # 单点 5s < 10s 阈值
        assert events == []

    def test_multiple_events(self):
        """模拟 3 次相同幅度下降。"""
        ts = datetime(2026, 4, 23, 23, 0)
        base = [95] * 10
        dip = [93, 89, 88, 90, 95]
        values = base + dip + base + dip + base + dip + base
        samples = _seq(ts, values)
        events = _detect_events(samples)
        assert len(events) == 3

    def test_minimum_samples_for_baseline(self):
        """基线至少需要 MIN_SAMPLES_FOR_BASELINE 个点，否则跳过。"""
        ts = datetime(2026, 4, 23, 23, 0)
        samples = _seq(ts, [95, 88])  # 只有 2 个
        events = _detect_events(samples)
        assert events == []

    def test_drop_threshold_exactly_at_4(self):
        """恰好 4% 下降应计入事件。"""
        ts = datetime(2026, 4, 23, 23, 0)
        values = [96] * 10 + [96, 93, 92, 93, 96]  # baseline=96, min=92, drop=4
        samples = _seq(ts, values)
        events = _detect_events(samples)
        # 边界情况：>= 4 应触发
        assert len(events) == 1
        assert events[0].drop_magnitude >= DROP_THRESHOLD_PCT
