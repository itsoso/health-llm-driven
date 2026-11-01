import type { AxiosRequestConfig } from 'axios';
import { getAuthSessionSnapshot } from './api';
import { aiConsentRevision, hasAIConsentIdentity } from './aiConsentState';

export interface ProgressReadSession {
  owner: number;
  revision: number;
  generation: number;
}

type ProgressReadConfig = Pick<AxiosRequestConfig, 'headers'> & {
  __revaConsentRevision?: number;
};

export function isProgressReadSessionCurrent(session: ProgressReadSession): boolean {
  const current = getAuthSessionSnapshot();
  return (
    Number.isSafeInteger(session.owner) && session.owner > 0 &&
    session.revision === aiConsentRevision() && hasAIConsentIdentity() &&
    current.initialized && Boolean(current.token) && session.generation === current.generation
  );
}

export function assertProgressReadSession(session: ProgressReadSession): void {
  if (!isProgressReadSessionCurrent(session)) {
    throw new Error('auth_session_changed');
  }
}

/** Keep legacy callers compatible; scoped readers reject obsolete responses. */
export async function readProgressForSession<T>(
  session: ProgressReadSession | undefined,
  send: (config: ProgressReadConfig) => Promise<{ data: T }>,
): Promise<T> {
  if (session) assertProgressReadSession(session);
  const config: ProgressReadConfig = session ? {
    headers: { 'X-Reva-AI-Subject': String(session.owner) },
    __revaConsentRevision: session.revision,
  } : {};
  const { data } = await send(config);
  if (session) assertProgressReadSession(session);
  return data;
}
