import { getToken } from './auth';

const SAFE_SUBJECT = /^[a-zA-Z0-9_-]{1,64}$/;

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return globalThis.atob(padded);
  } catch {
    return null;
  }
}

/** The JWT is already sourced from authenticated SecureStore; only its stable subject is used. */
export function authStorageScopeFromToken(token: string): string | null {
  const payload = String(token || '').split('.')[1];
  if (!payload) return null;
  const decoded = decodeBase64Url(payload);
  if (!decoded) return null;
  try {
    const subject = String(JSON.parse(decoded)?.sub ?? '').trim();
    return SAFE_SUBJECT.test(subject) ? `user-${subject}` : null;
  } catch {
    return null;
  }
}

export async function getAuthStorageScope(): Promise<string> {
  const scope = authStorageScopeFromToken((await getToken()) || '');
  if (!scope) throw new Error('auth_storage_scope_unavailable');
  return scope;
}
