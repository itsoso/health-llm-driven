import * as Location from 'expo-location';
import api from './api';
import { aiConsentRevision } from './aiConsentState';

export const SHARE_LOCATION_CONSENT = 'amap-share-location-v1';
export type SharePlace = { id: string; name: string; address: string; label: string; distance_m: number | null };
export type SharePlaces = { items: SharePlace[]; suggested_id: string | null };
export type ShareLocationContext = {
  consent: boolean; revision: number; signal: AbortSignal; assertActive: () => void;
};
class ShareLocationError extends Error {}
const stopped = () => new ShareLocationError('本次定位已停止，请重新查询或手动填写');

function check(context: ShareLocationContext) {
  if (!context.consent) throw new ShareLocationError('请先同意本次高德地点查询，或直接手动填写');
  if (context.signal.aborted || context.revision !== aiConsentRevision()) throw stopped();
  context.assertActive();
}

// Expo's one-shot GPS promise cannot be cancelled. Detach its result on timeout
// or abort, and check again before any coordinate egress.
function bounded<T>(promise: Promise<T>, signal: AbortSignal, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => { cleanup(); reject(stopped()); };
    const timer = setTimeout(() => { cleanup(); reject(new ShareLocationError('定位或查询超时，请重试或手动填写')); }, ms);
    const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); };
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    promise.then(value => { cleanup(); resolve(value); }, () => { cleanup(); reject(new ShareLocationError('定位暂不可用，请检查权限或手动填写')); });
  });
}

export function shareLocationErrorMessage(error: unknown): string {
  if (error instanceof ShareLocationError) return error.message;
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  if (status === 429) return '地点查询太频繁，请稍后重试或手动填写';
  if (status === 401 || status === 403) return '登录或查询授权已失效，请重新打开分享页面';
  if (status === 422) return '定位或搜索条件无效，请重新查询或手动填写';
  return '地点服务暂不可用，请稍后重试或手动填写';
}

function project(data: unknown): SharePlaces {
  const value = data as SharePlaces;
  if (!value || !Array.isArray(value.items) || value.items.length > 10) throw new ShareLocationError('地点查询结果无效，请手动填写');
  const items = value.items.map(item => {
    if (!item || typeof item.id !== 'string' || !item.id || item.id.length > 100
      || typeof item.name !== 'string' || !item.name.trim() || item.name.length > 200
      || typeof item.address !== 'string' || item.address.length > 500
      || typeof item.label !== 'string' || !item.label.trim() || [...item.label].length > 40
      || (item.distance_m !== null && (typeof item.distance_m !== 'number' || !Number.isFinite(item.distance_m) || item.distance_m < 0))) {
      throw new ShareLocationError('地点查询结果无效，请手动填写');
    }
    return { id: item.id, name: item.name, address: item.address, label: item.label, distance_m: item.distance_m };
  });
  if (new Set(items.map(item => item.id)).size !== items.length) throw new ShareLocationError('地点查询结果无效，请手动填写');
  return { items, suggested_id: items.some(item => item.id === value.suggested_id) ? value.suggested_id : null };
}

async function query(path: string, payload: Record<string, unknown>, context: ShareLocationContext): Promise<SharePlaces> {
  check(context);
  try {
    const response = await api.post(`/share-location/${path}`, { ...payload, consent: SHARE_LOCATION_CONSENT }, {
      signal: context.signal, timeout: 15000, __revaConsentRevision: context.revision,
    } as Parameters<typeof api.post>[2]);
    check(context);
    return project(response.data);
  } catch (error) {
    // Never propagate Axios config/response bodies, which can contain coordinates.
    throw new ShareLocationError(shareLocationErrorMessage(error));
  }
}

export async function nearbyShareLocations(context: ShareLocationContext): Promise<SharePlaces> {
  check(context);
  const permission = await bounded(Location.requestForegroundPermissionsAsync(), context.signal, 60000);
  check(context);
  if (!permission.granted) throw new ShareLocationError('未授权定位，仍可搜索地点或手动填写');
  const position = await bounded(Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }), context.signal, 15000);
  check(context);
  const { latitude, longitude, accuracy } = position.coords;
  if (!Number.isFinite(latitude) || Math.abs(latitude) > 90 || !Number.isFinite(longitude) || Math.abs(longitude) > 180
    || typeof accuracy !== 'number' || !Number.isFinite(accuracy) || accuracy <= 0 || accuracy > 200) {
    throw new ShareLocationError('定位精度不足，请开启精确位置后重试，或搜索、手动填写');
  }
  if (!Number.isFinite(position.timestamp) || Date.now() - position.timestamp > 120000 || position.timestamp - Date.now() > 10000) {
    throw new ShareLocationError('定位已过期，请重新定位或手动填写');
  }
  return query('nearby', { latitude, longitude, accuracy_m: accuracy, captured_at: new Date(position.timestamp).toISOString() }, context);
}

export async function searchShareLocations(keyword: string, context: ShareLocationContext): Promise<SharePlaces> {
  check(context);
  const queryText = keyword.trim();
  if (!queryText || [...queryText].length > 80 || /[\u0000-\u001f\u007f]/.test(queryText)) throw new ShareLocationError('请输入 1–80 字的餐厅或地址');
  // A text-only lookup never requests GPS and does not inherit profile location.
  return query('search', { keyword: queryText }, context);
}
