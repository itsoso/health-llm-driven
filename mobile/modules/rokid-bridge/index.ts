import { Platform, requireNativeModule } from 'expo-modules-core';

export const ROKID_SDK_ARTIFACTS = {
  clientM: 'com.rokid.cxr:client-m:1.2.2',
  clientL: 'com.rokid.cxr:client-l:1.0.3',
} as const;

export type RokidIntegrationMode = 'unavailable' | 'sdk_probe';

export type RokidIntegrationStatus = {
  platform: string;
  bridgeAvailable: boolean;
  hiRokidInstalled: boolean;
  canOpenHiRokid: boolean;
  mode: RokidIntegrationMode;
  sdkArtifacts: typeof ROKID_SDK_ARTIFACTS;
  sdkLinked?: boolean;
  installedPackage?: string | null;
  supportedPackages?: string[];
  sdkClassProbe?: Record<string, boolean>;
  reason?: string;
};

type RokidNativeModule = {
  getIntegrationStatus: () => Promise<Partial<RokidIntegrationStatus>>;
  openHiRokid: () => Promise<boolean>;
};

let cachedNative: RokidNativeModule | null | undefined;

function unavailableStatus(platform: string, reason = 'native_bridge_unavailable'): RokidIntegrationStatus {
  return {
    platform,
    bridgeAvailable: false,
    hiRokidInstalled: false,
    canOpenHiRokid: false,
    mode: 'unavailable',
    sdkArtifacts: ROKID_SDK_ARTIFACTS,
    reason,
  };
}

function getNativeBridge(): RokidNativeModule | null {
  if (Platform.OS !== 'android') {
    return null;
  }
  if (cachedNative !== undefined) {
    return cachedNative;
  }
  try {
    cachedNative = requireNativeModule('RokidBridge') as RokidNativeModule;
  } catch {
    cachedNative = null;
  }
  return cachedNative;
}

export async function getRokidIntegrationStatus(): Promise<RokidIntegrationStatus> {
  const native = getNativeBridge();
  if (!native) {
    return unavailableStatus(Platform.OS);
  }

  try {
    const status = await native.getIntegrationStatus();
    return {
      ...unavailableStatus(Platform.OS, 'native_bridge_ready'),
      ...status,
      bridgeAvailable: status.bridgeAvailable ?? true,
      mode: (status.mode as RokidIntegrationMode | undefined) ?? 'sdk_probe',
      sdkArtifacts: ROKID_SDK_ARTIFACTS,
    };
  } catch (error) {
    return unavailableStatus(
      Platform.OS,
      error instanceof Error ? error.message : 'native_bridge_probe_failed',
    );
  }
}

export async function openHiRokid(): Promise<boolean> {
  const native = getNativeBridge();
  if (!native) {
    return false;
  }
  try {
    return await native.openHiRokid();
  } catch {
    return false;
  }
}
