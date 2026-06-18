import {
  getRokidDeviceValidationSteps,
  getRokidIntegrationStatus,
  type RokidDeviceValidationStep,
  type RokidIntegrationStatus,
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
};

function passIf(condition: boolean, passValue: string, failValue: string, failSeverity: RokidSelfCheckSeverity) {
  return {
    value: condition ? passValue : failValue,
    severity: condition ? 'pass' as const : failSeverity,
  };
}

export function buildRokidSelfCheck(status: RokidIntegrationStatus): RokidSelfCheck {
  const bridgeReady = status.bridgeAvailable === true;
  const sdkLinked = status.sdkLinked === true;
  const companionReady = status.hiRokidInstalled === true && status.canOpenHiRokid === true;
  const authorized = status.authorizationState === 'authenticated';
  const sessionReady = status.customViewRunning === true && status.capabilitiesReady === true;
  const validationSteps = getRokidDeviceValidationSteps(status);

  const bridge = passIf(bridgeReady, 'Bridge 已就绪', 'Bridge 未就绪', 'block');
  const sdk = passIf(sdkLinked, 'SDK 已链接', 'SDK 未链接', bridgeReady ? 'warn' : 'block');
  const companion = passIf(companionReady, 'Hi Rokid 可用', 'Hi Rokid 未就绪', 'warn');
  const authorization = passIf(authorized, 'CXR-L 已授权', 'CXR-L 未授权', 'warn');
  const session = passIf(sessionReady, '会话能力就绪', '会话未构建完成', 'warn');
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
        label: 'Hi Rokid',
        ...companion,
        detail: companionReady ? '可唤起 Rokid AI / Hi Rokid' : '需要先安装并连接眼镜',
      },
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
        detail: status.lastCallbackUrl ?? status.callbackUrl,
      },
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
    ],
    validationSteps,
  };
}

export async function getRokidSelfCheck(): Promise<RokidSelfCheck> {
  return buildRokidSelfCheck(await getRokidIntegrationStatus());
}
