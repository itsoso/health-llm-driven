import api, { BASE_URL } from './api';
import * as Location from 'expo-location';
import { aiConsentRevision } from './aiConsentState';

export const journeySessionRevision = aiConsentRevision;
export function assertJourneySession(revision: number) {
  if (revision !== aiConsentRevision()) throw new Error('登录状态已改变，请重新打开这一路');
}
function sessionConfig(revision: number) {
  assertJourneySession(revision);
  return { __revaConsentRevision: revision } as Record<string, unknown>;
}

export type JourneyKind = 'diet' | 'life_event' | 'chat_photo';
export interface JourneyImage { key: string; url: string }
export interface JourneyPlaceBase {
  id: number; kind: JourneyKind; source_id: number; city: string; local_date: string;
  timezone: string; location_source: 'manual' | 'device'; version: number;
}
export interface JourneyPlace extends JourneyPlaceBase {
  title: string; images: JourneyImage[]; image_status: 'ready' | 'unavailable' | 'none';
}
export interface JourneySource {
  kind: JourneyKind; source_id: number; title: string; suggested_date: string;
  date_basis: 'record' | 'message'; images: JourneyImage[];
  image_status: JourneyPlace['image_status']; place: JourneyPlaceBase | null;
}
export interface JourneyPage<T> { items: T[]; total: number; offset: number; limit: number }
export interface JourneyExportItem { city: string; local_date: string; kind: JourneyKind; images: JourneyImage[] }
export interface JourneyExport { month: string; items: JourneyExportItem[] }
export interface JourneyExportSelection { place_id: number; version: number; image_keys: string[] }
export const JOURNEY_LABELS: Record<JourneyKind, string> = { diet: '饮食', life_event: '生活片段', chat_photo: '聊天照片' };
export const JOURNEY_MAX_HEIGHT = 16000;
export const JOURNEY_WIDTH = 360;

export function journeyToday(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}
export function isJourneyDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
export function shiftJourneyMonth(month: string, delta: number): string {
  const [year, number] = month.split('-').map(Number);
  const date = new Date(Date.UTC(year, number - 1 + delta, 1));
  return date.toISOString().slice(0, 7);
}
export function journeyImageSource(uri: string, token: string | null) {
  const url = new URL(uri, BASE_URL);
  const trusted = new URL(BASE_URL);
  if (!token || url.protocol !== 'https:' || url.origin !== trusted.origin || url.username || url.password || url.search || url.hash
    || !/^\/api\/v\d+\/upload\/files\/(chat|diet)\//.test(url.pathname)
    || /%2f|%5c|%2e/i.test(url.pathname)) throw new Error('照片地址无法安全验证');
  return { uri: url.toString(), headers: { Authorization: `Bearer ${token}` } };
}
export function exportSelection(places: JourneyPlace[], selection: Record<number, string[]>): JourneyExportSelection[] {
  const selected = places.filter(place => Object.prototype.hasOwnProperty.call(selection, place.id));
  if (selected.length > 30) throw new Error('每次最多选择 30 个片段');
  return selected.map(place => ({ place_id: place.id, version: place.version, image_keys: [...selection[place.id]] }));
}
/** Defense in depth: never spread private API records into the share renderer. */
export function projectJourneyExport(data: any): JourneyExport {
  if (!data || !/^\d{4}-\d{2}$/.test(data.month) || !Array.isArray(data.items) || !data.items.length || data.items.length > 30) throw new Error('预览数据无效');
  return { month: data.month, items: data.items.map((item: any) => {
    if (typeof item.city !== 'string' || !item.city.trim() || item.city.length > 80 || !isJourneyDate(item.local_date) || item.local_date.slice(0, 7) !== data.month || !Object.prototype.hasOwnProperty.call(JOURNEY_LABELS, item.kind) || !Array.isArray(item.images)) throw new Error('预览数据无效');
    return { city: item.city, local_date: item.local_date, kind: item.kind, images: item.images.map((image: any) => {
      if (typeof image.key !== 'string' || typeof image.url !== 'string') throw new Error('预览照片无效');
      return { key: image.key, url: image.url };
    }) };
  }) };
}
/** Coordinates stay inside the system geocoder; no profile or server writes. */
export async function locateJourneyCity(consent: boolean, date: string, today: string, assertActive: () => void = () => {}): Promise<string> {
  if (!consent || !isJourneyDate(date) || date !== today) throw new Error('历史日期请手动填写城市');
  assertActive();
  const permission = await Location.requestForegroundPermissionsAsync();
  assertActive();
  if (!permission.granted) throw new Error('未授权定位，仍可手动填写城市');
  const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  assertActive();
  const [place] = await Location.reverseGeocodeAsync({ latitude: position.coords.latitude, longitude: position.coords.longitude });
  assertActive();
  const city = place?.city || place?.subregion;
  if (!city) throw new Error('暂时无法识别城市，请手动填写');
  return city;
}
const root = '/journey';
export const journeyAPI = {
  async month(month: string, offset = 0, revision = aiConsentRevision()): Promise<JourneyPage<JourneyPlace>> {
    return (await api.get(`${root}/month`, { ...sessionConfig(revision), params: { month, offset, limit: 30 } })).data;
  },
  async sources(kind: JourneyKind, month: string, timezone: string, offset = 0, revision = aiConsentRevision()): Promise<JourneyPage<JourneySource>> {
    return (await api.get(`${root}/sources`, { ...sessionConfig(revision), params: { kind, month, timezone, offset, limit: 30 } })).data;
  },
  async save(source: JourneySource, body: { city: string; local_date: string; timezone: string; location_source: 'manual' | 'device'; expected_version: number; confirmed: true }, revision = aiConsentRevision()): Promise<JourneyPlace> {
    return (await api.put(`${root}/places/${source.kind}/${source.source_id}`, body, sessionConfig(revision))).data;
  },
  async remove(place: JourneyPlace, revision = aiConsentRevision()): Promise<void> { await api.delete(`${root}/places/${place.id}`, { ...sessionConfig(revision), params: { expected_version: place.version } }); },
  async preview(items: JourneyExportSelection[], revision = aiConsentRevision()): Promise<JourneyExport> {
    return projectJourneyExport((await api.post(`${root}/export-preview`, { items }, sessionConfig(revision))).data);
  },
};
