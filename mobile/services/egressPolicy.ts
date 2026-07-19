import type { AppMode } from './localIdentity';

let activeMode: AppMode | null = null;
let auditSink: ((code: string) => Promise<void>) | null = null;

export class AppEgressBlockedError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = 'AppEgressBlockedError';
  }
}

export function setAppEgressMode(mode: AppMode | null): void {
  activeMode = mode;
}

export function getAppEgressMode(): AppMode | null {
  return activeMode;
}

export function setAppEgressAuditSink(
  sink: ((code: string) => Promise<void>) | null,
): void {
  auditSink = sink;
}

function blockedError(
  intent: { explicitCloudAI?: boolean },
): AppEgressBlockedError | null {
  if (activeMode === 'cloud_account') return null;
  if (activeMode === 'local_first' && intent.explicitCloudAI) return null;
  if (activeMode === 'strict_local') {
    return new AppEgressBlockedError('strict_local_egress_blocked');
  }
  if (activeMode === 'local_first') {
    return new AppEgressBlockedError('local_first_egress_requires_explicit_ai');
  }
  return new AppEgressBlockedError('app_mode_unknown_egress_blocked');
}

export function assertAppEgressAllowed(
  intent: { explicitCloudAI?: boolean } = {},
): void {
  const error = blockedError(intent);
  if (error) throw error;
}

export async function enforceAppEgressAllowed(
  intent: { explicitCloudAI?: boolean } = {},
): Promise<void> {
  const error = blockedError(intent);
  if (!error) return;
  if (auditSink) await auditSink(error.code);
  throw error;
}
