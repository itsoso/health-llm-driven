import { Platform, requireNativeModule } from 'expo-modules-core';

export const ROKID_SDK_ARTIFACTS = {
  clientM: 'com.rokid.cxr:client-m:1.2.2',
  clientL: 'com.rokid.cxr:client-l:1.0.3',
  iosClient: 'RGCxrClient:1.0.1',
  iosCore: 'RGCoreKit:0.0.2',
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
  callbackScheme?: string;
  querySchemes?: string[];
  iosSdkDependencyMode?: 'linked' | 'opt_in_disabled' | string;
  iosSdkCompatibility?: string;
  sdkClassProbe?: Record<string, boolean>;
  reason?: string;
};

type RokidNativeModule = {
  getIntegrationStatus: () => Promise<Partial<RokidIntegrationStatus>>;
  openHiRokid: () => Promise<boolean>;
  requestAuthorization?: (scopes: string[], appName: string) => Promise<Record<string, unknown>>;
  clearAuthorization?: () => Promise<boolean>;
  openCustomView?: (view: string) => Promise<Record<string, unknown>>;
  updateCustomView?: (view: string) => Promise<Record<string, unknown>>;
  closeCustomView?: (view: string) => Promise<Record<string, unknown>>;
  takePhotoBase64?: (width: number, height: number, quality: number) => Promise<Record<string, unknown>>;
  startRecord?: (type: string, codec: string, mode: string) => Promise<Record<string, unknown>>;
  stopRecord?: (type: string) => Promise<Record<string, unknown>>;
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
  if (Platform.OS !== 'android' && Platform.OS !== 'ios') {
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

export async function requestRokidAuthorization(options?: {
  scopes?: string[];
  appName?: string;
}): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.requestAuthorization) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.requestAuthorization(
    options?.scopes ?? ['device_control', 'audio_stream'],
    options?.appName ?? 'Reva',
  );
}

export async function clearRokidAuthorization(): Promise<boolean> {
  const native = getNativeBridge();
  if (!native?.clearAuthorization) {
    return false;
  }
  return native.clearAuthorization();
}

export async function openRokidCustomView(view: string): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.openCustomView) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.openCustomView(view);
}

export async function updateRokidCustomView(view: string): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.updateCustomView) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.updateCustomView(view);
}

export async function closeRokidCustomView(view: string): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.closeCustomView) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.closeCustomView(view);
}

export async function takeRokidPhotoBase64(options?: {
  width?: number;
  height?: number;
  quality?: number;
}): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.takePhotoBase64) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.takePhotoBase64(
    options?.width ?? 1024,
    options?.height ?? 768,
    options?.quality ?? 80,
  );
}

export async function startRokidRecord(options?: {
  type?: string;
  codec?: string;
  mode?: string;
}): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.startRecord) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.startRecord(
    options?.type ?? 'interaction',
    options?.codec ?? 'pcm',
    options?.mode ?? 'rokidOmni',
  );
}

export async function stopRokidRecord(type = 'interaction'): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.stopRecord) {
    return { ok: false, reason: 'native_bridge_unavailable' };
  }
  return native.stopRecord(type);
}
