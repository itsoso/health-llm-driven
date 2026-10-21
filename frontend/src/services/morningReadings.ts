import { api } from './api/client';
import type { components } from '@/types/api.generated';

export type MorningReadingItem = components['schemas']['MorningReadingItem'];
export type MorningReadingList = components['schemas']['MorningReadingList'];
export type MorningReadingDetail = components['schemas']['MorningReadingDetail'];
const config = (owner: number, signal?: AbortSignal) => ({ headers: { 'X-Reva-AI-Subject': String(owner) }, signal });
export async function getMorningReadings(owner: number, offset: number, signal?: AbortSignal): Promise<MorningReadingList> {
  return (await api.get('/life-navigation/morning-readings', { ...config(owner, signal), params: { offset } })).data;
}
export async function getMorningReading(owner: number, id: string, signal?: AbortSignal): Promise<MorningReadingDetail> {
  return (await api.get(`/life-navigation/morning-readings/${encodeURIComponent(id)}`, config(owner, signal))).data;
}
