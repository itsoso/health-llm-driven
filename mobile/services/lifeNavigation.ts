import api from './api';
import type { AxiosRequestConfig } from 'axios';
import type { components } from '../types/api.generated';
import { aiConsentRevision } from './aiConsentState';
import type { LifeWorkspace, LifeData, LifeBackup, LifeVersion } from '../types/lifeNavigation';
export type { LifeWorkspace, LifeData, LifeTask, LifeWeek, LifeReview, LifeFocus, LifeBackup, LifeVersion, LifeOpportunity, LifeQuarter, TrackId } from '../types/lifeNavigation';
// Compile-time wire checks keep native editor fields compatible with generated contracts.
const writeBody = (revision: number, data: LifeData): components['schemas']['LifeWorkspaceWrite'] => ({ expected_revision: revision, data });
const importBody = (revision: number, backup: LifeBackup): components['schemas']['LifeImport'] => ({ expected_revision: revision, backup });
async function request<T>(owner: number, send: (config: AxiosRequestConfig) => Promise<{
    data: T;
}>): Promise<T> {
    const revision = aiConsentRevision();
    const config = { headers: { 'X-Reva-AI-Subject': String(owner) }, __revaConsentRevision: revision } as AxiosRequestConfig;
    const { data } = await send(config);
    if (revision !== aiConsentRevision())
        throw new Error('登录状态已变化，请重新打开导航。');
    return data;
}
export const fetchLifeWorkspace = (owner: number) => request(owner, config => api.get<LifeWorkspace>('/life-navigation/workspace', config));
export const saveLifeWorkspace = (owner: number, revision: number, data: LifeData) => request(owner, config => api.put<LifeWorkspace>('/life-navigation/workspace', writeBody(revision, data), config));
export const fetchLifeHistory = (owner: number) => request(owner, config => api.get<LifeVersion[]>('/life-navigation/history', config));
export const fetchLifeBackup = (owner: number) => request(owner, config => api.get<LifeBackup>('/life-navigation/backup', config));
export const restoreLifeWorkspace = (owner: number, revision: number, expectedRevision: number) => request(owner, config => api.post<LifeWorkspace>(`/life-navigation/restore/${revision}`, { expected_revision: expectedRevision }, config));
export const importLifeBackup = (owner: number, revision: number, backup: LifeBackup) => request(owner, config => api.post<LifeWorkspace>('/life-navigation/import', importBody(revision, backup), config));
