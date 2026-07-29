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
  expoAppVersion?: string | null;
  expoBuildVersion?: string | null;
};

export type AppUpdateTelemetryContext = {
  platform: string;
  channel: string;
  runtime: string;
  native_build: string;
  update_id?: string;
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
  expoAppVersion: Constants.expoConfig?.version,
  expoBuildVersion: Constants.expoConfig?.ios?.buildNumber,
}): string {
  const version = source.nativeAppVersion?.trim() || source.expoAppVersion?.trim();
  const build = source.nativeBuildVersion?.trim() || source.expoBuildVersion?.trim();
  if (version && build) return `${version} (${build})`;
  return version || build || '未知版本';
}

/** Only expose release identity fields; never include user or health content. */
export function getAppUpdateTelemetryContext(): AppUpdateTelemetryContext {
  const updateId = typeof Updates.updateId === 'string' ? Updates.updateId.trim() : '';
  return {
    platform: Platform.OS,
    channel: typeof Updates.channel === 'string' && Updates.channel.trim()
      ? Updates.channel.trim()
      : 'unknown',
    runtime: typeof Updates.runtimeVersion === 'string' && Updates.runtimeVersion.trim()
      ? Updates.runtimeVersion.trim()
      : 'unknown',
    native_build: Constants.nativeBuildVersion?.trim() || 'unknown',
    ...(updateId ? { update_id: updateId } : {}),
  };
}

export function getAppUpdateLaunchSource(): 'embedded' | 'ota' | 'emergency' | 'unknown' {
  if (Updates.isEmergencyLaunch) return 'emergency';
  if (Updates.isEmbeddedLaunch) return 'embedded';
  if (Updates.updateId) return 'ota';
  return 'unknown';
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
