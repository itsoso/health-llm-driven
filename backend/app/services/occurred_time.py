"""发生时间解析 — 把口语时刻确定性折算成 (北京时间, 诚实精度)。

背景(2026-07-12 founder):时间线总结只能"估",因为对话事件从不落
结构化发生时间。本模块是唯一解析真源:LLM 只负责把用户原话里的时间
表达**原样**放进 occurred_at 槽位("下午"/"刚才"/"21:07"/ISO),
折算与精度判定全在这里的确定性代码完成(R4:不让模型编时间)。

诚实精度(occurred_precision):
- exact        — ISO / HH:MM 明确时刻
- hour         — "刚才/刚刚" 这类 ±小时级
- part_of_day  — "下午/傍晚/晚上"(存代表时刻,总结时应显示"下午"而非假装 15:00)
- day          — 只有日期粒度("昨天")
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

BEIJING_TZ = timezone(timedelta(hours=8))

# 时段词 → (代表时刻 hour, minute)。代表时刻取区间中点附近的整点惯例值。
_PART_OF_DAY = {
    "凌晨": (3, 0),
    "清晨": (6, 0),
    "早上": (8, 0),
    "早晨": (8, 0),
    "上午": (10, 0),
    "中午": (12, 0),
    "下午": (15, 0),
    "傍晚": (18, 0),
    "晚上": (20, 0),
    "夜里": (22, 0),
    "深夜": (23, 0),
    "半夜": (23, 30),
}

# 日偏移前缀(含"昨晚"这类 缩合词 由组合逻辑处理)
_DAY_OFFSET = {"今天": 0, "今晚": 0, "昨天": -1, "昨晚": -1, "前天": -2}

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")
_CN_CLOCK_RE = re.compile(r"^(\d{1,2})[点时](半|\d{1,2}分?)?$")


def resolve_occurred_at(
    raw: Any, *, now: Optional[datetime] = None
) -> Tuple[datetime, str]:
    """解析任意时间表达 → (tz-aware 北京时间, precision)。

    None/空 → (now, "exact"):默认"此刻发生"。
    解析不了 → ValueError(fail-loud,调用方自行决定 400 或回退)。
    """
    now_bj = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    if raw is None:
        return now_bj, "exact"
    s = str(raw).strip()
    if not s:
        return now_bj, "exact"

    # ① ISO 日期时间(含空格分隔变体);naive 视为北京时间
    if "T" in s or ("-" in s and " " in s):
        try:
            dt = datetime.fromisoformat(s.replace(" ", "T", 1))
        except ValueError as exc:
            raise ValueError(f"无法解析发生时间: {s!r}") from exc
        dt = dt.replace(tzinfo=BEIJING_TZ) if dt.tzinfo is None else dt.astimezone(BEIJING_TZ)
        return dt, "exact"

    # ② "HH:MM"(未来时刻 → 视为昨天同刻:21:35 说"21:07"是今天,09:00 说"23:00"是昨晚)
    m = _HHMM_RE.match(s)
    if m:
        h, minute = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and 0 <= minute <= 59):
            raise ValueError(f"无法解析发生时间: {s!r}")
        dt = now_bj.replace(hour=h, minute=minute, second=0, microsecond=0)
        if dt > now_bj + timedelta(minutes=5):
            dt -= timedelta(days=1)
        return dt, "exact"

    # ③ "刚才/刚刚" → 十分钟前,小时级精度
    if s in ("刚才", "刚刚", "方才"):
        return now_bj - timedelta(minutes=10), "hour"

    # ④ 日偏移前缀 + 可选时段词/钟点("昨天下午"/"昨晚"/"今天 21点"/"昨天")
    day_offset = 0
    rest = s
    for prefix, offset in _DAY_OFFSET.items():
        if s.startswith(prefix):
            day_offset = offset
            rest = s[len(prefix):].strip()
            # "昨晚"/"今晚" 缩合词自带"晚上"语义
            if prefix in ("昨晚", "今晚") and not rest:
                rest = "晚上"
            break
    base_day = (now_bj + timedelta(days=day_offset)).replace(
        second=0, microsecond=0
    )

    if not rest:
        # 只有日期粒度 → 正午代表时刻,day 精度
        return base_day.replace(hour=12, minute=0), "day"

    if rest in _PART_OF_DAY:
        h, minute = _PART_OF_DAY[rest]
        return base_day.replace(hour=h, minute=minute), "part_of_day"

    m = _HHMM_RE.match(rest)
    if m:
        h, minute = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= minute <= 59:
            return base_day.replace(hour=h, minute=minute), "exact"

    m = _CN_CLOCK_RE.match(rest)
    if m:
        h = int(m.group(1))
        tail = m.group(2) or ""
        minute = 30 if tail == "半" else int(tail.rstrip("分")) if tail else 0
        if 0 <= h <= 23 and 0 <= minute <= 59:
            return base_day.replace(hour=h, minute=minute), "exact"

    # ⑤ 裸时段词("下午")
    if s in _PART_OF_DAY:
        h, minute = _PART_OF_DAY[s]
        return now_bj.replace(hour=h, minute=minute, second=0, microsecond=0), "part_of_day"

    raise ValueError(f"无法解析发生时间: {s!r}")


def precision_display(occurred_at: datetime, precision: str, raw: Optional[str] = None) -> str:
    """按精度诚实展示:part_of_day 显示原话时段,不假装精确到分。"""
    # PostgreSQL preserves timezone-aware values, but SQLite's DateTime
    # compatibility path returns a naive datetime.  Stored life-event times
    # are always normalized to Beijing time, so a naive value must be attached
    # to Beijing rather than interpreted in the server's local timezone.
    bj = (
        occurred_at.replace(tzinfo=BEIJING_TZ)
        if occurred_at.tzinfo is None
        else occurred_at.astimezone(BEIJING_TZ)
    )
    if precision == "exact":
        return bj.strftime("%H:%M")
    if precision == "hour":
        return f"约 {bj.strftime('%H:%M')}"
    if precision == "part_of_day":
        return (raw or "").strip() or bj.strftime("%H 时前后")
    return bj.strftime("%m月%d日")
