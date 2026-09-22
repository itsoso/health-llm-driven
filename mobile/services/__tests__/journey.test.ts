jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn(), post: jest.fn(), delete: jest.fn() }, BASE_URL: 'https://health.executor.life/api' }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), getCurrentPositionAsync: jest.fn(), reverseGeocodeAsync: jest.fn(), Accuracy: { Balanced: 3 } }));
import api from '../api';
import * as Location from 'expo-location';
import { isJourneyDate, shiftJourneyMonth, journeyImageSource, exportSelection, projectJourneyExport, locateJourneyCity, journeyAPI, journeySessionRevision } from '../journey';
import { setAIConsentIdentity } from '../aiConsentState';

describe('journey safety contract', () => {
  beforeEach(() => jest.clearAllMocks());
  it('validates real calendar dates, not normalized overflow', () => {
    expect(isJourneyDate('2026-02-29')).toBe(false);
    expect(isJourneyDate('2024-02-29')).toBe(true);
    expect(isJourneyDate('2026-9-2')).toBe(false);
    expect(shiftJourneyMonth('2026-01', -1)).toBe('2025-12');
  });
  it('never attaches auth to foreign or non-private origins', () => {
    expect(() => journeyImageSource('https://evil.example/api/v1/upload/files/chat/1/a.jpg', 'token')).toThrow();
    expect(() => journeyImageSource('https://health.executor.life/public/a.jpg', 'token')).toThrow();
    expect(journeyImageSource('https://health.executor.life/api/v1/upload/files/chat/1/a.jpg', 'token').headers).toEqual({ Authorization: 'Bearer token' });
    expect(journeyImageSource('/api/v1/upload/files/chat/1/a.jpg', 'token').uri).toBe('https://health.executor.life/api/v1/upload/files/chat/1/a.jpg');
    expect(() => journeyImageSource('/api/v1/upload/files/chat/1/a.jpg?token=capability', 'token')).toThrow();
    expect(() => journeyImageSource('/api/v1/upload/files/chat/1/a.jpg#fragment', 'token')).toThrow();
  });
  it('starts with no selected records/photos and caps export count', () => {
    expect(exportSelection([], {})).toEqual([]);
    expect(exportSelection([{ id: 2, version: 3 } as any], { 2: [] })).toEqual([{ place_id: 2, version: 3, image_keys: [] }]);
    expect(() => exportSelection(Array.from({ length: 31 }, (_, id) => ({ id, version: 1 } as any)), Object.fromEntries(Array.from({ length: 31 }, (_, id) => [id, []])))).toThrow();
  });
  it('projects only the export whitelist, never title/health/raw source', () => {
    expect(projectJourneyExport({ month: '2026-09', secret: 'x', items: [{ city: '北京', local_date: '2026-09-22', kind: 'diet', title: 'private', images: [] }] })).toEqual({ month: '2026-09', items: [{ city: '北京', local_date: '2026-09-22', kind: 'diet', images: [] }] });
  });
  it('rejects prototype kinds, invalid month grouping and oversized city inputs', () => {
    const make = (override: any) => ({ month: '2026-09', items: [{ city: '北京', local_date: '2026-09-22', kind: 'diet', images: [], ...override }] });
    expect(() => projectJourneyExport(make({ kind: 'toString' }))).toThrow();
    expect(() => projectJourneyExport(make({ local_date: '2026-08-22' }))).toThrow();
    expect(() => projectJourneyExport(make({ city: '北'.repeat(81) }))).toThrow();
  });
  it('does not request permission before consent or for historical dates', async () => {
    await expect(locateJourneyCity(false, '2026-09-21', '2026-09-22')).rejects.toThrow();
    await expect(locateJourneyCity(true, '2026-09-21', '2026-09-22')).rejects.toThrow();
    expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  });
  it('requests once, resolves city locally without backend/profile mutation', async () => {
    (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: true });
    (Location.getCurrentPositionAsync as jest.Mock).mockResolvedValue({ coords: { latitude: 1, longitude: 2 } });
    (Location.reverseGeocodeAsync as jest.Mock).mockResolvedValue([{ city: '北京', street: 'secret' }]);
    await expect(locateJourneyCity(true, '2026-09-22', '2026-09-22')).resolves.toBe('北京');
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
  });
  it('uses version bound preview and explicit pagination', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: { items: [], total: 42, offset: 30, limit: 30 } });
    await journeyAPI.sources('chat_photo', '2026-09', 'Asia/Shanghai', 30);
    expect(api.get).toHaveBeenCalledWith('/journey/sources', expect.objectContaining({ params: { kind: 'chat_photo', month: '2026-09', timezone: 'Asia/Shanghai', offset: 30, limit: 30 } }));
  });
  it('rejects stale-session writes BEFORE contacting backend', async () => {
    const old = journeySessionRevision();
    setAIConsentIdentity('new-account');
    await expect(journeyAPI.save({ kind: 'diet', source_id: 1 } as any, { city: '北京', local_date: '2026-09-22', timezone: 'Asia/Shanghai', location_source: 'manual', expected_version: 0, confirmed: true }, old)).rejects.toThrow();
    expect(api.put).not.toHaveBeenCalled();
  });
  it('cancels location after late permission return before GPS/geocoder', async () => {
    (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: true });
    let calls = 0;
    await expect(locateJourneyCity(true, '2026-09-22', '2026-09-22', () => { if (++calls > 1) throw new Error('cancelled'); })).rejects.toThrow('cancelled');
    expect(Location.getCurrentPositionAsync).not.toHaveBeenCalled();
    expect(Location.reverseGeocodeAsync).not.toHaveBeenCalled();
  });
});
