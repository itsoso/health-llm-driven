import { Platform, requireNativeModule } from 'expo-modules-core';

export const ROKID_SDK_ARTIFACTS = {
  clientM: 'com.rokid.cxr:client-m:1.2.2',
  clientL: 'com.rokid.cxr:client-l:1.0.3',
  iosClient: 'RGCxrClient:1.0.1',
  iosClientCandidate: 'RGCxrClient:1.0.2',
  iosCore: 'RGCoreKit:0.0.2',
} as const;

export type RokidIntegrationMode = 'unavailable' | 'sdk_probe';
export type RokidAuthorizationState =
  | 'unknown'
  | 'not_authenticated'
  | 'authenticating'
  | 'authenticated'
  | 'expired'
  | 'failed';
export type RokidSessionMode = 'customView' | 'customApp' | 'unknown';

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
  callbackSchemeSource?: string;
  acceptedCallbackSchemes?: string[];
  callbackUrl?: string;
  lastCallbackUrl?: string;
  lastCallbackAt?: string;
  lastCallbackHandled?: boolean;
  authorizationRequestTimeoutSeconds?: number;
  bundleIdentifier?: string;
  lastAuthorizationAttemptId?: string;
  authorizationAttemptCount?: number;
  lastAuthorizationPhase?: string;
  lastAuthorizationDurationMs?: number;
  lastAuthorizationStateBeforeReset?: string;
  lastAuthorizationStateAfterReset?: string;
  lastAuthorizationStateBeforeAuthenticate?: string;
  authorizationConfigSummary?: string;
  authDiagnosticTimeline?: string[];
  lastAuthorizationAppName?: string;
  lastAuthorizationScopes?: string[];
  lastAuthorizationRequestAt?: string;
  lastAuthorizationError?: string;
  lastAuthorizationErrorAt?: string;
  lastAuthorizationEvent?: string;
  lastAuthorizationEventAt?: string;
  currentDeviceName?: string;
  companionAppName?: string;
  companionServerScheme?: string;
  companionServerHost?: string;
  lastOpenUrlFingerprint?: string;
  lastOpenUrlAt?: string;
  lastOpenUrlExpectedAuthCallback?: boolean;
  querySchemes?: string[];
  iosSdkDependencyMode?: 'linked' | 'opt_in_disabled' | string;
  iosSdkCompatibility?: string;
  cxrClientInitialized?: boolean;
  cxrInitializationMode?: 'customView' | 'customApp' | 'unknown' | string;
  cxrInitializationOutcome?: string;
  authorizationState?: RokidAuthorizationState;
  iosBleConnected?: boolean;
  iosBleDeviceName?: string;
  capabilitiesReady?: boolean;
  customAppSupported?: boolean;
  customViewRunning?: boolean;
  sessionMode?: RokidSessionMode;
  sdkClassProbe?: Record<string, boolean>;
  reason?: string;
};

export type RokidDeviceValidationStepStatus = 'done' | 'next' | 'pending' | 'blocked';
export type RokidDeviceValidationStep = {
  id:
    | 'ios_sdk_linked'
    | 'hi_rokid_ready'
    | 'rokid_authorized'
    | 'custom_view_running'
    | 'capture_ready';
  title: string;
  detail: string;
  status: RokidDeviceValidationStepStatus;
  actionLabel?: string;
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
  queryApp?: (packageName: string) => Promise<Record<string, unknown>>;
  installBundledApp?: (
    resourceName: string,
    resourceExtension: string,
    packageName: string,
  ) => Promise<Record<string, unknown>>;
  installAppFileUri?: (fileUri: string, packageName: string) => Promise<Record<string, unknown>>;
  uninstallApp?: (packageName: string) => Promise<Record<string, unknown>>;
  openApp?: (packageName: string, activityName: string, url: string) => Promise<Record<string, unknown>>;
  stopApp?: (packageName: string) => Promise<Record<string, unknown>>;
  startRecord?: (type: string, codec: string, mode: string) => Promise<Record<string, unknown>>;
  stopRecord?: (type: string) => Promise<Record<string, unknown>>;
};

let cachedNative: RokidNativeModule | null | undefined;

type RevaCustomViewOptions = {
  title?: string;
  body?: string;
  priority?: string;
};

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

export function getRokidDeviceValidationSteps(
  status?: Partial<RokidIntegrationStatus> | null,
): RokidDeviceValidationStep[] {
  const platform = status?.platform ?? Platform.OS;
  const sdkLinked = platform === 'ios' && status?.bridgeAvailable === true && status?.sdkLinked === true;
  const hiRokidReady = status?.hiRokidInstalled === true && status?.canOpenHiRokid === true;
  const authorized = status?.authorizationState === 'authenticated';
  const customViewRunning = status?.customViewRunning === true;
  const captureReady = status?.capabilitiesReady === true;
  const iosClient = status?.sdkArtifacts?.iosClient ?? ROKID_SDK_ARTIFACTS.iosClient;

  const drafts: (Omit<RokidDeviceValidationStep, 'status'> & {
    done: boolean;
    blocked?: boolean;
  })[] = [
    {
      id: 'ios_sdk_linked',
      title: 'iOS SDK 已链接',
      detail: sdkLinked
        ? `当前包已链接 ${iosClient}。`
        : '安装 Rokid 版 Reva 包, 确认 ROKID_IOS_SDK_ENABLED=1。',
      actionLabel: '安装 Rokid 版 Reva',
      done: sdkLinked,
      blocked: platform !== 'ios' || status?.bridgeAvailable === false,
    },
    {
      id: 'hi_rokid_ready',
      title: 'Rokid companion 已连接',
      detail: hiRokidReady ? 'Rokid AI / Hi Rokid 可唤起, 可继续授权。' : '在 Rokid AI / Hi Rokid 中确认眼镜已连接。',
      actionLabel: '打开 Rokid AI / Hi Rokid',
      done: hiRokidReady,
    },
    {
      id: 'rokid_authorized',
      title: 'CXR-L 授权',
      detail: authorized ? '授权 token 可用。' : '在 Reva 中完成 CXR-L 授权回调后继续。',
      actionLabel: '授权 Rokid',
      done: authorized,
    },
    {
      id: 'custom_view_running',
      title: 'Reva 眼镜视图',
      detail: customViewRunning ? 'CustomView 已在眼镜端运行。' : '打开 Reva CustomView, 确认眼镜端已经显示。',
      actionLabel: '打开 Reva 眼镜视图',
      done: customViewRunning,
    },
    {
      id: 'capture_ready',
      title: '拍照能力就绪',
      detail: captureReady ? '可以主动触发食物/补剂/用药拍照。' : '完成会话构建后再进行食物视觉记录。',
      actionLabel: '拍照验证',
      done: captureReady,
    },
  ];

  let firstOpenStepAssigned = false;
  return drafts.map(({ done, blocked, ...step }) => {
    if (done) {
      return { ...step, status: 'done' };
    }
    if (!firstOpenStepAssigned) {
      firstOpenStepAssigned = true;
      return { ...step, status: blocked ? 'blocked' : 'next' };
    }
    return { ...step, status: 'pending' };
  });
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

export function createRokidRevaCustomViewLayout(options?: RevaCustomViewOptions): string {
  const title = options?.title ?? 'Reva Health';
  const body = options?.body ?? '等待 Reva 投递下一条健康行动';
  const priority = options?.priority ?? 'manual_confirm';
  return JSON.stringify({
    type: 'LinearLayout',
    props: {
      id: 'reva_root',
      layout_width: 'match_parent',
      layout_height: 'match_parent',
      orientation: 'vertical',
      gravity: 'center_vertical',
      paddingStart: '24dp',
      paddingEnd: '24dp',
      paddingTop: '120dp',
      paddingBottom: '100dp',
      backgroundColor: '#FF000000',
    },
    children: [
      {
        type: 'TextView',
        props: {
          id: 'reva_title',
          layout_width: 'wrap_content',
          layout_height: 'wrap_content',
          text: title,
          textColor: '#FFFFFFFF',
          textSize: '18sp',
          textStyle: 'bold',
          marginBottom: '14dp',
        },
      },
      {
        type: 'TextView',
        props: {
          id: 'reva_body',
          layout_width: 'match_parent',
          layout_height: 'wrap_content',
          text: body,
          textColor: '#FFE8F0FF',
          textSize: '16sp',
          gravity: 'center',
          marginBottom: '12dp',
        },
      },
      {
        type: 'TextView',
        props: {
          id: 'reva_priority',
          layout_width: 'wrap_content',
          layout_height: 'wrap_content',
          text: priority,
          textColor: '#FF9CCBFF',
          textSize: '12sp',
          gravity: 'center',
        },
      },
    ],
  });
}

export async function openRokidRevaCustomView(
  options?: RevaCustomViewOptions,
): Promise<Record<string, unknown>> {
  return openRokidCustomView(createRokidRevaCustomViewLayout(options));
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

export async function queryRokidApp(packageName: string): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.queryApp) {
    return { ok: false, installed: false, reason: 'native_bridge_unavailable' };
  }
  return native.queryApp(packageName);
}

export async function installBundledRokidApp(options: {
  resourceName: string;
  resourceExtension?: string;
  packageName: string;
}): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.installBundledApp) {
    return { ok: false, installed: false, reason: 'native_bridge_unavailable' };
  }
  return native.installBundledApp(
    options.resourceName,
    options.resourceExtension ?? 'apk',
    options.packageName,
  );
}

export async function installRokidAppFromFileUri(options: {
  fileUri: string;
  packageName: string;
}): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.installAppFileUri) {
    return { ok: false, installed: false, reason: 'native_bridge_unavailable' };
  }
  return native.installAppFileUri(options.fileUri, options.packageName);
}

export async function uninstallRokidApp(packageName: string): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.uninstallApp) {
    return { ok: false, uninstalled: false, reason: 'native_bridge_unavailable' };
  }
  return native.uninstallApp(packageName);
}

export async function openRokidApp(options: {
  packageName: string;
  activityName: string;
  url: string;
}): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.openApp) {
    return { ok: false, opened: false, reason: 'native_bridge_unavailable' };
  }
  return native.openApp(options.packageName, options.activityName, options.url);
}

export async function stopRokidApp(packageName: string): Promise<Record<string, unknown>> {
  const native = getNativeBridge();
  if (!native?.stopApp) {
    return { ok: false, stopped: false, reason: 'native_bridge_unavailable' };
  }
  return native.stopApp(packageName);
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
