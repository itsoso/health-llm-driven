import Constants from 'expo-constants';
import * as Updates from 'expo-updates';
import { Platform } from 'react-native';

export type AppLaunchSource = 'embedded' | 'ota' | 'unknown';

export type AppDiagnosticRow = {
  id: string;
  label: string;
  value: string;
  detail?: string;
};

export type AppDiagnosticsSnapshot = {
  summary: {
    appVersion: string;
    buildNumber: string;
    channel: string;
    runtimeVersion: string;
    launchSource: AppLaunchSource;
  };
  rows: AppDiagnosticRow[];
};

type AppDiagnosticsInput = {
  platform?: string;
  constants?: {
    nativeAppVersion?: string | null;
    nativeBuildVersion?: string | null;
    expoConfig?: Record<string, any> | null;
    easConfig?: Record<string, any> | null;
  };
  updates?: Record<string, any>;
};

function yesNo(value: unknown): string {
  if (value === true) return 'yes';
  if (value === false) return 'no';
  return 'unknown';
}

function asDisplayValue(value: unknown, fallback = 'unknown'): string {
  if (value === null || value === undefined || value === '') return fallback;
  if (value instanceof Date) return value.toISOString();
  return String(value);
}

function detectLaunchSource(updateId: unknown, isEmbeddedLaunch: unknown): AppLaunchSource {
  if (isEmbeddedLaunch === true) return 'embedded';
  if (typeof updateId === 'string' && updateId.length > 0) return 'ota';
  return 'unknown';
}

export function buildAppDiagnosticsSnapshot(input: AppDiagnosticsInput = {}): AppDiagnosticsSnapshot {
  const constants = input.constants ?? Constants;
  const updates = input.updates ?? Updates;
  const expoConfig = constants.expoConfig ?? {};
  const ios = (expoConfig.ios ?? {}) as Record<string, any>;
  const extra = (expoConfig.extra ?? {}) as Record<string, any>;
  const eas = (extra.eas ?? constants.easConfig ?? {}) as Record<string, any>;

  const appVersion = asDisplayValue(constants.nativeAppVersion ?? expoConfig.version);
  const buildNumber = asDisplayValue(constants.nativeBuildVersion ?? ios.buildNumber);
  const channel = asDisplayValue(updates.channel ?? extra.channel);
  const runtimeVersion = asDisplayValue(updates.runtimeVersion ?? expoConfig.runtimeVersion);
  const updateId = updates.updateId ?? null;
  const launchSource = detectLaunchSource(updateId, updates.isEmbeddedLaunch);

  const rows: AppDiagnosticRow[] = [
    { id: 'appName', label: 'App', value: asDisplayValue(expoConfig.name) },
    { id: 'platform', label: 'Platform', value: asDisplayValue(input.platform ?? Platform.OS) },
    { id: 'bundleIdentifier', label: 'Bundle ID', value: asDisplayValue(ios.bundleIdentifier) },
    { id: 'appVersion', label: 'Version', value: appVersion },
    { id: 'buildNumber', label: 'Build', value: buildNumber },
    { id: 'runtimeVersion', label: 'Runtime', value: runtimeVersion },
    { id: 'channel', label: 'Channel', value: channel },
    { id: 'launchSource', label: 'Launch source', value: launchSource },
    { id: 'updateId', label: 'Update ID', value: asDisplayValue(updateId, 'embedded') },
    { id: 'embeddedLaunch', label: 'Embedded launch', value: yesNo(updates.isEmbeddedLaunch) },
    { id: 'emergencyLaunch', label: 'Emergency launch', value: yesNo(updates.isEmergencyLaunch) },
    { id: 'updateCreatedAt', label: 'Update created', value: asDisplayValue(updates.createdAt) },
    { id: 'projectId', label: 'EAS Project ID', value: asDisplayValue(eas.projectId) },
  ];

  return {
    summary: {
      appVersion,
      buildNumber,
      channel,
      runtimeVersion,
      launchSource,
    },
    rows,
  };
}

export function getAppDiagnosticsSnapshot(): AppDiagnosticsSnapshot {
  return buildAppDiagnosticsSnapshot();
}
