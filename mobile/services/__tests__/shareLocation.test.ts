import api from '../api';
import * as Location from 'expo-location';
import { nearbyShareLocations, searchShareLocations, shareLocationErrorMessage } from '../shareLocation';
import { aiConsentRevision, setAIConsentIdentity } from '../aiConsentState';

jest.mock('../api', () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), getCurrentPositionAsync: jest.fn(), Accuracy: { High: 4 } }));

const result = { items: [{ id: 'p1', name: '示例餐厅', address: '示例路 1 号', label: '示例餐厅', distance_m: 20 }], suggested_id: 'p1' };
function context(consent = true) { return { consent, revision: aiConsentRevision(), signal: new AbortController().signal, assertActive: jest.fn() }; }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }

beforeEach(() => {
  jest.clearAllMocks();
  (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: true });
  (Location.getCurrentPositionAsync as jest.Mock).mockImplementation(async () => ({ timestamp: Date.now(), coords: { latitude: 30, longitude: 120, accuracy: 15 } }));
  (api.post as jest.Mock).mockResolvedValue({ data: result });
});

it('never reads GPS or sends queries without this-session consent', async () => {
  await expect(nearbyShareLocations(context(false))).rejects.toThrow();
  await expect(searchShareLocations('示例餐厅', context(false))).rejects.toThrow();
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  expect(api.post).not.toHaveBeenCalled();
});
it('uses high accuracy and passes only GPS coordinates with revision and consent in JSON', async () => {
  await expect(nearbyShareLocations(context())).resolves.toEqual(result);
  expect(Location.getCurrentPositionAsync).toHaveBeenCalledWith({ accuracy: Location.Accuracy.High });
  expect(api.post).toHaveBeenCalledWith('/share-location/nearby', {
    latitude: 30, longitude: 120, accuracy_m: 15, captured_at: expect.any(String), consent: 'amap-share-location-v1',
  }, expect.objectContaining({ signal: expect.any(Object), __revaConsentRevision: aiConsentRevision() }));
});
it.each([null, 0, -1, 201, NaN])('does not send imprecise coordinates (%s)', async accuracy => {
  (Location.getCurrentPositionAsync as jest.Mock).mockResolvedValue({ timestamp: Date.now(), coords: { latitude: 30, longitude: 120, accuracy } });
  await expect(nearbyShareLocations(context())).rejects.toThrow();
  expect(api.post).not.toHaveBeenCalled();
});
it('rejects stale GPS and denied permission without a backend request', async () => {
  (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValueOnce({ granted: false });
  await expect(nearbyShareLocations(context())).rejects.toThrow();
  expect(Location.getCurrentPositionAsync).not.toHaveBeenCalled();
  (Location.getCurrentPositionAsync as jest.Mock).mockResolvedValue({ timestamp: Date.now() - 130000, coords: { latitude: 30, longitude: 120, accuracy: 10 } });
  await expect(nearbyShareLocations(context())).rejects.toThrow();
  expect(api.post).not.toHaveBeenCalled();
});
it('stops late GPS before sending after account switch or abort', async () => {
  const gps = deferred<any>();
  (Location.getCurrentPositionAsync as jest.Mock).mockReturnValue(gps.promise);
  const ctx = context();
  const pending = nearbyShareLocations(ctx);
  await Promise.resolve(); await Promise.resolve();
  setAIConsentIdentity('different-account');
  gps.resolve({ timestamp: Date.now(), coords: { latitude: 30, longitude: 120, accuracy: 10 } });
  await expect(pending).rejects.toThrow();
  expect(api.post).not.toHaveBeenCalled();
  const controller = new AbortController(); controller.abort();
  await expect(nearbyShareLocations({ ...context(), signal: controller.signal })).rejects.toThrow();
});
it('searches only on explicit submission and validates keyword length', async () => {
  await searchShareLocations(' 示例餐厅 ', context());
  expect(api.post).toHaveBeenCalledWith('/share-location/search', { keyword: '示例餐厅', consent: 'amap-share-location-v1' }, expect.any(Object));
  await expect(searchShareLocations(' ', context())).rejects.toThrow();
  await expect(searchShareLocations('a'.repeat(81), context())).rejects.toThrow();
  expect(api.post).toHaveBeenCalledTimes(1);
});
it('projects whitelisted results and never trusts invalid suggested IDs', async () => {
  (api.post as jest.Mock).mockResolvedValue({ data: { ...result, secret: 'do-not-copy', suggested_id: 'unknown', items: [{ ...result.items[0], latitude: 30 }] } });
  expect(await searchShareLocations('餐厅', context())).toEqual({ ...result, suggested_id: null });
});
it('sanitizes upstream errors instead of exposing Axios payloads and URLs', async () => {
  const raw = { message: 'secret URL', config: { data: 'coordinates' }, response: { status: 503, data: { detail: 'secret' } } };
  expect(shareLocationErrorMessage(raw)).not.toMatch(/secret|coordinates/);
  (api.post as jest.Mock).mockRejectedValue(raw);
  await expect(searchShareLocations('餐厅', context())).rejects.toThrow('地点服务暂不可用');
});
it('times out stalled GPS and ignores its eventual resolution', async () => {
  jest.useFakeTimers();
  try {
    const gps = deferred<any>(); (Location.getCurrentPositionAsync as jest.Mock).mockReturnValue(gps.promise);
    const pending = nearbyShareLocations(context());
    const rejection = expect(pending).rejects.toThrow('超时');
    await jest.advanceTimersByTimeAsync(15001);
    await rejection;
    gps.resolve({ timestamp: Date.now(), coords: { latitude: 30, longitude: 120, accuracy: 10 } });
    await Promise.resolve();
    expect(api.post).not.toHaveBeenCalled();
  } finally { jest.useRealTimers(); }
});
it('rejects a response if the auth session changed while the request was in flight', async () => {
  const response = deferred<any>(); (api.post as jest.Mock).mockReturnValue(response.promise);
  const pending = searchShareLocations('餐厅', context());
  setAIConsentIdentity('another-account');
  response.resolve({ data: result });
  await expect(pending).rejects.toThrow();
});

it('does not start GPS when logout happens during the permission prompt', async () => {
  const permission = deferred<any>();
  (Location.requestForegroundPermissionsAsync as jest.Mock).mockReturnValue(permission.promise);
  const pending = nearbyShareLocations(context());
  setAIConsentIdentity(null);
  permission.resolve({ granted: true });
  await expect(pending).rejects.toThrow();
  expect(Location.getCurrentPositionAsync).not.toHaveBeenCalled();
  expect(api.post).not.toHaveBeenCalled();
});

it('rejects a late backend result after an aborted session even if transport resolves', async () => {
  const response = deferred<any>(); (api.post as jest.Mock).mockReturnValue(response.promise);
  const controller = new AbortController();
  const pending = searchShareLocations('餐厅', { ...context(), signal: controller.signal });
  controller.abort(); response.resolve({ data: result });
  await expect(pending).rejects.toThrow('本次定位已停止');
});
