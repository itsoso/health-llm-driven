import api from './api';

export type GarminHealth = 'healthy' | 'stale' | 'error' | 'unbound';

export interface GarminCredentialStatus {
  bound: boolean;
  health: GarminHealth;
  last_sync_at: string | null;
  minutes_since_last_sync: number | null;
  credentials_valid: boolean | null;
  requires_mfa: boolean;
  last_error: string | null;
  error_count: number;
  sync_enabled?: boolean;
}

export interface GarminCredentialsInput {
  garmin_email: string;
  garmin_password: string;
  is_cn: boolean;
}

export interface GarminConnectionResult {
  success: boolean;
  mfa_required: boolean;
  message: string;
  mfa_session_id?: string | null;
}

export interface GarminMfaResult {
  success: boolean;
  message: string;
  session_id?: string | null;
}

export interface GarminSyncResult {
  status: 'success' | 'skipped' | 'no_data';
  message: string;
  success_count?: number;
  error_count?: number;
  activities_count?: number;
}

export async function fetchGarminStatus(): Promise<GarminCredentialStatus> {
  const response = await api.get('/data-collection/garmin/me/credential-status');
  return response.data;
}

export async function saveGarminCredentials(input: GarminCredentialsInput): Promise<void> {
  await api.post('/auth/garmin/credentials', input);
}

export async function testGarminConnection(
  input: GarminCredentialsInput,
): Promise<GarminConnectionResult> {
  const response = await api.post('/auth/garmin/test-connection', input);
  return response.data;
}

export async function verifyGarminMfa(
  mfaCode: string,
  mfaSessionId: string,
): Promise<GarminMfaResult> {
  const response = await api.post('/auth/garmin/verify-mfa', {
    mfa_code: mfaCode,
    mfa_session_id: mfaSessionId,
  });
  return response.data;
}

export async function syncGarmin(days = 1): Promise<GarminSyncResult> {
  const response = await api.post(`/data-collection/garmin/me/sync?days=${days}`);
  return response.data;
}

export async function setGarminSyncEnabled(enabled: boolean): Promise<void> {
  await api.post(`/auth/garmin/toggle-sync?enabled=${enabled}`);
}

export async function deleteGarminCredentials(): Promise<void> {
  await api.delete('/auth/garmin/credentials');
}

export function garminErrorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)
    ?.response?.data?.detail;
  return typeof detail === 'string' && detail.trim()
    ? detail
    : '操作失败，请稍后重试';
}
