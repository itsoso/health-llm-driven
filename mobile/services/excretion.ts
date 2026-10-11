import type { AxiosRequestConfig } from 'axios';
import api, { BASE_URL } from './api';
import { aiConsentRevision } from './aiConsentState';
import type { components } from '../types/api.generated';

export type BowelRecordInput = components['schemas']['ExcretionRecordCreate'] & {
  record_time: string;
  type: 'bowel';
  client_request_id: string;
};
export type BowelRecord = components['schemas']['ExcretionRecordResponse'];
export interface BowelSession { owner: number; revision: number }
type BowelRequestConfig = Pick<AxiosRequestConfig, 'headers'> & { __revaConsentRevision: number };

async function scoped<T>(session: BowelSession, send: (config: BowelRequestConfig) => Promise<{ data: T }>): Promise<T> {
  if (!Number.isSafeInteger(session.owner) || session.owner <= 0 || session.revision !== aiConsentRevision()) {
    throw new Error('auth_session_changed');
  }
  const config: BowelRequestConfig = {
    headers: { 'X-Reva-AI-Subject': String(session.owner) },
    __revaConsentRevision: session.revision,
  };
  const { data } = await send(config);
  if (session.revision !== aiConsentRevision()) throw new Error('auth_session_changed');
  return data;
}

function owned(record: BowelRecord, session: BowelSession): BowelRecord {
  if (record.user_id !== session.owner || !Number.isSafeInteger(record.id) || record.id <= 0) throw new Error('record_owner_mismatch');
  return record;
}
export const listBowelRecords = async (session: BowelSession, date: string) => (await scoped<BowelRecord[]>(session,
  config => api.get('/excretion/records/me', { ...config, params: { type: 'bowel', start_date: date, end_date: date, limit: 100 } }))).map(record => owned(record, session));
export const getBowelRecord = async (session: BowelSession, id: number) => owned(await scoped<BowelRecord>(session,
  config => api.get(`/excretion/records/${id}`, config)), session);
export const createBowelRecord = async (session: BowelSession, input: BowelRecordInput) => owned(await scoped<BowelRecord>(session,
  config => api.post('/excretion/records', input, config)), session);

export async function uploadBowelPhoto(session: BowelSession, asset: { uri: string; mimeType?: string | null; fileName?: string | null }): Promise<string> {
  const form = new FormData();
  form.append('category', 'medical');
  form.append('file', { uri: asset.uri, name: asset.fileName || 'bowel.jpg', type: asset.mimeType || 'image/jpeg' } as any);
  const result = await scoped<{ success: boolean; filename: string }>(session, config => api.post('/upload/image', form,
    { ...config, headers: { ...config.headers, 'Content-Type': 'multipart/form-data' }, timeout: 60_000 }));
  if (!result.success || !result.filename.startsWith(`medical/${session.owner}/`)) throw new Error('private_upload_failed');
  return result.filename;
}

export function bowelPhotoUrl(url: string): string {
  // Only backend-issued relative private medical URLs are displayed.
  if (!/^\/api\/v1\/upload\/files\/medical\/\d+\/[^/?]+\?/.test(url)) throw new Error('invalid_private_photo_url');
  return `${BASE_URL.replace(/\/api\/?$/, '')}${url}`;
}
