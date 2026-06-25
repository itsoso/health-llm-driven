/**
 * 地理位置 / 天气定位偏好 (G-loc, 2026-05-06).
 *
 * 流程:
 *   - GET /profile/me 读 manual_location + use_manual_location 状态
 *   - PUT /profile/me/manual-location 提交手动城市 (后端会清旧 city 天气/AQI 缓存)
 */
import api from './api';
import * as Location from 'expo-location';

export interface ManualLocationPayload {
  use_manual_location: boolean;
  city: string | null;
  region?: string | null;
  country?: string | null;
}

export interface ManualLocationResponse {
  success: boolean;
  use_manual_location: boolean;
  manual_location: {
    city: string | null;
    region: string | null;
    country: string | null;
  };
  detected_location: {
    city: string | null;
    region: string | null;
    country: string | null;
  };
}

export async function updateManualLocation(payload: ManualLocationPayload): Promise<ManualLocationResponse> {
  const resp = await api.put<ManualLocationResponse>('/profile/me/manual-location', payload);
  return resp.data;
}

/** 让后端按 IP 重新检测一次城市. 用户在新城市但还没自动同步时可调. */
export async function refreshDetectedLocation(): Promise<{ city: string | null; region: string | null; country: string | null }> {
  const resp = await api.post<{ location?: { city: string; region: string; country: string } }>('/profile/me/refresh-location');
  return resp.data?.location || { city: null, region: null, country: null };
}

/**
 * GPS 定位: 传经纬度给后端反查城市. 比 IP 精到区/县级别.
 * 成功后后端自动清旧/新 city 天气 + AQI 缓存, 并把 detected_city 更新为新城市.
 *
 * 客户端可选传 city/region/country (从 expo-location `reverseGeocodeAsync` 拿的),
 * 后端有 city 就直接信任写, 跳过 qweather GeoAPI 调用 — 去 qweather 单点依赖,
 * 离线/qweather 故障时也能跑.
 */
export async function updateGPSLocation(
  lat: number, lon: number,
  hint?: { city?: string | null; region?: string | null; country?: string | null },
): Promise<{ city: string | null; region: string | null; country: string | null }> {
  const resp = await api.post<{ location?: { city: string; region: string; country: string } }>(
    '/profile/me/gps-location',
    { lat, lon, ...(hint || {}) },
  );
  return resp.data?.location || { city: null, region: null, country: null };
}

/**
 * 客户端用 iOS CLGeocoder (Android Geocoder) 反查 lat/lon → city.
 * 离线可用 (iOS 系统库缓存), 失败返空对象. 永不抛 — 调用方都期望 fallback 到后端.
 *
 * 返回字段透传给 backend `/me/gps-location` 的 city/region/country hint. backend 看到
 * city 非空就跳过 qweather, 直接信任写入. 是去 qweather 单点依赖的核心.
 *
 * 注意: PRC 用户 iOS 偶尔返英文 "Beijing" — backend 检测非中文 + country=中国
 * 就丢弃 hint 走 qweather 兜底, 客户端这里不预先过滤.
 */
export async function reverseGeocodeOnDevice(lat: number, lon: number): Promise<{
  city?: string; region?: string; country?: string;
}> {
  try {
    const results = await Location.reverseGeocodeAsync({ latitude: lat, longitude: lon });
    const place = results?.[0];
    if (!place) return {};
    return {
      city: place.city || place.subregion || undefined,
      region: place.region || undefined,
      country: place.country || undefined,
    };
  } catch {
    return {};
  }
}

// ── 时区: 跟随设备地理位置时区 (自动) + 手动锁定 (override) ────────────────
// 生效优先级 (后端 resolve_timezone_name): manual_timezone → detected_timezone → 默认中国.
// 用药时长 / 随访到期等"今天"按生效时区的日历日算.

export interface EffectiveTimezone {
  timezone: string;                                        // 当前生效 IANA 时区
  source: 'manual' | 'detected' | 'profile' | 'default';   // 来源
  detected_timezone: string | null;                        // 设备/位置检测到的
  manual_timezone: string | null;                          // 手动锁定的 (非空=已锁)
}

/**
 * 设备当前时区 (IANA, 如 Asia/Shanghai) —— 由系统按地理位置解析.
 * 纯 JS (Intl), 无 native 依赖. 取不到 / 解析失败返 null (调用方跳过上报).
 */
export function getDeviceTimezone(): string | null {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return tz && tz.length > 1 ? tz : null;
  } catch {
    return null;
  }
}

/** 上报设备时区 → 写 detected_timezone (用户没手动锁定时即生效时区). */
export async function reportDeviceTimezone(tz: string): Promise<EffectiveTimezone> {
  const resp = await api.post<EffectiveTimezone>('/profile/me/device-timezone', { timezone: tz });
  return resp.data;
}

/** 手动锁定时区; 传 null 解锁, 恢复自动跟随设备. */
export async function setManualTimezone(tz: string | null): Promise<EffectiveTimezone> {
  const resp = await api.put<EffectiveTimezone>('/profile/me/manual-timezone', { timezone: tz });
  return resp.data;
}

/** 读当前生效时区 + 来源. */
export async function getEffectiveTimezone(): Promise<EffectiveTimezone> {
  const resp = await api.get<EffectiveTimezone>('/profile/me/effective-timezone');
  return resp.data;
}
