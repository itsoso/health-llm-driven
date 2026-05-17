/**
 * 地理位置 / 天气定位偏好 (G-loc, 2026-05-06).
 *
 * 流程:
 *   - GET /v1/profile/me 读 manual_location + use_manual_location 状态
 *   - PUT /v1/profile/me/manual-location 提交手动城市 (后端会清旧 city 天气/AQI 缓存)
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
  const resp = await api.put<ManualLocationResponse>('/v1/profile/me/manual-location', payload);
  return resp.data;
}

/** 让后端按 IP 重新检测一次城市. 用户在新城市但还没自动同步时可调. */
export async function refreshDetectedLocation(): Promise<{ city: string | null; region: string | null; country: string | null }> {
  const resp = await api.post<{ location?: { city: string; region: string; country: string } }>('/v1/profile/me/refresh-location');
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
    '/v1/profile/me/gps-location',
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
