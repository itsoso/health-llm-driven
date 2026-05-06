/**
 * 地理位置 / 天气定位偏好 (G-loc, 2026-05-06).
 *
 * 流程:
 *   - GET /v1/profile/me 读 manual_location + use_manual_location 状态
 *   - PUT /v1/profile/me/manual-location 提交手动城市 (后端会清旧 city 天气/AQI 缓存)
 */
import api from './api';

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
