type AppEgressMode = 'cloud_account';

let activeMode: AppEgressMode | null = null;

export class AppEgressBlockedError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = 'AppEgressBlockedError';
  }
}

export function setAppEgressMode(mode: AppEgressMode | null): void {
  activeMode = mode;
}

export function getAppEgressMode(): AppEgressMode | null {
  return activeMode;
}

function blockedError(): AppEgressBlockedError | null {
  if (activeMode === 'cloud_account') return null;
  return new AppEgressBlockedError('cloud_session_required');
}

export function assertAppEgressAllowed(
  _intent: { explicitCloudAI?: boolean } = {},
): void {
  const error = blockedError();
  if (error) throw error;
}

export async function enforceAppEgressAllowed(
  _intent: { explicitCloudAI?: boolean } = {},
): Promise<void> {
  const error = blockedError();
  if (error) throw error;
}
