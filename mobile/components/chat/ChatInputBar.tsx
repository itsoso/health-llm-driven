import React, { useCallback, useRef, useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, Text,
  Modal, Pressable, ActivityIndicator, TextStyle, ScrollView,
  Alert, AppState, Keyboard, NativeSyntheticEvent, TextInputContentSizeChangeEventData,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import ReAnimated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming } from 'react-native-reanimated';
import { useMediaPicker, type PendingImage } from '../../hooks/useMediaPicker';
import { useRealtimeDictation } from '../../hooks/useRealtimeDictation';
import {
  canStartDictation,
  canStartHold,
  createInitialComposerState,
  reduceComposerState,
  shouldShowDisabledMic,
} from './composerState';
import {
  executeMedicalExamImportSkillForDocumentAsset,
  type ChatMedicalExamImportSkillResult,
} from '../../services/chatMedicalExamImportSkill';
import {
  cleanupAbandonedChatDraftFiles,
  clearPersistedChatDraft,
  hydrateDraftImagesForSend,
  loadChatDraft,
  persistChatDraft,
  type ChatDraftMetadata,
} from '../../services/chatDraftStorage';
import { registerAppReloadPreparation } from '../../services/appReloadPreparation';
import {
  revaColors as C,
  revaRadii,
  revaShadows,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import {
  buildVoiceDraft,
  buildVoiceDraftExtraContext,
  mergeExtraContext,
  type VoiceDraft,
  type VoiceInputSource,
} from '../../services/voiceDraft';
import type { TranscribeAudioResult } from '../../services/transcribe';
import { durationBucket, emitClientEvent } from '../../services/clientEvents';

const CANCEL_THRESHOLD = 80;
const VOICE_SLIDE_THRESHOLD = 88;
const INPUT_HOLD_DICTATION_DELAY_MS = 260;
const COMPOSER_HIT_SLOP = { top: 6, right: 6, bottom: 6, left: 6 };
const COMPOSER_BAR_BG = C.paper;
const COMPOSER_INPUT_BG = C.surface;
const COMPOSER_INPUT_BG_PRESSED = C.surface2;
const COMPOSER_INPUT_BG_ACTIVE = C.green50;
const COMPOSER_BUTTON_BG = C.surface2;
const COMPOSER_BUTTON_BG_ACTIVE = C.green50;
const COMPOSER_ICON = C.ink2;
const COMPOSER_ICON_MUTED = C.ink3;
const COMPOSER_TEXT_MIN_HEIGHT = 40;
const COMPOSER_TEXT_MAX_HEIGHT = 72;
const COMPOSER_TEXT_VERTICAL_CHROME = 8;
const VOICE_WAVE_BARS = Array.from({ length: 28 }, (_, i) => i);

type ChatAgentMode = 'daily' | 'deep' | 'vision';
type AttachmentPayloadBucket =
  | 'unknown'
  | 'lt_256kb'
  | '256kb_1mb'
  | '1_4mb'
  | 'gte_4mb';

function attachmentPayloadBucket(images: PendingImage[]): AttachmentPayloadBucket {
  const encodedLength = images.reduce((total, image) => (
    total + (typeof image.base64 === 'string' ? image.base64.length : 0)
  ), 0);
  if (encodedLength === 0) return 'unknown';
  const approximateBytes = Math.floor(encodedLength * 0.75);
  if (approximateBytes < 256 * 1024) return 'lt_256kb';
  if (approximateBytes < 1024 * 1024) return '256kb_1mb';
  if (approximateBytes < 4 * 1024 * 1024) return '1_4mb';
  return 'gte_4mb';
}

export interface ChatInputSendOptions {
  extraContext?: string;
  channel?: 'typed' | 'voice' | 'siri';
}

const AGENT_MODES: {
  id: ChatAgentMode;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
}[] = [
  { id: 'daily', label: '日常', icon: 'flash-outline' },
  { id: 'deep', label: '深思', icon: 'diamond-outline' },
  { id: 'vision', label: '识图', icon: 'image-outline' },
];

const MODE_PLACEHOLDER: Record<ChatAgentMode, string> = {
  daily: '问小巴，或点麦克风说话',
  deep: '让小巴深思一个计划',
  vision: '拍照/报告后问小巴',
};

const MEAL_PHOTO_CONTEXT = {
  source: 'mobile_chat_meal_photo',
  intent: 'diet_photo_record',
  instruction: '用户刚通过拍照记餐明确发起记录。把本轮全部餐食照片作为同一餐的上下文,综合识别食物和份量,识别完成后直接保存为今日饮食记录,不要等待二次确认。保存成功后返回已保存的结构化饮食卡,并注明营养值为估算值,允许用户稍后调整。',
};

function createMealCaptureSessionId(): string {
  return `meal-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createAttachmentEventKey(): string {
  return `attachment-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function draftMetadataForPhotoContext(
  context: Record<string, string> | null,
): ChatDraftMetadata {
  if (context?.intent !== 'diet_photo_record') return {};
  return {
    intent: 'diet_photo_record',
    captureSessionId: context.capture_session_id,
  };
}

function mergePhotoContext(base: string | undefined, photoContext: Record<string, string>): string {
  if (!base) return JSON.stringify(photoContext);
  try {
    const parsed = JSON.parse(base);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return JSON.stringify({ ...parsed, ...photoContext });
    }
  } catch {
    // Preserve non-JSON caller context instead of dropping it.
  }
  return JSON.stringify({ prior_context: base, ...photoContext });
}

function buildAgentModeOptions(mode: ChatAgentMode): ChatInputSendOptions | undefined {
  if (mode === 'daily') return undefined;
  const instruction = mode === 'deep'
    ? '先梳理目标、约束和健康风险边界，再给出可执行计划、验证信号和下一步确认动作。'
    : '优先理解图片、报告或饮食运动线索，输出可确认的记录、复核卡片或下一步补充信息。';
  return {
    extraContext: JSON.stringify({
      source: 'mobile_chat_composer',
      mode,
      instruction,
    }),
  };
}

function PulsingRing() {
  const scale = useSharedValue(1);
  React.useEffect(() => {
    scale.value = withRepeat(withTiming(1.4, { duration: 800 }), -1, true);
  }, [scale]);
  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: 2 - scale.value,
  }));
  return <ReAnimated.View style={[styles.pulsingRing, animStyle]} />;
}

interface Props {
  onSend: (
    text: string,
    images?: PendingImage[] | null,
    options?: ChatInputSendOptions,
  ) => boolean | void | Promise<boolean | void>;
  isStreaming: boolean;
  /** Prefills the composer when callers deep-link into chat with a prompt. */
  initialText?: string;
  /** Bumps when callers need to inject the same prompt text again. */
  initialTextKey?: string | number;
  /** Reserved for callers that keep composer API aligned with chat-level voice entry. */
  conversationId?: number;
  onMedicalExamImportResult?: (result: ChatMedicalExamImportSkillResult) => void;
  /** 变化(>0)即请求聚焦输入框 — GPT/Gemini 式默认唤起键盘;空对话进入时由 chat.tsx 递增。 */
  autoFocusToken?: number;
  /** 变化(>0)即从聊天页直接拍照记餐,照片先进入当前对话。 */
  captureMealPhotoToken?: number;
}

export default function ChatInputBar({
  onSend,
  isStreaming,
  initialText,
  initialTextKey,
  onMedicalExamImportResult,
  autoFocusToken,
  captureMealPhotoToken,
}: Props) {
  const [input, setInput] = useState(initialText ?? '');
  const [showMenu, setShowMenu] = useState(false);
  const [showMedicalImportMenu, setShowMedicalImportMenu] = useState(false);
  const [medicalImportBusy, setMedicalImportBusy] = useState(false);
  const [agentMode, setAgentMode] = useState<ChatAgentMode>('daily');
  const [cancelHint, setCancelHint] = useState(false);
  const [holdTranscript, setHoldTranscript] = useState('');
  const [textInputFocused, setTextInputFocused] = useState(false);
  const [textInputHeight, setTextInputHeight] = useState(COMPOSER_TEXT_MIN_HEIGHT);
  const [composer, dispatchComposer] = React.useReducer(
    reduceComposerState,
    undefined,
    createInitialComposerState,
  );
  const [draftHydrated, setDraftHydrated] = useState(false);
  const [justSent, setJustSent] = useState(false);  // 刚发送, 按钮停留 1s 避免误切 mic
  const {
    pendingImages,
    setPendingImages,
    removeImage,
    releaseImagesAfterSend,
    pickImage,
    takePhoto,
  } = useMediaPicker();
  const textInputRef = useRef<TextInput>(null);
  const lastKeyboardSubmitAtRef = useRef(0);
  const holdStartXRef = useRef(0);
  const voiceGestureActiveRef = useRef(false);
  const voiceCommitModeRef = useRef<'send' | 'text'>('send');
  const realtimeBaseInputRef = useRef('');
  const realtimeInputEditedRef = useRef(false);
  const realtimeAsrResultRef = useRef<TranscribeAudioResult | undefined>(undefined);
  const activeVoiceSourceRef = useRef<'hold' | 'dictation' | null>(null);
  const inputHoldDictationActiveRef = useRef(false);
  const inputHoldDictationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dictationStopRequestedRef = useRef(false);
  const holdTranscriptRef = useRef('');
  const inputChannelRef = useRef<'typed' | 'voice'>('typed');
  const composerRef = useRef(composer);
  const stopDictationRef = useRef<() => Promise<string>>(async () => '');
  const cancelDictationRef = useRef<() => Promise<void>>(async () => {});
  const cancelVoiceRef = useRef<() => Promise<void>>(async () => {});
  const dictationRealtimeActiveRef = useRef(false);
  const voiceRealtimeActiveRef = useRef(false);
  const voiceDraftRef = useRef<VoiceDraft | null>(null);
  const pendingPhotoContextRef = useRef<Record<string, string> | null>(null);
  const draftInteractionVersionRef = useRef(0);
  const draftPersistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draftHydratedRef = useRef(false);
  const draftSnapshotRef = useRef({
    text: input,
    images: pendingImages,
    photoContext: pendingPhotoContextRef.current,
  });
  const justSentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sendInFlightRef = useRef(false);
  composerRef.current = composer;
  draftHydratedRef.current = draftHydrated;
  draftSnapshotRef.current = {
    text: input,
    images: pendingImages,
    photoContext: pendingPhotoContextRef.current,
  };
  const canSend = (!!input.trim() || pendingImages.length > 0)
    && composer.phase !== 'submitting';

  React.useEffect(() => {
    if (initialText == null) return;
    inputChannelRef.current = 'typed';
    setInput(prev => (prev === initialText ? prev : initialText));
    if (initialText.trim() && composerRef.current.mode === 'hold') {
      dispatchComposer({ type: 'toggle_mode' });
    }
  }, [initialText, initialTextKey]);

  React.useEffect(() => {
    let mounted = true;
    const hydrationVersion = draftInteractionVersionRef.current;
    void (async () => {
      try {
        const draft = await loadChatDraft();
        if (!mounted) return;
        if (draftInteractionVersionRef.current !== hydrationVersion) {
          void cleanupAbandonedChatDraftFiles(
            draftSnapshotRef.current.images.map(image => image.uri),
          );
          return;
        }
        if (initialText == null) {
          inputChannelRef.current = 'typed';
          setInput(prev => prev || draft.text);
          if (draft.text.trim() && composerRef.current.mode === 'hold') {
            dispatchComposer({ type: 'toggle_mode' });
          }
        }
        if (draft.intent === 'diet_photo_record' && draft.captureSessionId && draft.images.length > 0) {
          pendingPhotoContextRef.current = {
            ...MEAL_PHOTO_CONTEXT,
            capture_session_id: draft.captureSessionId,
          };
        }
        setPendingImages(draft.images, draft.intent === 'diet_photo_record' ? 3 : 9);
        void cleanupAbandonedChatDraftFiles(draft.images.map(image => image.uri));
      } catch (e) {
        if (__DEV__) console.warn('[ChatInputBar] draft restore failed:', e);
      } finally {
        if (mounted) setDraftHydrated(true);
      }
    })();
    return () => {
      mounted = false;
    };
    // Draft restoration is mount-only. Later deep-link prefills use the initialText effect above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (!draftHydrated) return;
    if (draftPersistTimerRef.current) clearTimeout(draftPersistTimerRef.current);
    draftPersistTimerRef.current = setTimeout(() => {
      draftPersistTimerRef.current = null;
      void persistChatDraft(
        input,
        pendingImages,
        Date.now(),
        draftMetadataForPhotoContext(pendingPhotoContextRef.current),
      ).catch((e) => {
        if (__DEV__) console.warn('[ChatInputBar] draft persistence failed:', e);
      });
    }, 250);
    return () => {
      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }
    };
  }, [draftHydrated, input, pendingImages]);

  React.useEffect(() => registerAppReloadPreparation(async () => {
    if (!draftHydratedRef.current) return;
    if (draftPersistTimerRef.current) {
      clearTimeout(draftPersistTimerRef.current);
      draftPersistTimerRef.current = null;
    }
    const snapshot = draftSnapshotRef.current;
    await persistChatDraft(
      snapshot.text,
      snapshot.images,
      Date.now(),
      draftMetadataForPhotoContext(snapshot.photoContext),
    );
  }), []);

  const restoreVoiceTranscriptDraft = useCallback((text: string) => {
    const clean = text.trim();
    if (!clean) return;
    const draft = buildVoiceDraft({
      source: voiceDraftRef.current?.source ?? 'hold_to_talk',
      rawTranscript: voiceDraftRef.current?.rawTranscript || clean,
    });
    voiceDraftRef.current = { ...draft, normalizedText: clean };
    inputChannelRef.current = 'voice';
    setInput(clean);
    dispatchComposer({ type: 'voice_draft_ready' });
    setTimeout(() => textInputRef.current?.focus(), 30);
  }, []);

  const applyVoiceTranscript = useCallback((
    source: VoiceInputSource,
    rawTranscript: string,
    asr?: TranscribeAudioResult,
  ) => {
    const draft = buildVoiceDraft({
      source,
      rawTranscript,
      asr: asr
        ? {
          provider: asr.provider,
          model: asr.model,
          durationMs: asr.durationMs,
          confidence: asr.confidence,
        }
        : undefined,
    });
    voiceDraftRef.current = draft;
    inputChannelRef.current = 'voice';
    setInput(draft.normalizedText);
    return draft;
  }, []);

  // Explicit focus requests enter text mode first; ordinary chat entry stays voice-first.
  React.useEffect(() => {
    if (!autoFocusToken) return;
    setTextInputFocused(true);
    if (composerRef.current.mode === 'hold') {
      dispatchComposer({ type: 'toggle_mode' });
    }
    const t = setTimeout(() => {
      textInputRef.current?.focus();
    }, 380);
    return () => clearTimeout(t);
  }, [autoFocusToken]);

  const performSend = useCallback(async (text?: string, sendOptions?: ChatInputSendOptions) => {
    let msg = (text || input).trim();
    if (!msg && pendingImages.length === 0) return;
    const phase = composerRef.current.phase;
    let effectiveChannelForSend: 'typed' | 'voice' | 'siri' = sendOptions?.channel ?? inputChannelRef.current;
    const attachmentStartedAt = Date.now();
    const attachmentImageCount = pendingImages.length;
    const attachmentEventKey = createAttachmentEventKey();
    let attachmentStage: 'local_prepare' | 'server_accept' = 'local_prepare';
    let attachmentPayload: AttachmentPayloadBucket = (
      attachmentImageCount > 0 ? attachmentPayloadBucket(pendingImages) : 'unknown'
    );
    dispatchComposer({ type: 'submit' });
    try {
      let voiceDraftForSend: VoiceDraft | null = null;
      if (phase === 'live_dictating' || dictationRealtimeActiveRef.current) {
        dictationStopRequestedRef.current = true;
        const finalTranscript = String(await stopDictationRef.current() || '').trim();
        activeVoiceSourceRef.current = null;
        if (!text && finalTranscript) {
          const base = realtimeBaseInputRef.current.trim();
          const raw = base ? `${base} ${finalTranscript}` : finalTranscript;
          voiceDraftForSend = applyVoiceTranscript('realtime_mic', raw, realtimeAsrResultRef.current);
          msg = voiceDraftForSend.normalizedText;
        }
      } else if (phase === 'hold_starting' || phase === 'hold_recording') {
        await cancelVoiceRef.current();
      }
      const sendImages = pendingImages.length > 0
        ? await hydrateDraftImagesForSend(pendingImages)
        : pendingImages;
      if (attachmentImageCount > 0) {
        attachmentPayload = attachmentPayloadBucket(sendImages);
        attachmentStage = 'server_accept';
      }
      const modeOptions = buildAgentModeOptions(agentMode);
      const effectiveChannel = sendOptions?.channel ?? inputChannelRef.current;
      effectiveChannelForSend = effectiveChannel;
      if (effectiveChannel === 'voice') {
        if (!voiceDraftForSend && voiceDraftRef.current?.normalizedText === msg) {
          voiceDraftForSend = voiceDraftRef.current;
        }
        if (!voiceDraftForSend && msg) {
          voiceDraftForSend = buildVoiceDraft({
            source: phase === 'live_dictating' || dictationRealtimeActiveRef.current ? 'realtime_mic' : 'hold_to_talk',
            rawTranscript: msg,
          });
          msg = voiceDraftForSend.normalizedText;
          voiceDraftRef.current = voiceDraftForSend;
        }
      }
      const outboundOptions: ChatInputSendOptions = {
        ...(modeOptions || {}),
        ...(sendOptions || {}),
        ...(effectiveChannel !== 'typed' ? { channel: effectiveChannel } : {}),
      };
      if (sendImages.length > 0 && pendingPhotoContextRef.current) {
        outboundOptions.extraContext = mergePhotoContext(
          outboundOptions.extraContext,
          pendingPhotoContextRef.current,
        );
      }
      if (voiceDraftForSend) {
        outboundOptions.extraContext = mergeExtraContext(
          sendOptions?.extraContext ?? modeOptions?.extraContext,
          buildVoiceDraftExtraContext(voiceDraftForSend),
        );
      }
      const sendResult = onSend(
        msg || '请分析这些图片',
        sendImages.length > 0 ? sendImages : null,
        Object.keys(outboundOptions).length > 0 ? outboundOptions : undefined,
      );
      const accepted = await Promise.resolve(sendResult);
      if (accepted === false) {
        if (attachmentImageCount > 0) {
          try {
            await emitClientEvent('chat_attachment_terminal', {
              phase: 'failed',
              stage: 'server_accept',
              image_count: attachmentImageCount,
              duration_bucket: durationBucket(attachmentStartedAt),
              payload_bucket: attachmentPayload,
              error_code: 'server_not_accepted',
            }, { eventKey: attachmentEventKey });
          } catch {
            // The rejected send already preserves the draft for a later retry.
          }
        }
        if (effectiveChannelForSend === 'voice' && msg) {
          restoreVoiceTranscriptDraft(msg);
          Alert.alert('发送失败', '语音已转成文字并保留在输入框里，请修改后重试。');
          return;
        }
        dispatchComposer({ type: 'fail', errorCode: 'send_not_accepted' });
        Alert.alert('发送失败', '消息和图片草稿已保留，请检查网络后重试。');
        return;
      }
      if (attachmentImageCount > 0) {
        try {
          await emitClientEvent('chat_attachment_terminal', {
            phase: 'accepted',
            stage: 'server_accept',
            image_count: attachmentImageCount,
            duration_bucket: durationBucket(attachmentStartedAt),
            payload_bucket: attachmentPayload,
          }, { eventKey: attachmentEventKey });
        } catch (e) {
          // The server already accepted the Turn. Telemetry persistence must
          // not turn that success into a user-visible retry and duplicate send.
          if (__DEV__) console.warn('[ChatInputBar] accepted-send telemetry persistence failed:', e);
        }
      }
    } catch (e) {
      if (attachmentImageCount > 0) {
        try {
          await emitClientEvent('chat_attachment_terminal', {
            phase: 'failed',
            stage: attachmentStage,
            image_count: attachmentImageCount,
            duration_bucket: durationBucket(attachmentStartedAt),
            payload_bucket: attachmentPayload,
            error_code: attachmentStage === 'local_prepare'
              ? 'draft_hydration_failed'
              : 'send_rejected',
          }, { eventKey: attachmentEventKey });
        } catch {
          // The failure path retains the source draft regardless of telemetry.
        }
      }
      if (effectiveChannelForSend === 'voice' && msg) {
        restoreVoiceTranscriptDraft(msg);
        Alert.alert('发送失败', '语音已转成文字并保留在输入框里，请修改后重试。');
        if (__DEV__) console.warn('[ChatInputBar] voice send rejected:', e);
        return;
      }
      dispatchComposer({ type: 'fail', errorCode: 'send_rejected' });
      Alert.alert('发送失败', '消息和图片草稿已保留，请检查网络后重试。');
      if (__DEV__) console.warn('[ChatInputBar] send rejected:', e);
      return;
    }

    if (draftPersistTimerRef.current) {
      clearTimeout(draftPersistTimerRef.current);
      draftPersistTimerRef.current = null;
    }
    setInput('');
    inputChannelRef.current = 'typed';
    voiceDraftRef.current = null;
    realtimeAsrResultRef.current = undefined;
    pendingPhotoContextRef.current = null;
    draftInteractionVersionRef.current += 1;
    draftSnapshotRef.current = {
      text: '',
      images: [],
      photoContext: null,
    };
    try {
      await releaseImagesAfterSend();
    } catch (e) {
      if (__DEV__) console.warn('[ChatInputBar] sent image cleanup failed:', e);
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setJustSent(true);
    if (justSentTimerRef.current) clearTimeout(justSentTimerRef.current);
    justSentTimerRef.current = setTimeout(() => {
      justSentTimerRef.current = null;
      setJustSent(false);
    }, 1000);
    dispatchComposer({ type: 'submit_complete' });
    try {
      await clearPersistedChatDraft();
    } catch (e) {
      if (__DEV__) console.warn('[ChatInputBar] sent draft cleanup failed:', e);
    }
  }, [
    agentMode,
    applyVoiceTranscript,
    input,
    pendingImages,
    onSend,
    releaseImagesAfterSend,
    restoreVoiceTranscriptDraft,
  ]);

  const handleSend = useCallback(async (
    text?: string,
    sendOptions?: ChatInputSendOptions,
  ) => {
    if (sendInFlightRef.current) return;
    sendInFlightRef.current = true;
    try {
      await performSend(text, sendOptions);
    } finally {
      sendInFlightRef.current = false;
    }
  }, [performSend]);

  const handleRealtimeTranscript = useCallback((text: string, asr?: TranscribeAudioResult) => {
    const clean = text.trim();
    realtimeAsrResultRef.current = asr;
    if (activeVoiceSourceRef.current === 'hold') {
      holdTranscriptRef.current = clean;
      setHoldTranscript(clean);
      return;
    }
    if (realtimeInputEditedRef.current) return;
    const base = realtimeBaseInputRef.current.trim();
    applyVoiceTranscript('realtime_mic', base ? `${base} ${clean}` : clean, asr);
  }, [applyVoiceTranscript]);

  const realtimeDictation = useRealtimeDictation({
    onTranscript: handleRealtimeTranscript,
    onEnd: () => {
      if (activeVoiceSourceRef.current === 'dictation') {
        dispatchComposer({ type: 'dictation_end' });
      }
    },
    onError: (message) => dispatchComposer({ type: 'fail', errorCode: message || 'dictation_failed' }),
  });

  stopDictationRef.current = realtimeDictation.stopDictation;
  cancelDictationRef.current = realtimeDictation.cancelDictation;
  dictationRealtimeActiveRef.current = realtimeDictation.isDictating;

  React.useEffect(() => {
    if (
      realtimeDictation.isDictating
      && !dictationStopRequestedRef.current
      && composerRef.current.mode === 'text'
      && composerRef.current.phase === 'idle'
    ) {
      dispatchComposer({ type: 'dictation_start' });
    }
  }, [composer.mode, composer.phase, realtimeDictation.isDictating]);

  const startRealtimeDictation = useCallback(async () => {
    const state = composerRef.current;
    if (!canStartDictation(state)) return false;
    realtimeInputEditedRef.current = false;
    dictationStopRequestedRef.current = false;
    realtimeAsrResultRef.current = undefined;
    realtimeBaseInputRef.current = input.trim();
    activeVoiceSourceRef.current = 'dictation';
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    dispatchComposer({ type: 'dictation_start' });
    const started = await realtimeDictation.startDictation();
    const cancelledDuringStartup = dictationStopRequestedRef.current
      || activeVoiceSourceRef.current !== 'dictation';
    if (started === false) {
      if (!cancelledDuringStartup) {
        dispatchComposer({ type: 'fail', errorCode: realtimeDictation.error || 'dictation_start_failed' });
      }
      activeVoiceSourceRef.current = null;
      return false;
    }
    if (cancelledDuringStartup) return false;
    return true;
  }, [input, realtimeDictation]);

  const applyRealtimeFinalTranscript = useCallback((finalTranscript: string) => {
    const clean = finalTranscript.trim();
    if (!clean || realtimeInputEditedRef.current) return;
    const base = realtimeBaseInputRef.current.trim();
    applyVoiceTranscript('realtime_mic', base ? `${base} ${clean}` : clean, realtimeAsrResultRef.current);
  }, [applyVoiceTranscript]);

  const handleRealtimeMicPress = useCallback(async () => {
    const state = composerRef.current;
    if (state.phase === 'live_dictating' || realtimeDictation.isDictating) {
      dictationStopRequestedRef.current = true;
      dispatchComposer({ type: 'dictation_stop' });
      await realtimeDictation.stopDictation();
      activeVoiceSourceRef.current = null;
      return;
    }
    await startRealtimeDictation();
  }, [realtimeDictation, startRealtimeDictation]);

  const handleInputLongPressDictation = useCallback(async () => {
    const state = composerRef.current;
    if (
      inputHoldDictationActiveRef.current
      || state.mode !== 'text'
      || state.phase === 'live_dictating'
      || realtimeDictation.isDictating
    ) return;
    inputHoldDictationActiveRef.current = true;
    const started = await startRealtimeDictation();
    if (!started) {
      inputHoldDictationActiveRef.current = false;
    }
  }, [realtimeDictation.isDictating, startRealtimeDictation]);

  const clearInputHoldDictationTimer = useCallback(() => {
    if (!inputHoldDictationTimerRef.current) return;
    clearTimeout(inputHoldDictationTimerRef.current);
    inputHoldDictationTimerRef.current = null;
  }, []);

  const handleInputPressInDictation = useCallback(() => {
    clearInputHoldDictationTimer();
    inputHoldDictationTimerRef.current = setTimeout(() => {
      inputHoldDictationTimerRef.current = null;
      void handleInputLongPressDictation();
    }, INPUT_HOLD_DICTATION_DELAY_MS);
  }, [clearInputHoldDictationTimer, handleInputLongPressDictation]);

  const handleInputPressOutDictation = useCallback(async () => {
    clearInputHoldDictationTimer();
    if (!inputHoldDictationActiveRef.current) return;
    inputHoldDictationActiveRef.current = false;
    dictationStopRequestedRef.current = true;
    const finalTranscript = String(await realtimeDictation.stopDictation() || '').trim();
    applyRealtimeFinalTranscript(finalTranscript);
    activeVoiceSourceRef.current = null;
    dispatchComposer({ type: 'dictation_end' });
  }, [applyRealtimeFinalTranscript, clearInputHoldDictationTimer, realtimeDictation]);

  const handleKeyboardSubmit = useCallback(() => {
    if (!canSend) return;
    const now = Date.now();
    if (now - lastKeyboardSubmitAtRef.current < 250) return;
    lastKeyboardSubmitAtRef.current = now;
    void handleSend();
  }, [canSend, handleSend]);

  const handleTextInputKeyPress = useCallback((event: any) => {
    const key = event?.nativeEvent?.key;
    if (key === 'Enter' || key === 'Return' || key === '\n') {
      handleKeyboardSubmit();
    }
  }, [handleKeyboardSubmit]);

  const realtimeActive = composer.phase === 'live_dictating' || realtimeDictation.isDictating;
  const realtimeDictationDisabled = shouldShowDisabledMic(composer);
  const realtimeMicLabel = realtimeActive
    ? '停止实时语音转文字'
    : realtimeDictationDisabled
      ? '语音监听已禁用'
      : '实时语音转文字';
  const realtimeMicHint = realtimeActive
    ? '点击停止语音监听并切换到非语音输入'
    : realtimeDictationDisabled
      ? '点击重新开启语音监听'
      : '点击开启语音监听并实时转文字';
  const realtimeMicIcon = realtimeDictationDisabled ? 'mic-off' : 'mic';
  const isVoiceMode = composer.mode === 'hold';
  const textComposerActive = !isVoiceMode && (textInputFocused || realtimeActive);
  const textComposerMinHeight = Math.max(
    48,
    textInputHeight + COMPOSER_TEXT_VERTICAL_CHROME,
  );
  const voiceGesture = composer.gesture;
  const voiceModeToggleLabel = isVoiceMode ? '切换到键盘输入' : '切换到语音输入';

  cancelVoiceRef.current = realtimeDictation.cancelDictation;
  voiceRealtimeActiveRef.current = realtimeDictation.isDictating
    && activeVoiceSourceRef.current === 'hold';
  const holdRecordingActive = (
    composer.phase === 'hold_starting'
    || composer.phase === 'hold_recording'
  ) && activeVoiceSourceRef.current === 'hold';
  const holdTranscribing = composer.phase === 'hold_transcribing'
    && activeVoiceSourceRef.current === 'hold';

  const cancelledRef = useRef(false);
  const startYRef = useRef(0);

  const handleHoldStart = useCallback(async (pageX: number, pageY: number) => {
    if (!canStartHold(composerRef.current) || dictationRealtimeActiveRef.current) return;
    cancelledRef.current = false;
    voiceGestureActiveRef.current = true;
    voiceCommitModeRef.current = 'send';
    activeVoiceSourceRef.current = 'hold';
    holdTranscriptRef.current = '';
    setHoldTranscript('');
    realtimeAsrResultRef.current = undefined;
    holdStartXRef.current = pageX;
    startYRef.current = pageY;
    dispatchComposer({ type: 'hold_start' });
    setCancelHint(false);
    const started = await realtimeDictation.startDictation();
    const cancelledDuringStartup = cancelledRef.current
      || !voiceGestureActiveRef.current
      || activeVoiceSourceRef.current !== 'hold';
    if (started === false) {
      voiceGestureActiveRef.current = false;
      if (!cancelledDuringStartup && composerRef.current.phase === 'hold_starting') {
        dispatchComposer({ type: 'fail', errorCode: 'hold_recording_start_failed' });
      }
      return;
    }
    if (cancelledDuringStartup) return;
    dispatchComposer({ type: 'hold_ready' });
  }, [realtimeDictation]);

  const handleHoldMove = useCallback((pageX: number, pageY: number) => {
    if (!voiceGestureActiveRef.current || cancelledRef.current) return;
    const dy = startYRef.current - pageY;
    const dx = pageX - holdStartXRef.current;
    if (dy > CANCEL_THRESHOLD || dx < -VOICE_SLIDE_THRESHOLD) {
      cancelledRef.current = true;
      voiceGestureActiveRef.current = false;
      dispatchComposer({ type: 'hold_move', gesture: 'cancel' });
      setCancelHint(false);
      activeVoiceSourceRef.current = null;
      void Promise.resolve(realtimeDictation.cancelDictation())
        .finally(() => dispatchComposer({ type: 'hold_cancel' }));
    } else if (dx > VOICE_SLIDE_THRESHOLD) {
      voiceCommitModeRef.current = 'text';
      dispatchComposer({ type: 'hold_move', gesture: 'text' });
      setCancelHint(false);
    } else {
      voiceCommitModeRef.current = 'send';
      dispatchComposer({ type: 'hold_move', gesture: 'send' });
      setCancelHint(dy > 30);
    }
  }, [realtimeDictation]);

  const handleHoldEnd = useCallback(async () => {
    setCancelHint(false);
    if (cancelledRef.current) return;
    if (!voiceGestureActiveRef.current) return;
    voiceGestureActiveRef.current = false;
    dispatchComposer({ type: 'hold_release' });
    const commitMode = voiceCommitModeRef.current;
    const finalText = String(await realtimeDictation.stopDictation() || '').trim();
    const transcript = finalText || holdTranscriptRef.current.trim();
    activeVoiceSourceRef.current = null;
    if (!transcript) {
      dispatchComposer({ type: 'fail', errorCode: 'empty_voice_transcript' });
      return;
    }
    const draft = buildVoiceDraft({
      source: 'hold_to_talk',
      rawTranscript: transcript,
      asr: realtimeAsrResultRef.current
        ? {
          provider: realtimeAsrResultRef.current.provider,
          model: realtimeAsrResultRef.current.model,
          durationMs: realtimeAsrResultRef.current.durationMs,
          confidence: realtimeAsrResultRef.current.confidence,
        }
        : undefined,
    });
    voiceDraftRef.current = draft;
    if (commitMode === 'send') {
      await handleSend(draft.normalizedText, { channel: 'voice' });
    } else {
      const previous = input.trim();
      applyVoiceTranscript(
        'hold_to_talk',
        previous ? `${previous} ${transcript}` : transcript,
        realtimeAsrResultRef.current,
      );
      setTimeout(() => textInputRef.current?.focus(), 30);
    }
    holdTranscriptRef.current = '';
    setHoldTranscript('');
    dispatchComposer({ type: 'hold_transcribed' });
  }, [applyVoiceTranscript, handleSend, input, realtimeDictation]);

  const handleHoldTerminate = useCallback(() => {
    if (!voiceGestureActiveRef.current) return;
    cancelledRef.current = true;
    voiceGestureActiveRef.current = false;
    setCancelHint(false);
    dispatchComposer({ type: 'hold_move', gesture: 'cancel' });
    activeVoiceSourceRef.current = null;
    void Promise.resolve(realtimeDictation.cancelDictation())
      .finally(() => dispatchComposer({ type: 'hold_cancel' }));
  }, [realtimeDictation]);

  const handleHoldStartEvent = useCallback((event: any) => {
    handleHoldStart(event.nativeEvent.pageX ?? 0, event.nativeEvent.pageY ?? 0);
  }, [handleHoldStart]);

  const handleHoldMoveEvent = useCallback((event: any) => {
    handleHoldMove(event.nativeEvent.pageX ?? 0, event.nativeEvent.pageY ?? 0);
  }, [handleHoldMove]);

  const handleVoiceModeToggle = useCallback(async () => {
    const state = composerRef.current;
    if (
      state.phase === 'hold_starting'
      || state.phase === 'hold_recording'
      || state.phase === 'hold_transcribing'
      || state.phase === 'submitting'
    ) return;
    if (state.phase === 'live_dictating' && !dictationRealtimeActiveRef.current) {
      return;
    }
    if (state.phase === 'live_dictating' || dictationRealtimeActiveRef.current) {
      dictationStopRequestedRef.current = true;
      await stopDictationRef.current();
      activeVoiceSourceRef.current = null;
      dispatchComposer({ type: 'dictation_stop' });
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    dispatchComposer({ type: 'toggle_mode' });
    if (state.mode === 'text') {
      setTextInputFocused(false);
      textInputRef.current?.blur();
      Keyboard.dismiss();
    } else {
      setTimeout(() => textInputRef.current?.focus(), 30);
    }
  }, []);

  React.useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'background' && nextState !== 'inactive') return;
      if (draftHydratedRef.current) {
        if (draftPersistTimerRef.current) {
          clearTimeout(draftPersistTimerRef.current);
          draftPersistTimerRef.current = null;
        }
        const snapshot = draftSnapshotRef.current;
        void persistChatDraft(
          snapshot.text,
          snapshot.images,
          Date.now(),
          draftMetadataForPhotoContext(snapshot.photoContext),
        ).catch((e) => {
          if (__DEV__) console.warn('[ChatInputBar] background draft persistence failed:', e);
        });
      }
      const phase = composerRef.current.phase;
      cancelledRef.current = true;
      voiceGestureActiveRef.current = false;
      dictationStopRequestedRef.current = true;
      activeVoiceSourceRef.current = null;
      setCancelHint(false);
      dispatchComposer({ type: 'background' });
      void (async () => {
        if (
          phase === 'live_dictating'
          || phase === 'hold_starting'
          || phase === 'hold_recording'
          || phase === 'hold_transcribing'
          || dictationRealtimeActiveRef.current
          || voiceRealtimeActiveRef.current
        ) {
          await cancelDictationRef.current();
        }
      })();
    });
    return () => subscription.remove();
  }, []);

  React.useEffect(() => () => {
    if (justSentTimerRef.current) clearTimeout(justSentTimerRef.current);
    if (inputHoldDictationTimerRef.current) clearTimeout(inputHoldDictationTimerRef.current);
  }, []);

  const focusTextInput = useCallback(() => {
    setTextInputFocused(true);
    textInputRef.current?.focus();
  }, []);

  const handleTextInputFocus = useCallback(() => {
    setTextInputFocused(true);
  }, []);

  const handleTextInputBlur = useCallback(() => {
    setTextInputFocused(false);
  }, []);

  const handleInputChange = useCallback((text: string) => {
    draftInteractionVersionRef.current += 1;
    const realtimeDictationActive =
      composerRef.current.phase === 'live_dictating'
      || dictationRealtimeActiveRef.current;
    if (realtimeDictationActive) {
      // iOS can deliver a final ASR callback after TextInput.onChangeText.
      // Invalidate first so stopping the native recognizer cannot overwrite
      // the text the user just edited.
      realtimeInputEditedRef.current = true;
      dispatchComposer({ type: 'dictation_stop' });
      void stopDictationRef.current().catch((error) => {
        if (__DEV__) {
          console.warn('[ChatInputBar] stop realtime dictation after text edit failed:', error);
        }
      });
    }
    inputChannelRef.current = 'typed';
    voiceDraftRef.current = null;
    setInput(text);
  }, []);

  const handleTextContentSizeChange = useCallback((
    event: NativeSyntheticEvent<TextInputContentSizeChangeEventData>,
  ) => {
    const measured = Number(event.nativeEvent.contentSize.height);
    if (!Number.isFinite(measured)) return;
    const nextHeight = Math.min(
      COMPOSER_TEXT_MAX_HEIGHT,
      Math.max(COMPOSER_TEXT_MIN_HEIGHT, measured),
    );
    setTextInputHeight(current => current === nextHeight ? current : nextHeight);
  }, []);

  React.useEffect(() => {
    if (!input) setTextInputHeight(COMPOSER_TEXT_MIN_HEIGHT);
  }, [input]);

  const handlePickImage = useCallback(async () => {
    setShowMenu(false);
    draftInteractionVersionRef.current += 1;
    await pickImage(pendingPhotoContextRef.current?.intent === 'diet_photo_record' ? 3 : 9);
  }, [pickImage]);
  const stageCameraPhoto = useCallback(async (mealPhoto: boolean) => {
    setShowMenu(false);
    if (
      mealPhoto
      && pendingImages.length > 0
      && pendingPhotoContextRef.current?.intent !== 'diet_photo_record'
    ) {
      Alert.alert(
        '先处理已选图片',
        '为避免误记，小巴不会把普通附件自动当成餐食照片。请先发送或移除已选图片，再开始拍照记餐。',
      );
      return [];
    }
    draftInteractionVersionRef.current += 1;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const mealSessionActive = mealPhoto
      || pendingPhotoContextRef.current?.intent === 'diet_photo_record';
    const photos = await takePhoto(mealSessionActive ? 3 : 9);
    if (!photos || photos.length === 0) return [];
    if (mealPhoto) {
      pendingPhotoContextRef.current = {
        ...MEAL_PHOTO_CONTEXT,
        capture_session_id: pendingPhotoContextRef.current?.capture_session_id
          || createMealCaptureSessionId(),
      };
      inputChannelRef.current = 'typed';
      setInput(current => current.trim() ? current : '记录这餐');
    }
    return photos;
  }, [pendingImages.length, takePhoto]);
  const handleCaptureMealPhoto = useCallback(() => {
    void stageCameraPhoto(true);
  }, [stageCameraPhoto]);
  const handleContinueCamera = useCallback(() => {
    void stageCameraPhoto(false);
  }, [stageCameraPhoto]);

  const lastCaptureMealPhotoTokenRef = useRef(captureMealPhotoToken ?? 0);
  React.useEffect(() => {
    const token = Number(captureMealPhotoToken || 0);
    if (token <= 0 || token === lastCaptureMealPhotoTokenRef.current) return;
    lastCaptureMealPhotoTokenRef.current = token;
    void stageCameraPhoto(true);
  }, [captureMealPhotoToken, stageCameraPhoto]);
  const handlePickFile = useCallback(async () => {
    setShowMenu(false);
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true });
      if (!result.canceled && result.assets[0]) {
        inputChannelRef.current = 'typed';
        setInput(`请分析文件：${result.assets[0].name}`);
      }
    } catch (e) {
      if (__DEV__) console.warn('[chat] DocumentPicker failed:', e);
    }
  }, []);

  const runMedicalExamImport = useCallback(async (asset: { uri: string; name?: string | null; mimeType?: string | null }) => {
    if (medicalImportBusy) return;
    setMedicalImportBusy(true);
    try {
      const result = await executeMedicalExamImportSkillForDocumentAsset(asset);
      onMedicalExamImportResult?.(result);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch (e: any) {
      Alert.alert('导入体检报告失败', e?.message || '请稍后再试');
    } finally {
      setMedicalImportBusy(false);
      setShowMedicalImportMenu(false);
    }
  }, [medicalImportBusy, onMedicalExamImportResult]);

  const handleImportMedicalExamFile = useCallback(async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'image/*'],
        copyToCacheDirectory: true,
      });
      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];
        await runMedicalExamImport({
          uri: asset.uri,
          name: asset.name,
          mimeType: asset.mimeType,
        });
      }
    } catch (e: any) {
      Alert.alert('选择报告失败', e?.message || '请稍后再试');
    }
  }, [runMedicalExamImport]);

  const handleImportMedicalExamPhoto = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相机权限', '请在系统设置中允许小巴使用相机。');
        return;
      }
      const picked = await ImagePicker.launchCameraAsync({
        mediaTypes: ['images'],
        quality: 0.85,
        allowsEditing: false,
      });
      if (!picked.canceled && picked.assets[0]) {
        const asset = picked.assets[0];
        await runMedicalExamImport({
          uri: asset.uri,
          name: asset.fileName || 'medical-exam-photo.jpg',
          mimeType: asset.mimeType || 'image/jpeg',
        });
      }
    } catch (e: any) {
      Alert.alert('拍摄报告失败', e?.message || '请稍后再试');
    }
  }, [runMedicalExamImport]);

  const handleImportMedicalExamLibrary = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相册权限', '请在系统设置中允许小巴访问照片。');
        return;
      }
      const picked = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.85,
        allowsEditing: false,
      });
      if (!picked.canceled && picked.assets[0]) {
        const asset = picked.assets[0];
        await runMedicalExamImport({
          uri: asset.uri,
          name: asset.fileName || 'medical-exam-image.jpg',
          mimeType: asset.mimeType || 'image/jpeg',
        });
      }
    } catch (e: any) {
      Alert.alert('选择报告图片失败', e?.message || '请稍后再试');
    }
  }, [runMedicalExamImport]);

  const toggleMenu = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setShowMenu(!showMenu);
  };
  const pendingImageLimit = pendingPhotoContextRef.current?.intent === 'diet_photo_record' ? 3 : 9;

  return (
    <>
      {/* 图片预览 */}
      {pendingImages.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.previewBar} contentContainerStyle={styles.previewContent}>
          {pendingImages.map((img, i) => (
            <View key={img.uri} style={styles.previewItem}>
              <Image source={{ uri: img.uri }} style={styles.previewImg} />
              <TouchableOpacity
                style={styles.previewRemove}
                onPress={() => {
                  draftInteractionVersionRef.current += 1;
                  if (pendingImages.length === 1) pendingPhotoContextRef.current = null;
                  void removeImage(i);
                }}
                hitSlop={6}
              >
                <Ionicons name="close-circle" size={18} color={revaSemantic.risk.fg} />
              </TouchableOpacity>
            </View>
          ))}
          {pendingImages.length < pendingImageLimit && (
            <View style={styles.previewActionGroup}>
              <TouchableOpacity
                style={styles.previewAddBtn}
                onPress={handleContinueCamera}
                accessibilityRole="button"
                accessibilityLabel="继续拍照"
              >
                <Ionicons name="camera-outline" size={20} color={C.ink2} />
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.previewAddBtn}
                onPress={handlePickImage}
                accessibilityRole="button"
                accessibilityLabel="继续从相册选择"
              >
                <Ionicons name="images-outline" size={20} color={C.ink2} />
              </TouchableOpacity>
            </View>
          )}
          <Text style={styles.previewCount}>{pendingImages.length}/{pendingImageLimit}</Text>
        </ScrollView>
      )}

      {/* 云端实时语音输入 */}
      {holdRecordingActive && (
        <View style={styles.recordingOverlay}>
          <View style={styles.wechatVoiceBubble}>
            <Text
              testID="voice-live-transcript"
              style={styles.voiceLiveTranscript}
            >
              {holdTranscript || '正在听，请说话'}
            </Text>
            <View style={styles.wechatWaveRow}>
              {VOICE_WAVE_BARS.map((bar) => (
                <View
                  key={bar}
                  style={[
                    styles.wechatWaveBar,
                    {
                      height: 5 + ((bar * 7) % 10)
                        + Math.round(realtimeDictation.audioLevel * (bar % 3 === 0 ? 16 : 9)),
                    },
                    bar > 18 && styles.wechatWaveBarLoud,
                  ]}
                />
              ))}
            </View>
          </View>
          <Text style={styles.recordingDuration}>
            {Math.floor(realtimeDictation.durationMs / 1000)}″
          </Text>
          <View style={styles.wechatReleaseDock}>
            <Text style={styles.wechatReleaseText}>
              {cancelHint || voiceGesture === 'cancel' ? '松开 取消' : voiceGesture === 'text' ? '松开 转文字' : '松开 发送'}
            </Text>
          </View>
        </View>
      )}

      {/* 识别中提示 */}
      {holdTranscribing && (
        <View style={styles.transcribingBar}>
          <ActivityIndicator size="small" color={C.green500} />
          <Text style={styles.transcribingText}>语音识别中...</Text>
        </View>
      )}

      {medicalImportBusy && (
        <View style={styles.transcribingBar}>
          <ActivityIndicator size="small" color={C.green500} />
          <Text style={styles.transcribingText}>体检报告导入中...</Text>
        </View>
      )}

      <View testID="chat-composer-surface" style={styles.composerSurface}>
        {/* 输入栏 */}
        <View style={styles.inputBar}>
          <Pressable
            testID="composer-voice-mode"
            onPress={handleVoiceModeToggle}
            style={({ pressed }) => [
              styles.voiceModeBtn,
              pressed && styles.voiceModeBtnActive,
            ]}
            hitSlop={COMPOSER_HIT_SLOP}
            accessibilityRole="button"
            accessibilityLabel={voiceModeToggleLabel}
            accessibilityHint={isVoiceMode ? '切换回键盘文字输入' : '切换到按住说话'}
          >
            {isVoiceMode ? (
              <MaterialCommunityIcons
                testID="voice-keyboard-icon"
                name="keyboard-outline"
                size={22}
                color={COMPOSER_ICON}
              />
            ) : (
              <Ionicons name="volume-medium-outline" size={22} color={COMPOSER_ICON} />
            )}
          </Pressable>

          {isVoiceMode ? (
            <View
              testID="wechat-hold-to-talk"
              style={[
                styles.inputWrap,
                styles.holdToTalk,
                voiceGesture != null && styles.holdToTalkActive,
              ]}
              onStartShouldSetResponder={() => true}
              onMoveShouldSetResponder={() => true}
              onResponderGrant={handleHoldStartEvent}
              onResponderMove={handleHoldMoveEvent}
              onResponderRelease={handleHoldEnd}
              onResponderTerminate={handleHoldTerminate}
              accessibilityRole="button"
              accessibilityLabel="按住说话"
              accessibilityHint="按住开始语音输入，左滑取消，右滑转文字"
            >
              <Text style={styles.holdToTalkText}>按住 说话</Text>
            </View>
          ) : (
            <Pressable
              testID="wechat-composer-input"
              accessible={false}
              style={({ pressed }) => [
                styles.inputWrap,
                { minHeight: textComposerMinHeight },
                textComposerActive && styles.inputWrapFocused,
                realtimeActive && styles.inputWrapDictating,
                pressed && styles.inputWrapPressed,
              ]}
              onPress={focusTextInput}
              onLongPress={handleInputLongPressDictation}
              onPressOut={handleInputPressOutDictation}
              delayLongPress={INPUT_HOLD_DICTATION_DELAY_MS}
            >
              <TextInput
                ref={textInputRef}
                style={[styles.textInput, { height: textInputHeight, pointerEvents: 'auto' }]}
                placeholder={MODE_PLACEHOLDER[agentMode]}
                placeholderTextColor={C.ink3}
                value={input}
                onChangeText={handleInputChange}
                onFocus={handleTextInputFocus}
                onBlur={handleTextInputBlur}
                onPressIn={handleInputPressInDictation}
                onPressOut={handleInputPressOutDictation}
                onContentSizeChange={handleTextContentSizeChange}
                onKeyPress={handleTextInputKeyPress}
                onSubmitEditing={handleKeyboardSubmit}
                returnKeyType="send"
                submitBehavior="submit"
                selectionColor={C.greenBright}
                multiline
                maxLength={2000}
                accessibilityLabel="消息输入框"
              />
              <TouchableOpacity
                onPress={handleRealtimeMicPress}
                style={[
                  styles.inlineMicBtn,
                  realtimeActive && styles.inlineMicBtnActive,
                  realtimeDictationDisabled && !realtimeActive && styles.inlineMicBtnDisabled,
                ]}
                hitSlop={COMPOSER_HIT_SLOP}
                activeOpacity={0.72}
                accessibilityRole="button"
                accessibilityState={{ selected: realtimeActive }}
                accessibilityLabel={realtimeMicLabel}
                accessibilityHint={realtimeMicHint}
              >
                {realtimeActive && <PulsingRing />}
                <Ionicons
                  name={realtimeMicIcon}
                  size={21}
                  color={realtimeActive ? '#FFFFFF' : realtimeDictationDisabled ? COMPOSER_ICON_MUTED : COMPOSER_ICON}
                />
              </TouchableOpacity>
            </Pressable>
          )}

          {canSend ? (
            <TouchableOpacity onPress={() => handleSend()} style={styles.sendBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="发送消息">
              <Ionicons name="arrow-up" size={20} color="#fff" />
            </TouchableOpacity>
          ) : justSent ? (
            <View style={[styles.sendBtn, { opacity: 0.4 }]}>
              <Ionicons name="checkmark" size={20} color="#fff" />
            </View>
          ) : (
            <TouchableOpacity testID="composer-plus" onPress={toggleMenu} style={styles.plusBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="附件菜单">
              <Ionicons name={showMenu ? 'close' : 'add'} size={26} color={COMPOSER_ICON} />
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* 附件菜单 */}
      <Modal visible={showMenu} transparent animationType="slide" onRequestClose={toggleMenu}>
        <Pressable style={styles.menuOverlay} onPress={toggleMenu}>
          <Pressable
            testID="attachment-menu-sheet"
            style={styles.menuSheet}
            onPress={e => e.stopPropagation()}
          >
            <View testID="attachment-menu-handle" style={styles.menuHandle} />
            <View testID="attachment-action-grid" style={styles.attachmentGrid}>
              <AttachmentGridItem icon="camera-outline" label="拍照记餐" desc="确认后写入" onPress={handleCaptureMealPhoto} />
              <AttachmentGridItem icon="image-outline" label="相册" desc="最多9张" onPress={handlePickImage} />
              <AttachmentGridItem icon="document-outline" label="文件" desc="文档/报告" onPress={handlePickFile} />
              <AttachmentGridItem
                icon="document-text-outline"
                label="导入体检报告"
                desc={medicalImportBusy ? '导入中' : '入库成卡片'}
                onPress={() => {
                  setShowMenu(false);
                  setShowMedicalImportMenu(true);
                }}
              />
            </View>
            <Text style={styles.menuSectionTitle}>模式</Text>
            <View testID="agent-mode-segmented-row" style={styles.modeSegmentedRow}>
              {AGENT_MODES.map(mode => (
                <ModeSegmentItem
                  key={mode.id}
                  icon={mode.icon}
                  label={mode.label}
                  accessibilityLabel={`${mode.label}模式`}
                  selected={agentMode === mode.id}
                  onPress={() => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    setAgentMode(mode.id);
                    setShowMenu(false);
                  }}
                />
              ))}
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={showMedicalImportMenu} transparent animationType="slide" onRequestClose={() => setShowMedicalImportMenu(false)}>
        <Pressable style={styles.menuOverlay} onPress={() => setShowMedicalImportMenu(false)}>
          <Pressable
            testID="medical-exam-import-sheet"
            style={styles.menuSheet}
            onPress={e => e.stopPropagation()}
          >
            <View testID="medical-exam-import-menu-handle" style={styles.menuHandle} />
            <View style={styles.medicalImportHeader}>
              <Text style={styles.menuLabel}>导入体检报告</Text>
              <Text style={styles.menuDesc}>写入体检记录，并在对话中生成可复核卡片</Text>
            </View>
            <MenuItem icon="document-outline" label="选择 PDF 或图片报告" desc="从文件中选择体检 PDF 或化验单图片" onPress={handleImportMedicalExamFile} />
            <MenuItem icon="camera-outline" label="拍摄体检/化验单" desc="拍照后直接 OCR 入库" onPress={handleImportMedicalExamPhoto} />
            <MenuItem icon="images-outline" label="从相册选择报告图片" desc="选择已有报告照片并入库" onPress={handleImportMedicalExamLibrary} />
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

function ModeSegmentItem({
  icon,
  label,
  accessibilityLabel,
  selected,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  accessibilityLabel: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      style={[styles.modeMenuItem, selected && styles.modeMenuItemActive]}
      onPress={onPress}
      activeOpacity={0.68}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={accessibilityLabel}
    >
      <Ionicons name={icon} size={15} color={selected ? C.green500 : C.ink2} />
      <Text style={[styles.modeMenuLabel, selected && styles.modeMenuLabelActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function AttachmentGridItem({ icon, label, desc, onPress }: { icon: any; label: string; desc: string; onPress: () => void }) {
  return (
    <TouchableOpacity
      style={styles.attachmentGridItem}
      onPress={onPress}
      activeOpacity={0.68}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <View style={styles.attachmentGridIconWrap}>
        <Ionicons name={icon} size={18} color={C.ink1} />
      </View>
      <View style={styles.attachmentGridText}>
        <Text style={styles.attachmentGridLabel} numberOfLines={1}>{label}</Text>
        <Text style={styles.attachmentGridDesc} numberOfLines={1}>{desc}</Text>
      </View>
    </TouchableOpacity>
  );
}

function MenuItem({ icon, label, desc, onPress }: { icon: any; label: string; desc: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.menuItem} onPress={onPress} activeOpacity={0.6} accessibilityRole="button" accessibilityLabel={label}>
      <View style={styles.menuIconWrap}>
        <Ionicons name={icon} size={20} color={C.ink1} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.menuLabel}>{label}</Text>
        <Text style={styles.menuDesc}>{desc}</Text>
      </View>
    </TouchableOpacity>
  );
}

// Reva 设计语言: 暖白 paper 输入栏 / surface 卡 / green500 发送 / ink 文字.
// 实时录音态沿用 Reva 的纸张、墨色与健康绿,避免脱离对话页主题.
const styles = StyleSheet.create({
  /* ── 输入栏 ── */
  composerSurface: {
    marginHorizontal: 0,
    marginTop: 0,
    marginBottom: 0,
    borderRadius: 0,
    backgroundColor: COMPOSER_BAR_BG,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  inputBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 10,
    paddingTop: 7,
    paddingBottom: 7,
    backgroundColor: COMPOSER_BAR_BG,
  },
  voiceModeBtn: {
    width: 40, height: 40, borderRadius: 20,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.lineStrong,
    backgroundColor: COMPOSER_BUTTON_BG,
    alignItems: 'center', justifyContent: 'center',
  },
  voiceModeBtnActive: {
    borderColor: C.green500,
    backgroundColor: COMPOSER_BUTTON_BG_ACTIVE,
  },
  plusBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: COMPOSER_BUTTON_BG, borderWidth: StyleSheet.hairlineWidth, borderColor: C.lineStrong,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    minHeight: 48,
    flex: 1, flexDirection: 'row', alignItems: 'center',
    backgroundColor: COMPOSER_INPUT_BG, borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.lineStrong,
    paddingLeft: 14, paddingRight: 4, paddingVertical: 3,
  },
  inputWrapPressed: {
    backgroundColor: COMPOSER_INPUT_BG_PRESSED,
    borderColor: C.lineStrong,
  },
  inputWrapFocused: {
    borderColor: C.green500,
  },
  inputWrapDictating: {
    backgroundColor: COMPOSER_INPUT_BG_ACTIVE,
    borderColor: C.green500,
  },
  holdToTalk: {
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  holdToTalkActive: {
    backgroundColor: COMPOSER_INPUT_BG_ACTIVE,
    borderColor: C.green500,
  },
  holdToTalkText: {
    flex: 1,
    textAlign: 'center',
    fontFamily: revaFonts.sans,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  textInput: {
    flex: 1, fontFamily: revaFonts.sans, fontSize: 16, maxHeight: 96, color: C.ink1,
    paddingTop: 8, paddingBottom: 8,
  },
  inlineMicBtn: {
    width: 38, height: 38, borderRadius: 19,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'transparent',
    overflow: 'hidden',
  },
  inlineMicBtnActive: {
    backgroundColor: C.green500,
    ...revaShadows.sm,
  },
  inlineMicBtnDisabled: {
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: C.green500,
    alignItems: 'center', justifyContent: 'center',
    ...revaShadows.sm,
  },

  /* ── 录音中蒙层 ── */
  recordingOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(247,247,243,0.96)',
    zIndex: 100,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  pulsingRing: {
    position: 'absolute',
    width: 36, height: 36, borderRadius: 18,
    borderWidth: 2, borderColor: 'rgba(58,210,159,0.5)',
  },
  wechatVoiceBubble: {
    width: '100%',
    maxWidth: 520,
    minHeight: 174,
    maxHeight: 320,
    borderRadius: 16,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    paddingVertical: 24,
    marginBottom: 18,
    ...revaShadows.md,
  },
  voiceLiveTranscript: {
    width: '100%',
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 20,
    lineHeight: 30,
    fontWeight: '600',
    color: C.ink1,
    textAlign: 'center',
    marginBottom: 22,
  },
  wechatWaveRow: {
    height: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  wechatWaveBar: {
    width: 3,
    borderRadius: 2,
    backgroundColor: C.greenBright,
  },
  wechatWaveBarLoud: {
    backgroundColor: C.green500,
  },
  recordingDuration: {
    fontFamily: revaFonts.mono, fontSize: 16, fontWeight: '700', color: C.ink2,
    marginBottom: 96,
  } as TextStyle,
  wechatReleaseDock: {
    position: 'absolute',
    left: -30,
    right: -30,
    bottom: 0,
    minHeight: 88,
    borderTopLeftRadius: 120,
    borderTopRightRadius: 120,
    backgroundColor: C.paper2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: 10,
  },
  wechatReleaseText: {
    fontFamily: revaFonts.sans,
    fontSize: 18,
    color: C.ink1,
    fontWeight: '800',
  } as TextStyle,

  /* ── 识别中 ── */
  transcribingBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: revaSpacing.s4, paddingVertical: 10,
    backgroundColor: C.surface,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line,
  },
  transcribingText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.green500 } as TextStyle,

  /* ── 图片预览 ── */
  previewBar: {
    maxHeight: 72,
    backgroundColor: C.surface,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line,
  },
  previewContent: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: revaSpacing.s3, paddingVertical: 6,
  },
  previewItem: { position: 'relative' },
  previewImg: { width: 52, height: 52, borderRadius: 8 },
  previewRemove: { position: 'absolute', top: -6, right: -6 },
  previewActionGroup: { flexDirection: 'row', gap: 6 },
  previewAddBtn: {
    width: 52, height: 52, borderRadius: 8,
    borderWidth: 1.5, borderColor: C.line, borderStyle: 'dashed',
    alignItems: 'center', justifyContent: 'center',
  },
  previewCount: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3, marginLeft: 4 } as TextStyle,

  /* ── 附件菜单 ── */
  menuOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'flex-end' },
  menuSheet: {
    backgroundColor: C.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingHorizontal: revaSpacing.s5, paddingBottom: 24, paddingTop: 8,
  },
  menuHandle: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: C.ink4,
    alignSelf: 'center', marginBottom: 8,
  },
  medicalImportHeader: {
    paddingHorizontal: 4,
    paddingBottom: 8,
  },
  menuSectionTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.ink3,
    marginTop: 12,
    marginBottom: 6,
    paddingHorizontal: 4,
  } as TextStyle,
  menuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line,
  },
  menuIconWrap: {
    width: 38, height: 38, borderRadius: 12, backgroundColor: C.paper,
    alignItems: 'center', justifyContent: 'center',
  },
  attachmentGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 2,
  },
  attachmentGridItem: {
    width: '48%',
    minHeight: 62,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 9,
    paddingVertical: 9,
    borderRadius: revaRadii.lg,
    backgroundColor: C.paper,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  attachmentGridIconWrap: {
    width: 30,
    height: 30,
    borderRadius: 10,
    backgroundColor: C.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attachmentGridText: {
    flex: 1,
    minWidth: 0,
  },
  attachmentGridLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink1,
    fontWeight: '800',
  } as TextStyle,
  attachmentGridDesc: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    marginTop: 1,
  } as TextStyle,
  modeSegmentedRow: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    padding: 3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
  },
  modeMenuItem: {
    flex: 1,
    minHeight: 30,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 8,
  },
  modeMenuItemActive: {
    backgroundColor: C.paper,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.normal.line,
  },
  modeMenuLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink2,
    fontWeight: '700',
  } as TextStyle,
  modeMenuLabelActive: {
    color: C.green500,
  } as TextStyle,
  menuLabel: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '500', color: C.ink1 } as TextStyle,
  menuDesc: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, marginTop: 1 } as TextStyle,
});
