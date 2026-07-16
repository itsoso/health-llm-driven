import * as Updates from 'expo-updates';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

export type AppUpdatePhase = 'checking' | 'downloading';
export type AppUpdateDownloadResult = 'disabled' | 'current' | 'ready';

export type AppUpdateAdapter = {
  readonly isEnabled: boolean;
  checkForUpdateAsync: () => Promise<{ isAvailable: boolean }>;
  fetchUpdateAsync: () => Promise<unknown>;
  reloadAsync: () => Promise<void>;
};

type NativeVersionSource = {
  nativeAppVersion?: string | null;
  nativeBuildVersion?: string | null;
};

const expoAppUpdateAdapter: AppUpdateAdapter = {
  get isEnabled() {
    return Platform.OS !== 'web' && Updates.isEnabled;
  },
  checkForUpdateAsync: () => Updates.checkForUpdateAsync(),
  fetchUpdateAsync: () => Updates.fetchUpdateAsync(),
  reloadAsync: () => Updates.reloadAsync(),
};

export function getNativeVersionLabel(source: NativeVersionSource = {
  nativeAppVersion: Constants.nativeAppVersion,
  nativeBuildVersion: Constants.nativeBuildVersion,
}): string {
  const version = source.nativeAppVersion?.trim();
  const build = source.nativeBuildVersion?.trim();
  if (version && build) return `${version} (${build})`;
  return version || build || '未知版本';
}

export async function downloadAvailableUpdate(
  adapter: AppUpdateAdapter = expoAppUpdateAdapter,
  onPhase?: (phase: AppUpdatePhase) => void
): Promise<AppUpdateDownloadResult> {
  if (!adapter.isEnabled) return 'disabled';

  onPhase?.('checking');
  const update = await adapter.checkForUpdateAsync();
  if (!update.isAvailable) return 'current';

  onPhase?.('downloading');
  await adapter.fetchUpdateAsync();
  return 'ready';
}

export async function applyDownloadedUpdate(
  adapter: AppUpdateAdapter = expoAppUpdateAdapter
): Promise<void> {
  if (!adapter.isEnabled) return;
  await adapter.reloadAsync();
}
