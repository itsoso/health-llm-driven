import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Voice, {
  type SpeechErrorEvent,
  type SpeechResultsEvent,
} from '@react-native-voice/voice';
import * as Clipboard from 'expo-clipboard';
import * as ImagePicker from 'expo-image-picker';
import { setAudioModeAsync } from 'expo-audio';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  buildRokidCapabilityGateway,
  formatRokidLogTimestamp,
  addRokidTranscriptListener,
  createRokidRevaCustomViewLayout,
  getRokidDeviceValidationSteps,
  getRokidIntegrationStatus,
  openRokidRevaCustomView,
  requestRokidAuthorization,
  takeRokidPhotoBase64,
  updateRokidCustomView,
  type RokidCapabilityGateway,
  type RokidCapabilityState,
  type RokidDeviceValidationStep,
  type RokidEventSubscription,
  type RokidIntegrationStatus,
  type RokidRecommendedPath,
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
type RokidMealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

type CaptureState = {
  status: CaptureStatus;
  actionTitle?: string;
  message?: string;
};

type VoiceDebugState = {
  lastTranscript?: string;
  lastRawTranscript?: string;
  lastNormalizedTranscript?: string;
  lastTranscriptNormalizedBy?: string;
  lastTranscriptAt?: string;
  lastCommandAction?: string;
  lastCommandAt?: string;
  lastCommandReply?: string;
  lastCommandError?: string;
  fallbackMode?: 'phone_mic';
  fallbackReason?: string;
  fallbackStartedAt?: string;
  fallbackLastPartial?: string;
  fallbackLastSource?: string;
  fallbackLastEventAt?: string;
  fallbackError?: string;
};

type VoiceSelfCheckStatus = 'pass' | 'warn' | 'fail' | 'info';

type VoiceSelfCheckItem = {
  id: string;
  title: string;
  status: VoiceSelfCheckStatus;
  detail: string;
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

const PHONE_VOICE_FALLBACK_SILENCE_MS = 1800;
// council #3 去重窗口:过度捕获会让同一句话产生多个 final("记录"→"记录这一餐"→"记录这一餐明天天气"),
// 在该窗口内、与上次已路由转写相互包含的,视为同一句,跳过 → 防止一句话触发多次拍照/草稿。
const ROKID_VOICE_ROUTE_DEDUP_MS = 8000;
const ROKID_VOICE_NORMALIZER_VERSION = 'short-food-record-v2';

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

function guessMealType(now = new Date()): RokidMealType {
  const hour = now.getHours();
  if (hour < 10) {
    return 'breakfast';
  }
  if (hour < 14) {
    return 'lunch';
  }
  if (hour < 20) {
    return 'dinner';
  }
  return 'snack';
}

function formatFoodItemSummary(food: FoodRecognitionResponse['foods'][number]) {
  const name = food.name?.trim();
  if (!name) {
    return undefined;
  }
  const quantity = typeof food.quantity === 'string' && food.quantity.trim().length > 0
    ? ` ${food.quantity.trim()}`
    : '';
  return `${name}${quantity}`;
}

function roundNutrition(value: number) {
  return Math.round(value);
}

function foodRecognitionSummary(result?: FoodRecognitionResponse) {
  if (!result || result.success === false) {
    return undefined;
  }
  const parts: string[] = [];
  const description = result.meal_description?.trim()
    || result.foods
      .map(formatFoodItemSummary)
      .filter((value): value is string => Boolean(value))
      .join(', ');
  if (description) {
    parts.push(description);
  }
  if (typeof result.total_calories === 'number') {
    parts.push(`${roundNutrition(result.total_calories)}kcal`);
  }
  if (typeof result.total_protein === 'number') {
    parts.push(`蛋白${roundNutrition(result.total_protein)}g`);
  }
  if (typeof result.total_carbs === 'number') {
    parts.push(`碳水${roundNutrition(result.total_carbs)}g`);
  }
  if (typeof result.total_fat === 'number') {
    parts.push(`脂肪${roundNutrition(result.total_fat)}g`);
  }
  return parts.length > 0 ? parts.join(' · ') : undefined;
}

function isSavedDietRecordResponse(response: Awaited<ReturnType<typeof submitRokidVisualInput>>) {
  return response.event?.target_type === 'diet_record' && typeof response.event.target_id === 'number';
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
    || normalized.includes('rokid_audio_session_not_ready')
    || normalized.includes('open_callback_error_code')
    || normalized.includes('auto_retry_open_callback_error_code')
    || normalized.includes('rokid_glasses_ble_not_connected')
    || normalized.includes('rokid_capture_failed')
    || normalized.includes('rokid_photo_timeout')
    || normalized.includes('rokid_record_failed');
}

// 眼镜拍照经 BLE 回传(~100-300KB)较慢, 且 native takePhotoWithData 的完成闭包无超时——
// 数据卡住时 promise 永不 resolve, JS 会永久挂在"提交中"(用户实测:眼镜拍了照但照片没回传)。
// 给一个宽裕的超时(覆盖慢速 BLE), 超时则返回 ok:false 让上层降级到手机相机, 而不是永久挂起。
const ROKID_PHOTO_CAPTURE_TIMEOUT_MS = 25000;

async function takeRokidPhotoBase64WithTimeout(options: {
  width: number;
  height: number;
  quality: number;
}): Promise<Record<string, unknown>> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<Record<string, unknown>>((resolve) => {
    timer = setTimeout(
      () => resolve({ ok: false, reason: 'rokid_photo_timeout' }),
      ROKID_PHOTO_CAPTURE_TIMEOUT_MS,
    );
  });
  try {
    return await Promise.race([takeRokidPhotoBase64(options), timeout]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

function hasRokidAudioSession(result?: Partial<RokidIntegrationStatus> | Record<string, unknown> | null) {
  return result?.customViewRunning === true || result?.capabilitiesReady === true;
}

function hasRokidCustomViewSessionEvidence(result?: Partial<RokidIntegrationStatus> | Record<string, unknown> | null) {
  if (!result) {
    return false;
  }
  const rawNotify = typeof result.lastCustomViewRawNotify === 'string'
    ? result.lastCustomViewRawNotify.trim().toLowerCase()
    : '';
  const hasNotifyEvidence = rawNotify.length > 0
    && rawNotify !== 'none'
    && !rawNotify.includes('nonetwork')
    && !rawNotify.includes('open_failed');
  return result.customViewRunning === true
    || result.capabilitiesReady === true
    || result.customViewSessionEvidence === true
    || result.customViewDisplayInferred === true
    || result.lastCustomViewOpenCommandAccepted === true
    || hasNotifyEvidence;
}

function transcriptText(event: RokidTranscriptEvent) {
  const value = event.transcript ?? event.text;
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;
}

function normalizeRokidHealthTranscript(rawTranscript: string) {
  const compact = rawTranscript.replace(/[，。！？!?.,\s]/g, '');
  const normalizedBy = 'rokid_health_short_food_record';
  const shortFoodRecordPhrases = new Set([
    '记',
    '记录',
    '记一下',
    '记录一下',
    '帮我记',
    '帮我记录',
    '拍',
    '拍照',
    '拍一下',
    '这餐',
    '这顿',
    '这顿饭',
    '这一餐',
  ]);
  if (shortFoodRecordPhrases.has(compact)) {
    return {
      transcript: '记录这餐',
      normalizedBy,
      meta: {
        raw_transcript: rawTranscript,
        transcript_normalized_by: normalizedBy,
      },
    };
  }
  return {
    transcript: rawTranscript,
    normalizedBy: undefined,
    meta: {},
  };
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
  if (normalized.includes('rokid_glasses_no_network') || normalized.includes('subcmd=nonetwork')) {
    return '眼镜网络未就绪: 请在 Rokid AI / Hi Rokid 中确认眼镜已连 WiFi，并让手机与眼镜处在同一可互通网络，再回 Reva 刷新。';
  }
  if (normalized.includes('rokid_glasses_ble_not_connected')) {
    return '眼镜蓝牙链路未连接: 授权完成后请「完全退出」Rokid AI / Hi Rokid(它会独占眼镜蓝牙, 一次只能一个 App 连眼镜), 再回 Reva 刷新。';
  }
  if (normalized.includes('rokid_custom_view_not_running_after_open')) {
    return 'SDK 已接受打开命令，但眼镜端没有回报 CustomView 运行。请确认眼镜端是否显示 Reva；若未显示，请重新打开眼镜视图。';
  }
  if (normalized.includes('rokid_custom_view_open_callback_missing')) {
    return 'SDK 没有返回 CustomView 打开回调，眼镜端也没有回报运行。请确认 Rokid AI 已退出后台占用后重新打开眼镜视图。';
  }
  if (normalized.includes('open_callback_error_code') || normalized.includes('auto_retry_open_callback_error_code')) {
    return 'SDK 回调拒绝 CustomView 打开，但未给出明确错误码。眼镜蓝牙可能已连接，仍需要眼镜端回报 CustomView 运行后才能使用原生语音/拍照。';
  }
  return reason;
}

function formatQueuedCustomViewMessage(status?: RokidIntegrationStatus) {
  if (status?.iosBleConnected === true) {
    return 'Reva 眼镜视图已排队, 但 SDK 尚未回报 CustomView 运行。眼镜蓝牙当前已连接; 若长时间不变, 请完全退出 Rokid AI / Hi Rokid 后重新打开眼镜视图。';
  }
  return '眼镜蓝牙未连接,已排队: 完全退出 Rokid AI / Hi Rokid 释放眼镜蓝牙后,Reva 会在连上时自动打开眼镜视图。';
}

function isCustomViewCallbackMissing(status?: RokidIntegrationStatus) {
  return status?.lastCustomViewOpenError?.toLowerCase().includes('rokid_custom_view_open_callback_missing') === true;
}

function voiceSelfCheckTone(status: VoiceSelfCheckStatus, s: ReturnType<typeof useTheme>['s'], c: ColorPalette) {
  switch (status) {
    case 'pass':
      return { fg: s.success.solid, bg: s.success.bg, icon: 'checkmark-circle' as keyof typeof Ionicons.glyphMap };
    case 'fail':
      return { fg: s.warning.solid, bg: s.warning.bg, icon: 'alert-circle' as keyof typeof Ionicons.glyphMap };
    case 'warn':
      return { fg: c.orange, bg: c.tintOrange, icon: 'alert-circle' as keyof typeof Ionicons.glyphMap };
    default:
      return { fg: c.labelTertiary, bg: c.fill, icon: 'information-circle' as keyof typeof Ionicons.glyphMap };
  }
}

function buildVoiceSelfCheck(
  status: RokidIntegrationStatus | undefined,
  voiceState: { status: VoiceControlStatus; message?: string },
  voiceDebug: VoiceDebugState,
) {
  const chunks = status?.audioStreamChunkCount ?? 0;
  const bytes = status?.audioStreamByteCount ?? 0;
  const recordingRequested = voiceState.status === 'listening'
    || status?.activeRecordType === 'reva_voice_command'
    || status?.lastAudioRecordType === 'reva_voice_command'
    || status?.lastAudioEventType === 'record_start_requested'
    || status?.lastAudioEventType === 'started'
    || status?.lastAudioEventType === 'stream';
  const customViewEvidence = status?.customViewRunning === true
    || status?.customViewSessionEvidence === true
    || status?.customViewDisplayInferred === true
    || status?.lastCustomViewOpenCommandAccepted === true;
  const transcript = status?.lastSpeechTranscript || voiceDebug.lastTranscript;
  const commandAction = voiceDebug.lastCommandAction;
  const speechDenied = status?.speechAuthorizationStatus === 'denied'
    || status?.speechAuthorizationStatus === 'restricted';
  const phoneFallbackActive = voiceState.status === 'listening' && voiceDebug.fallbackMode === 'phone_mic';

  let summary = '等待启动 Rokid 语音控制';
  if (voiceState.status === 'failed') {
    summary = 'Rokid 语音控制失败，查看下方自检项';
  } else if (commandAction) {
    summary = `语音指令已路由: ${commandAction}`;
  } else if (transcript) {
    summary = `已识别: ${transcript}`;
  } else if (phoneFallbackActive) {
    summary = 'Rokid 音频未到，手机麦克风兜底已开启';
  } else if (recordingRequested && chunks === 0 && bytes === 0) {
    summary = '录音已请求，但 Rokid 尚未返回音频流';
  } else if (chunks > 0 && bytes > 0 && !transcript) {
    summary = speechDenied ? '音频已到达，但 iOS Speech 未授权' : '音频已到达，等待 iOS Speech 转写';
  } else if (voiceState.status === 'listening') {
    summary = voiceState.message ?? 'Rokid 语音控制已开启';
  }

  const items: VoiceSelfCheckItem[] = [
    {
      id: 'display',
      title: '眼镜视图',
      status: status?.customViewRunning
        ? 'pass'
        : customViewEvidence
          ? 'warn'
          : isCustomViewCallbackMissing(status)
            ? 'warn'
            : 'info',
      detail: status?.customViewRunning
        ? 'CustomView 已运行'
        : customViewEvidence
          ? '眼镜显示有证据，但 SDK 未回报 running'
          : isCustomViewCallbackMissing(status)
            ? 'CustomView 回调缺失，眼镜显示可能已出现但 SDK 未确认'
            : '等待打开 Reva 眼镜视图',
    },
    {
      id: 'record',
      title: '录音请求',
      status: recordingRequested ? 'pass' : 'info',
      detail: recordingRequested
        ? `event=${status?.lastAudioEventType ?? 'unknown'} · active=${status?.activeRecordType ?? 'none'}`
        : '尚未请求 Rokid startRecord',
    },
    {
      id: 'audio',
      title: '音频流',
      status: chunks > 0 && bytes > 0 ? 'pass' : recordingRequested ? 'fail' : 'info',
      detail: `${chunks} chunks · ${bytes} bytes`,
    },
    {
      id: 'speech',
      title: 'iOS Speech',
      status: transcript
        ? 'pass'
        : speechDenied
          ? 'fail'
          : chunks > 0 && bytes > 0
            ? 'warn'
            : 'info',
      detail: transcript
        ? `转写: ${transcript}`
        : speechDenied
          ? `Speech 权限不可用: ${status?.speechAuthorizationStatus}`
          : status?.lastSpeechError
            ? `Speech 错误: ${status.lastSpeechError}`
          : `state=${status?.speechRecognitionState ?? 'idle'} · auth=${status?.speechAuthorizationStatus ?? 'unknown'}`,
    },
    ...(voiceDebug.fallbackMode === 'phone_mic' ? [{
      id: 'phone_mic_fallback',
      title: '手机麦克风兜底',
      status: voiceDebug.fallbackError ? 'fail' as const : 'pass' as const,
      detail: voiceDebug.fallbackError
        ? voiceDebug.fallbackError
        : `reason=${voiceDebug.fallbackReason ?? 'rokid_audio_session_not_ready'} · ${voiceDebug.fallbackLastPartial ?? '等待语音'}`,
    }] : []),
    ...(voiceDebug.lastRawTranscript ? [{
      id: 'normalizer',
      title: '语音归一化',
      status: voiceDebug.lastTranscriptNormalizedBy ? 'pass' as const : 'info' as const,
      detail: voiceDebug.lastTranscriptNormalizedBy
        ? `${voiceDebug.lastRawTranscript} -> ${voiceDebug.lastNormalizedTranscript ?? voiceDebug.lastTranscript ?? 'n/a'} · ${voiceDebug.lastTranscriptNormalizedBy}`
        : `未改写: ${voiceDebug.lastRawTranscript}`,
    }] : []),
    {
      id: 'route',
      title: '命令路由',
      status: commandAction ? 'pass' : transcript ? 'warn' : 'info',
      detail: commandAction
        ? `${commandAction}${voiceDebug.lastCommandReply ? ` · ${voiceDebug.lastCommandReply}` : ''}`
        : transcript
          ? '已有转写，等待命令服务返回'
          : '等待明确语音指令，例如“记录这顿饭”',
    },
  ];

  return { summary, items };
}

function debugValue(value: unknown) {
  if (value === undefined || value === null || value === '') {
    return 'n/a';
  }
  return String(value);
}

function buildRokidVoiceDebugText(
  status: RokidIntegrationStatus | undefined,
  voiceState: { status: VoiceControlStatus; message?: string },
  voiceDebug: VoiceDebugState,
  selfCheck: ReturnType<typeof buildVoiceSelfCheck>,
  authDiagnosticLines: string[],
) {
  const lines = [
    'Rokid Voice Self Check',
    `generated_at=${formatRokidLogTimestamp(new Date().toISOString())}`,
    `voice.state=${voiceState.status}`,
    `voice.message=${debugValue(voiceState.message)}`,
    `voice.normalizer=${ROKID_VOICE_NORMALIZER_VERSION}`,
    `summary=${selfCheck.summary}`,
    `build=${debugValue(status?.nativeBuildNumber)}`,
    `version=${debugValue(status?.nativeAppVersion)}`,
    `bundle=${debugValue(status?.bundleIdentifier)}`,
    `companion=${debugValue(status?.companionServerScheme)}://${debugValue(status?.companionServerHost)}`,
    `device=${debugValue(status?.iosBleDeviceName ?? status?.currentDeviceName)}`,
    `auth=${debugValue(status?.authorizationState)}`,
    `ble.connected=${debugValue(status?.iosBleConnected)}`,
    `customView.running=${debugValue(status?.customViewRunning)}`,
    `customView.evidence=${debugValue(status?.customViewSessionEvidence)}`,
    `customView.displayInferred=${debugValue(status?.customViewDisplayInferred)}`,
    `customView.error=${debugValue(status?.lastCustomViewOpenError)}`,
    `audio.event=${debugValue(status?.lastAudioEventType)}`,
    `audio.active=${debugValue(status?.activeRecordType)}`,
    `audio.type=${debugValue(status?.lastAudioRecordType)}`,
    `audio.chunks=${debugValue(status?.audioStreamChunkCount)}`,
    `audio.bytes=${debugValue(status?.audioStreamByteCount)}`,
    `audio.lastChunk=${debugValue(status?.lastAudioChunkBytes)}`,
    `audio.codec=${debugValue(status?.lastAudioCodec)}`,
    `audio.channels=${debugValue(status?.lastAudioChannels)}`,
    `audio.at=${debugValue(status?.lastAudioEventAt ? formatRokidLogTimestamp(status.lastAudioEventAt) : undefined)}`,
    `speech.state=${debugValue(status?.speechRecognitionState)}`,
    `speech.auth=${debugValue(status?.speechAuthorizationStatus)}`,
    `speech.available=${debugValue(status?.speechRecognizerAvailable)}`,
    `speech.locale=${debugValue(status?.speechRecognitionLocale)}`,
    `speech.sampleRate=${debugValue(status?.speechAudioSampleRate)}`,
    `speech.channels=${debugValue(status?.speechAudioChannels)}`,
    `speech.appends=${debugValue(status?.speechAudioAppendCount)}`,
    `speech.frames=${debugValue(status?.speechAudioFrameCount)}`,
    `speech.lastTranscript=${debugValue(status?.lastSpeechTranscript ?? voiceDebug.lastTranscript)}`,
    `speech.lastTranscriptAt=${debugValue(status?.lastSpeechTranscriptAt ?? voiceDebug.lastTranscriptAt)}`,
    `speech.lastEventSource=${debugValue(status?.lastSpeechEventSource)}`,
    `speech.lastError=${debugValue(status?.lastSpeechError)}`,
    `fallback.mode=${debugValue(voiceDebug.fallbackMode)}`,
    `fallback.reason=${debugValue(voiceDebug.fallbackReason)}`,
    `fallback.startedAt=${debugValue(voiceDebug.fallbackStartedAt)}`,
    `fallback.lastPartial=${debugValue(voiceDebug.fallbackLastPartial)}`,
    `fallback.lastSource=${debugValue(voiceDebug.fallbackLastSource)}`,
    `fallback.lastEventAt=${debugValue(voiceDebug.fallbackLastEventAt)}`,
    `fallback.error=${debugValue(voiceDebug.fallbackError)}`,
    `route.rawTranscript=${debugValue(voiceDebug.lastRawTranscript)}`,
    `route.normalizedTranscript=${debugValue(voiceDebug.lastNormalizedTranscript)}`,
    `route.normalizedBy=${debugValue(voiceDebug.lastTranscriptNormalizedBy)}`,
    `route.lastAction=${debugValue(voiceDebug.lastCommandAction)}`,
    `route.lastAt=${debugValue(voiceDebug.lastCommandAt)}`,
    `route.lastReply=${debugValue(voiceDebug.lastCommandReply)}`,
    `route.lastError=${debugValue(voiceDebug.lastCommandError)}`,
    '',
    '[self_check]',
    ...selfCheck.items.map((item) => `${item.status} ${item.title}: ${item.detail}`),
    '',
    '[native_diagnostics]',
    ...authDiagnosticLines,
  ];
  return lines.join('\n');
}

function capabilityRouteTitle(path: RokidRecommendedPath) {
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

function displayRouteLabel(state: RokidCapabilityState) {
  switch (state) {
    case 'ready':
      return 'CXR-L 可用';
    case 'blocked':
      return 'CXR-L 阻塞';
    case 'degraded':
      return 'CXR-L 待确认';
    default:
      return '等待检测';
  }
}

function captureRouteLabel(gateway: RokidCapabilityGateway) {
  return gateway.summary.capture === 'ready' ? '眼镜拍照' : '手机拍照兜底';
}

function movementRouteLabel(gateway: RokidCapabilityGateway) {
  return gateway.summary.movement === 'ready' ? '眼镜端 App 优先' : '本地计数兜底';
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
  if (
    typeof status.audioStreamChunkCount === 'number'
    || typeof status.audioStreamByteCount === 'number'
    || status.lastAudioEventType
    || status.activeRecordType
  ) {
    const parts: string[] = [];
    if (status.lastAudioEventType) {
      parts.push(`event=${status.lastAudioEventType}`);
    }
    if (status.activeRecordType) {
      parts.push(`active=${status.activeRecordType}`);
    }
    if (status.lastAudioRecordType) {
      parts.push(`type=${status.lastAudioRecordType}`);
    }
    if (typeof status.audioStreamChunkCount === 'number') {
      parts.push(`chunks=${status.audioStreamChunkCount}`);
    }
    if (typeof status.audioStreamByteCount === 'number') {
      parts.push(`bytes=${status.audioStreamByteCount}`);
    }
    if (typeof status.lastAudioChunkBytes === 'number') {
      parts.push(`lastChunk=${status.lastAudioChunkBytes}`);
    }
    if (typeof status.lastAudioCodec === 'number') {
      parts.push(`codec=${status.lastAudioCodec}`);
    }
    if (typeof status.lastAudioChannels === 'number') {
      parts.push(`channels=${status.lastAudioChannels}`);
    }
    if (status.lastAudioTimestamp) {
      parts.push(`ts=${status.lastAudioTimestamp}`);
    }
    if (status.lastAudioEventAt) {
      parts.push(formatRokidLogTimestamp(status.lastAudioEventAt));
    }
    lines.push(`Rokid audio: ${parts.join(' · ')}`);
  }
  if (
    status.speechRecognitionState
    || status.speechAuthorizationStatus
    || typeof status.speechAudioAppendCount === 'number'
    || status.lastSpeechTranscript
    || status.lastSpeechError
  ) {
    const parts: string[] = [];
    if (status.speechRecognitionState) {
      parts.push(`state=${status.speechRecognitionState}`);
    }
    if (status.speechAuthorizationStatus) {
      parts.push(`auth=${status.speechAuthorizationStatus}`);
    }
    if (typeof status.speechRecognizerAvailable === 'boolean') {
      parts.push(`available=${status.speechRecognizerAvailable}`);
    }
    if (status.speechRecognitionLocale) {
      parts.push(`locale=${status.speechRecognitionLocale}`);
    }
    if (typeof status.speechAudioAppendCount === 'number') {
      parts.push(`appends=${status.speechAudioAppendCount}`);
    }
    if (typeof status.speechAudioFrameCount === 'number') {
      parts.push(`frames=${status.speechAudioFrameCount}`);
    }
    if (status.lastSpeechTranscript) {
      parts.push(`transcript=${status.lastSpeechTranscript}`);
    }
    if (status.lastSpeechError) {
      parts.push(`error=${status.lastSpeechError}`);
    }
    if (status.lastSpeechEventAt) {
      parts.push(formatRokidLogTimestamp(status.lastSpeechEventAt));
    }
    lines.push(`iOS Speech: ${parts.join(' · ')}`);
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
  if (status.customViewSessionEvidence === true || status.customViewDisplayInferred === true || status.lastCustomViewSessionEvidenceReason) {
    const parts: string[] = [];
    if (typeof status.customViewSessionEvidence === 'boolean') {
      parts.push(`sessionEvidence=${status.customViewSessionEvidence}`);
    }
    if (typeof status.customViewDisplayInferred === 'boolean') {
      parts.push(`displayInferred=${status.customViewDisplayInferred}`);
    }
    if (status.lastCustomViewSessionEvidenceReason) {
      parts.push(`reason=${status.lastCustomViewSessionEvidenceReason}`);
    }
    if (status.lastCustomViewSessionEvidenceAt) {
      parts.push(formatRokidLogTimestamp(status.lastCustomViewSessionEvidenceAt));
    }
    lines.push(`CustomView evidence: ${parts.join(' · ')}`);
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
  const queryClient = useQueryClient();
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
  const [voiceDebug, setVoiceDebug] = useState<VoiceDebugState>({});
  const voiceTranscriptSubscriptionRef = useRef<RokidEventSubscription | null>(null);
  const voiceListeningRef = useRef(false);
  const phoneVoiceFallbackActiveRef = useRef(false);
  const phoneVoiceFallbackSilenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const phoneVoiceFallbackLatestTextRef = useRef('');
  const phoneVoiceFallbackLastSubmittedRef = useRef('');
  // council #3:命令处理中(拍照/路由)期间忽略新转写;并记录上次已路由转写做包含去重。
  const voiceCommandInFlightRef = useRef(false);
  const lastRoutedTranscriptRef = useRef<{ text: string; at: number } | null>(null);

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
  const capabilityGateway = useMemo(() => buildRokidCapabilityGateway(status), [status]);
  const authDiagnosticLines = useMemo(() => buildAuthDiagnosticLines(status), [status]);
  const voiceSelfCheck = useMemo(
    () => buildVoiceSelfCheck(status, voiceState, voiceDebug),
    [status, voiceState, voiceDebug],
  );
  const voiceDebugText = useMemo(
    () => buildRokidVoiceDebugText(status, voiceState, voiceDebug, voiceSelfCheck, authDiagnosticLines),
    [status, voiceState, voiceDebug, voiceSelfCheck, authDiagnosticLines],
  );
  const isRefreshing = statusQuery.isRefetching || glanceQuery.isRefetching;

  const removeVoiceTranscriptListener = () => {
    voiceTranscriptSubscriptionRef.current?.remove();
    voiceTranscriptSubscriptionRef.current = null;
  };

  const clearPhoneVoiceFallbackTimer = () => {
    if (phoneVoiceFallbackSilenceTimerRef.current) {
      clearTimeout(phoneVoiceFallbackSilenceTimerRef.current);
      phoneVoiceFallbackSilenceTimerRef.current = null;
    }
  };

  const setPhoneVoiceFallbackPlaybackMode = async (allowsRecording: boolean) => {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'duckOthers',
        allowsRecording,
      });
    } catch {
      // Audio session mode is best-effort; Voice.start/stop will surface actionable failures.
    }
  };

  const routePhoneVoiceFallbackText = (rawText: string | undefined, source: string) => {
    const transcript = rawText?.trim();
    if (!transcript || !phoneVoiceFallbackActiveRef.current || !voiceListeningRef.current) {
      return;
    }
    if (phoneVoiceFallbackLastSubmittedRef.current === transcript) {
      return;
    }
    phoneVoiceFallbackLastSubmittedRef.current = transcript;
    clearPhoneVoiceFallbackTimer();
    const capturedAt = new Date().toISOString();
    setVoiceDebug((prev) => ({
      ...prev,
      fallbackLastPartial: transcript,
      fallbackLastSource: source,
      fallbackLastEventAt: capturedAt,
      fallbackError: undefined,
    }));
    void Voice.stop().catch(() => undefined);
    void setPhoneVoiceFallbackPlaybackMode(false);
    void handleVoiceTranscript({
      transcript,
      capturedAt,
      final: true,
      meta: {
        source_event: 'phone_mic_fallback',
        fallback_reason: voiceDebug.fallbackReason ?? 'rokid_audio_session_not_ready',
      },
    });
  };

  const armPhoneVoiceFallbackSilenceTimer = () => {
    clearPhoneVoiceFallbackTimer();
    phoneVoiceFallbackSilenceTimerRef.current = setTimeout(() => {
      routePhoneVoiceFallbackText(phoneVoiceFallbackLatestTextRef.current, 'phone_mic_silence');
    }, PHONE_VOICE_FALLBACK_SILENCE_MS);
  };

  const stopPhoneVoiceFallback = async () => {
    const wasActive = phoneVoiceFallbackActiveRef.current;
    phoneVoiceFallbackActiveRef.current = false;
    phoneVoiceFallbackLatestTextRef.current = '';
    phoneVoiceFallbackLastSubmittedRef.current = '';
    clearPhoneVoiceFallbackTimer();
    try {
      await Voice.stop();
    } catch {
      // The fallback may not have been active; stop is best-effort.
    }
    try {
      await Voice.destroy();
    } catch {
      // Keep cleanup best-effort to avoid masking the original UI action.
    }
    try {
      Voice.removeAllListeners();
    } catch {
      // Some test/native shims expose removeAllListeners as optional.
    }
    await setPhoneVoiceFallbackPlaybackMode(false);
    if (wasActive) {
      setVoiceDebug((prev) => ({
        ...prev,
        fallbackLastEventAt: new Date().toISOString(),
      }));
    }
  };

  const startPhoneVoiceFallback = async (reason: string) => {
    removeVoiceTranscriptListener();
    await stopPhoneVoiceFallback();
    const startedAt = new Date().toISOString();
    phoneVoiceFallbackActiveRef.current = true;
    phoneVoiceFallbackLatestTextRef.current = '';
    phoneVoiceFallbackLastSubmittedRef.current = '';
    voiceListeningRef.current = true;
    lastRoutedTranscriptRef.current = null;
    voiceCommandInFlightRef.current = false;
    setVoiceDebug((prev) => ({
      ...prev,
      fallbackMode: 'phone_mic',
      fallbackReason: reason,
      fallbackStartedAt: startedAt,
      fallbackLastPartial: undefined,
      fallbackLastSource: undefined,
      fallbackLastEventAt: startedAt,
      fallbackError: undefined,
      lastCommandError: undefined,
    }));

    Voice.onSpeechPartialResults = (event: SpeechResultsEvent) => {
      const text = event.value?.[0]?.trim();
      if (!text || !phoneVoiceFallbackActiveRef.current) {
        return;
      }
      phoneVoiceFallbackLatestTextRef.current = text;
      const at = new Date().toISOString();
      setVoiceDebug((prev) => ({
        ...prev,
        fallbackLastPartial: text,
        fallbackLastEventAt: at,
      }));
      setVoiceState({ status: 'listening', message: `手机麦克风识别中: ${text}` });
      armPhoneVoiceFallbackSilenceTimer();
    };
    Voice.onSpeechResults = (event: SpeechResultsEvent) => {
      const text = event.value?.[0]?.trim();
      if (!text || !phoneVoiceFallbackActiveRef.current) {
        return;
      }
      // 根因(诊断 3/3 一致):iOS zh-CN SFSpeech 在停顿处把 "记录" 当 intermediate final 抛出。
      // 立即路由 + Voice.stop() 会截断后续 "这顿饭"。把 final 当高置信 partial:取最长转写、重置静音
      // 计时器,只在真静音(1.8s 无新结果)或 onSpeechEnd 后才路由完整句。
      const longest =
        text.length >= (phoneVoiceFallbackLatestTextRef.current?.length ?? 0)
          ? text
          : phoneVoiceFallbackLatestTextRef.current;
      phoneVoiceFallbackLatestTextRef.current = longest;
      const at = new Date().toISOString();
      setVoiceDebug((prev) => ({
        ...prev,
        fallbackLastPartial: longest,
        fallbackLastSource: 'phone_mic_result',
        fallbackLastEventAt: at,
      }));
      setVoiceState({ status: 'listening', message: `手机麦克风识别中: ${longest}` });
      armPhoneVoiceFallbackSilenceTimer();
    };
    Voice.onSpeechEnd = () => {
      // 用户停止说话 = 自然的路由时机。路由累积到的最长转写(onSpeechResults/onSpeechPartialResults
      // 已把 latestTextRef 维护为最长)。静音计时器作为 onSpeechEnd 不触发时的兜底。
      routePhoneVoiceFallbackText(phoneVoiceFallbackLatestTextRef.current, 'phone_mic_end');
    };
    Voice.onSpeechError = (event: SpeechErrorEvent) => {
      const message = event.error?.message || 'phone_voice_recognition_failed';
      clearPhoneVoiceFallbackTimer();
      phoneVoiceFallbackActiveRef.current = false;
      voiceListeningRef.current = false;
      setVoiceDebug((prev) => ({
        ...prev,
        fallbackError: message,
        fallbackLastEventAt: new Date().toISOString(),
      }));
      setVoiceState({ status: 'failed', message: `手机麦克风语音识别失败: ${message}` });
      void setPhoneVoiceFallbackPlaybackMode(false);
    };

    await setPhoneVoiceFallbackPlaybackMode(true);
    await Voice.start('zh-CN');
    setVoiceState({
      status: 'listening',
      message: 'Rokid 暂无音频流，已切到手机麦克风。请说“记录这顿饭”。',
    });
  };

  useEffect(() => () => {
    phoneVoiceFallbackActiveRef.current = false;
    clearPhoneVoiceFallbackTimer();
    Voice.destroy().then(() => Voice.removeAllListeners()).catch(() => undefined);
    // council #2 隐私(L3 音频):卸载/离屏时若眼镜语音会话仍在录,必须停掉原生录音 + SFSpeech,
    // 否则离开本屏后眼镜仍在采集 L3 音频、且无可见的停止入口。removeVoiceTranscriptListener 只摘 JS
    // 监听器,不会停原生 CxrClient.startRecord(见 stopRecord → CxrClient.stopRecord + finishSpeechRecognitionSession)。
    if (voiceListeningRef.current) {
      voiceListeningRef.current = false;
      void stopRokidVoiceCommandCapture().catch(() => undefined);
    }
  }, []);

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

  // council 回归修复:'waiting'(已排队)态的文案是在排队瞬间从可能过期的 status 算的
  // (formatQueuedCustomViewMessage),BLE 随后连上 / CustomView 跑起来都不刷新 → 顶部误显
  // "眼镜蓝牙未连接"而底部诊断 connected=true。随 live status 收敛:已运行→ready;BLE 连上但
  // 未运行→用 live 状态重算文案(native 会在连上后自动重发 openCustomView)。
  useEffect(() => {
    if (sessionState.status !== 'waiting') {
      return;
    }
    if (status?.customViewRunning === true) {
      setSessionState({ status: 'ready', message: 'Reva 眼镜视图已运行' });
    } else if (status?.iosBleConnected === true) {
      setSessionState((prev) =>
        prev.status === 'waiting'
          ? { ...prev, message: formatQueuedCustomViewMessage(status) }
          : prev,
      );
    }
  }, [status, sessionState.status]);

  const refresh = () => {
    statusQuery.refetch();
    glanceQuery.refetch();
  };

  const copyRokidVoiceDebugInfo = async () => {
    await Clipboard.setStringAsync(voiceDebugText);
    Alert.alert('已复制', 'Rokid 语音自检信息已复制。');
  };

  // 共享草稿提交:眼镜或手机相机拍到的食物图都走这里 —— 一律 manual_confirm_required:true,
  // 后端落 needs_confirmation 草稿,绝不自动写 DietRecord(council #1 R4)。
  const submitRokidFoodDraft = async (
    action: (typeof CAPTURE_ACTIONS)[number],
    opts: { imageBase64?: string; imageUri?: string; imageSha256?: string; imageByteLength?: number; captureSource: string },
  ) => {
    const capturedAt = new Date().toISOString();
    const meta: Record<string, unknown> = {
      privacy_mode: privacyMode,
      source_surface: 'rokid_health_mode',
      raw_media_retained: false,
      manual_confirm_required: true,
      meal_type: guessMealType(new Date(capturedAt)),
      capture_source: opts.captureSource,
    };
    if (typeof opts.imageByteLength === 'number') {
      meta.image_byte_length = opts.imageByteLength;
    }

    let recognitionResult: Record<string, unknown> | undefined;
    let foodRecognition: FoodRecognitionResponse | undefined;
    let confidence: number | undefined;
    if (action.intent === 'food_scan' && opts.imageBase64) {
      try {
        const recognition = await recognizeFood(opts.imageBase64);
        foodRecognition = recognition;
        recognitionResult = recognition as unknown as Record<string, unknown>;
        confidence = recognitionConfidence(recognition);
        meta.recognition_source = 'diet_recognize';
      } catch (error) {
        meta.recognition_error = error instanceof Error ? error.message : 'food_recognition_failed';
      }
    }

    // council #6 不假装成功:食物拍照既无识别结果、也无可持久化图像引用 → 没有用户可确认的草稿,
    // 不要显示"已提交草稿"。明确报失败。
    if (action.intent === 'food_scan' && !recognitionResult && !opts.imageUri && !opts.imageSha256) {
      setCaptureState({
        status: 'failed',
        actionTitle: action.title,
        message: '拍照识别失败,未生成可确认的草稿,请重试',
      });
      return;
    }

    const submitResult = await submitRokidVisualInput({
      intent: action.intent,
      imageUri: opts.imageUri,
      imageSha256: opts.imageSha256,
      recognitionResult,
      confidence,
      capturedAt,
      privacyClass: 'health_l3',
      meta,
    });
    const nutritionSummary = action.intent === 'food_scan'
      ? foodRecognitionSummary(foodRecognition)
      : undefined;
    const savedDietRecord = action.intent === 'food_scan' && isSavedDietRecordResponse(submitResult);
    if (savedDietRecord) {
      await queryClient.invalidateQueries({ queryKey: ['diet'] });
    }
    setCaptureState({
      status: 'submitted',
      actionTitle: action.title,
      message: savedDietRecord
        ? `已保存饮食记录${nutritionSummary ? `：${nutritionSummary}` : ''}`
        : `已提交${action.title}草稿${nutritionSummary ? `：${nutritionSummary}` : ''}`,
    });
  };

  // council #1 R4:眼镜拍照不可用时用手机相机,但仍走 Rokid 草稿流(needs_confirmation)。
  // 不再深链到 /diet?capture=photo —— 那条 diet.tsx 会立即 createDietRecord 入库,逃离 draft+confirm。
  const openMobileFoodCameraFallback = async (action: (typeof CAPTURE_ACTIONS)[number]) => {
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        setCaptureState({ status: 'failed', actionTitle: action.title, message: '需要相机权限才能用手机拍照记录' });
        return;
      }
      setCaptureState({
        status: 'capturing',
        actionTitle: action.title,
        message: '眼镜拍照不可用,已切到手机相机(拍完仍需你确认后入库)…',
      });
      const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.6, base64: true });
      if (result.canceled || !result.assets?.[0]?.base64) {
        setCaptureState({ status: 'idle', actionTitle: action.title, message: '已取消手机拍照' });
        return;
      }
      const asset = result.assets[0];
      await submitRokidFoodDraft(action, {
        imageBase64: asset.base64 ?? undefined,
        imageUri: asset.uri,
        captureSource: 'phone_camera_fallback',
      });
    } catch (error) {
      setCaptureState({
        status: 'failed',
        actionTitle: action.title,
        message: `手机拍照失败: ${error instanceof Error ? error.message : 'capture_failed'}`,
      });
    }
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
          let refreshedStatus = statusQuery.data;
          try {
            const refreshed = await statusQuery.refetch();
            refreshedStatus = refreshed.data ?? refreshedStatus;
          } catch {
            // diagnostics refresh is best-effort; the waiting message still stands.
          }
          setSessionState({
            status: 'waiting',
            message: formatQueuedCustomViewMessage(refreshedStatus),
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
    setVoiceDebug((prev) => ({ ...prev, lastCommandError: undefined }));
    let recordingStarted = false;
    try {
      const viewResult = await openRokidRevaCustomView({
        title: 'Reva 语音控制',
        body: '正在等待明确语音指令',
        priority: 'voice',
      });
      const refreshed = await statusQuery.refetch();
      const audioSessionReady =
        hasRokidAudioSession(viewResult) ||
        hasRokidAudioSession(refreshed.data);
      const customViewHasWeakEvidence =
        hasRokidCustomViewSessionEvidence(viewResult) ||
        hasRokidCustomViewSessionEvidence(refreshed.data);
      if (viewResult.ok === false) {
        if (!audioSessionReady && (
          customViewHasWeakEvidence ||
          isRokidNativeChannelNotReady(typeof viewResult.reason === 'string' ? viewResult.reason : undefined)
        )) {
          await startPhoneVoiceFallback('rokid_audio_session_not_ready');
          return;
        }
        if (!audioSessionReady) {
          throw new Error(typeof viewResult.reason === 'string' ? viewResult.reason : 'rokid_custom_view_failed');
        }
      }
      if (!audioSessionReady) {
        await startPhoneVoiceFallback('rokid_audio_session_not_ready');
        return;
      }
      const recordResult = await startRokidVoiceCommandCapture();
      if (recordResult.ok === false) {
        const reason = typeof recordResult.reason === 'string' ? recordResult.reason : 'rokid_record_failed';
        if (isRokidNativeChannelNotReady(reason)) {
          await startPhoneVoiceFallback(reason === 'rokid_audio_session_not_ready' ? reason : 'rokid_audio_session_not_ready');
          return;
        }
        throw new Error(reason);
      }
      // council #2(不假装成功):ASR 未就绪(语音/麦克风权限被拒、识别器不可用)时,麦克风在录但
      // 永远不会产生 transcript → 别显"已开启"造成"启动了却没反应"。停掉无用录音、明确告知原因。
      if (recordResult.speechRecognitionReady === false) {
        await stopRokidVoiceCommandCapture().catch(() => undefined);
        const reason =
          typeof recordResult.speechRecognitionReason === 'string' && recordResult.speechRecognitionReason
            ? recordResult.speechRecognitionReason
            : 'speech_recognition_unavailable';
        setVoiceState({
          status: 'failed',
          message: `语音识别未就绪(${reason}):请在 设置 → Reva 里允许"语音识别"和"麦克风",再重试。`,
        });
        return;
      }
      recordingStarted = true;
      removeVoiceTranscriptListener();
      voiceTranscriptSubscriptionRef.current = addRokidTranscriptListener((event) => {
        void handleVoiceTranscript(event);
      });
      voiceListeningRef.current = true;
      lastRoutedTranscriptRef.current = null;
      voiceCommandInFlightRef.current = false;
      setVoiceState({ status: 'listening', message: 'Rokid 语音控制已开启' });
    } catch (error) {
      voiceListeningRef.current = false;
      removeVoiceTranscriptListener();
      await stopPhoneVoiceFallback();
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
    const phoneFallbackWasActive = phoneVoiceFallbackActiveRef.current;
    voiceListeningRef.current = false;
    removeVoiceTranscriptListener();
    try {
      await stopPhoneVoiceFallback();
      if (!phoneFallbackWasActive) {
        const result = await stopRokidVoiceCommandCapture();
        if (result.ok === false) {
          throw new Error(typeof result.reason === 'string' ? result.reason : 'rokid_stop_record_failed');
        }
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
          await openMobileFoodCameraFallback(action);
          return;
        }
        throw new Error('rokid_custom_view_not_ready');
      }
      setCaptureState({
        status: 'capturing',
        actionTitle: action.title,
        message: `正在从眼镜拍照并回传(BLE 较慢,请稍候)…`,
      });
      const captureResult = await takeRokidPhotoBase64WithTimeout({ width: 1024, height: 768, quality: 80 });
      if (captureResult.ok === false) {
        const reason = typeof captureResult.reason === 'string' ? captureResult.reason : 'rokid_capture_failed';
        if (action.intent === 'food_scan' && isRokidNativeChannelNotReady(reason)) {
          await openMobileFoodCameraFallback(action);
          return;
        }
        throw new Error(reason);
      }
      const imageByteLength = readNumber(captureResult, ['byteLength', 'byte_length', 'size']);
      await submitRokidFoodDraft(action, {
        imageBase64: readString(captureResult, ['base64', 'imageBase64', 'image_base64']),
        imageUri: readString(captureResult, ['imageUri', 'image_uri', 'uri', 'localUri', 'path']),
        imageSha256: readValidSha256(captureResult),
        imageByteLength: typeof imageByteLength === 'number' ? imageByteLength : undefined,
        captureSource: 'rokid_glasses',
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
    const rawTranscript = transcriptText(event);
    if (!rawTranscript) {
      return;
    }
    // council #3 去重:① 命令处理中(拍照/路由)忽略新转写;② 对"同一句话的多个 final"
    // (与上次已路由转写相互包含、且在短窗内)去重 —— 防止过度捕获把一句话路由成多次拍照/草稿。
    // 眼镜路径此前完全没有去重(手机路径只按精确文本去重,对增长式 final 无效)。
    if (voiceCommandInFlightRef.current) {
      return;
    }
    const routedAt = Date.now();
    const lastRouted = lastRoutedTranscriptRef.current;
    if (
      lastRouted &&
      routedAt - lastRouted.at < ROKID_VOICE_ROUTE_DEDUP_MS &&
      (rawTranscript === lastRouted.text ||
        rawTranscript.includes(lastRouted.text) ||
        lastRouted.text.includes(rawTranscript))
    ) {
      return;
    }
    lastRoutedTranscriptRef.current = { text: rawTranscript, at: routedAt };
    voiceCommandInFlightRef.current = true;
    const normalizedTranscript = normalizeRokidHealthTranscript(rawTranscript);
    const transcript = normalizedTranscript.transcript;

    const capturedAt = transcriptCapturedAt(event);
    setVoiceDebug((prev) => ({
      ...prev,
      lastTranscript: transcript,
      lastRawTranscript: rawTranscript,
      lastNormalizedTranscript: transcript,
      lastTranscriptNormalizedBy: normalizedTranscript.normalizedBy,
      lastTranscriptAt: capturedAt ?? new Date().toISOString(),
      lastCommandError: undefined,
    }));
    setVoiceState({ status: 'listening', message: `识别: ${transcript}` });
    void updateVoiceCustomView(`识别: ${transcript}`);
    try {
      const response = await submitRokidVoiceCommand({
        transcript,
        confidence: typeof event.confidence === 'number' ? event.confidence : undefined,
        context: 'rokid_health',
        capturedAt,
        meta: {
          source_surface: 'rokid_health_mode',
          source_event: 'rokid_transcript',
          ...normalizedTranscript.meta,
          ...(event.meta ?? {}),
        },
      });
      const command = response.command;
      const reply = command?.voice_reply || command?.display_text;
      setVoiceDebug((prev) => ({
        ...prev,
        lastCommandAction: command?.client_action ?? command?.intent ?? 'unknown',
        lastCommandAt: new Date().toISOString(),
        lastCommandReply: reply,
        lastCommandError: undefined,
      }));
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
      const message = error instanceof Error ? error.message : 'voice_command_failed';
      setVoiceDebug((prev) => ({
        ...prev,
        lastCommandError: message,
        lastCommandAt: new Date().toISOString(),
      }));
      setVoiceState({
        status: 'failed',
        message: `Rokid 语音指令失败: ${message}`,
      });
    } finally {
      // council #3:命令处理结束(成功或失败)后解锁,允许下一条明确指令。
      voiceCommandInFlightRef.current = false;
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

              <View style={styles.capabilityBox}>
                <View style={styles.capabilityHeader}>
                  <Text style={txt.capabilityTitle}>能力路由</Text>
                  <Text style={txt.capabilityRoute}>
                    推荐路径: {capabilityRouteTitle(capabilityGateway.recommendedPath)}
                  </Text>
                </View>
                <View style={styles.capabilityGrid}>
                  <Text style={txt.capabilityItem}>
                    运动: {movementRouteLabel(capabilityGateway)}
                  </Text>
                  <Text style={txt.capabilityItem}>
                    饮食: {captureRouteLabel(capabilityGateway)}
                  </Text>
                  <Text style={txt.capabilityItem}>
                    显示: {displayRouteLabel(capabilityGateway.summary.display)}
                  </Text>
                </View>
                {capabilityGateway.blockers.slice(0, 2).map((blocker) => (
                  <Text key={blocker} style={txt.capabilityBlocker} numberOfLines={3}>
                    {blocker}
                  </Text>
                ))}
              </View>

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
              <Text style={txt.featureDetail}>眼镜端 App 优先，CXR-L 安装/启动失败时可用本地计数兜底。</Text>
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
          <View style={styles.voiceSelfCheckBox}>
            <View style={styles.voiceSelfCheckHeader}>
              <Text style={txt.voiceSelfCheckTitle}>语音自检</Text>
              <Text
                style={[
                  txt.voiceSelfCheckSummary,
                  voiceState.status === 'failed' ? { color: s.warning.solid } : null,
                ]}
              >
                {voiceSelfCheck.summary}
              </Text>
            </View>
            {voiceSelfCheck.items.map((item) => {
              const tone = voiceSelfCheckTone(item.status, s, c);
              return (
                <View key={item.id} style={styles.voiceSelfCheckRow}>
                  <View style={[styles.voiceSelfCheckIcon, { backgroundColor: tone.bg }]}>
                    <Ionicons name={tone.icon} size={15} color={tone.fg} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={txt.voiceSelfCheckTitle}>{item.title}</Text>
                    <Text style={txt.voiceSelfCheckDetail}>{item.detail}</Text>
                  </View>
                </View>
              );
            })}
            <View style={styles.voiceSelfCheckActions}>
              <Pressable
                onPress={refresh}
                style={({ pressed }) => [styles.fallbackButton, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel="刷新语音自检"
              >
                <Ionicons name="refresh-outline" size={15} color={c.brand} />
                <Text style={txt.fallbackButton}>刷新自检</Text>
              </Pressable>
              <Pressable
                onPress={copyRokidVoiceDebugInfo}
                style={({ pressed }) => [styles.fallbackButton, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel="复制 Rokid 语音自检信息"
              >
                <Ionicons name="copy-outline" size={15} color={c.brand} />
                <Text style={txt.fallbackButton}>复制调试信息</Text>
              </Pressable>
            </View>
          </View>
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
  capabilityBox: {
    marginTop: spacing.md,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    padding: spacing.sm,
    gap: 8,
  },
  capabilityHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  capabilityGrid: {
    flexDirection: 'column',
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
  voiceSelfCheckBox: {
    marginTop: spacing.md,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    padding: spacing.sm,
    gap: 9,
  },
  voiceSelfCheckHeader: {
    gap: 4,
  },
  voiceSelfCheckRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 9,
  },
  voiceSelfCheckIcon: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  voiceSelfCheckActions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: 2,
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
  capabilityTitle: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  capabilityRoute: { fontSize: 11, fontWeight: '800', color: c.brand, textAlign: 'right', flexShrink: 1 } as TextStyle,
  capabilityItem: { fontSize: 12, fontWeight: '700', color: c.labelSecondary, lineHeight: 17 } as TextStyle,
  capabilityBlocker: { fontSize: 11, fontWeight: '700', color: c.orange, lineHeight: 16 } as TextStyle,
  validationHeading: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  validationTitle: { flex: 1, fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  validationNext: { fontSize: 11, fontWeight: '800', color: c.brand, maxWidth: 140 } as TextStyle,
  validationDetail: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sessionState: { fontSize: 12, fontWeight: '800', color: c.labelSecondary } as TextStyle,
  voiceSelfCheckTitle: { fontSize: 12, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  voiceSelfCheckSummary: { fontSize: 12, lineHeight: 17, fontWeight: '700', color: c.labelSecondary } as TextStyle,
  voiceSelfCheckDetail: { fontSize: 11, lineHeight: 16, fontWeight: '700', color: c.labelSecondary, marginTop: 1 } as TextStyle,
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
