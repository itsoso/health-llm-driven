import {
  buildRokidCapabilityGateway,
  formatRokidLogTimestamp,
  getRokidDeviceValidationSteps,
  getRokidIntegrationStatus,
  isRokidBleBlockedByCompanionSuspected,
  type RokidCapabilityGateway,
  type RokidDeviceValidationStep,
  type RokidIntegrationStatus,
  type RokidRecommendedPath,
} from '../modules/rokid-bridge';

export type RokidSelfCheckSeverity = 'pass' | 'warn' | 'block' | 'info';

export type RokidSelfCheckItem = {
  id: string;
  label: string;
  value: string;
  severity: RokidSelfCheckSeverity;
  detail?: string;
};

export type RokidSelfCheck = {
  summary: {
    bridge: 'ready' | 'missing';
    sdk: 'linked' | 'not_linked' | 'unknown';
    companion: 'ready' | 'missing';
    authorization: 'authenticated' | 'not_authenticated' | 'unknown';
    session: 'ready' | 'not_ready';
  };
  items: RokidSelfCheckItem[];
  validationSteps: RokidDeviceValidationStep[];
  capabilityGateway: RokidCapabilityGateway;
};

function passIf(condition: boolean, passValue: string, failValue: string, failSeverity: RokidSelfCheckSeverity) {
  return {
    value: condition ? passValue : failValue,
    severity: condition ? 'pass' as const : failSeverity,
  };
}

function redactCallbackUrl(url?: string) {
  if (!url) {
    return undefined;
  }
  const queryIndex = url.indexOf('?');
  if (queryIndex < 0) {
    return url;
  }
  return `${url.slice(0, queryIndex)}?<redacted>`;
}

function formatAuthorizationError(error?: string) {
  if (!error) {
    return undefined;
  }
  const normalized = error.toLowerCase();
  if (
    error.includes('鉴权请求超时')
    || normalized.includes('rgcxrclientautherror code=-1')
    || normalized.includes('timeout')
  ) {
    return '鉴权请求超时';
  }
  return error;
}

function authorizationErrorDetail(status: RokidIntegrationStatus) {
  const parts: string[] = [];
  if (status.lastAuthorizationRequestAt) {
    parts.push(`lastRequestAt=${formatRokidLogTimestamp(status.lastAuthorizationRequestAt)}`);
  }
  if (typeof status.authorizationRequestTimeoutSeconds === 'number') {
    parts.push(`timeout=${Math.round(status.authorizationRequestTimeoutSeconds)}s`);
  }
  return parts.length > 0 ? parts.join('; ') : undefined;
}

function authorizationAttemptValue(status: RokidIntegrationStatus) {
  const parts: string[] = [];
  if (status.lastAuthorizationAttemptId) {
    parts.push(status.lastAuthorizationAttemptId);
  }
  if (typeof status.authorizationAttemptCount === 'number') {
    parts.push(`#${status.authorizationAttemptCount}`);
  }
  if (status.lastAuthorizationPhase) {
    parts.push(status.lastAuthorizationPhase);
  }
  return parts.length > 0 ? parts.join(' / ') : undefined;
}

function authorizationAttemptDetail(status: RokidIntegrationStatus) {
  return typeof status.lastAuthorizationDurationMs === 'number'
    ? `duration=${status.lastAuthorizationDurationMs}ms`
    : undefined;
}

function authorizationAttemptSeverity(status: RokidIntegrationStatus): RokidSelfCheckSeverity {
  const phase = status.lastAuthorizationPhase?.toLowerCase() ?? '';
  if (phase.includes('succeeded') || phase.includes('cached_authenticated')) {
    return 'pass';
  }
  if (phase.includes('failed') || phase.includes('timeout')) {
    return 'warn';
  }
  return 'info';
}

function authorizationStateTraceValue(status: RokidIntegrationStatus) {
  const parts: string[] = [];
  if (status.lastAuthorizationStateBeforeReset) {
    parts.push(`beforeReset=${status.lastAuthorizationStateBeforeReset}`);
  }
  if (status.lastAuthorizationStateAfterReset) {
    parts.push(`afterReset=${status.lastAuthorizationStateAfterReset}`);
  }
  if (status.lastAuthorizationStateBeforeAuthenticate) {
    parts.push(`beforeAuth=${status.lastAuthorizationStateBeforeAuthenticate}`);
  }
  return parts.length > 0 ? parts.join('; ') : undefined;
}

function companionDetail(status: RokidIntegrationStatus, companionReady: boolean) {
  const parts: string[] = [];
  if (status.companionServerScheme && status.companionServerHost) {
    parts.push(`server=${status.companionServerScheme}://${status.companionServerHost}`);
  }
  if (status.currentDeviceName) {
    parts.push(`device=${status.currentDeviceName}`);
  }
  if (parts.length > 0) {
    return parts.join('; ');
  }
  return companionReady ? '可唤起 Rokid AI / Hi Rokid' : '需要先安装并连接眼镜';
}

function authorizationEventSeverity(event?: string): RokidSelfCheckSeverity {
  const normalized = event?.toLowerCase() ?? '';
  if (normalized.includes('failed') || normalized.includes('expired')) {
    return 'warn';
  }
  if (normalized.includes('succeeded') || normalized.includes('authenticated')) {
    return 'pass';
  }
  return 'info';
}

function iosOpenUrlValue(status: RokidIntegrationStatus, authorized: boolean) {
  if (!status.lastOpenUrlFingerprint) {
    return authorized ? '本次启动无 iOS 回跳记录' : '尚未收到 iOS openURL';
  }
  return status.lastOpenUrlExpectedAuthCallback
    ? '最近回跳匹配授权 scheme'
    : '最近回跳不是授权 scheme';
}

function iosOpenUrlSeverity(status: RokidIntegrationStatus, authorized: boolean): RokidSelfCheckSeverity {
  if (!status.lastOpenUrlFingerprint) {
    return authorized ? 'info' : 'warn';
  }
  return status.lastOpenUrlExpectedAuthCallback ? 'pass' : 'warn';
}

function iosOpenUrlDetail(status: RokidIntegrationStatus) {
  if (!status.lastOpenUrlFingerprint) {
    return status.callbackUrl ? `expected=${status.callbackUrl}` : undefined;
  }
  const parts = [status.lastOpenUrlFingerprint];
  if (status.lastOpenUrlAt) {
    parts.push(`at=${formatRokidLogTimestamp(status.lastOpenUrlAt)}`);
  }
  if (status.callbackUrl) {
    parts.push(`expected=${status.callbackUrl}`);
  }
  return parts.join('; ');
}

function acceptedCallbackSchemesValue(status: RokidIntegrationStatus) {
  if (!Array.isArray(status.acceptedCallbackSchemes) || status.acceptedCallbackSchemes.length === 0) {
    return undefined;
  }
  return status.acceptedCallbackSchemes
    .filter((scheme) => typeof scheme === 'string' && scheme.trim().length > 0)
    .join(', ');
}

function callbackSchemesDetail(status: RokidIntegrationStatus) {
  const parts: string[] = [];
  if (status.callbackScheme) {
    parts.push(`configured=${status.callbackScheme}`);
  }
  if (status.callbackSchemeSource) {
    parts.push(`source=${status.callbackSchemeSource}`);
  }
  return parts.length > 0 ? parts.join('; ') : undefined;
}

function capabilityRouteValue(path: RokidRecommendedPath) {
  switch (path) {
    case 'glasses_android_app':
      return '眼镜端 App 优先';
    case 'cxrl_customview':
      return 'CXR-L CustomView';
    case 'diagnostic_only':
      return '仅诊断';
    default:
      return '手机兜底';
  }
}

function capabilityRouteSeverity(gateway: RokidCapabilityGateway): RokidSelfCheckSeverity {
  if (gateway.recommendedPath === 'diagnostic_only') {
    return 'block';
  }
  return gateway.blockers.length > 0 || Object.values(gateway.summary).includes('blocked')
    ? 'warn'
    : 'pass';
}

export function buildRokidSelfCheck(status: RokidIntegrationStatus): RokidSelfCheck {
  const bridgeReady = status.bridgeAvailable === true;
  const sdkLinked = status.sdkLinked === true;
  const companionReady = status.hiRokidInstalled === true && status.canOpenHiRokid === true;
  const authorized = status.authorizationState === 'authenticated';
  const sessionReady = status.customViewRunning === true && status.capabilitiesReady === true;
  const validationSteps = getRokidDeviceValidationSteps(status);
  const capabilityGateway = buildRokidCapabilityGateway(status);

  const bridge = passIf(bridgeReady, 'Bridge 已就绪', 'Bridge 未就绪', 'block');
  const sdk = passIf(sdkLinked, 'SDK 已链接', 'SDK 未链接', bridgeReady ? 'warn' : 'block');
  const companionName = status.companionAppName ?? 'Rokid AI / Hi Rokid';
  const companion = passIf(companionReady, 'Rokid companion 可用', 'Rokid companion 未就绪', 'warn');
  const authorization = passIf(authorized, 'CXR-L 已授权', 'CXR-L 未授权', 'warn');
  const session = passIf(sessionReady, '会话能力就绪', '会话未构建完成', 'warn');
  const companionBleSuspected = isRokidBleBlockedByCompanionSuspected(status);
  const callbackSeen = typeof status.lastCallbackUrl === 'string' && status.lastCallbackUrl.length > 0;
  const callbackHandled = status.lastCallbackHandled === true;
  const callbackValue = callbackHandled
    ? '最近回调已进入 Reva'
    : callbackSeen
      ? '回调进入 Reva, SDK 未确认'
      : authorized
        ? '已授权, 本次启动无回调记录'
        : '尚未收到授权回调';
  const callbackSeverity: RokidSelfCheckSeverity = callbackHandled
    ? 'pass'
    : callbackSeen
      ? 'warn'
      : authorized
        ? 'pass'
        : 'warn';
  const authErrorValue = formatAuthorizationError(status.lastAuthorizationError);
  const authAttemptValue = authorizationAttemptValue(status);
  const authStateTraceValue = authorizationStateTraceValue(status);
  const authTimeline = Array.isArray(status.authDiagnosticTimeline)
    ? status.authDiagnosticTimeline.slice(-8)
    : [];
  const callbackSchemesValue = acceptedCallbackSchemesValue(status);

  return {
    summary: {
      bridge: bridgeReady ? 'ready' : 'missing',
      sdk: sdkLinked ? 'linked' : bridgeReady ? 'unknown' : 'not_linked',
      companion: companionReady ? 'ready' : 'missing',
      authorization: authorized ? 'authenticated' : status.authorizationState ? 'not_authenticated' : 'unknown',
      session: sessionReady ? 'ready' : 'not_ready',
    },
    items: [
      {
        id: 'bridge',
        label: 'Native Bridge',
        ...bridge,
        detail: status.reason,
      },
      {
        id: 'sdk',
        label: 'Rokid SDK',
        ...sdk,
        detail: status.iosSdkCompatibility ?? status.iosSdkDependencyMode,
      },
      {
        id: 'companion',
        label: companionName,
        ...companion,
        detail: companionDetail(status, companionReady),
      },
      ...(companionBleSuspected ? [{
        id: 'ble_companion_suspected',
        label: '眼镜蓝牙疑似占用',
        value: '疑似 Rokid AI / Hi Rokid 仍占用 BLE central',
        severity: 'warn' as const,
        detail: `device=${status.iosBleDeviceName ?? status.currentDeviceName ?? 'unknown'}; action=完全退出/划掉 Rokid AI / Hi Rokid 后回 Reva 刷新`,
      }] : []),
      {
        id: 'authorization',
        label: '授权',
        ...authorization,
        detail: status.callbackUrl ?? status.callbackScheme,
      },
      {
        id: 'auth_callback',
        label: '授权回调',
        value: callbackValue,
        severity: callbackSeverity,
        detail: redactCallbackUrl(status.lastCallbackUrl ?? status.callbackUrl),
      },
      ...(callbackSchemesValue ? [{
        id: 'callback_schemes',
        label: 'Callback Schemes',
        value: callbackSchemesValue,
        severity: 'info' as const,
        detail: callbackSchemesDetail(status),
      }] : []),
      {
        id: 'ios_open_url',
        label: 'iOS 回跳',
        value: iosOpenUrlValue(status, authorized),
        severity: iosOpenUrlSeverity(status, authorized),
        detail: iosOpenUrlDetail(status),
      },
      {
        id: 'auth_error',
        label: '最近授权错误',
        value: authErrorValue ?? (authorized ? '无近期授权错误' : '尚无授权错误'),
        severity: authErrorValue ? 'warn' : authorized ? 'pass' : 'info',
        detail: authErrorValue ? authorizationErrorDetail(status) : undefined,
      },
      ...(authAttemptValue ? [{
        id: 'auth_attempt',
        label: '授权 Attempt',
        value: authAttemptValue,
        severity: authorizationAttemptSeverity(status),
        detail: authorizationAttemptDetail(status),
      }] : []),
      ...(authStateTraceValue ? [{
        id: 'auth_state_trace',
        label: 'SDK 状态轨迹',
        value: authStateTraceValue,
        severity: 'info' as const,
        detail: status.authorizationConfigSummary,
      }] : []),
      ...(status.lastAuthorizationEvent ? [{
        id: 'auth_event',
        label: 'SDK 授权事件',
        value: status.lastAuthorizationEvent,
        severity: authorizationEventSeverity(status.lastAuthorizationEvent),
        detail: status.lastAuthorizationEventAt ? `eventAt=${formatRokidLogTimestamp(status.lastAuthorizationEventAt)}` : undefined,
      }] : []),
      ...(authTimeline.length > 0 ? [{
        id: 'auth_timeline',
        label: 'Native 授权时间线',
        value: authTimeline.map(formatRokidLogTimestamp).join('\n'),
        severity: authTimeline.some((line) => line.toLowerCase().includes('failed')) ? 'warn' as const : 'info' as const,
      }] : []),
      {
        id: 'session',
        label: '会话',
        ...session,
        detail: status.sessionMode,
      },
      {
        id: 'capture',
        label: '采集能力',
        value: status.capabilitiesReady ? '拍照 / 音频可用' : '等待会话完成',
        severity: status.capabilitiesReady ? 'pass' : 'warn',
      },
      {
        id: 'capability_route',
        label: '能力路由',
        value: capabilityRouteValue(capabilityGateway.recommendedPath),
        severity: capabilityRouteSeverity(capabilityGateway),
        detail: `显示=${capabilityGateway.summary.display}; 采集=${capabilityGateway.summary.capture}; 运动=${capabilityGateway.summary.movement}`,
      },
    ],
    validationSteps,
    capabilityGateway,
  };
}

export async function getRokidSelfCheck(): Promise<RokidSelfCheck> {
  return buildRokidSelfCheck(await getRokidIntegrationStatus());
}
