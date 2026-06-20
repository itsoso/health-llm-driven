import {
  EventEmitter,
  Platform,
  requireNativeModule,
  type EventSubscription,
} from 'expo-modules-core';

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
export const ROKID_TRANSCRIPT_EVENT = 'onRokidTranscript';

export type RokidIntegrationStatus = {
  platform: string;
  bridgeAvailable: boolean;
  hiRokidInstalled: boolean;
  canOpenHiRokid: boolean;
  mode: RokidIntegrationMode;
  sdkArtifacts: typeof ROKID_SDK_ARTIFACTS;
  sdkLinked?: boolean;
  sdkLinkedReason?: string;
  nativeAppVersion?: string;
  nativeBuildNumber?: string;
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
  cxrCallbackApiEnabled?: boolean;
  cxrNotifySubscriptionMode?: string;
  cxrClientInitialized?: boolean;
  cxrInitializationMode?: 'customView' | 'customApp' | 'unknown' | string;
  cxrInitializationOutcome?: string;
  authorizationState?: RokidAuthorizationState;
  iosBleConnected?: boolean;
  iosBleDeviceName?: string;
  capabilitiesReady?: boolean;
  customAppSupported?: boolean;
  customViewRunning?: boolean;
  customViewSessionEvidence?: boolean;
  customViewDisplayInferred?: boolean;
  lastCustomViewPayloadHash?: string;
  lastCustomViewPayloadShape?: string;
  lastCustomViewPayloadBytes?: number;
  customViewPendingRetry?: boolean;
  lastCustomViewAutoRetryAt?: string;
  lastCustomViewCommandAt?: string;
  lastCustomViewSessionEvidenceAt?: string;
  lastCustomViewSessionEvidenceReason?: string;
  lastCustomViewRawNotify?: string;
  lastCustomViewRawNotifyAt?: string;
  lastCustomViewOpenError?: string;
  lastCustomViewOpenCommandAccepted?: boolean;
  lastCustomViewOpenCallbackSuccess?: boolean;
  lastCustomViewOpenCallbackErrorCode?: string;
  lastCustomViewOpenCallbackAt?: string;
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
    | 'glasses_ble_connected'
    | 'custom_view_running'
    | 'capture_ready';
  title: string;
  detail: string;
  status: RokidDeviceValidationStepStatus;
  actionLabel?: string;
};

export type RokidCapabilityId =
  | 'cxrl_auth'
  | 'glasses_ble'
  | 'custom_view'
  | 'camera_capture'
  | 'audio_record'
  | 'custom_app_install'
  | 'custom_app_open'
  | 'pushup_backend_session'
  | 'mobile_fallback';
export type RokidCapabilityState = 'ready' | 'degraded' | 'blocked' | 'unknown';
export type RokidRecommendedSurface = 'rokid_glasses' | 'mobile' | 'watch' | 'backend' | 'manual';
export type RokidRecommendedPath =
  | 'glasses_android_app'
  | 'mobile_fallback'
  | 'cxrl_customview'
  | 'diagnostic_only';
export type RokidCapability = {
  id: RokidCapabilityId;
  label: string;
  state: RokidCapabilityState;
  detail: string;
  source: string;
  recommendedSurface: RokidRecommendedSurface;
  priority: number;
};
export type RokidCapabilityGateway = {
  summary: {
    native: RokidCapabilityState;
    display: RokidCapabilityState;
    capture: RokidCapabilityState;
    voice: RokidCapabilityState;
    movement: RokidCapabilityState;
  };
  capabilities: RokidCapability[];
  recommendedPath: RokidRecommendedPath;
  blockers: string[];
};

export type RokidTranscriptEvent = {
  transcript?: string;
  text?: string;
  confidence?: number;
  capturedAt?: string;
  captured_at?: string;
  source?: string;
  type?: string;
  partial?: boolean;
  isFinal?: boolean;
  is_final?: boolean;
  final?: boolean;
  meta?: Record<string, unknown>;
};

export type RokidEventSubscription = {
  remove: () => void;
};

type RokidBridgeEvents = {
  [ROKID_TRANSCRIPT_EVENT]: (event: RokidTranscriptEvent) => void;
};

type RokidNativeEventEmitter = {
  addListener: (
    eventName: typeof ROKID_TRANSCRIPT_EVENT,
    listener: RokidBridgeEvents[typeof ROKID_TRANSCRIPT_EVENT],
  ) => EventSubscription;
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
let cachedEmitter: RokidNativeEventEmitter | null | undefined;

type RevaCustomViewOptions = {
  title?: string;
  body?: string;
  priority?: string;
};

const BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000;
const ISO_TIMESTAMP_PATTERN = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})/;

function pad2(value: number) {
  return String(value).padStart(2, '0');
}

function formatTimestampInBeijing(value: string) {
  const timestampMs = Date.parse(value);
  if (!Number.isFinite(timestampMs)) {
    return value;
  }
  const beijing = new Date(timestampMs + BEIJING_OFFSET_MS);
  return `${beijing.getUTCFullYear()}-${pad2(beijing.getUTCMonth() + 1)}-${pad2(beijing.getUTCDate())}`
    + `T${pad2(beijing.getUTCHours())}:${pad2(beijing.getUTCMinutes())}:${pad2(beijing.getUTCSeconds())}+08:00`;
}

export function formatRokidLogTimestamp(value: string) {
  const match = value.match(ISO_TIMESTAMP_PATTERN);
  if (!match) {
    return value;
  }
  return value.replace(match[0], formatTimestampInBeijing(match[0]));
}

function includesAny(value: string | undefined, needles: string[]) {
  if (!value) {
    return false;
  }
  const normalized = value.toLowerCase();
  return needles.some((needle) => normalized.includes(needle));
}

function hasCustomViewCompletionFailure(status?: Partial<RokidIntegrationStatus> | null) {
  return includesAny(status?.lastCustomViewOpenError, [
    'rokid_custom_view_open_callback_missing',
    'rokid_custom_view_not_running_after_open',
    'custom_view_open_failed',
    'open_callback_error_code',
  ]);
}

function rawNotifyFromOpenError(error?: string) {
  const rawNotifyMatch = error?.match(/rawnotify=([^;]+)/i);
  return rawNotifyMatch?.[1]?.trim();
}

function rawNotifyEvidence(status?: Partial<RokidIntegrationStatus> | null) {
  const direct = status?.lastCustomViewRawNotify?.trim();
  if (direct && direct.toLowerCase() !== 'none') {
    return direct;
  }
  const fromError = rawNotifyFromOpenError(status?.lastCustomViewOpenError);
  if (fromError && fromError.toLowerCase() !== 'none') {
    return fromError;
  }
  return undefined;
}

function hasNotifyEvidence(status?: Partial<RokidIntegrationStatus> | null) {
  return Boolean(rawNotifyEvidence(status));
}

function hasNetworkPreconditionFailure(status?: Partial<RokidIntegrationStatus> | null) {
  const combined = [
    status?.lastCustomViewOpenError,
    status?.lastCustomViewRawNotify,
  ].filter(Boolean).join('; ');
  return includesAny(combined, [
    'rokid_glasses_no_network',
    'subcmd=nonetwork',
    'no_network',
    'no network',
  ]);
}

function hasSilentCustomViewFailure(status?: Partial<RokidIntegrationStatus> | null) {
  if (!hasCustomViewCompletionFailure(status) || hasNetworkPreconditionFailure(status)) {
    return false;
  }
  if (hasNotifyEvidence(status)) {
    return false;
  }
  return includesAny(status?.lastCustomViewOpenError, [
    'rokid_custom_view_open_callback_missing',
    'rokid_custom_view_not_running_after_open',
    'rawnotify=none',
  ]);
}

function hasCustomViewCompletionFailureWithNotify(status?: Partial<RokidIntegrationStatus> | null) {
  return hasCustomViewCompletionFailure(status)
    && hasNotifyEvidence(status)
    && !hasNetworkPreconditionFailure(status);
}

function hasBlePendingRetry(status?: Partial<RokidIntegrationStatus> | null) {
  return status?.customViewPendingRetry === true
    || includesAny(status?.lastCustomViewOpenError, ['pending_retry_on_ble_connect']);
}

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

function getNativeEmitter(): RokidNativeEventEmitter | null {
  const native = getNativeBridge();
  if (!native) {
    return null;
  }
  if (cachedEmitter !== undefined) {
    return cachedEmitter;
  }
  const emitter = new EventEmitter(native as any) as RokidNativeEventEmitter;
  cachedEmitter = emitter;
  return emitter;
}

export function buildRokidCapabilityGateway(
  status?: Partial<RokidIntegrationStatus> | null,
): RokidCapabilityGateway {
  const platform = status?.platform ?? Platform.OS;
  const ios = platform === 'ios';
  const bridgeReady = status?.bridgeAvailable === true;
  const sdkLinked = ios ? status?.sdkLinked === true : bridgeReady;
  const companionReady = status?.hiRokidInstalled === true && status?.canOpenHiRokid === true;
  const authorized = status?.authorizationState === 'authenticated';
  const bleReady = !ios || status?.iosBleConnected === true;
  const customViewRunning = status?.customViewRunning === true;
  const captureReady = status?.capabilitiesReady === true;
  const networkPreconditionFailure = hasNetworkPreconditionFailure(status);
  const silentCustomView = hasSilentCustomViewFailure(status);
  const customViewCompletionFailureWithNotify = hasCustomViewCompletionFailureWithNotify(status);
  const pendingCustomView = hasBlePendingRetry(status);
  const customAppSupported = status?.customAppSupported !== false;
  const nativeState: RokidCapabilityState = bridgeReady && sdkLinked
    ? 'ready'
    : bridgeReady
      ? 'degraded'
      : 'blocked';
  const blockers: string[] = [];

  if (!bridgeReady) {
    blockers.push('Rokid native bridge 不可用: 当前只能走手机端兜底。');
  }
  if (ios && bridgeReady && !sdkLinked) {
    blockers.push('iOS RGCxrClient 未链接: 眼镜原生能力不可用。');
  }
  if (networkPreconditionFailure) {
    blockers.push('Rokid 眼镜网络未就绪: 请确认眼镜已连 WiFi、手机和眼镜同网或 companion 已建立数据通道。');
  } else if (silentCustomView) {
    blockers.push('CXR-L CustomView 静默: openCustomView 未收到 callback/notify, 不应再阻塞运动和饮食主流程。');
  } else if (customViewCompletionFailureWithNotify) {
    blockers.push('CXR-L notify 通道有响应，但 CustomView 未完成: 继续收集 typed notify/status 后再升级 Rokid。');
  }

  let customViewState: RokidCapabilityState = 'unknown';
  let customViewDetail = '等待 CXR-L 会话状态。';
  if (customViewRunning) {
    customViewState = 'ready';
    customViewDetail = 'CustomView 已在眼镜端运行。';
  } else if (!bridgeReady || (ios && !sdkLinked)) {
    customViewState = 'blocked';
    customViewDetail = 'native bridge 或 iOS SDK 未就绪。';
  } else if (!authorized) {
    customViewState = 'degraded';
    customViewDetail = '等待 CXR-L 授权。';
  } else if (pendingCustomView) {
    customViewState = 'degraded';
    customViewDetail = 'CustomView 已排队, 等待眼镜蓝牙链路恢复后重试。';
  } else if (!bleReady) {
    customViewState = 'degraded';
    customViewDetail = '等待眼镜蓝牙链路连接。';
  } else if (networkPreconditionFailure) {
    customViewState = 'blocked';
    customViewDetail = '眼镜未建立 CXR 数据通道(TCP/WiFi), 先确认眼镜 WiFi/同网状态。';
  } else if (silentCustomView) {
    customViewState = 'blocked';
    customViewDetail = 'CXR-L CustomView 命令静默, 不再作为核心健康流程前置条件。';
  } else if (customViewCompletionFailureWithNotify) {
    customViewState = 'blocked';
    customViewDetail = 'CXR-L notify 通道有事件, 但未收到 CustomView running/成功回调。';
  } else {
    customViewState = 'degraded';
    customViewDetail = '已具备基础链路, 仍需眼镜端 running 事件确认。';
  }

  const customAppState: RokidCapabilityState =
    bridgeReady && sdkLinked && authorized && customAppSupported
      ? 'degraded'
      : !customAppSupported
        ? 'blocked'
        : bridgeReady && sdkLinked
          ? 'degraded'
          : 'blocked';
  const movementState: RokidCapabilityState =
    networkPreconditionFailure
      ? 'degraded'
      : bridgeReady && sdkLinked && authorized && customAppSupported
      ? 'ready'
      : bridgeReady || customAppSupported
        ? 'degraded'
        : 'blocked';
  const captureState: RokidCapabilityState = captureReady
    ? 'ready'
    : networkPreconditionFailure
      ? 'blocked'
      : 'degraded';
  const voiceState: RokidCapabilityState =
    captureReady && !silentCustomView && !networkPreconditionFailure
      ? 'degraded'
      : networkPreconditionFailure || silentCustomView || !bridgeReady || (ios && !sdkLinked)
        ? 'blocked'
        : 'degraded';

  const capabilities: RokidCapability[] = [
    {
      id: 'cxrl_auth',
      label: 'CXR-L 授权',
      state: authorized ? 'ready' : bridgeReady && sdkLinked && companionReady ? 'degraded' : 'blocked',
      detail: authorized ? '授权 token 可用。' : '需要先完成 Rokid 授权回调。',
      source: 'RGCxrClient.auth',
      recommendedSurface: 'mobile',
      priority: 10,
    },
    {
      id: 'glasses_ble',
      label: '眼镜蓝牙链路',
      state: bleReady ? 'ready' : authorized ? 'degraded' : 'unknown',
      detail: bleReady ? '眼镜链路可用。' : 'Rokid AI / Hi Rokid 可能仍占用或眼镜未在线。',
      source: 'RGCxrClientBLE.connectionStatePublisher',
      recommendedSurface: 'rokid_glasses',
      priority: 20,
    },
    {
      id: 'custom_view',
      label: 'CXR-L CustomView',
      state: customViewState,
      detail: customViewDetail,
      source: 'RGCxrClient.openCustomView',
      recommendedSurface: customViewState === 'blocked' ? 'manual' : 'rokid_glasses',
      priority: 30,
    },
    {
      id: 'camera_capture',
      label: '眼镜拍照采集',
      state: captureReady ? 'ready' : customViewState === 'blocked' ? 'blocked' : 'degraded',
      detail: captureReady
        ? '拍照能力可用。'
        : networkPreconditionFailure
          ? '眼镜 CXR 数据通道未就绪; 饮食记录先走手机拍照兜底。'
          : 'Rokid iOS 拍照依赖会话构建; 饮食记录应保持手机拍照兜底。',
      source: 'RGCxrClient.takePhoto',
      recommendedSurface: captureReady ? 'rokid_glasses' : 'mobile',
      priority: 40,
    },
    {
      id: 'audio_record',
      label: '眼镜语音输入',
      state: voiceState,
      detail: voiceState === 'blocked'
        ? networkPreconditionFailure
          ? '眼镜 CXR 数据通道未就绪; 语音记录食物先走手机输入兜底。'
          : '原生录音/转写尚不能作为稳定入口; 语音记录食物先走手机输入兜底。'
        : '音频能力仍需真实 transcript 事件验证。',
      source: 'RGCxrClient.startRecord + onRokidTranscript',
      recommendedSurface: voiceState === 'blocked' ? 'mobile' : 'rokid_glasses',
      priority: 50,
    },
    {
      id: 'custom_app_install',
      label: '眼镜端 App 安装',
      state: customAppState,
      detail: customAppState === 'blocked'
        ? 'CustomApp 安装/启动接口不可用或未授权。'
        : '需要继续验证 life.executor.health.rokid.pushup APK 安装结果。',
      source: 'RGCxrClient.installApp',
      recommendedSurface: 'rokid_glasses',
      priority: 60,
    },
    {
      id: 'custom_app_open',
      label: '眼镜端 App 启动',
      state: customAppState,
      detail: customAppState === 'blocked'
        ? '无法启动眼镜端 Android App。'
        : '运动识别应优先走眼镜端 Android App, 不依赖 CustomView running。',
      source: 'RGCxrClient.openApp / manual ADB',
      recommendedSurface: 'rokid_glasses',
      priority: 70,
    },
    {
      id: 'pushup_backend_session',
      label: '俯卧撑后端会话',
      state: 'ready',
      detail: 'Reva 可接收 pose/rep 事件; 眼镜端 App 或本地计数都可写入同一会话。',
      source: 'Rokid push-up session API',
      recommendedSurface: 'backend',
      priority: 80,
    },
    {
      id: 'mobile_fallback',
      label: '手机端兜底',
      state: 'ready',
      detail: '食物拍照、语音输入和本地俯卧撑计数保持可用。',
      source: 'Reva mobile routes',
      recommendedSurface: 'mobile',
      priority: 90,
    },
  ];

  let recommendedPath: RokidRecommendedPath = 'mobile_fallback';
  if (!bridgeReady || (ios && !sdkLinked)) {
    recommendedPath = 'mobile_fallback';
  } else if (networkPreconditionFailure) {
    recommendedPath = 'mobile_fallback';
  } else if (captureReady && customViewRunning) {
    recommendedPath = 'cxrl_customview';
  } else if ((silentCustomView || authorized) && customAppSupported) {
    recommendedPath = 'glasses_android_app';
  } else if (!companionReady && !authorized) {
    recommendedPath = 'diagnostic_only';
  }

  return {
    summary: {
      native: nativeState,
      display: customViewState,
      capture: captureState,
      voice: voiceState,
      movement: movementState,
    },
    capabilities,
    recommendedPath,
    blockers,
  };
}

export function getRokidDeviceValidationSteps(
  status?: Partial<RokidIntegrationStatus> | null,
): RokidDeviceValidationStep[] {
  const platform = status?.platform ?? Platform.OS;
  const sdkLinked = platform === 'ios' && status?.bridgeAvailable === true && status?.sdkLinked === true;
  const sdkRequestedButUnlinked = platform === 'ios'
    && status?.bridgeAvailable === true
    && status?.sdkLinked !== true
    && (
      status?.iosSdkDependencyMode === 'requested_but_unlinked'
      || status?.cxrCallbackApiEnabled === true
      || status?.sdkLinkedReason?.includes('unavailable') === true
    );
  const hiRokidReady = status?.hiRokidInstalled === true && status?.canOpenHiRokid === true;
  const authorized = status?.authorizationState === 'authenticated';
  const bleDevice = status?.iosBleDeviceName || status?.currentDeviceName;
  const glassesBleConnected = platform !== 'ios' || status?.iosBleConnected === true;
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
        : sdkRequestedButUnlinked
          ? `Rokid SDK 编译开关已打开, 但 native 未导入 RGCxrClient: ${status?.sdkLinkedReason ?? status?.iosSdkDependencyMode ?? 'unknown'}。`
        : '安装 Rokid 版 Reva 包, 确认 ROKID_IOS_SDK_ENABLED=1。',
      actionLabel: '安装 Rokid 版 Reva',
      done: sdkLinked,
      blocked: platform !== 'ios' || status?.bridgeAvailable === false,
    },
    {
      id: 'hi_rokid_ready',
      title: 'Rokid companion 已连接',
      detail: hiRokidReady ? 'Rokid AI / Hi Rokid 可唤起, 可继续授权。' : '安装并登录 Rokid AI / Hi Rokid。',
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
    ...(platform === 'ios' ? [{
      id: 'glasses_ble_connected' as const,
      title: '眼镜蓝牙链路',
      detail: glassesBleConnected
        ? `Rokid CXR-L 已连接眼镜蓝牙链路${bleDevice ? `: ${bleDevice}` : ''}。`
        : `Rokid CXR-L 还未连接到眼镜蓝牙链路${bleDevice ? `: ${bleDevice}` : ''}。授权完成后请「完全退出」Rokid AI / Hi Rokid(它会独占眼镜蓝牙, 一次只能一个 App 连眼镜), 再回 Reva 刷新。`,
      actionLabel: '打开 Rokid AI / Hi Rokid',
      done: glassesBleConnected,
    }] : []),
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

export function addRokidTranscriptListener(
  listener: (event: RokidTranscriptEvent) => void,
): RokidEventSubscription {
  const emitter = getNativeEmitter();
  if (!emitter) {
    return { remove: () => undefined };
  }
  return emitter.addListener(ROKID_TRANSCRIPT_EVENT, listener) as EventSubscription;
}
