import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  createLocalHealthVault,
  deleteLocalHealthVault,
} from '../modules/local-health-kernel';

export type AppMode = 'strict_local' | 'local_first' | 'cloud_account';
export type LocalAppMode = Exclude<AppMode, 'cloud_account'>;

export type AppModePreference = {
  schemaVersion: 1;
  mode: AppMode;
  localIdentityId: string | null;
};

export const APP_MODE_STORAGE_KEY = 'reva_app_mode_preference_v1';
export const LOCAL_RECOVERY_WARNING_KEY = 'reva_local_recovery_warning_v1';

export class LocalIdentityError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = 'LocalIdentityError';
  }
}

function isAppMode(value: unknown): value is AppMode {
  return value === 'strict_local' || value === 'local_first' || value === 'cloud_account';
}

function validatePreference(value: unknown): AppModePreference {
  if (!value || typeof value !== 'object') {
    throw new LocalIdentityError('invalid_local_session_preference');
  }
  const candidate = value as Partial<AppModePreference>;
  const identityValid = candidate.localIdentityId === null
    || (typeof candidate.localIdentityId === 'string' && candidate.localIdentityId.length > 0);
  const localModeHasIdentity = candidate.mode === 'cloud_account'
    || typeof candidate.localIdentityId === 'string';
  if (candidate.schemaVersion !== 1 || !isAppMode(candidate.mode)
      || !identityValid || !localModeHasIdentity) {
    throw new LocalIdentityError('invalid_local_session_preference');
  }
  return {
    schemaVersion: 1,
    mode: candidate.mode,
    localIdentityId: candidate.localIdentityId ?? null,
  };
}

export async function loadAppModePreference(): Promise<AppModePreference | null> {
  const raw = await AsyncStorage.getItem(APP_MODE_STORAGE_KEY);
  if (!raw) return null;
  try {
    return validatePreference(JSON.parse(raw));
  } catch (error) {
    if (error instanceof LocalIdentityError) throw error;
    throw new LocalIdentityError('invalid_local_session_preference');
  }
}

export async function persistAppModePreference(
  preference: AppModePreference,
): Promise<AppModePreference> {
  const valid = validatePreference(preference);
  await AsyncStorage.setItem(APP_MODE_STORAGE_KEY, JSON.stringify(valid));
  return valid;
}

export async function clearAppModePreference(): Promise<void> {
  await AsyncStorage.removeItem(APP_MODE_STORAGE_KEY);
}

export function generateLocalIdentityId(random: () => number = Math.random): string {
  const words = Array.from({ length: 4 }, () => {
    const value = random();
    if (!Number.isFinite(value) || value < 0 || value >= 1) {
      throw new LocalIdentityError('local_identity_random_failed');
    }
    return Math.floor(value * 0x100000000).toString(16).padStart(8, '0');
  });
  return `local-${words.join('-')}`;
}

export async function createPersistedLocalIdentity(
  mode: LocalAppMode,
  generateIdentity: () => string = generateLocalIdentityId,
): Promise<AppModePreference> {
  const localIdentityId = generateIdentity();
  await createLocalHealthVault(localIdentityId);
  const preference: AppModePreference = {
    schemaVersion: 1,
    mode,
    localIdentityId,
  };
  try {
    return await persistAppModePreference(preference);
  } catch (error) {
    try {
      await deleteLocalHealthVault();
    } catch {
      throw new LocalIdentityError('local_identity_rollback_failed');
    }
    throw error;
  }
}

export async function hasSeenLocalRecoveryWarning(): Promise<boolean> {
  return await AsyncStorage.getItem(LOCAL_RECOVERY_WARNING_KEY) === '1';
}

export async function markLocalRecoveryWarningSeen(): Promise<void> {
  await AsyncStorage.setItem(LOCAL_RECOVERY_WARNING_KEY, '1');
}
