import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useFocusEffect, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as Clipboard from 'expo-clipboard';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';

import {
  closeRokidCustomView,
  getRokidIntegrationStatus,
  installBundledRokidApp,
  installRokidAppFromFileUri,
  openRokidCustomView,
  openRokidApp,
  queryRokidApp,
  stopRokidApp,
  updateRokidCustomView,
  type RokidIntegrationStatus,
} from '../modules/rokid-bridge';
import { invalidateRecordMutation } from '../applib/queryKeys';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import api from '../services/api';
import {
  buildPushupExercisePayload,
  createPushupCoachState,
  createRokidPushupCoachCustomViewLayout,
  updatePushupCoach,
  type PushupCoachState,
  type PushupPoseSample,
} from '../services/pushupCoach';
import {
  ROKID_PUSHUP_APK_DOWNLOAD_URL,
  ROKID_PUSHUP_APK_RESOURCE_EXTENSION,
  ROKID_PUSHUP_APK_RESOURCE_NAME,
  ROKID_PUSHUP_APP_ACTIVITY,
  ROKID_PUSHUP_APP_PACKAGE,
  applyRokidPushupEventToCoach,
  createRokidPushupSession,
  finishRokidPushupSession,
  getRokidPushupSessionReview,
  listRokidPushupEvents,
  type RokidPushupSession,
  type RokidPushupSessionReview,
} from '../services/rokidPushupSession';

type RokidSessionState = 'idle' | 'opening' | 'opened' | 'failed';
type RealPoseSessionState = 'idle' | 'installing' | 'creating' | 'running' | 'stopping' | 'failed';
type SaveState = 'idle' | 'saving' | 'saved' | 'failed';
type GlassesAppInstallStatus = 'unknown' | 'checking' | 'installed' | 'missing';
type GlassesAppInstallPhase = 'idle' | 'downloading' | 'downloaded' | 'installing' | 'confirming' | 'succeeded' | 'failed';
type GlassesAppInstallSnapshot = {
  phase: GlassesAppInstallPhase;
  diagnostics: string[];
  message: string;
  error: string | null;
};

const ROKID_PUSHUP_APK_CACHE_NAME = 'rokid-pushup-glasses.apk';
const ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS = 3;
const ROKID_PUSHUP_APK_MIN_BYTES = 15 * 1024 * 1024;
const ROKID_PUSHUP_APK_INSTALL_PENDING_LOG_INTERVAL_MS = 30 * 1000;
const ROKID_PUSHUP_APK_INSTALL_NATIVE_TIMEOUT_MS = 25 * 60 * 1000;

// 模块级:眼镜端 App 的安装是后台进行的——用户可离开本页,安装(下载约20MB + 传到眼镜)
// 继续跑;再次进入/点击时复用这个 in-flight promise,不重启下载。组件卸载不影响它。
let glassesAppInstallInFlight: Promise<void> | null = null;
let glassesAppInstallStartedAt = 0;
let glassesAppInstallSnapshot: GlassesAppInstallSnapshot = {
  phase: 'idle',
  diagnostics: [],
  message: '',
  error: null,
};
const glassesAppInstallListeners = new Set<(snapshot: GlassesAppInstallSnapshot) => void>();
// APK 经弱网下载 + BLE/Hi Rokid 传眼镜可能很慢,但单例必须有上限——否则下载/BLE 传输/picker 永不 settle
// 会把整个安装流程永久锁死(council P1)。超时后下次 acquire 会重起。
const GLASSES_APP_INSTALL_TIMEOUT_MS = 30 * 60 * 1000;

export function __resetRokidPushupInstallStateForTests() {
  glassesAppInstallInFlight = null;
  glassesAppInstallStartedAt = 0;
  glassesAppInstallSnapshot = {
    phase: 'idle',
    diagnostics: [],
    message: '',
    error: null,
  };
  glassesAppInstallListeners.clear();
}

function copyGlassesAppInstallSnapshot() {
  return {
    ...glassesAppInstallSnapshot,
    diagnostics: [...glassesAppInstallSnapshot.diagnostics],
  };
}

function notifyGlassesAppInstallListeners() {
  const snapshot = copyGlassesAppInstallSnapshot();
  for (const listener of glassesAppInstallListeners) {
    listener(snapshot);
  }
  return snapshot;
}

function setGlassesAppInstallSnapshot(partial: Partial<GlassesAppInstallSnapshot>) {
  glassesAppInstallSnapshot = {
    ...glassesAppInstallSnapshot,
    ...partial,
    diagnostics: partial.diagnostics ?? glassesAppInstallSnapshot.diagnostics,
  };
  return notifyGlassesAppInstallListeners();
}

function beginGlassesAppInstallTask(message: string) {
  glassesAppInstallSnapshot = {
    phase: 'installing',
    diagnostics: [],
    message,
    error: null,
  };
  return notifyGlassesAppInstallListeners();
}

function appendGlassesAppInstallDiagnostic(message: string) {
  glassesAppInstallSnapshot = {
    ...glassesAppInstallSnapshot,
    diagnostics: [
      ...glassesAppInstallSnapshot.diagnostics.slice(-39),
      `${formatBeijingTimestamp()} ${message}`,
    ],
  };
  return notifyGlassesAppInstallListeners();
}

function subscribeGlassesAppInstallState(listener: (snapshot: GlassesAppInstallSnapshot) => void) {
  glassesAppInstallListeners.add(listener);
  listener(copyGlassesAppInstallSnapshot());
  return () => {
    glassesAppInstallListeners.delete(listener);
  };
}

function readResultOk(result: Record<string, unknown>) {
  return result.ok !== false;
}

function resultReason(result: Record<string, unknown>, fallback: string) {
  return typeof result.reason === 'string' ? result.reason : fallback;
}

function resultFailureDetail(result: Record<string, unknown>, fallback: string) {
  const reason = resultReason(result, fallback);
  if (reason === 'rokid_cxrl_wrong_session_mode') {
    const mode = typeof result.cxrInitializationMode === 'string'
      ? result.cxrInitializationMode
      : 'unknown';
    const relaunchRequired = result.relaunchRequired === true ? 'true' : 'false';
    return `${reason}; currentMode=${mode}; relaunchRequired=${relaunchRequired}`;
  }
  return reason;
}

function nativeBuildNeedsCustomAppFix(status?: Partial<RokidIntegrationStatus> | null) {
  const build = Number.parseInt(status?.nativeBuildNumber ?? '', 10);
  return Number.isFinite(build) && build < 179;
}

function resultInstallFailureDetail(
  result: Record<string, unknown>,
  fallback: string,
  status?: Partial<RokidIntegrationStatus> | null,
) {
  const detail = resultFailureDetail(result, fallback);
  if (detail === fallback && result.installed === false) {
    const nativeBuild = status?.nativeBuildNumber ?? 'unknown';
    const requiredBuild = nativeBuildNeedsCustomAppFix(status) ? '; requiredBuild>=179' : '';
    return `rokid_app_install_rejected_without_reason; nativeBuild=${nativeBuild}${requiredBuild}`;
  }
  return detail;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function isRetryableRokidApkDownloadFailure(detail: string) {
  const normalized = detail.toLowerCase();
  if (/rokid_apk_download_http_4\d\d/.test(normalized)) {
    return false;
  }
  if (normalized.includes('rokid_apk_download_too_small')) {
    return false;
  }
  return true;
}

function formatBeijingTimestamp(date = new Date()) {
  return `${date.toLocaleString('sv-SE', {
    timeZone: 'Asia/Shanghai',
    hour12: false,
  }).replace(' ', 'T')}+08:00`;
}

function formatBytes(bytes?: number | null) {
  if (!bytes || bytes <= 0) {
    return 'unknown';
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(1)}KB`;
  }
  return `${bytes}B`;
}

function compactResult(result: Record<string, unknown>) {
  return Object.entries(result)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join('; ');
}

function compactRokidInstallStatus(status: Partial<RokidIntegrationStatus>) {
  const nativeBuild = status.nativeBuildNumber ?? 'unknown';
  const requiredBuild = nativeBuildNeedsCustomAppFix(status) ? '; requiredBuild>=179' : '';
  return [
    `nativeBuild=${nativeBuild}${requiredBuild}`,
    `version=${status.nativeAppVersion ?? 'unknown'}`,
    `sdkLinked=${String(status.sdkLinked ?? 'unknown')}`,
    `cxrMode=${status.cxrInitializationMode ?? 'unknown'}`,
    `auth=${status.authorizationState ?? 'unknown'}`,
    `bleConnected=${String(status.iosBleConnected ?? 'unknown')}`,
    `bleDevice=${status.iosBleDeviceName ?? 'unknown'}`,
  ].join('; ');
}

async function captureRokidInstallStatusDiagnostic(
  phase: string,
  appendDiagnostic: (message: string) => void,
) {
  try {
    const status = await getRokidIntegrationStatus();
    appendDiagnostic(`native_status phase=${phase}; ${compactRokidInstallStatus(status)}`);
    return status;
  } catch (error) {
    appendDiagnostic(`native_status_failed phase=${phase}; ${errorMessage(error, 'unknown')}`);
    return null;
  }
}

async function waitForNativeInstallWithDiagnostics<T>(
  operationName: string,
  operation: () => Promise<T>,
  appendDiagnostic: (message: string) => void,
) {
  const startedAt = Date.now();
  const installPromise = operation();
  installPromise.catch(() => undefined);

  const pendingTimer = setInterval(() => {
    appendDiagnostic(
      `${operationName}_pending elapsedMs=${Date.now() - startedAt}; timeoutMs=${ROKID_PUSHUP_APK_INSTALL_NATIVE_TIMEOUT_MS}`,
    );
  }, ROKID_PUSHUP_APK_INSTALL_PENDING_LOG_INTERVAL_MS);

  let timeoutTimer: ReturnType<typeof setTimeout> | null = null;
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timeoutTimer = setTimeout(() => {
      const elapsedMs = Date.now() - startedAt;
      appendDiagnostic(`${operationName}_timeout elapsedMs=${elapsedMs}; timeoutMs=${ROKID_PUSHUP_APK_INSTALL_NATIVE_TIMEOUT_MS}`);
      reject(new Error(`rokid_app_install_timeout; operation=${operationName}; timeoutMs=${ROKID_PUSHUP_APK_INSTALL_NATIVE_TIMEOUT_MS}`));
    }, ROKID_PUSHUP_APK_INSTALL_NATIVE_TIMEOUT_MS);
  });

  try {
    return await Promise.race([installPromise, timeoutPromise]);
  } finally {
    clearInterval(pendingTimer);
    if (timeoutTimer) {
      clearTimeout(timeoutTimer);
    }
  }
}

// council R3 #2:query/open/stop 等单发原生调用没有超时 —— BLE 掉线/眼镜崩时 SDK 回调永不来,
// JS promise 永不 resolve,UI 永久卡(检测中/启动中/停止中)。统一包一层超时,超时抛
// rokid_app_<op>_timeout,由调用方既有 try/catch 落到 unknown/failed,而非卡死(同 takePhoto 无超时挂死的修法)。
const ROKID_PUSHUP_OP_TIMEOUT_MS = 15000;
async function withRokidAppOpTimeout<T>(opName: string, op: () => Promise<T>): Promise<T> {
  const opPromise = op();
  opPromise.catch(() => undefined);
  let timer: ReturnType<typeof setTimeout> | null = null;
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(
      () => reject(new Error(`rokid_app_${opName}_timeout; timeoutMs=${ROKID_PUSHUP_OP_TIMEOUT_MS}`)),
      ROKID_PUSHUP_OP_TIMEOUT_MS,
    );
  });
  try {
    return await Promise.race([opPromise, timeoutPromise]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

function isRokidPushupNativeSetupFailure(reason?: string) {
  if (!reason) {
    return false;
  }
  const normalized = reason.toLowerCase();
  return normalized.includes('rokid_apk')
    || normalized.includes('rokid_cxrl_wrong_session_mode')
    || normalized.includes('rokid_app_install_rejected')
    || normalized.includes('rokid_app_install_rejected_without_reason')
    || normalized.includes('rokid_app_probe_failed')
    || normalized.includes('rokid_pushup_app_install')
    || normalized.includes('rokid_pushup_app_open_failed')
    || normalized.includes('rokid_pushup_session_open_url_missing');
}

function formatRealPushupSessionIssue(reason?: string) {
  const fallback = reason ?? 'rokid_pushup_real_session_failed';
  if (!isRokidPushupNativeSetupFailure(fallback)) {
    return fallback;
  }
  if (fallback.includes('rokid_apk_download_http_') || fallback.includes('rokid_apk_download_failed')) {
    return `眼镜端 App 下载失败: ${fallback}。已改为不自动弹文件选择器；可重试自动下载，或使用「手动选择 APK 安装」。本地计数仍可保存。`;
  }
  if (fallback.includes('rokid_app_install_rejected') || fallback.includes('rokid_pushup_app_install_not_confirmed')) {
    return `下载已完成，但安装到眼镜失败: ${fallback}。请保持手机 Wi‑Fi 开启、Rokid AI / Hi Rokid 前台、眼镜蓝牙在线后重试；也可以用「手动选择 APK 安装」。本地计数仍可保存。`;
  }
  if (fallback.includes('rokid_cxrl_wrong_session_mode')) {
    const mode = fallback.match(/currentMode=([^;]+)/)?.[1] ?? 'unknown';
    return `Rokid CXR-L 当前已在 ${mode} 会话，无法安装或启动眼镜端 App。请完全退出 Reva（从后台划掉）后，直接进入「Rokid 俯卧撑计数」再点安装/启动；不要先打开 Reva 眼镜视图。本地计数仍可保存。`;
  }
  return `眼镜识别暂不可用: ${fallback}。先用下方「+1 校准」本地计数，本组仍可保存。`;
}

export default function RokidPushupCoachScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [coach, setCoach] = useState<PushupCoachState>(() => createPushupCoachState({ targetReps: 20 }));
  const [sessionState, setSessionState] = useState<RokidSessionState>('idle');
  const [sessionMessage, setSessionMessage] = useState('');
  const [realSessionState, setRealSessionState] = useState<RealPoseSessionState>('idle');
  const [glassesAppInstalled, setGlassesAppInstalled] = useState<GlassesAppInstallStatus>('unknown');
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  const [realSession, setRealSession] = useState<RokidPushupSession | null>(null);
  const [realSessionMessage, setRealSessionMessage] = useState('');
  const [installDiagnostics, setInstallDiagnostics] = useState<string[]>([]);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [pushupReview, setPushupReview] = useState<RokidPushupSessionReview | null>(null);
  const [reviewState, setReviewState] = useState<'idle' | 'loading' | 'loaded' | 'failed'>('idle');
  const lastRokidEventIdRef = useRef(0);
  const pollInFlightRef = useRef(false);

  const applyInstallSnapshot = useCallback((snapshot: GlassesAppInstallSnapshot) => {
    setInstallDiagnostics(snapshot.diagnostics);
    if (snapshot.phase === 'idle') {
      return;
    }
    if (snapshot.phase === 'downloading' || snapshot.phase === 'downloaded' || snapshot.phase === 'installing' || snapshot.phase === 'confirming') {
      setRealSessionState('installing');
      setGlassesAppInstalled('checking');
      setRealSessionMessage(snapshot.message || '眼镜端应用正在后台安装...');
      return;
    }
    if (snapshot.phase === 'succeeded') {
      setRealSessionState('idle');
      setGlassesAppInstalled('installed');
      setRealSessionMessage(snapshot.message || '眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)');
      return;
    }
    setRealSessionState('failed');
    setGlassesAppInstalled('missing');
    setRealSessionMessage(formatRealPushupSessionIssue(snapshot.error ?? 'rokid_pushup_app_install_failed'));
  }, []);

  useEffect(() => subscribeGlassesAppInstallState((snapshot) => {
    if (!mountedRef.current) {
      return;
    }
    applyInstallSnapshot(snapshot);
  }), [applyInstallSnapshot]);

  const appendInstallDiagnostic = useCallback((message: string) => {
    const snapshot = appendGlassesAppInstallDiagnostic(message);
    if (mountedRef.current) {
      setInstallDiagnostics(snapshot.diagnostics);
    }
  }, []);

  const copyInstallDiagnostics = useCallback(async () => {
    await Clipboard.setStringAsync([
      'Rokid Pushup Install Diagnostics',
      `generated_at=${formatBeijingTimestamp()}`,
      `package=${ROKID_PUSHUP_APP_PACKAGE}`,
      `apk_url=${ROKID_PUSHUP_APK_DOWNLOAD_URL}`,
      `state=${realSessionState}`,
      `glassesAppInstalled=${glassesAppInstalled}`,
      `message=${realSessionMessage || 'n/a'}`,
      '',
      ...installDiagnostics,
    ].join('\n'));
    setRealSessionMessage('安装调试信息已复制');
  }, [glassesAppInstalled, installDiagnostics, realSessionMessage, realSessionState]);

  const pushViewToGlasses = useCallback(async (nextCoach: PushupCoachState, force = false) => {
    if (!force && sessionState !== 'opened') {
      return;
    }
    try {
      const result = force
        ? await openRokidCustomView(createRokidPushupCoachCustomViewLayout(nextCoach))
        : await updateRokidCustomView(createRokidPushupCoachCustomViewLayout(nextCoach));
      if (!readResultOk(result)) {
        throw new Error(typeof result.reason === 'string' ? result.reason : 'rokid_custom_view_failed');
      }
      if (force) {
        setSessionState('opened');
        setSessionMessage('眼镜计数视图已打开');
      }
    } catch (error) {
      setSessionState('failed');
      setSessionMessage(error instanceof Error ? error.message : 'rokid_custom_view_failed');
    }
  }, [sessionState]);

  const applyPoseSample = useCallback((sample: PushupPoseSample) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setCoach((prev) => {
      const next = updatePushupCoach(prev, sample);
      void pushViewToGlasses(next);
      return next;
    });
  }, [pushViewToGlasses]);

  const openCoachView = useCallback(async () => {
    setSessionState('opening');
    setSessionMessage('正在打开眼镜计数视图...');
    await pushViewToGlasses(coach, true);
  }, [coach, pushViewToGlasses]);

  const installDownloadedGlassesApp = useCallback(async () => {
    const downloadMessage = '眼镜端应用未内置, 正在从 health 下载 (约20MB, 可离开本页, 后台继续)...';
    setGlassesAppInstallSnapshot({ phase: 'downloading', message: downloadMessage, error: null });
    setRealSessionMessage(downloadMessage);
    appendInstallDiagnostic(`download_start url=${ROKID_PUSHUP_APK_DOWNLOAD_URL}`);
    let downloadedUri: string | null = null;
    const target = `${FileSystem.cacheDirectory ?? ''}${ROKID_PUSHUP_APK_CACHE_NAME}`;
    let lastErrorDetail = 'download_failed';
    for (let attempt = 1; attempt <= ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS; attempt += 1) {
      let lastProgressLogAt = 0;
      const startedAt = Date.now();
      if (attempt > 1) {
        appendInstallDiagnostic(`download_retry attempt=${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS}; previous=${lastErrorDetail}`);
        const retryMessage = `下载中断, 正在第 ${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS} 次重试...`;
        setGlassesAppInstallSnapshot({ phase: 'downloading', message: retryMessage });
        if (mountedRef.current) {
          setRealSessionMessage(retryMessage);
        }
      }
      appendInstallDiagnostic(`download_attempt_start attempt=${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS}; target=${target}`);
      try {
        const download = FileSystem.createDownloadResumable(
          ROKID_PUSHUP_APK_DOWNLOAD_URL,
          target,
          {},
          (progress) => {
            const written = progress.totalBytesWritten ?? 0;
            const expected = progress.totalBytesExpectedToWrite ?? 0;
            const now = Date.now();
            if (now - lastProgressLogAt < 2500 && written !== expected) {
              return;
            }
            lastProgressLogAt = now;
            appendInstallDiagnostic(`download_progress attempt=${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS}; written=${written}; expected=${expected}; human=${formatBytes(written)}/${formatBytes(expected)}`);
            if (expected > 0) {
              const progressMessage = `眼镜端应用下载中: ${formatBytes(written)} / ${formatBytes(expected)}...`;
              setGlassesAppInstallSnapshot({ phase: 'downloading', message: progressMessage });
              if (mountedRef.current) {
                setRealSessionMessage(progressMessage);
              }
            }
          },
        );
        const dl = await download.downloadAsync();
        if (!dl) {
          throw new Error('rokid_apk_download_empty_result');
        }
        if (dl.status !== 200) {
          throw new Error(`rokid_apk_download_http_${dl.status}; url=${ROKID_PUSHUP_APK_DOWNLOAD_URL}`);
        }
        downloadedUri = dl.uri;
        const info = await FileSystem.getInfoAsync(downloadedUri);
        const size = info.exists && typeof info.size === 'number' ? info.size : null;
        if (size !== null && size < ROKID_PUSHUP_APK_MIN_BYTES) {
          throw new Error(`rokid_apk_download_too_small; size=${size}; min=${ROKID_PUSHUP_APK_MIN_BYTES}; url=${ROKID_PUSHUP_APK_DOWNLOAD_URL}`);
        }
        appendInstallDiagnostic(`download_complete attempt=${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS}; status=${dl.status}; uri=${downloadedUri}; size=${size ?? 'unknown'}; human=${formatBytes(size)}; durationMs=${Date.now() - startedAt}`);
        setGlassesAppInstallSnapshot({
          phase: 'downloaded',
          message: 'APK 已下载完成, 准备传到眼镜安装...',
        });
        break;
      } catch (error) {
        const detail = errorMessage(error, 'download_failed');
        lastErrorDetail = detail;
        appendInstallDiagnostic(`download_attempt_failed attempt=${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS}; ${detail}`);
        const canRetry = attempt < ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS && isRetryableRokidApkDownloadFailure(detail);
        if (canRetry) {
          continue;
        }
        appendInstallDiagnostic(`download_failed attempts=${attempt}/${ROKID_PUSHUP_APK_DOWNLOAD_MAX_ATTEMPTS}; ${detail}`);
        if (detail.startsWith('rokid_apk_download_')) {
          throw new Error(detail);
        }
        throw new Error(`rokid_apk_download_failed; url=${ROKID_PUSHUP_APK_DOWNLOAD_URL}; error=${detail}`);
      }
    }
    if (!downloadedUri) {
      throw new Error('rokid_apk_download_empty_result');
    }
    const installMessage = '下载完成, 正在把眼镜端应用传到眼镜安装...';
    setGlassesAppInstallSnapshot({ phase: 'installing', message: installMessage });
    setRealSessionMessage(installMessage);
    appendInstallDiagnostic(`install_file_uri_start fileUri=${downloadedUri}; package=${ROKID_PUSHUP_APP_PACKAGE}`);
    const installStartedAt = Date.now();
    await captureRokidInstallStatusDiagnostic('before_file_install', appendInstallDiagnostic);
    const fileInstall = await waitForNativeInstallWithDiagnostics(
      'install_file_uri',
      () => installRokidAppFromFileUri({
        fileUri: downloadedUri,
        packageName: ROKID_PUSHUP_APP_PACKAGE,
      }),
      appendInstallDiagnostic,
    );
    appendInstallDiagnostic(`install_file_uri_result durationMs=${Date.now() - installStartedAt}; ${compactResult(fileInstall)}`);
    if (!readResultOk(fileInstall) || fileInstall.installed === false) {
      const status = await captureRokidInstallStatusDiagnostic('after_file_install_failure', appendInstallDiagnostic);
      throw new Error(resultInstallFailureDetail(fileInstall, 'rokid_pushup_app_install_failed', status));
    }
  }, [appendInstallDiagnostic]);

  const installBundledOrDownloadedGlassesApp = useCallback(async () => {
    appendInstallDiagnostic(`bundle_install_start resource=${ROKID_PUSHUP_APK_RESOURCE_NAME}.${ROKID_PUSHUP_APK_RESOURCE_EXTENSION}`);
    const installResult = await installBundledRokidApp({
      resourceName: ROKID_PUSHUP_APK_RESOURCE_NAME,
      resourceExtension: ROKID_PUSHUP_APK_RESOURCE_EXTENSION,
      packageName: ROKID_PUSHUP_APP_PACKAGE,
    });
    appendInstallDiagnostic(`bundle_install_result ${compactResult(installResult)}`);
    if (readResultOk(installResult) && installResult.installed !== false) {
      return;
    }
    const bundledReason = resultFailureDetail(installResult, 'rokid_pushup_app_install_failed');
    if (bundledReason !== 'rokid_apk_resource_missing') {
      throw new Error(bundledReason);
    }
    // IPA 没内置 APK 时,从 health 公开目录下载到本地缓存,再用 file uri 传到眼镜安装。
    await installDownloadedGlassesApp();
  }, [appendInstallDiagnostic, installDownloadedGlassesApp]);

  const confirmGlassesAppInstalled = useCallback(async () => {
    // 眼镜端确认:installed===true 才算装上;安装在眼镜上可能还在收尾,重试几次再判失败(council P2)。
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const probe = await withRokidAppOpTimeout('query', () => queryRokidApp(ROKID_PUSHUP_APP_PACKAGE));
      appendInstallDiagnostic(`query_app_attempt attempt=${attempt + 1}/3; ${compactResult(probe)}`);
      if (readResultOk(probe) && probe.installed === true) {
        return;
      }
      if (attempt < 2) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    }
    throw new Error('rokid_pushup_app_install_not_confirmed');
  }, [appendInstallDiagnostic]);

  // 安装核心: bundled → 从 health 下载; 装完在眼镜端 strict 验证(带重试)。
  const performGlassesAppInstall = useCallback(async () => {
    await installBundledOrDownloadedGlassesApp();
    setGlassesAppInstallSnapshot({
      phase: 'confirming',
      message: '安装命令已返回, 正在确认眼镜端包是否可见...',
    });
    await confirmGlassesAppInstalled();
  }, [confirmGlassesAppInstalled, installBundledOrDownloadedGlassesApp]);

  const performPickedGlassesAppInstall = useCallback(async () => {
    const picked = await DocumentPicker.getDocumentAsync({
      copyToCacheDirectory: true,
      multiple: false,
      type: [
        'application/vnd.android.package-archive',
        'application/octet-stream',
        'public.data',
      ],
    });
    if (picked.canceled) {
      throw new Error('rokid_apk_picker_cancelled');
    }
    const asset = picked.assets?.[0];
    if (!asset?.uri) {
      throw new Error('rokid_apk_file_missing');
    }
    if (asset.name && !asset.name.toLowerCase().endsWith('.apk')) {
      throw new Error('rokid_apk_file_required');
    }
    appendInstallDiagnostic(`manual_install_file_uri_start fileUri=${asset.uri}; package=${ROKID_PUSHUP_APP_PACKAGE}`);
    await captureRokidInstallStatusDiagnostic('before_manual_file_install', appendInstallDiagnostic);
    const installResult = await waitForNativeInstallWithDiagnostics(
      'manual_install_file_uri',
      () => installRokidAppFromFileUri({
        fileUri: asset.uri,
        packageName: ROKID_PUSHUP_APP_PACKAGE,
      }),
      appendInstallDiagnostic,
    );
    if (!readResultOk(installResult) || installResult.installed === false) {
      const status = await captureRokidInstallStatusDiagnostic('after_manual_file_install_failure', appendInstallDiagnostic);
      throw new Error(resultInstallFailureDetail(installResult, 'rokid_pushup_app_install_failed', status));
    }
    await confirmGlassesAppInstalled();
  }, [appendInstallDiagnostic, confirmGlassesAppInstalled]);

  // 单例 + 超时:后台安装 survive 导航;任何入口(安装按钮 / 启动识别)都复用同一进行中的安装,
  // 不重启 APK 下载(council P2:startReal 之前会重复下载)。必须有超时,否则永不 settle 会锁死流程。
  const acquireGlassesAppInstall = useCallback(() => {
    const now = Date.now();
    if (glassesAppInstallInFlight && now - glassesAppInstallStartedAt < GLASSES_APP_INSTALL_TIMEOUT_MS) {
      appendInstallDiagnostic(`install_reuse_in_flight ageMs=${now - glassesAppInstallStartedAt}`);
      return glassesAppInstallInFlight;
    }
    glassesAppInstallStartedAt = now;
    beginGlassesAppInstallTask('正在安装眼镜端应用(可离开本页, 后台继续下载并安装到眼镜)...');
    appendInstallDiagnostic(`install_singleton_start timeoutMs=${GLASSES_APP_INSTALL_TIMEOUT_MS}`);
    const timed = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => {
          appendInstallDiagnostic(`install_timeout timeoutMs=${GLASSES_APP_INSTALL_TIMEOUT_MS}`);
          // council R3:超时也要把快照置 failed,否则停在 installing/downloading 显示陈旧"安装中"
          setGlassesAppInstallSnapshot({
            phase: 'failed',
            message: '',
            error: 'rokid_apk_install_timeout',
          });
          reject(new Error('rokid_apk_install_timeout'));
        },
        GLASSES_APP_INSTALL_TIMEOUT_MS,
      );
      performGlassesAppInstall().then(
        () => {
          clearTimeout(timer);
          setGlassesAppInstallSnapshot({
            phase: 'succeeded',
            message: '眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)',
            error: null,
          });
          resolve();
        },
        (error) => {
          clearTimeout(timer);
          setGlassesAppInstallSnapshot({
            phase: 'failed',
            message: '',
            error: errorMessage(error, 'rokid_pushup_app_install_failed'),
          });
          reject(error);
        },
      );
    });
    const promise = timed.finally(() => {
      // 只清自己这次的单例(防超时后旧安装回来误清掉新单例)
      if (glassesAppInstallInFlight === promise) {
        glassesAppInstallInFlight = null;
      }
    });
    glassesAppInstallInFlight = promise;
    return promise;
  }, [appendInstallDiagnostic, performGlassesAppInstall]);

  const refreshGlassesAppInstalled = useCallback(async () => {
    const inFlight = glassesAppInstallInFlight;
    if (inFlight) {
      setGlassesAppInstalled('checking');
      // 返回早于安装完成:等它装完再查真实状态(council P2:否则一直卡"检测中")
      try {
        await inFlight;
      } catch {
        // 失败也继续查眼镜端真实状态
      }
    } else {
      setGlassesAppInstalled((prev) => (prev === 'installed' ? prev : 'checking'));
    }
    try {
      const probe = await withRokidAppOpTimeout('query', () => queryRokidApp(ROKID_PUSHUP_APP_PACKAGE));
      if (!mountedRef.current) {
        return;
      }
      setGlassesAppInstalled(readResultOk(probe) && probe.installed === true ? 'installed' : 'missing');
    } catch {
      if (mountedRef.current) {
        setGlassesAppInstalled('unknown');
      }
    }
  }, []);

  const ensureGlassesAppInstalled = useCallback(async (options?: { force?: boolean }) => {
    if (!options?.force) {
      const appProbe = await withRokidAppOpTimeout('query', () => queryRokidApp(ROKID_PUSHUP_APP_PACKAGE));
      if (!readResultOk(appProbe)) {
        throw new Error(resultFailureDetail(appProbe, 'rokid_app_probe_failed'));
      }
      if (appProbe.installed === true) {
        return;
      }
    }
    setRealSessionState('installing');
    setRealSessionMessage(options?.force ? '正在更新眼镜端应用...' : '正在安装眼镜端应用...');
    // 复用进行中的单例安装,不重起 APK 下载;含 strict 验证
    await acquireGlassesAppInstall();
  }, [acquireGlassesAppInstall]);

  const installGlassesApp = useCallback(async () => {
    setRealSessionState('installing');
    setRealSessionMessage(
      glassesAppInstallInFlight
        ? '眼镜端应用正在后台安装(可离开本页, 装好后回来自动检测)...'
        : '正在安装眼镜端应用(可离开本页, 后台继续下载并安装到眼镜)...',
    );
    try {
      await acquireGlassesAppInstall();
      if (!mountedRef.current) {
        return;
      }
      setGlassesAppInstalled('installed');
      setRealSessionState('idle');
      setRealSessionMessage('眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)');
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      setGlassesAppInstalled('missing');
      setRealSessionState('failed');
      setRealSessionMessage(formatRealPushupSessionIssue(
        error instanceof Error ? error.message : 'rokid_pushup_app_install_failed',
      ));
    }
  }, [acquireGlassesAppInstall]);

  const installPickedGlassesApp = useCallback(async () => {
    setRealSessionState('installing');
    setRealSessionMessage('请选择 Rokid 俯卧撑眼镜端 APK...');
    try {
      await performPickedGlassesAppInstall();
      if (!mountedRef.current) {
        return;
      }
      setGlassesAppInstalled('installed');
      setRealSessionState('idle');
      setRealSessionMessage('眼镜端应用已安装到眼镜 ✓(已在眼镜端验证)');
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      setGlassesAppInstalled('missing');
      setRealSessionState('failed');
      setRealSessionMessage(formatRealPushupSessionIssue(errorMessage(error, 'rokid_pushup_app_install_failed')));
    }
  }, [performPickedGlassesAppInstall]);

  // 进入本页 / 从别处返回本页时,都重新查一次眼镜端 App 是否已装好
  // (覆盖"离开页面后台安装,回来自动检测"的需求)
  useFocusEffect(
    useCallback(() => {
      void refreshGlassesAppInstalled();
    }, [refreshGlassesAppInstalled]),
  );

  const startRealGlassesCoach = useCallback(async () => {
    setRealSessionState('creating');
    setRealSessionMessage('正在启动眼镜端识别...');
    try {
      await ensureGlassesAppInstalled();
      const session = await createRokidPushupSession({
        targetReps: coach.targetReps,
        sourceDevice: 'rokid_glasses',
        meta: {
          packageName: ROKID_PUSHUP_APP_PACKAGE,
          activityName: ROKID_PUSHUP_APP_ACTIVITY,
          mode: 'pushup_pose',
        },
      });
      if (!session.open_url) {
        throw new Error('rokid_pushup_session_open_url_missing');
      }
      const openUrl = session.open_url; // 闭包内会丢失上面 guard 的窄化,先固化为 string
      const opened = await withRokidAppOpTimeout('open', () => openRokidApp({
        packageName: ROKID_PUSHUP_APP_PACKAGE,
        activityName: ROKID_PUSHUP_APP_ACTIVITY,
        url: openUrl,
      }));
      if (!readResultOk(opened) || opened.opened === false) {
        throw new Error(resultFailureDetail(opened, 'rokid_pushup_app_open_failed'));
      }
      lastRokidEventIdRef.current = 0;
      setRealSession(session);
      setRealSessionState('running');
      setRealSessionMessage('眼镜端识别已启动, 等待姿态数据...');
    } catch (error) {
      setRealSessionState('failed');
      setRealSessionMessage(formatRealPushupSessionIssue(
        error instanceof Error ? error.message : 'rokid_pushup_real_session_failed',
      ));
    }
  }, [coach.targetReps, ensureGlassesAppInstalled]);

  const stopRealGlassesCoach = useCallback(async () => {
    setRealSessionState('stopping');
    setRealSessionMessage('正在停止眼镜端识别...');
    try {
      if (realSession) {
        await finishRokidPushupSession(realSession.id);
      }
      // council R3 #1(不假装成功):stopRokidApp 被拒时是 resolve {ok:false}(不抛),旧代码不检查 ok
      // → 即使停止被拒也显"已停止"。现检查 ok + 包超时,被拒/超时落 failed 态而非假成功。
      const stopped = await withRokidAppOpTimeout('stop', () => stopRokidApp(ROKID_PUSHUP_APP_PACKAGE));
      if (!readResultOk(stopped)) {
        throw new Error(resultFailureDetail(stopped, 'rokid_pushup_app_stop_failed'));
      }
      setRealSessionState('idle');
      setRealSession(null);
      setRealSessionMessage('眼镜端识别已停止');
    } catch (error) {
      setRealSessionState('failed');
      setRealSessionMessage(error instanceof Error ? error.message : 'rokid_pushup_stop_failed');
    }
  }, [realSession]);

  useEffect(() => {
    if (realSessionState !== 'running' || !realSession) {
      return undefined;
    }
    let cancelled = false;

    const poll = async () => {
      if (pollInFlightRef.current) {
        return;
      }
      pollInFlightRef.current = true;
      try {
        const events = await listRokidPushupEvents(realSession.id, {
          afterId: lastRokidEventIdRef.current,
          limit: 80,
        });
        if (cancelled || events.length === 0) {
          return;
        }
        lastRokidEventIdRef.current = Math.max(
          lastRokidEventIdRef.current,
          ...events.map((event) => event.id),
        );
        setCoach((prev) => {
          let next = prev;
          for (const event of events) {
            next = applyRokidPushupEventToCoach(next, event);
          }
          if (next.reps > prev.reps) {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          }
          void pushViewToGlasses(next);
          return next;
        });
        setRealSessionMessage(`已接收 ${events.length} 条眼镜姿态事件`);
      } catch (error) {
        if (!cancelled) {
          setRealSessionMessage(error instanceof Error ? error.message : 'rokid_pushup_event_poll_failed');
        }
      } finally {
        pollInFlightRef.current = false;
      }
    };

    void poll();
    const timer = setInterval(() => {
      void poll();
    }, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pushViewToGlasses, realSession, realSessionState]);

  const closeCoachView = useCallback(async () => {
    try {
      await closeRokidCustomView(createRokidPushupCoachCustomViewLayout(coach));
    } catch {
      // Best effort close; the mobile session can still reset locally.
    }
    setSessionState('idle');
    setSessionMessage('眼镜计数视图已关闭');
  }, [coach]);

  const resetSession = useCallback(() => {
    const next = createPushupCoachState({ targetReps: coach.targetReps });
    setCoach(next);
    setSaveState('idle');
    void pushViewToGlasses(next);
  }, [coach.targetReps, pushViewToGlasses]);

  const addFullRep = useCallback(() => {
    const now = Date.now();
    setCoach((prev) => {
      const ready = updatePushupCoach(prev, {
        timestampMs: now,
        elbowAngleDeg: 170,
        shoulderHipAnkleAngleDeg: 176,
        visibility: 0.94,
      });
      const down = updatePushupCoach(ready, {
        timestampMs: now + 450,
        elbowAngleDeg: 84,
        shoulderHipAnkleAngleDeg: 174,
        visibility: 0.94,
      });
      const up = updatePushupCoach(down, {
        timestampMs: now + 1250,
        elbowAngleDeg: 166,
        shoulderHipAnkleAngleDeg: 175,
        visibility: 0.94,
      });
      void pushViewToGlasses(up);
      return up;
    });
  }, [pushViewToGlasses]);

  const saveExercise = useCallback(async () => {
    if (coach.reps <= 0) {
      Alert.alert('还没有计数', '完成至少 1 个俯卧撑后再保存本组。');
      return;
    }
    setSaveState('saving');
    try {
      const payload = buildPushupExercisePayload(coach);
      await api.post('/daily-health/exercise', {
        record_date: payload.record_date,
        exercise_type: payload.exercise_type,
        reps: payload.reps,
        sets: payload.sets,
        intensity: payload.intensity,
        notes: payload.notes,
      });
      await invalidateRecordMutation(qc);
      setSaveState('saved');
      const savedCoach: PushupCoachState = {
        ...coach,
        feedback: `已保存 ${coach.reps} 个俯卧撑。`,
        suggestion: '休息后再决定是否追加一组, 不需要硬撑。',
      };
      setCoach(savedCoach);
      void pushViewToGlasses(savedCoach);
      // 赛后复盘:仅眼镜会话有 session id 可复盘。复盘失败不影响已保存的记录(不假装成功)。
      if (realSession) {
        setReviewState('loading');
        getRokidPushupSessionReview(realSession.id)
          .then((review) => {
            setPushupReview(review);
            setReviewState('loaded');
          })
          .catch(() => {
            setReviewState('failed');
          });
      }
    } catch (error) {
      setSaveState('failed');
      Alert.alert('保存失败', error instanceof Error ? error.message : '俯卧撑记录保存失败。');
    }
  }, [coach, pushViewToGlasses, qc, realSession]);

  const progress = Math.min(coach.reps / coach.targetReps, 1);
  const sessionTone = sessionState === 'opened'
    ? s.success.solid
    : sessionState === 'failed'
      ? s.warning.solid
      : c.labelSecondary;
  const realSessionTone = realSessionState === 'running'
    ? s.success.solid
    : realSessionState === 'failed'
      ? s.warning.solid
      : c.labelSecondary;

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
        <Text style={txt.title}>Rokid 俯卧撑计数</Text>
        <Pressable
          onPress={resetSession}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="重置俯卧撑计数"
          hitSlop={10}
        >
          <Ionicons name="refresh" size={20} color={c.labelSecondary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.heroPanel}>
          <View style={styles.heroTop}>
            <View style={styles.heroIcon}>
              <Ionicons name="body-outline" size={24} color={c.orange} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={txt.heroKicker}>本组目标</Text>
              <Text style={txt.heroTitle}>{coach.targetReps} 个标准俯卧撑</Text>
            </View>
          </View>

          <View style={styles.countRow}>
            <Text style={txt.count}>{coach.reps}</Text>
            <Text style={txt.countTotal}>/ {coach.targetReps}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
          </View>
          <Text style={txt.feedback}>{coach.feedback}</Text>
          <Text style={txt.suggestion}>{coach.suggestion}</Text>
        </View>

        <View style={styles.panel}>
          <View style={styles.sectionHeader}>
            <Text style={txt.sectionTitle}>真实识别</Text>
            <Text style={[txt.sessionState, { color: realSessionTone }]}>
              {realSessionState === 'running'
                ? '运行中'
                : realSessionState === 'installing'
                  ? '安装中'
                : realSessionState === 'creating'
                  ? '启动中'
                  : realSessionState === 'stopping'
                    ? '停止中'
                    : '未启动'}
            </Text>
          </View>
          <Text style={txt.sessionMessage}>
            {glassesAppInstalled === 'installed'
              ? '眼镜端 App: 已安装到眼镜 ✓'
              : glassesAppInstalled === 'checking'
                ? '眼镜端 App: 检测中…'
                : glassesAppInstalled === 'missing'
                  ? '眼镜端 App: 未安装 — 点下方「安装/更新」会自动下载并装到眼镜(可离开本页, 后台继续)'
                  : '眼镜端 App: 状态未知,点「安装/更新」检测并安装'}
          </Text>
          <View style={styles.buttonRow}>
            <Pressable
              onPress={startRealGlassesCoach}
              disabled={realSessionState === 'creating' || realSessionState === 'installing' || realSessionState === 'running' || realSessionState === 'stopping'}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                (realSessionState === 'creating' || realSessionState === 'installing' || realSessionState === 'running' || realSessionState === 'stopping') && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="scan-outline" size={17} color="#fff" />
              <Text style={txt.primaryButton}>
                {realSessionState === 'creating' || realSessionState === 'installing' ? '启动中...' : '启动眼镜识别'}
              </Text>
            </Pressable>
            <Pressable
              onPress={stopRealGlassesCoach}
              disabled={realSessionState !== 'running'}
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed && styles.pressed,
                realSessionState !== 'running' && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="stop-circle-outline" size={16} color={c.brand} />
              <Text style={txt.secondaryButton}>停止</Text>
            </Pressable>
          </View>
          <Pressable
            onPress={installGlassesApp}
            disabled={realSessionState === 'installing' || realSessionState === 'creating' || realSessionState === 'running' || realSessionState === 'stopping'}
            style={({ pressed }) => [
              styles.fullWidthSecondaryButton,
              pressed && styles.pressed,
              (realSessionState === 'installing' || realSessionState === 'creating' || realSessionState === 'running' || realSessionState === 'stopping') && styles.disabledButton,
            ]}
            accessibilityRole="button"
            accessibilityLabel="安装或更新 Rokid 俯卧撑眼镜应用"
          >
            <Ionicons name="download-outline" size={16} color={c.brand} />
            <Text style={txt.secondaryButton}>
              {realSessionState === 'installing' ? '安装中...' : '安装/更新眼镜端 App'}
            </Text>
          </Pressable>
          <Pressable
            onPress={installPickedGlassesApp}
            disabled={realSessionState === 'installing' || realSessionState === 'creating' || realSessionState === 'running' || realSessionState === 'stopping'}
            style={({ pressed }) => [
              styles.fullWidthSecondaryButton,
              pressed && styles.pressed,
              (realSessionState === 'installing' || realSessionState === 'creating' || realSessionState === 'running' || realSessionState === 'stopping') && styles.disabledButton,
            ]}
            accessibilityRole="button"
            accessibilityLabel="手动选择 Rokid 俯卧撑眼镜应用 APK"
          >
            <Ionicons name="folder-open-outline" size={16} color={c.brand} />
            <Text style={txt.secondaryButton}>手动选择 APK 安装</Text>
          </Pressable>
          {realSessionMessage ? <Text style={txt.sessionMessage}>{realSessionMessage}</Text> : null}
          {installDiagnostics.length > 0 ? (
            <View style={styles.installDiagnosticsBox}>
              <View style={styles.sectionHeader}>
                <Text style={txt.installDiagnosticsTitle}>安装诊断</Text>
                <Pressable
                  onPress={copyInstallDiagnostics}
                  style={({ pressed }) => [styles.copyDiagnosticsButton, pressed && styles.pressed]}
                  accessibilityRole="button"
                  accessibilityLabel="复制 Rokid 俯卧撑安装日志"
                >
                  <Ionicons name="copy-outline" size={14} color={c.brand} />
                  <Text style={txt.copyDiagnosticsButton}>复制安装日志</Text>
                </Pressable>
              </View>
              {installDiagnostics.slice(-8).map((line) => (
                <Text key={line} style={txt.installDiagnosticsLine}>{line}</Text>
              ))}
            </View>
          ) : null}
        </View>

        <View style={styles.panel}>
          <View style={styles.sectionHeader}>
            <Text style={txt.sectionTitle}>CustomView 接力显示</Text>
            <Text style={[txt.sessionState, { color: sessionTone }]}>
              {sessionState === 'opened' ? '已打开' : sessionState === 'opening' ? '打开中' : '未打开'}
            </Text>
          </View>
          <View style={styles.buttonRow}>
            <Pressable
              onPress={openCoachView}
              disabled={sessionState === 'opening'}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                sessionState === 'opening' && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="browsers-outline" size={17} color="#fff" />
              <Text style={txt.primaryButton}>{sessionState === 'opening' ? '打开中...' : '打开眼镜视图'}</Text>
            </Pressable>
            <Pressable
              onPress={closeCoachView}
              disabled={sessionState !== 'opened'}
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed && styles.pressed,
                sessionState !== 'opened' && styles.disabledButton,
              ]}
              accessibilityRole="button"
            >
              <Ionicons name="close-circle-outline" size={16} color={c.brand} />
              <Text style={txt.secondaryButton}>关闭</Text>
            </Pressable>
          </View>
          {sessionMessage ? <Text style={txt.sessionMessage}>{sessionMessage}</Text> : null}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>本地计数 / 校准采样</Text>
          <Text style={txt.localModeHint}>
            眼镜识别不可用时，先用「+1 校准」本地计数，本组仍可保存。
          </Text>
          <View style={styles.sampleGrid}>
            <PoseButton
              label="下放"
              icon="arrow-down-outline"
              color={c.orange}
              onPress={() => applyPoseSample({
                timestampMs: Date.now(),
                elbowAngleDeg: 84,
                shoulderHipAnkleAngleDeg: 174,
                visibility: 0.94,
              })}
            />
            <PoseButton
              label="推起"
              icon="arrow-up-outline"
              color={c.green}
              onPress={() => applyPoseSample({
                timestampMs: Date.now(),
                elbowAngleDeg: 166,
                shoulderHipAnkleAngleDeg: 175,
                visibility: 0.94,
              })}
            />
            <PoseButton
              label="+1 校准"
              icon="add-circle-outline"
              color={c.blue}
              onPress={addFullRep}
            />
            <PoseButton
              label="身体松动"
              icon="alert-circle-outline"
              color={s.warning.solid}
              onPress={() => applyPoseSample({
                timestampMs: Date.now(),
                elbowAngleDeg: 96,
                shoulderHipAnkleAngleDeg: 142,
                visibility: 0.94,
              })}
            />
          </View>
        </View>

        {coach.formWarnings.length > 0 ? (
          <View style={styles.panel}>
            <Text style={txt.sectionTitle}>动作评价</Text>
            <View style={styles.scoreRow}>
              <Text style={txt.score}>{coach.qualityScore}</Text>
              <Text style={txt.scoreUnit}>分</Text>
            </View>
            {coach.formWarnings.map((warning) => (
              <View key={warning.code} style={styles.warningRow}>
                <Ionicons name="information-circle-outline" size={16} color={s.warning.solid} />
                <Text style={txt.warningText}>{warning.message}</Text>
              </View>
            ))}
          </View>
        ) : null}

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>保存</Text>
          <Text style={txt.saveHint}>保存后会进入今日力量训练记录, 参与日程和训练负荷判断。</Text>
          <Pressable
            onPress={saveExercise}
            disabled={saveState === 'saving' || coach.reps <= 0}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed,
              (saveState === 'saving' || coach.reps <= 0) && styles.disabledButton,
            ]}
            accessibilityRole="button"
          >
            <Ionicons name="save-outline" size={17} color="#fff" />
            <Text style={txt.primaryButton}>
              {saveState === 'saving' ? '保存中...' : saveState === 'saved' ? '已保存' : '保存本组'}
            </Text>
          </Pressable>
        </View>

        {reviewState !== 'idle' ? (
          <View style={styles.panel}>
            <Text style={txt.sectionTitle}>赛后复盘</Text>
            {reviewState === 'loading' ? (
              <Text style={txt.saveHint}>正在生成观察性复盘...</Text>
            ) : reviewState === 'failed' ? (
              <Text style={txt.saveHint}>复盘暂不可用(记录已保存)。</Text>
            ) : pushupReview ? (
              <>
                <Text style={txt.saveHint}>
                  本组 {pushupReview.session_quality.reps} 个
                  {pushupReview.session_quality.avg_quality_score != null
                    ? ` · 平均质量分 ${Math.round(pushupReview.session_quality.avg_quality_score)}`
                    : ''}
                </Text>
                {pushupReview.observations.map((obs, i) => (
                  <Text key={`obs-${i}`} style={txt.saveHint}>· {obs}</Text>
                ))}
                {pushupReview.teaching_links.map((link) => (
                  <Text key={link.key} style={txt.saveHint}>📖 {link.title}</Text>
                ))}
                {pushupReview.disclaimer ? (
                  <Text style={[txt.saveHint, { opacity: 0.6 }]}>{pushupReview.disclaimer}</Text>
                ) : null}
              </>
            ) : null}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );

  function PoseButton({
    label,
    icon,
    color,
    onPress,
  }: {
    label: string;
    icon: keyof typeof Ionicons.glyphMap;
    color: string;
    onPress: () => void;
  }) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [styles.poseButton, pressed && styles.pressed]}
        accessibilityRole="button"
      >
        <Ionicons name={icon} size={18} color={color} />
        <Text style={[txt.poseButtonText, { color }]}>{label}</Text>
      </Pressable>
    );
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
  heroPanel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  heroTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: spacing.md,
  },
  heroIcon: {
    width: 44,
    height: 44,
    borderRadius: radii.sm,
    backgroundColor: c.tintOrange,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginTop: spacing.sm,
  },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: c.fill,
    overflow: 'hidden',
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  progressFill: {
    height: 8,
    borderRadius: 4,
    backgroundColor: c.orange,
  },
  panel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  primaryButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: c.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: spacing.sm,
  },
  secondaryButton: {
    minHeight: 44,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: spacing.md,
  },
  fullWidthSecondaryButton: {
    minHeight: 44,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: spacing.md,
    marginTop: spacing.sm,
  },
  installDiagnosticsBox: {
    marginTop: spacing.md,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    padding: spacing.md,
    gap: 6,
  },
  copyDiagnosticsButton: {
    minHeight: 30,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.bgCard,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingHorizontal: spacing.sm,
  },
  sampleGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  poseButton: {
    width: '48%',
    minHeight: 42,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    paddingTop: spacing.sm,
  },
  pressed: { opacity: 0.82 },
  disabledButton: { opacity: 0.5 },
});

const createTxt = (c: ColorPalette) => ({
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  heroKicker: { fontSize: 12, fontWeight: '800', color: c.orange } as TextStyle,
  heroTitle: { fontSize: 18, fontWeight: '900', color: c.labelPrimary, marginTop: 2 } as TextStyle,
  count: { fontSize: 68, fontWeight: '900', color: c.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  countTotal: { fontSize: 24, fontWeight: '800', color: c.labelTertiary, marginBottom: 12 } as TextStyle,
  feedback: { fontSize: 16, fontWeight: '800', color: c.labelPrimary, lineHeight: 22 } as TextStyle,
  suggestion: { fontSize: 13, color: c.labelSecondary, lineHeight: 19, marginTop: 6 } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sessionState: { fontSize: 12, fontWeight: '800' } as TextStyle,
  sessionMessage: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: spacing.sm } as TextStyle,
  installDiagnosticsTitle: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  installDiagnosticsLine: { fontSize: 11, lineHeight: 15, color: c.labelSecondary, fontFamily: 'IBMPlexMono-Regular' } as TextStyle,
  localModeHint: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 4 } as TextStyle,
  primaryButton: { fontSize: 14, fontWeight: '800', color: '#fff' } as TextStyle,
  secondaryButton: { fontSize: 13, fontWeight: '800', color: c.brand } as TextStyle,
  copyDiagnosticsButton: { fontSize: 12, fontWeight: '800', color: c.brand } as TextStyle,
  poseButtonText: { fontSize: 13, fontWeight: '800' } as TextStyle,
  score: { fontSize: 42, fontWeight: '900', color: c.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  scoreUnit: { fontSize: 14, fontWeight: '800', color: c.labelSecondary, marginBottom: 8, marginLeft: 4 } as TextStyle,
  warningText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.labelSecondary } as TextStyle,
  saveHint: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 4, marginBottom: spacing.md } as TextStyle,
});
