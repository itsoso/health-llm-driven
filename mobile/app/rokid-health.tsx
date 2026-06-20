import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import {
  formatRokidLogTimestamp,
  addRokidTranscriptListener,
  createRokidRevaCustomViewLayout,
  getRokidDeviceValidationSteps,
  getRokidIntegrationStatus,
  openRokidRevaCustomView,
  requestRokidAuthorization,
  takeRokidPhotoBase64,
  updateRokidCustomView,
  type RokidDeviceValidationStep,
  type RokidEventSubscription,
  type RokidIntegrationStatus,
  type RokidTranscriptEvent,
} from '../modules/rokid-bridge';
import {
  listRokidGlanceCards,
  openRokidCompanionIfAvailable,
  submitRokidVisualInput,
  type RokidVisualIntent,
} from '../services/rokidAmbient';
import {
  executeRokidVoiceClientAction,
  startRokidVoiceCommandCapture,
  stopRokidVoiceCommandCapture,
  submitRokidVoiceCommand,
} from '../services/rokidVoiceControl';
import { recognizeFood, type FoodRecognitionResponse } from '../services/diet';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

type PrivacyMode = 'private' | 'workplace' | 'public';
type OpenState = 'idle' | 'opening' | 'opened' | 'unavailable' | 'failed';
type CaptureStatus = 'idle' | 'capturing' | 'submitted' | 'failed';
type SessionStatus = 'idle' | 'running' | 'ready' | 'waiting' | 'failed';
type VoiceControlStatus = 'idle' | 'starting' | 'listening' | 'stopping' | 'failed';

type CaptureState = {
  status: CaptureStatus;
  actionTitle?: string;
  message?: string;
};

type RokidGlanceCard = {
  id?: string | number;
  title?: string;
  text?: string;
  summary?: string;
  action_text?: string;
  priority?: string;
  priority_tier?: string;
};

const PRIVACY_MODES: { key: PrivacyMode; label: string; description: string }[] = [
  { key: 'private', label: '私密', description: '可保留原始素材, 仍需主动触发' },
  { key: 'workplace', label: '办公', description: '默认保留摘要和 hash' },
  { key: 'public', label: '公共', description: '默认不保留原图和原音频' },
];

const CAPTURE_ACTIONS: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  detail: string;
  intent: RokidVisualIntent;
}[] = [
  { icon: 'fast-food-outline', title: '食物视觉记录', detail: '拍菜单 / 餐盘后生成饮食草稿', intent: 'food_scan' },
  { icon: 'nutrition-outline', title: '补剂标签扫描', detail: 'OCR 后进入补剂待确认队列', intent: 'supplement_scan' },
  { icon: 'medkit-outline', title: '用药标签扫描', detail: '只做识别和安全提示, 不自动改药', intent: 'medication_scan' },
] as const;

function statusLabel(status?: RokidIntegrationStatus) {
  if (!status) {
    return {
      hiRokid: '检测中',
      bridge: 'Bridge 检测中',
      sdk: 'SDK 检测中',
    };
  }
  const sdkRequestedButUnlinked = status.platform === 'ios'
    && status.bridgeAvailable === true
    && status.sdkLinked !== true
    && (
      status.iosSdkDependencyMode === 'requested_but_unlinked'
      || status.cxrCallbackApiEnabled === true
      || status.sdkLinkedReason?.includes('unavailable') === true
    );
  return {
    hiRokid: status.hiRokidInstalled ? 'Rokid companion 已安装' : '未检测到 Rokid companion',
    bridge: status.bridgeAvailable ? 'Bridge 已就绪' : 'Bridge 未就绪',
    sdk: status.sdkLinked ? 'SDK 已链接' : sdkRequestedButUnlinked ? 'SDK 请求但未导入' : 'SDK 未链接',
  };
}

function cardTitle(card: RokidGlanceCard) {
  return card.title || card.action_text || card.text || card.summary || `GlanceCard ${card.id ?? ''}`.trim();
}

function readString(result: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === 'string' && value.length > 0) {
      return value;
    }
  }
  return undefined;
}

function readNumber(result: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }
  return undefined;
}

function readValidSha256(result: Record<string, unknown>) {
  const value = readString(result, ['imageSha256', 'image_sha256', 'sha256']);
  if (!value || !/^[a-f0-9]{64}$/i.test(value)) {
    return undefined;
  }
  return value;
}

function recognitionConfidence(result?: FoodRecognitionResponse) {
  if (!result?.foods?.length) {
    return undefined;
  }
  const confidences = result.foods
    .map((food) => food.confidence)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (confidences.length === 0) {
    return undefined;
  }
  return confidences.reduce((sum, value) => sum + value, 0) / confidences.length;
}

function captureActionForVisualIntent(visualIntent?: string) {
  if (visualIntent) {
    const matched = CAPTURE_ACTIONS.find((action) => action.intent === visualIntent);
    if (matched) {
      return matched;
    }
  }
  return CAPTURE_ACTIONS.find((action) => action.intent === 'food_scan');
}

function isRokidNativeChannelNotReady(reason?: string) {
  if (!reason) {
    return false;
  }
  const normalized = reason.toLowerCase();
  return normalized.includes('rokid_custom_view_not_ready')
    || normalized.includes('rokid_custom_view_not_running_after_open')
    || normalized.includes('rokid_custom_view_open_callback_missing')
    || normalized.includes('rokid_glasses_ble_not_connected')
    || normalized.includes('rokid_capture_failed')
    || normalized.includes('rokid_record_failed');
}

function transcriptText(event: RokidTranscriptEvent) {
  const value = event.transcript ?? event.text;
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;
}

function transcriptCapturedAt(event: RokidTranscriptEvent) {
  const value = event.capturedAt ?? event.captured_at;
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function shouldRouteTranscript(event: RokidTranscriptEvent) {
  return event.partial !== true && event.isFinal !== false && event.is_final !== false && event.final !== false;
}

function iosAuthorizationLabel(status?: RokidIntegrationStatus) {
  switch (status?.authorizationState) {
    case 'authenticated':
      return '已授权';
    case 'authenticating':
      return '授权中';
    case 'expired':
      return '授权过期';
    case 'failed':
      return '授权失败';
    default:
      return '未授权';
  }
}

function isRecoverableRokidAuthorizationDelay(reason?: string) {
  if (!reason) {
    return false;
  }
  const normalized = reason.toLowerCase();
  return normalized.includes('鉴权请求超时')
    || normalized.includes('rgcxrclientautherror code=-1')
    || normalized.includes('authorization_callback_pending')
    || normalized.includes('authorization request timed out')
    || normalized.includes('request timeout')
    || normalized.includes('timeout');
}

function formatRokidAuthorizationIssue(reason?: string) {
  if (isRecoverableRokidAuthorizationDelay(reason)) {
    return '鉴权请求超时: Rokid AI / Hi Rokid 未在等待窗口内回调 Reva';
  }
  return reason ?? 'authorization_failed';
}

function formatRokidCustomViewIssue(reason?: string) {
  if (!reason) {
    return 'custom_view_failed';
  }
  const normalized = reason.toLowerCase();
  if (normalized.includes('rokid_glasses_ble_not_connected')) {
    return '眼镜蓝牙链路未连接: 授权完成后请「完全退出」Rokid AI / Hi Rokid(它会独占眼镜蓝牙, 一次只能一个 App 连眼镜), 再回 Reva 刷新。';
  }
  if (normalized.includes('rokid_custom_view_not_running_after_open')) {
    return 'SDK 已接受打开命令，但眼镜端没有回报 CustomView 运行。请确认眼镜端是否显示 Reva；若未显示，请重新打开眼镜视图。';
  }
  if (normalized.includes('rokid_custom_view_open_callback_missing')) {
    return 'SDK 没有返回 CustomView 打开回调，眼镜端也没有回报运行。请确认 Rokid AI 已退出后台占用后重新打开眼镜视图。';
  }
  return reason;
}

function buildAuthDiagnosticLines(status?: RokidIntegrationStatus) {
  const lines: string[] = [];
  if (!status) {
    return lines;
  }
  if (status.companionServerScheme && status.companionServerHost) {
    const device = status.currentDeviceName ? ` · device=${status.currentDeviceName}` : '';
    lines.push(`Companion: ${status.companionServerScheme}://${status.companionServerHost}${device}`);
  }
  if (status.nativeAppVersion || status.nativeBuildNumber) {
    lines.push(`Reva build: version=${status.nativeAppVersion ?? 'unknown'} · build=${status.nativeBuildNumber ?? 'unknown'}`);
  }
  if (
    typeof status.sdkLinked === 'boolean'
    || status.iosSdkDependencyMode
    || status.sdkLinkedReason
  ) {
    const parts: string[] = [];
    if (typeof status.sdkLinked === 'boolean') {
      parts.push(`sdkLinked=${status.sdkLinked}`);
    }
    if (status.iosSdkDependencyMode) {
      parts.push(`mode=${status.iosSdkDependencyMode}`);
    }
    if (status.sdkLinkedReason) {
      parts.push(`reason=${status.sdkLinkedReason}`);
    }
    lines.push(`SDK linkage: ${parts.join(' · ')}`);
  }
  if (status.lastAuthorizationAttemptId || status.authorizationAttemptCount || status.lastAuthorizationPhase) {
    const parts: string[] = [];
    if (status.lastAuthorizationAttemptId) {
      parts.push(status.lastAuthorizationAttemptId);
    }
    if (typeof status.authorizationAttemptCount === 'number') {
      parts.push(`#${status.authorizationAttemptCount}`);
    }
    if (status.lastAuthorizationPhase) {
      parts.push(`phase=${status.lastAuthorizationPhase}`);
    }
    if (typeof status.lastAuthorizationDurationMs === 'number') {
      parts.push(`duration=${status.lastAuthorizationDurationMs}ms`);
    }
    lines.push(`授权 attempt: ${parts.join(' · ')}`);
  }
  if (
    status.lastAuthorizationStateBeforeReset
    || status.lastAuthorizationStateAfterReset
    || status.lastAuthorizationStateBeforeAuthenticate
  ) {
    lines.push(
      `SDK state: beforeReset=${status.lastAuthorizationStateBeforeReset ?? 'unknown'}`
      + ` · afterReset=${status.lastAuthorizationStateAfterReset ?? 'unknown'}`
      + ` · beforeAuth=${status.lastAuthorizationStateBeforeAuthenticate ?? 'unknown'}`,
    );
  }
  if (status.authorizationConfigSummary) {
    lines.push(`Auth config: ${status.authorizationConfigSummary}`);
  }
  if (typeof status.iosBleConnected === 'boolean') {
    const device = status.iosBleDeviceName ? ` · device=${status.iosBleDeviceName}` : '';
    lines.push(`iOS BLE: connected=${status.iosBleConnected}${device}`);
  }
  if (typeof status.cxrCallbackApiEnabled === 'boolean' || status.cxrNotifySubscriptionMode) {
    const parts: string[] = [];
    if (typeof status.cxrCallbackApiEnabled === 'boolean') {
      parts.push(`callbackApi=${status.cxrCallbackApiEnabled}`);
    }
    if (status.cxrNotifySubscriptionMode) {
      parts.push(`notify=${status.cxrNotifySubscriptionMode}`);
    }
    lines.push(`CXR-L API: ${parts.join(' · ')}`);
  }
  if (typeof status.lastCustomViewPayloadBytes === 'number' || status.lastCustomViewPayloadHash) {
    const parts: string[] = [];
    if (typeof status.lastCustomViewPayloadBytes === 'number') {
      parts.push(`bytes=${status.lastCustomViewPayloadBytes}`);
    }
    if (status.lastCustomViewPayloadHash) {
      parts.push(`hash=${status.lastCustomViewPayloadHash}`);
    }
    lines.push(`CustomView payload: ${parts.join(' · ')}`);
  }
  if (status.lastCustomViewPayloadShape) {
    lines.push(`CustomView shape: ${status.lastCustomViewPayloadShape}`);
  }
  if (status.customViewPendingRetry === true || status.lastCustomViewAutoRetryAt) {
    const parts: string[] = [];
    if (status.customViewPendingRetry === true) {
      parts.push('pending=true');
    }
    if (status.lastCustomViewAutoRetryAt) {
      parts.push(`lastAutoRetry=${formatRokidLogTimestamp(status.lastCustomViewAutoRetryAt)}`);
    }
    lines.push(`CustomView retry: ${parts.join(' · ')}`);
  }
  if (status.lastCustomViewRawNotify) {
    const at = status.lastCustomViewRawNotifyAt ? ` · ${formatRokidLogTimestamp(status.lastCustomViewRawNotifyAt)}` : '';
    lines.push(`CustomView raw: ${status.lastCustomViewRawNotify}${at}`);
  }
  if (status.lastCustomViewOpenError) {
    lines.push(`CustomView error: ${status.lastCustomViewOpenError}`);
  }
  if (
    typeof status.lastCustomViewOpenCallbackSuccess === 'boolean'
    || status.lastCustomViewOpenCallbackErrorCode
  ) {
    const parts: string[] = [];
    if (typeof status.lastCustomViewOpenCallbackSuccess === 'boolean') {
      parts.push(`success=${status.lastCustomViewOpenCallbackSuccess}`);
    }
    if (status.lastCustomViewOpenCallbackErrorCode) {
      parts.push(`errorCode=${status.lastCustomViewOpenCallbackErrorCode}`);
    }
    if (status.lastCustomViewOpenCallbackAt) {
      parts.push(formatRokidLogTimestamp(status.lastCustomViewOpenCallbackAt));
    }
    lines.push(`CustomView callback: ${parts.join(' · ')}`);
  }
  if (Array.isArray(status.acceptedCallbackSchemes) && status.acceptedCallbackSchemes.length > 0) {
    const parts = [`accepted=${status.acceptedCallbackSchemes.join(', ')}`];
    if (status.callbackScheme) {
      parts.push(`configured=${status.callbackScheme}`);
    }
    if (status.callbackSchemeSource) {
      parts.push(`source=${status.callbackSchemeSource}`);
    }
    lines.push(`Callback schemes: ${parts.join(' · ')}`);
  }
  if (status.lastAuthorizationError) {
    lines.push(`最近授权错误: ${formatRokidAuthorizationIssue(status.lastAuthorizationError)}`);
  }
  if (status.lastAuthorizationEvent) {
    lines.push(`SDK 授权事件: ${status.lastAuthorizationEvent}`);
  }
  if (status.lastOpenUrlFingerprint) {
    const route = status.lastOpenUrlExpectedAuthCallback ? '匹配授权 scheme' : '不是授权 scheme';
    const at = status.lastOpenUrlAt ? ` · ${formatRokidLogTimestamp(status.lastOpenUrlAt)}` : '';
    lines.push(`iOS 回跳: ${status.lastOpenUrlFingerprint} · ${route}${at}`);
  }
  if (status.lastAuthorizationRequestAt) {
    lines.push(`最近授权请求: ${formatRokidLogTimestamp(status.lastAuthorizationRequestAt)}`);
  }
  if (typeof status.authorizationRequestTimeoutSeconds === 'number') {
    lines.push(`SDK 等待窗口: ${Math.round(status.authorizationRequestTimeoutSeconds)} 秒`);
  }
  if (status.lastCallbackAt) {
    lines.push(`最近回调: ${status.lastCallbackHandled ? 'SDK 已处理' : 'SDK 未确认'} · ${formatRokidLogTimestamp(status.lastCallbackAt)}`);
  } else if (status.lastAuthorizationError && isRecoverableRokidAuthorizationDelay(status.lastAuthorizationError)) {
    lines.push('最近回调: 尚未进入 Reva');
    lines.push('iOS 回跳: 尚未收到 AppDelegate openURL');
  }
  if (Array.isArray(status.authDiagnosticTimeline)) {
    status.authDiagnosticTimeline.slice(-6).forEach((entry) => {
      lines.push(`Native: ${formatRokidLogTimestamp(entry)}`);
    });
  }
  return lines;
}

export default function RokidHealthScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>('workplace');
  const [openState, setOpenState] = useState<OpenState>('idle');
  const [captureState, setCaptureState] = useState<CaptureState>({ status: 'idle' });
  const [sessionState, setSessionState] = useState<{
    status: SessionStatus;
    message?: string;
  }>({ status: 'idle' });
  const [voiceState, setVoiceState] = useState<{
    status: VoiceControlStatus;
    message?: string;
  }>({ status: 'idle' });
  const voiceTranscriptSubscriptionRef = useRef<RokidEventSubscription | null>(null);
  const voiceListeningRef = useRef(false);

  const statusQuery = useQuery({
    queryKey: ['rokid-health', 'status'],
    queryFn: getRokidIntegrationStatus,
    staleTime: 30_000,
  });
  const glanceQuery = useQuery({
    queryKey: ['rokid-health', 'glance-cards'],
    queryFn: listRokidGlanceCards,
    staleTime: 30_000,
  });

  const status = statusQuery.data;
  const labels = statusLabel(status);
  const glanceCards = Array.isArray(glanceQuery.data)
    ? (glanceQuery.data as RokidGlanceCard[])
    : [];
  const isIOS = status?.platform === 'ios';
  const iosCapabilitiesReady = isIOS && status?.capabilitiesReady === true;
  const validationSteps = useMemo(() => getRokidDeviceValidationSteps(status), [status]);
  const authDiagnosticLines = useMemo(() => buildAuthDiagnosticLines(status), [status]);
  const isRefreshing = statusQuery.isRefetching || glanceQuery.isRefetching;

  const removeVoiceTranscriptListener = () => {
    voiceTranscriptSubscriptionRef.current?.remove();
    voiceTranscriptSubscriptionRef.current = null;
  };

  const updateVoiceCustomView = async (body: string, priority = 'voice') => {
    try {
      await updateRokidCustomView(createRokidRevaCustomViewLayout({
        title: 'Reva 语音控制',
        body,
        priority,
      }));
    } catch {
      // The phone-side flow remains authoritative if glasses UI refresh fails.
    }
  };

  useEffect(() => removeVoiceTranscriptListener, []);

  const refresh = () => {
    statusQuery.refetch();
    glanceQuery.refetch();
  };

  const openMobileFoodCameraFallback = (action: (typeof CAPTURE_ACTIONS)[number]) => {
    setCaptureState({
      status: 'submitted',
      actionTitle: action.title,
      message: '眼镜拍照不可用，已切到手机拍照记录。',
    });
    router.push('/diet?capture=photo' as any);
  };

  const settleRokidAuthorizationStatus = async (attempts: number) => {
    let latest = statusQuery.data;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const refreshed = await statusQuery.refetch();
      latest = refreshed.data ?? latest;
      if (latest?.authorizationState === 'authenticated') {
        break;
      }
    }
    return latest;
  };

  const openCompanion = async () => {
    setOpenState('opening');
    try {
      const result = await openRokidCompanionIfAvailable();
      setOpenState(result.opened ? 'opened' : 'unavailable');
      await statusQuery.refetch();
    } catch {
      setOpenState('failed');
    }
  };

  const authorizeRokid = async () => {
    setSessionState({ status: 'running', message: 'Rokid 授权中...' });
    try {
      const result = await requestRokidAuthorization({
        appName: 'Reva',
        scopes: ['device_control', 'audio_stream'],
      });
      if (result.ok === false) {
        const reason = typeof result.reason === 'string' ? result.reason : 'rokid_authorization_failed';
        const settledStatus = await settleRokidAuthorizationStatus(3);
        if (settledStatus?.authorizationState === 'authenticated') {
          setSessionState({ status: 'ready', message: 'Rokid 已授权' });
          return;
        }
        if (isRecoverableRokidAuthorizationDelay(reason)) {
          setSessionState({
            status: 'waiting',
            message: '等待 Rokid 授权回调。请在 Rokid AI / Hi Rokid 完成授权后回到 Reva 并点刷新; 若仍超时, 继续点授权重试。',
          });
          return;
        }
        throw new Error(reason);
      }
      await settleRokidAuthorizationStatus(1);
      setSessionState({ status: 'ready', message: 'Rokid 已授权' });
    } catch (error) {
      setSessionState({
        status: 'failed',
        message: `Rokid 授权失败: ${error instanceof Error ? error.message : 'authorization_failed'}`,
      });
    }
  };

  const openRevaCustomView = async () => {
    setSessionState({ status: 'running', message: '正在打开 Reva 眼镜视图...' });
    try {
      const result = await openRokidRevaCustomView({
        title: 'Reva Health',
        body: '等待 Reva 投递下一条健康行动',
        priority: 'manual_confirm',
      });
      if (result.ok === false) {
        const reason = typeof result.reason === 'string' ? result.reason : 'rokid_custom_view_failed';
        // 眼镜蓝牙未连接时 native 已把本次 view 排入 pending,连上(connectionStatePublisher)会自动重发。
        // 这不是终态失败,显示"等待中"而非"失败",别误吓用户(council 共识 P2:Codex/Claude B/A)。
        if (result.customViewPendingRetry === true || reason.includes('rokid_glasses_ble_not_connected')) {
          try {
            await statusQuery.refetch();
          } catch {
            // diagnostics refresh is best-effort; the waiting message still stands.
          }
          setSessionState({
            status: 'waiting',
            message: '眼镜蓝牙未连接,已排队: 完全退出 Rokid AI / Hi Rokid 释放眼镜蓝牙后,Reva 会在连上时自动打开眼镜视图。',
          });
          return;
        }
        throw new Error(reason);
      }
      const refreshed = await statusQuery.refetch();
      const customViewRunning =
        result.customViewRunning === true ||
        refreshed.data?.customViewRunning === true;
      if (customViewRunning) {
        setSessionState({ status: 'ready', message: 'Reva 眼镜视图已运行' });
        return;
      }
      setSessionState({
        status: 'waiting',
        message: 'Reva 眼镜视图已请求打开，等待眼镜端确认运行。请确认眼镜已显示后刷新。',
      });
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'custom_view_failed';
      try {
        await statusQuery.refetch();
      } catch {
        // The failure message is still useful even if the diagnostic refresh fails.
      }
      setSessionState({
        status: 'failed',
        message: `Reva 眼镜视图失败: ${formatRokidCustomViewIssue(reason)}`,
      });
    }
  };

  const startVoiceControl = async () => {
    setVoiceState({ status: 'starting', message: 'Rokid 语音控制启动中...' });
    let recordingStarted = false;
    try {
      const recordResult = await startRokidVoiceCommandCapture();
      if (recordResult.ok === false) {
        throw new Error(typeof recordResult.reason === 'string' ? recordResult.reason : 'rokid_record_failed');
      }
      recordingStarted = true;
      const viewResult = await openRokidRevaCustomView({
        title: 'Reva 语音控制',
        body: '正在等待明确语音指令',
        priority: 'voice',
      });
      if (viewResult.ok === false) {
        throw new Error(typeof viewResult.reason === 'string' ? viewResult.reason : 'rokid_custom_view_failed');
      }
      removeVoiceTranscriptListener();
      voiceTranscriptSubscriptionRef.current = addRokidTranscriptListener((event) => {
        void handleVoiceTranscript(event);
      });
      voiceListeningRef.current = true;
      setVoiceState({ status: 'listening', message: 'Rokid 语音控制已开启' });
      await statusQuery.refetch();
    } catch (error) {
      voiceListeningRef.current = false;
      removeVoiceTranscriptListener();
      if (recordingStarted) {
        try {
          await stopRokidVoiceCommandCapture();
        } catch {
          // Best-effort cleanup; keep the original start failure visible.
        }
      }
      const reason = error instanceof Error ? error.message : 'voice_control_failed';
      setVoiceState({
        status: 'failed',
        message: isRokidNativeChannelNotReady(reason)
          ? '眼镜原生语音依赖 CustomView，目前不可用。先用下方入口继续：手机拍餐或本地俯卧撑。'
          : `Rokid 语音控制失败: ${reason}`,
      });
    }
  };

  const stopVoiceControl = async () => {
    setVoiceState({ status: 'stopping', message: 'Rokid 语音控制停止中...' });
    voiceListeningRef.current = false;
    removeVoiceTranscriptListener();
    try {
      const result = await stopRokidVoiceCommandCapture();
      if (result.ok === false) {
        throw new Error(typeof result.reason === 'string' ? result.reason : 'rokid_stop_record_failed');
      }
      setVoiceState({ status: 'idle', message: 'Rokid 语音控制已停止' });
      await statusQuery.refetch();
    } catch (error) {
      setVoiceState({
        status: 'failed',
        message: `Rokid 语音控制停止失败: ${error instanceof Error ? error.message : 'voice_control_stop_failed'}`,
      });
    } finally {
      removeVoiceTranscriptListener();
    }
  };

  const handleVisualCapture = async (action: (typeof CAPTURE_ACTIONS)[number]) => {
    setCaptureState({ status: 'capturing', actionTitle: action.title, message: `${action.title}提交中...` });
    try {
      if (status?.platform === 'ios' && status.capabilitiesReady !== true) {
        if (action.intent === 'food_scan') {
          openMobileFoodCameraFallback(action);
          return;
        }
        throw new Error('rokid_custom_view_not_ready');
      }
      const captureResult = await takeRokidPhotoBase64({ width: 1024, height: 768, quality: 80 });
      if (captureResult.ok === false) {
        const reason = typeof captureResult.reason === 'string' ? captureResult.reason : 'rokid_capture_failed';
        if (action.intent === 'food_scan' && isRokidNativeChannelNotReady(reason)) {
          openMobileFoodCameraFallback(action);
          return;
        }
        throw new Error(reason);
      }
      const imageBase64 = readString(captureResult, ['base64', 'imageBase64', 'image_base64']);
      const imageByteLength = readNumber(captureResult, ['byteLength', 'byte_length', 'size']);
      const meta: Record<string, unknown> = {
        privacy_mode: privacyMode,
        source_surface: 'rokid_health_mode',
        raw_media_retained: false,
        manual_confirm_required: true,
      };
      if (typeof imageByteLength === 'number') {
        meta.image_byte_length = imageByteLength;
      }

      let recognitionResult: Record<string, unknown> | undefined;
      let confidence: number | undefined;
      if (action.intent === 'food_scan' && imageBase64) {
        try {
          const recognition = await recognizeFood(imageBase64);
          recognitionResult = recognition as unknown as Record<string, unknown>;
          confidence = recognitionConfidence(recognition);
          meta.recognition_source = 'diet_recognize';
        } catch (error) {
          meta.recognition_error = error instanceof Error ? error.message : 'food_recognition_failed';
        }
      }

      await submitRokidVisualInput({
        intent: action.intent,
        imageUri: readString(captureResult, ['imageUri', 'image_uri', 'uri', 'localUri', 'path']),
        imageSha256: readValidSha256(captureResult),
        recognitionResult,
        confidence,
        privacyClass: 'health_l3',
        meta,
      });

      setCaptureState({
        status: 'submitted',
        actionTitle: action.title,
        message: `已提交${action.title}草稿`,
      });
    } catch (error) {
      setCaptureState({
        status: 'failed',
        actionTitle: action.title,
        message: `${action.title}失败: ${error instanceof Error ? error.message : 'capture_failed'}`,
      });
    }
  };

  async function handleVoiceTranscript(event: RokidTranscriptEvent) {
    if (!voiceListeningRef.current) {
      return;
    }
    if (!shouldRouteTranscript(event)) {
      return;
    }
    const transcript = transcriptText(event);
    if (!transcript) {
      return;
    }

    setVoiceState({ status: 'listening', message: `识别: ${transcript}` });
    void updateVoiceCustomView(`识别: ${transcript}`);
    try {
      const response = await submitRokidVoiceCommand({
        transcript,
        confidence: typeof event.confidence === 'number' ? event.confidence : undefined,
        context: 'rokid_health',
        capturedAt: transcriptCapturedAt(event),
        meta: {
          source_surface: 'rokid_health_mode',
          source_event: 'rokid_transcript',
          ...(event.meta ?? {}),
        },
      });
      const command = response.command;
      const reply = command?.voice_reply || command?.display_text;
      if (reply) {
        setVoiceState({ status: 'listening', message: reply });
        await updateVoiceCustomView(reply);
      }
      await executeRokidVoiceClientAction(response, {
        captureFoodPhoto: async ({ visualIntent }) => {
          const action = captureActionForVisualIntent(visualIntent);
          if (!action) {
            setVoiceState({ status: 'failed', message: `Rokid 语音指令不支持视觉意图: ${visualIntent}` });
            return;
          }
          await handleVisualCapture(action);
        },
        openPushupCoach: async ({ route }) => {
          router.push((route ?? '/rokid-pushup-coach') as any);
        },
        stopPushupCoach: async ({ route }) => {
          if (route) {
            router.push(route as any);
          }
        },
        savePushupSet: async ({ route }) => {
          if (route) {
            router.push(route as any);
          }
        },
        openGuidedTask: async ({ route }) => {
          router.push(route as any);
        },
        clarify: async (commandToClarify) => {
          setVoiceState({
            status: 'listening',
            message: commandToClarify.voice_reply || commandToClarify.display_text || '请再说一遍',
          });
        },
      });
    } catch (error) {
      setVoiceState({
        status: 'failed',
        message: `Rokid 语音指令失败: ${error instanceof Error ? error.message : 'voice_command_failed'}`,
      });
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="返回"
          hitSlop={10}
        >
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>Rokid 眼镜健康模式</Text>
        <Pressable
          onPress={refresh}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="刷新 Rokid 状态"
          hitSlop={10}
        >
          <Ionicons name="refresh" size={20} color={c.labelSecondary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={refresh} />}
      >
        <View style={styles.panel}>
          <View style={styles.panelHeader}>
            <View style={styles.panelIcon}>
              <Ionicons name="scan-outline" size={20} color={c.brand} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={txt.panelTitle}>Ambient capture surface</Text>
              <Text style={txt.panelSub}>眼镜只负责低摩擦捕获和短提示, 决策仍回到 Reva Health OS。</Text>
            </View>
          </View>

          <View style={styles.statusGrid}>
            <StatusPill label={labels.hiRokid} ok={status?.hiRokidInstalled === true} />
            <StatusPill label={labels.bridge} ok={status?.bridgeAvailable === true} />
            <StatusPill label={labels.sdk} ok={status?.sdkLinked === true} muted={!status?.sdkLinked} />
          </View>

          <Pressable
            onPress={openCompanion}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed,
              openState === 'opening' && styles.disabledButton,
            ]}
            disabled={openState === 'opening'}
            accessibilityRole="button"
          >
            <Ionicons name="open-outline" size={17} color="#fff" />
            <Text style={txt.primaryButton}>{openState === 'opening' ? '打开中...' : '打开 Rokid AI / Hi Rokid'}</Text>
          </Pressable>

          {isIOS ? (
            <View style={styles.iosSessionBox}>
              <View style={styles.statusGrid}>
                <StatusPill
                  label={iosAuthorizationLabel(status)}
                  ok={status?.authorizationState === 'authenticated'}
                  muted={!status?.authorizationState || status.authorizationState === 'not_authenticated'}
                />
                <StatusPill
                  label={status?.customViewRunning ? 'CustomView 运行中' : 'CustomView 未运行'}
                  ok={status?.customViewRunning === true}
                  muted={!status?.customViewRunning}
                />
                <StatusPill
                  label={iosCapabilitiesReady ? '能力已就绪' : '能力未就绪'}
                  ok={iosCapabilitiesReady}
                  muted={!iosCapabilitiesReady}
                />
              </View>
              <View style={styles.buttonRow}>
                <Pressable
                  onPress={authorizeRokid}
                  disabled={!status?.sdkLinked || sessionState.status === 'running'}
                  style={({ pressed }) => [
                    styles.secondaryButton,
                    pressed && styles.pressed,
                    (!status?.sdkLinked || sessionState.status === 'running') && styles.disabledButton,
                  ]}
                  accessibilityRole="button"
                >
                  <Ionicons name="key-outline" size={16} color={c.brand} />
                  <Text style={txt.secondaryButton}>授权 Rokid</Text>
                </Pressable>
                <Pressable
                  onPress={openRevaCustomView}
                  disabled={!status?.sdkLinked || sessionState.status === 'running'}
                  style={({ pressed }) => [
                    styles.secondaryButton,
                    pressed && styles.pressed,
                    (!status?.sdkLinked || sessionState.status === 'running') && styles.disabledButton,
                  ]}
                  accessibilityRole="button"
                >
                  <Ionicons name="browsers-outline" size={16} color={c.brand} />
                  <Text style={txt.secondaryButton}>打开 Reva 眼镜视图</Text>
                </Pressable>
              </View>
              {sessionState.message ? (
                <Text style={[
                  txt.sessionMessage,
                  sessionState.status === 'ready' ? { color: s.success.solid } : null,
                  sessionState.status === 'waiting' ? { color: c.brand } : null,
                  sessionState.status === 'failed' ? { color: s.warning.solid } : null,
                ]}>
                  {sessionState.message}
                </Text>
              ) : null}

              {authDiagnosticLines.length > 0 ? (
                <View style={styles.authDiagnosticBox}>
                  {authDiagnosticLines.map((line) => (
                    <Text key={line} style={txt.authDiagnostic} numberOfLines={3}>{line}</Text>
                  ))}
                </View>
              ) : null}

              <View style={styles.validationBox}>
                <Text style={txt.validationHeading}>真机验证</Text>
                {validationSteps.map((step) => {
                  const tone = validationTone(step);
                  return (
                    <View key={step.id} style={styles.validationRow}>
                      <View style={[styles.validationIcon, { backgroundColor: tone.bg }]}>
                        <Ionicons name={validationIcon(step.status)} size={16} color={tone.fg} />
                      </View>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <View style={styles.validationTitleRow}>
                          <Text style={txt.validationTitle} numberOfLines={1}>{step.title}</Text>
                          {step.status === 'next' && step.actionLabel ? (
                            <Text style={txt.validationNext} numberOfLines={1}>
                              下一步: {step.actionLabel}
                            </Text>
                          ) : null}
                        </View>
                        <Text style={txt.validationDetail} numberOfLines={2}>{step.detail}</Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          ) : null}

          {openState !== 'idle' && openState !== 'opening' ? (
            <Text style={[
              txt.openState,
              openState === 'opened' ? { color: s.success.solid } : { color: s.warning.solid },
            ]}>
              {openState === 'opened' ? '已请求打开 Rokid AI / Hi Rokid' : '当前设备无法打开 Rokid AI / Hi Rokid'}
            </Text>
          ) : null}

          <Pressable
            onPress={() => router.push('/rokid-pushup-coach' as any)}
            style={({ pressed }) => [styles.featureRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="打开 Rokid 俯卧撑计数"
          >
            <View style={styles.featureIcon}>
              <Ionicons name="body-outline" size={18} color={c.orange} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={txt.featureTitle}>俯卧撑计数</Text>
              <Text style={txt.featureDetail}>眼镜视图展示计数、动作评价和下一步建议。</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
          </Pressable>
        </View>

        <View style={styles.panel}>
          <View style={styles.sectionHeader}>
            <Text style={txt.sectionTitle}>语音控制</Text>
            <Text style={[
              txt.sessionState,
              voiceState.status === 'listening' ? { color: s.success.solid } : null,
              voiceState.status === 'failed' ? { color: s.warning.solid } : null,
            ]}>
              {voiceState.status === 'listening'
                ? '已开启'
                : voiceState.status === 'starting'
                  ? '启动中'
                  : voiceState.status === 'stopping'
                    ? '停止中'
                    : '未开启'}
            </Text>
          </View>
          <View style={styles.buttonRow}>
            <Pressable
              onPress={startVoiceControl}
              disabled={voiceState.status === 'starting' || voiceState.status === 'listening' || voiceState.status === 'stopping'}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                (voiceState.status === 'starting' || voiceState.status === 'listening' || voiceState.status === 'stopping') && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="mic-outline" size={17} color="#fff" />
              <Text style={txt.primaryButton}>
                {voiceState.status === 'starting' ? '启动中...' : '启动语音控制'}
              </Text>
            </Pressable>
            <Pressable
              onPress={stopVoiceControl}
              disabled={voiceState.status !== 'listening'}
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed && styles.pressed,
                voiceState.status !== 'listening' && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="mic-off-outline" size={16} color={c.brand} />
              <Text style={txt.secondaryButton}>停止语音控制</Text>
            </Pressable>
          </View>
          {voiceState.message ? (
            <Text style={[
              txt.sessionMessage,
              voiceState.status === 'listening' ? { color: s.success.solid } : null,
              voiceState.status === 'failed' ? { color: s.warning.solid } : null,
            ]}>
              {voiceState.message}
            </Text>
          ) : null}
          {voiceState.status === 'failed' ? (
            <View style={styles.fallbackActions}>
              <Pressable
                onPress={() => router.push('/diet?capture=photo' as any)}
                style={({ pressed }) => [styles.fallbackButton, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel="手机拍餐"
              >
                <Ionicons name="camera-outline" size={16} color={c.brand} />
                <Text style={txt.fallbackButton}>手机拍餐</Text>
              </Pressable>
              <Pressable
                onPress={() => router.push('/rokid-pushup-coach' as any)}
                style={({ pressed }) => [styles.fallbackButton, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel="本地俯卧撑"
              >
                <Ionicons name="body-outline" size={16} color={c.brand} />
                <Text style={txt.fallbackButton}>本地俯卧撑</Text>
              </Pressable>
            </View>
          ) : null}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>隐私模式</Text>
          <View style={styles.segmentRow}>
            {PRIVACY_MODES.map((mode) => {
              const active = mode.key === privacyMode;
              return (
                <Pressable
                  key={mode.key}
                  onPress={() => setPrivacyMode(mode.key)}
                  style={[styles.segment, active && { backgroundColor: c.brand }]}
                  accessibilityRole="button"
                >
                  <Text style={[txt.segmentText, active && { color: '#fff' }]}>{mode.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={txt.privacyDesc}>
            {PRIVACY_MODES.find((mode) => mode.key === privacyMode)?.description}
          </Text>
          <BoundaryRow icon="radio-button-on-outline" text="仅主动触发拍照 / 录音" />
          <BoundaryRow icon="business-outline" text="办公 / 公共场景默认保留摘要和 hash" />
          <BoundaryRow icon="shield-checkmark-outline" text="用药和补剂只生成待确认草稿" />
        </View>

        <View style={styles.panel}>
          <View style={styles.sectionHeader}>
            <Text style={txt.sectionTitle}>待投递短提示</Text>
            {glanceQuery.isLoading ? <ActivityIndicator size="small" color={c.labelTertiary} /> : null}
          </View>
          {glanceQuery.isError ? (
            <Text style={txt.empty}>GlanceCard 加载失败, 下拉重试。</Text>
          ) : glanceCards.length === 0 ? (
            <Text style={txt.empty}>暂无 Rokid glasses surface 的行动卡。</Text>
          ) : (
            glanceCards.map((card, index) => (
              <View key={`${card.id ?? index}`} style={styles.glanceRow}>
                <View style={styles.glanceIndex}>
                  <Text style={txt.glanceIndex}>{index + 1}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={txt.glanceTitle} numberOfLines={2}>{cardTitle(card)}</Text>
                  <Text style={txt.glanceMeta} numberOfLines={1}>
                    {card.priority || card.priority_tier || 'manual_confirm'}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>捕获动作</Text>
          <Text style={txt.sectionHint}>每次点击只触发一次拍照, 生成待确认草稿; 不连续录音、不后台拍摄。</Text>
          {CAPTURE_ACTIONS.map((action) => (
            <Pressable
              key={action.title}
              onPress={() => handleVisualCapture(action)}
              disabled={captureState.status === 'capturing'}
              style={({ pressed }) => [
                styles.captureRow,
                pressed && styles.pressed,
                captureState.status === 'capturing' && styles.disabledButton,
              ]}
              accessibilityRole="button"
              accessibilityLabel={`主动触发 ${action.title}`}
            >
              <View style={styles.captureIcon}>
                <Ionicons name={action.icon} size={18} color={c.brand} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={txt.captureTitle}>{action.title}</Text>
                <Text style={txt.captureDetail}>{action.detail}</Text>
              </View>
              <Text style={txt.captureStatus}>
                {captureState.status === 'capturing' && captureState.actionTitle === action.title ? '提交中' : '主动触发'}
              </Text>
            </Pressable>
          ))}
          {captureState.message ? (
            <Text style={[
              txt.captureMessage,
              captureState.status === 'submitted' ? { color: s.success.solid } : null,
              captureState.status === 'failed' ? { color: s.warning.solid } : null,
            ]}>
              {captureState.message}
            </Text>
          ) : null}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>最近捕获</Text>
          <Text style={txt.empty}>
            {captureState.message ? `最近状态: ${captureState.message}` : '等待主动触发。不会连续录音或后台拍摄。'}
          </Text>
          {status?.installedPackage ? (
            <Text style={txt.technical}>Rokid companion package: {status.installedPackage}</Text>
          ) : null}
          {status?.iosSdkCompatibility ? (
            <Text style={txt.technical}>{status.iosSdkCompatibility}</Text>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );

  function StatusPill({
    label,
    ok,
    muted = false,
  }: {
    label: string;
    ok: boolean;
    muted?: boolean;
  }) {
    const color = ok ? s.success.solid : muted ? c.labelTertiary : s.warning.solid;
    const bg = ok ? s.success.bg : muted ? c.fill : s.warning.bg;
    return (
      <View style={[styles.statusPill, { backgroundColor: bg }]}>
        <View style={[styles.statusDot, { backgroundColor: color }]} />
        <Text style={[txt.statusPill, { color }]} numberOfLines={1}>{label}</Text>
      </View>
    );
  }

  function BoundaryRow({ icon, text }: { icon: keyof typeof Ionicons.glyphMap; text: string }) {
    return (
      <View style={styles.boundaryRow}>
        <Ionicons name={icon} size={15} color={c.labelSecondary} />
        <Text style={txt.boundaryText}>{text}</Text>
      </View>
    );
  }

  function validationIcon(status: RokidDeviceValidationStep['status']): keyof typeof Ionicons.glyphMap {
    switch (status) {
      case 'done':
        return 'checkmark-circle';
      case 'blocked':
        return 'alert-circle';
      case 'next':
        return 'radio-button-on';
      default:
        return 'ellipse-outline';
    }
  }

  function validationTone(step: RokidDeviceValidationStep) {
    switch (step.status) {
      case 'done':
        return { fg: s.success.solid, bg: s.success.bg };
      case 'blocked':
        return { fg: s.warning.solid, bg: s.warning.bg };
      case 'next':
        return { fg: c.brand, bg: c.brandLight };
      default:
        return { fg: c.labelTertiary, bg: c.fill };
    }
  }
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  iconButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    padding: spacing.lg,
    paddingBottom: 110,
  },
  panel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  panelHeader: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  panelIcon: {
    width: 40,
    height: 40,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brandLight,
  },
  statusGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: spacing.md,
  },
  statusPill: {
    minHeight: 30,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  primaryButton: {
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: c.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  iosSessionBox: {
    marginTop: spacing.sm,
  },
  buttonRow: {
    flexDirection: 'column',
    gap: 8,
  },
  validationBox: {
    marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
    paddingTop: spacing.md,
    gap: 10,
  },
  authDiagnosticBox: {
    marginTop: spacing.sm,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    padding: spacing.sm,
    gap: 4,
  },
  validationRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  validationIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  validationTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  secondaryButton: {
    minHeight: 42,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: spacing.sm,
  },
  pressed: { opacity: 0.82 },
  disabledButton: { opacity: 0.55 },
  segmentRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  segment: {
    flex: 1,
    minHeight: 34,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boundaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: spacing.sm,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  glanceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  glanceIndex: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: c.brandLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  captureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  captureIcon: {
    width: 30,
    height: 30,
    borderRadius: radii.sm,
    backgroundColor: c.brandLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  featureRow: {
    marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
    paddingTop: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  featureIcon: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    backgroundColor: c.tintOrange,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fallbackActions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  fallbackButton: {
    flex: 1,
    minHeight: 40,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: spacing.sm,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  panelTitle: { fontSize: 17, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  panelSub: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 3 } as TextStyle,
  primaryButton: { fontSize: 15, fontWeight: '800', color: '#fff' } as TextStyle,
  secondaryButton: { fontSize: 12, fontWeight: '800', color: c.brand, textAlign: 'center' } as TextStyle,
  openState: { fontSize: 12, fontWeight: '700', marginTop: spacing.sm, textAlign: 'center' } as TextStyle,
  sessionMessage: { fontSize: 12, fontWeight: '700', marginTop: spacing.sm, textAlign: 'center' } as TextStyle,
  authDiagnostic: { fontSize: 11, fontWeight: '700', color: c.labelSecondary, lineHeight: 16 } as TextStyle,
  validationHeading: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  validationTitle: { flex: 1, fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  validationNext: { fontSize: 11, fontWeight: '800', color: c.brand, maxWidth: 140 } as TextStyle,
  validationDetail: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sessionState: { fontSize: 12, fontWeight: '800', color: c.labelSecondary } as TextStyle,
  sectionHint: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 4, marginBottom: spacing.sm } as TextStyle,
  statusPill: { fontSize: 12, fontWeight: '800', maxWidth: 140 } as TextStyle,
  segmentText: { fontSize: 13, fontWeight: '800', color: c.labelSecondary } as TextStyle,
  privacyDesc: { fontSize: 12, color: c.labelSecondary, lineHeight: 17, marginBottom: spacing.xs } as TextStyle,
  boundaryText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.labelSecondary } as TextStyle,
  empty: { fontSize: 13, lineHeight: 19, color: c.labelTertiary } as TextStyle,
  glanceIndex: { fontSize: 12, fontWeight: '800', color: c.brand } as TextStyle,
  glanceTitle: { fontSize: 14, fontWeight: '700', color: c.labelPrimary, lineHeight: 19 } as TextStyle,
  glanceMeta: { fontSize: 11, color: c.labelTertiary, fontWeight: '700', marginTop: 2 } as TextStyle,
  captureTitle: { fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  captureDetail: { fontSize: 12, color: c.labelSecondary, lineHeight: 17, marginTop: 2 } as TextStyle,
  captureStatus: { fontSize: 11, color: c.labelTertiary, fontWeight: '800' } as TextStyle,
  captureMessage: { fontSize: 12, fontWeight: '700', lineHeight: 17, marginTop: spacing.sm } as TextStyle,
  featureTitle: { fontSize: 14, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  featureDetail: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  fallbackButton: { fontSize: 12, fontWeight: '800', color: c.brand, textAlign: 'center' } as TextStyle,
  technical: { fontSize: 11, color: c.labelTertiary, marginTop: spacing.sm, lineHeight: 16 } as TextStyle,
});
