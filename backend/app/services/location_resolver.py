"""
Effective Location Resolver — 位置字段单一事实之主.

历史问题: profile.city / detected_city / manual_city + use_manual_location 散在 13 处
backend 调用方各自实现优先级. 有的看 flag 有的不看, 有的把 detected_city (区/县)
当主名, 有的硬写 "北京"/"杭州" default. 用户出差 / 切换地区时各处看到不一致结果.

这个 resolver 把"用户当前有效位置"语义收口到一个纯函数, 所有 backend 读源都该
经过它, 不再各搞一套.

约定:
- city: 优先级 manual (use_manual_location=True 且 manual_city 非空)
        → detected_region 去末尾"市/省" (后者是 qweather adm1 = 城市级)
        → detected_city (district 兜底, 如"海淀")
        → None (调用方自己判断怎么 fallback, 不再硬编默认城市)
- lat/lon: 优先 detected_lat/lon (GPS / IP 反查时存的精确坐标)
- source: 'manual' | 'gps' | 'ip' | 'unknown'
  * 'manual' = use_manual_location=True 且 manual_city 非空
  * 'gps'    = 有 detected_lat/lon (gps-location 端点写的, 最精)
  * 'ip'     = 仅有 detected_city/region (老 IP 反查, 没坐标)
  * 'unknown' = 三个都空, city=None
- updated_at: ISO 字符串. manual 没单独时间戳, 用 profile.updated_at; 其它走 location_updated_at
- stale_minutes: 距 updated_at 多少分钟. None = 没时间戳
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, TypedDict


class EffectiveLocation(TypedDict):
    city: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    source: str  # 'manual' | 'gps' | 'ip' | 'unknown'
    updated_at: Optional[str]
    stale_minutes: Optional[int]


def _strip_admin_suffix(name: Optional[str]) -> Optional[str]:
    """'北京市' → '北京', '浙江省' → '浙江'. 空值原样."""
    if not name:
        return None
    s = name.strip()
    if s.endswith("市") or s.endswith("省"):
        return s[:-1] or None
    return s


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _stale_minutes(dt: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cur = now or datetime.now(timezone.utc)
    delta = cur - dt
    return max(0, int(delta.total_seconds() // 60))


def resolve_effective_location(
    profile, now: Optional[datetime] = None,
) -> EffectiveLocation:
    """从 UserProfile 派生有效位置. 纯函数, 不查 DB.

    profile 是 UserProfile ORM 实例 (或任何带相同属性名的对象, 测试 stub 也行).
    传 None 返回全空 unknown.
    """
    if profile is None:
        return EffectiveLocation(
            city=None, lat=None, lon=None,
            source="unknown", updated_at=None, stale_minutes=None,
        )

    use_manual = bool(getattr(profile, "use_manual_location", False))
    manual_city = (getattr(profile, "manual_city", None) or "").strip() or None

    detected_lat = getattr(profile, "detected_lat", None)
    detected_lon = getattr(profile, "detected_lon", None)
    detected_region = (getattr(profile, "detected_region", None) or "").strip() or None
    detected_city = (getattr(profile, "detected_city", None) or "").strip() or None
    stored_source = (getattr(profile, "detected_source", None) or "").strip() or None

    # 优先级: manual → detected_region 去市/省 → detected_city (district)
    city: Optional[str] = None
    source = "unknown"
    if use_manual and manual_city:
        city = manual_city
        source = "manual"
    else:
        # 非手动模式: 优先用 detected_region 派生的城市级 (如"北京市" → "北京")
        # 退回到 detected_city (district / qweather loc.name, 如"海淀")
        city = _strip_admin_suffix(detected_region) or detected_city
        # 信任 stored_source (writer 写时 stamp); legacy 行 (NULL) 才走启发式.
        if stored_source in ("gps", "ip"):
            source = stored_source
        elif detected_lat is not None and detected_lon is not None:
            source = "gps"  # legacy backfill safety net
        elif city:
            source = "ip"
        else:
            source = "unknown"

    # lat/lon — 仅当非手动模式时有意义 (manual 用户的 city 字符串无对应坐标)
    lat = None if use_manual and manual_city else detected_lat
    lon = None if use_manual and manual_city else detected_lon

    # updated_at: GPS/IP 用 location_updated_at; manual 没专属字段, 用 profile.updated_at
    if source == "manual":
        updated = getattr(profile, "updated_at", None)
    else:
        updated = getattr(profile, "location_updated_at", None) or getattr(profile, "updated_at", None)

    return EffectiveLocation(
        city=city,
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        source=source,
        updated_at=_to_iso(updated),
        stale_minutes=_stale_minutes(updated, now),
    )


# stale 阈值 (分钟). manual=None 表示永不过期; gps 12h; ip 6h.
_DEFAULT_MAX_AGE_MIN = {"gps": 12 * 60, "ip": 6 * 60, "manual": None, "unknown": 0}


def get_fresh_city(
    db, user_id: int,
    max_age_min: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """读用户 city, 如果 stale 且有 last_ip 就同步重跑 IP geo 一次, 单用户单日 1 次.

    Celery 早晨任务调度时用 — app 在后台没 GPS 上报, 拿到的 detected_city 可能是
    昨天的城市. 用 last_ip 同步重跑 (~1s) 把当前的城市拿到, 推送才不发错地方天气.

    不走 GPS — 后端拿不到 phone 当前坐标, 只有 phone 上报时的 last_ip 能 fallback.
    GPS 数据由 mobile foreground / BackgroundFetch 通道维护.

    频率限制: 单用户 location_updated_at 已是今天就不刷 (避免早晨 N 个 Celery 任务
    并发刷 N 次).

    失败 fallback: 返 resolver 算出的旧 city. 永远不抛.
    """
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        return None

    loc = resolve_effective_location(profile, now=now)
    thresholds = max_age_min or _DEFAULT_MAX_AGE_MIN
    threshold = thresholds.get(loc["source"])

    cur = now or datetime.now(timezone.utc)

    needs_refresh = (
        threshold is not None
        and loc["stale_minutes"] is not None
        and loc["stale_minutes"] > threshold
        and bool(getattr(profile, "last_ip", None))
    )

    # 单用户单日限速 — location_updated_at 已是今天就跳过 (无论刷新成不成).
    if needs_refresh:
        last_updated = getattr(profile, "location_updated_at", None)
        if last_updated:
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            if last_updated.date() == cur.date():
                needs_refresh = False

    if not needs_refresh:
        return loc["city"]

    # 同步 re-geo. 不阻塞主任务: 失败就用旧 city.
    try:
        import asyncio
        from app.services.ip_geolocation import get_geolocation_service
        new_loc = asyncio.run(get_geolocation_service().get_location_from_ip(profile.last_ip))
        if new_loc and new_loc.city:
            profile.detected_city = new_loc.city
            profile.detected_region = new_loc.region
            profile.detected_country = new_loc.country
            profile.detected_source = "ip"
            profile.location_updated_at = cur
            db.commit()
            # re-resolve 拿规范化后的 city (region 去市/省)
            return resolve_effective_location(profile, now=now)["city"]
    except Exception:
        # 限速失败/网络炸 → 用旧 city, 不打断推送任务
        pass

    return loc["city"]
