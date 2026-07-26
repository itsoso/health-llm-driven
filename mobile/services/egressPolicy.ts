type AppEgressMode = 'cloud_account';

let activeMode: AppEgressMode | null = null;

export type AppEgressIntent = {
  explicitCloudAI?: boolean;
  cloudSessionBootstrap?: boolean;
  cloudCredentialPresent?: boolean;
};

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

function blockedError(intent: AppEgressIntent): AppEgressBlockedError | null {
  if (
    activeMode === 'cloud_account'
    || intent.cloudSessionBootstrap === true
    || intent.cloudCredentialPresent === true
  ) {
    return null;
  }
  return new AppEgressBlockedError('cloud_session_required');
}

export function assertAppEgressAllowed(
  intent: AppEgressIntent = {},
): void {
  const error = blockedError(intent);
  if (error) throw error;
}

export async function enforceAppEgressAllowed(
  intent: AppEgressIntent = {},
): Promise<void> {
  const error = blockedError(intent);
  if (error) throw error;
}
