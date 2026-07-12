import React, { useCallback, useRef, useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, Text,
  Modal, Pressable, ActivityIndicator, TextStyle, ScrollView,
  Alert, AppState, Keyboard,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import ReAnimated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming } from 'react-native-reanimated';
import { useMediaPicker, type PendingImage } from '../../hooks/useMediaPicker';
import { useVoiceRecording } from '../../hooks/useVoiceRecording';
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
} from '../../services/chatDraftStorage';
import {
  revaColors as C,
  revaRadii,
  revaShadows,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

const CANCEL_THRESHOLD = 80;
const VOICE_SLIDE_THRESHOLD = 88;
const COMPOSER_HIT_SLOP = { top: 6, right: 6, bottom: 6, left: 6 };
const RECORDING_OVERLAY_TOP_INSET = 64;
// 2026-07-07 founder「这个按钮不协调」:深色 #1F1F1F 输入栏贴在暖奶油页上割裂,
// 且微信真实输入栏本就是浅灰(不是深色)。收回 revaTheme 暖白语言,与页面同调。
const COMPOSER_BAR_BG = C.paper;
const COMPOSER_INPUT_BG = C.surface;
const COMPOSER_INPUT_BG_PRESSED = C.surface2;
const COMPOSER_INPUT_BG_ACTIVE = C.green50;
const COMPOSER_BUTTON_BG = C.surface2;
const COMPOSER_BUTTON_BG_ACTIVE = C.green50;
const COMPOSER_ICON = C.ink2;
const COMPOSER_ICON_MUTED = C.ink3;
const VOICE_WAVE_BARS = Array.from({ length: 28 }, (_, i) => i);

export interface ChatInputSendOptions {
  extraContext?: string;
  channel?: 'typed' | 'voice' | 'siri';
}

// 2026-07-05 founder: 删掉「日常/深思/识图」三模式段。日常=无操作(默认);
// 深思/识图的 instruction 之前经 extra_context 落到后端「入口上下文(用户正在
// 看的具体方案)」注入点(那是给 SNP/饮食 deeplink「详细聊」用的),被错误框成
// 「别重新生成方案」——与深思本意相反, 效果garbled;识图更是冗余(带图自动走
// 视觉路径)。深浅由 agent 从问题判断, 不靠藏在附件菜单里的隐藏开关。
const COMPOSER_PLACEHOLDER = '问小巴';

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

function WeChatKeyboardIcon() {
  return (
    <View testID="wechat-keyboard-icon" style={styles.wechatKeyboardIcon}>
      <View testID="wechat-keyboard-icon-frame" style={styles.wechatKeyboardIconFrame}>
        <View style={styles.wechatKeyboardGrid}>
          {Array.from({ length: 9 }, (_, index) => (
            <View key={index} style={styles.wechatKeyboardKey} />
          ))}
        </View>
        <View style={styles.wechatKeyboardBottomRow}>
          <View style={styles.wechatKeyboardSpaceKey} />
        </View>
      </View>
    </View>
  );
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
  /** 变化(>0)即请求聚焦输入框;默认打开页面不会自动递增。 */
  autoFocusToken?: number;
}

export default function ChatInputBar({ onSend, isStreaming, initialText, initialTextKey, onMedicalExamImportResult, autoFocusToken }: Props) {
  const [input, setInput] = useState(initialText ?? '');
  const [showMenu, setShowMenu] = useState(false);
  const [showMedicalImportMenu, setShowMedicalImportMenu] = useState(false);
  const [medicalImportBusy, setMedicalImportBusy] = useState(false);
  const [cancelHint, setCancelHint] = useState(false);
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
  const voiceDraftBaseRef = useRef('');
  const voiceDraftPreviewRef = useRef('');
  const realtimeBaseInputRef = useRef('');
  const inputChannelRef = useRef<'typed' | 'voice'>('typed');
  const composerRef = useRef(composer);
  const stopDictationRef = useRef<() => Promise<string>>(async () => '');
  const cancelDictationRef = useRef<() => Promise<void>>(async () => {});
  const cancelVoiceRef = useRef<() => Promise<void>>(async () => {});
  const dictationNativeActiveRef = useRef(false);
  const voiceNativeActiveRef = useRef(false);
  const draftPersistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const justSentTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  composerRef.current = composer;
  const canSend = (!!input.trim() || pendingImages.length > 0)
    && !isStreaming
    && composer.phase !== 'submitting';

  React.useEffect(() => {
    if (initialText == null) return;
    inputChannelRef.current = 'typed';
    setInput(prev => (prev === initialText ? prev : initialText));
  }, [initialText, initialTextKey]);

  React.useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const draft = await loadChatDraft();
        if (!mounted) return;
        if (initialText == null) {
          inputChannelRef.current = 'typed';
          setInput(prev => prev || draft.text);
        }
        setPendingImages(draft.images);
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
      void persistChatDraft(input, pendingImages).catch((e) => {
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

  // 明确用户动作触发的聚焦:默认进入页面不拉键盘,避免首屏被键盘占掉。
  // 延迟等 tab 过渡完成;流式时不抢焦点。
  React.useEffect(() => {
    if (!autoFocusToken) return;
    if (isStreaming) return;
    if (composerRef.current.mode === 'hold') {
      dispatchComposer({ type: 'toggle_mode' });
    }
    const t = setTimeout(() => {
      textInputRef.current?.focus();
    }, 380);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFocusToken]);

  const handleSend = useCallback(async (text?: string, sendOptions?: ChatInputSendOptions) => {
    let msg = (text || input).trim();
    if (!msg && pendingImages.length === 0) return;
    const phase = composerRef.current.phase;
    dispatchComposer({ type: 'submit' });
    try {
      if (phase === 'live_dictating' || dictationNativeActiveRef.current) {
        const finalTranscript = String(await stopDictationRef.current() || '').trim();
        if (!text && finalTranscript) {
          const base = realtimeBaseInputRef.current.trim();
          msg = base ? `${base} ${finalTranscript}` : finalTranscript;
        }
      } else if (phase === 'hold_starting' || phase === 'hold_recording') {
        await cancelVoiceRef.current();
      }
      const sendImages = pendingImages.length > 0
        ? await hydrateDraftImagesForSend(pendingImages)
        : pendingImages;
      const effectiveChannel = sendOptions?.channel ?? inputChannelRef.current;
      const outboundOptions: ChatInputSendOptions = {
        ...(sendOptions || {}),
        ...(effectiveChannel !== 'typed' ? { channel: effectiveChannel } : {}),
      };
      const sendResult = onSend(
        msg || '请分析这些图片',
        sendImages.length > 0 ? sendImages : null,
        Object.keys(outboundOptions).length > 0 ? outboundOptions : undefined,
      );
      const accepted = await Promise.resolve(sendResult);
      if (accepted === false) {
        dispatchComposer({ type: 'fail', errorCode: 'send_not_accepted' });
        Alert.alert('发送失败', '消息和图片草稿已保留，请检查网络后重试。');
        return;
      }
    } catch (e) {
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
    releaseImagesAfterSend();
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
  }, [input, pendingImages, onSend, releaseImagesAfterSend]);

  const handleRealtimeTranscript = useCallback((text: string) => {
    const clean = text.trim();
    const base = realtimeBaseInputRef.current.trim();
    inputChannelRef.current = 'voice';
    setInput(base ? `${base} ${clean}` : clean);
  }, []);

  const realtimeDictation = useRealtimeDictation({
    onTranscript: handleRealtimeTranscript,
    onEnd: () => dispatchComposer({ type: 'dictation_end' }),
    onError: (message) => dispatchComposer({ type: 'fail', errorCode: message || 'dictation_failed' }),
  });

  stopDictationRef.current = realtimeDictation.stopDictation;
  cancelDictationRef.current = realtimeDictation.cancelDictation;
  dictationNativeActiveRef.current = realtimeDictation.isDictating;

  React.useEffect(() => {
    if (
      realtimeDictation.isDictating
      && composerRef.current.mode === 'text'
      && composerRef.current.phase === 'idle'
    ) {
      dispatchComposer({ type: 'dictation_start' });
    }
  }, [realtimeDictation.isDictating]);

  const handleRealtimeMicPress = useCallback(async () => {
    if (isStreaming) return;
    const state = composerRef.current;
    if (state.phase === 'live_dictating' || realtimeDictation.isDictating) {
      dispatchComposer({ type: 'dictation_stop' });
      await realtimeDictation.stopDictation();
      return;
    }
    if (!canStartDictation(state)) return;
    realtimeBaseInputRef.current = input.trim();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    dispatchComposer({ type: 'dictation_start' });
    const started = await realtimeDictation.startDictation();
    if (started === false) {
      dispatchComposer({ type: 'fail', errorCode: realtimeDictation.error || 'dictation_start_failed' });
    }
  }, [input, isStreaming, realtimeDictation]);

  const handleSubmitComposer = useCallback(() => {
    if (!canSend) return;
    const now = Date.now();
    if (now - lastKeyboardSubmitAtRef.current < 250) return;
    lastKeyboardSubmitAtRef.current = now;
    void handleSend();
  }, [canSend, handleSend]);

  const handleTextInputKeyPress = useCallback((event: any) => {
    const key = event?.nativeEvent?.key;
    if (key === 'Enter' || key === 'Return' || key === '\n') {
      handleSubmitComposer();
    }
  }, [handleSubmitComposer]);

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
  const voiceGesture = composer.gesture;
  const voiceModeToggleLabel = isVoiceMode ? '切换到键盘输入' : '切换到语音输入';
  const shouldHideInlineMicAfterSend = justSent && !input.trim() && pendingImages.length === 0;

  const voice = useVoiceRecording({
    onTranscript: (text) => {
      const clean = text.trim();
      if (!clean) return;
      if (voiceCommitModeRef.current === 'send') {
        voiceDraftPreviewRef.current = '';
        void handleSend(clean, { channel: 'voice' });
        return;
      }
      dispatchComposer({ type: 'hold_transcribed' });
      inputChannelRef.current = 'voice';
      const hadDraftPreview = Boolean(voiceDraftPreviewRef.current);
      const draftBase = voiceDraftBaseRef.current.trim();
      setInput(prev => {
        if (hadDraftPreview) {
          return draftBase ? `${draftBase} ${clean}` : clean;
        }
        return prev ? `${prev.trim()} ${clean}` : clean;
      });
      voiceDraftPreviewRef.current = '';
      setTimeout(() => textInputRef.current?.focus(), 30);
    },
  });

  React.useEffect(() => {
    if (voiceGesture !== 'text' || !voice.isRecording) return;
    const clean = voice.partialText.trim();
    if (!clean || clean === voiceDraftPreviewRef.current) return;
    const base = voiceDraftBaseRef.current.trim();
    voiceDraftPreviewRef.current = clean;
    setInput(base ? `${base} ${clean}` : clean);
  }, [voice.partialText, voice.isRecording, voiceGesture]);

  cancelVoiceRef.current = voice.cancelRecording;
  voiceNativeActiveRef.current = voice.isRecording || voice.isTranscribing;
  const holdRecordingActive = composer.phase === 'hold_recording' || voice.isRecording;
  const holdTranscribing = composer.phase === 'hold_transcribing' || voice.isTranscribing;

  const cancelledRef = useRef(false);
  const startYRef = useRef(0);

  const handleHoldStart = useCallback(async (pageX: number, pageY: number) => {
    if (isStreaming || !canStartHold(composerRef.current) || dictationNativeActiveRef.current) return;
    cancelledRef.current = false;
    voiceGestureActiveRef.current = true;
    voiceCommitModeRef.current = 'send';
    voiceDraftBaseRef.current = input.trim();
    voiceDraftPreviewRef.current = '';
    holdStartXRef.current = pageX;
    startYRef.current = pageY;
    dispatchComposer({ type: 'hold_start' });
    setCancelHint(false);
    const started = await voice.startRecording();
    if (started === false) {
      voiceGestureActiveRef.current = false;
      if (composerRef.current.phase === 'hold_starting') {
        dispatchComposer({ type: 'fail', errorCode: 'hold_recording_start_failed' });
      }
      return;
    }
    dispatchComposer({ type: 'hold_ready' });
  }, [input, isStreaming, voice]);

  const handleHoldMove = useCallback((pageX: number, pageY: number) => {
    if (!voiceGestureActiveRef.current || cancelledRef.current) return;
    const dy = startYRef.current - pageY;
    const dx = pageX - holdStartXRef.current;
    if (dy > CANCEL_THRESHOLD || dx < -VOICE_SLIDE_THRESHOLD) {
      cancelledRef.current = true;
      voiceGestureActiveRef.current = false;
      voiceDraftPreviewRef.current = '';
      dispatchComposer({ type: 'hold_move', gesture: 'cancel' });
      setCancelHint(false);
      void Promise.resolve(voice.cancelRecording())
        .finally(() => dispatchComposer({ type: 'hold_cancel' }));
    } else if (dx > VOICE_SLIDE_THRESHOLD) {
      voiceCommitModeRef.current = 'text';
      dispatchComposer({ type: 'hold_move', gesture: 'text' });
      setCancelHint(false);
    } else {
      voiceCommitModeRef.current = 'send';
      voiceDraftPreviewRef.current = '';
      dispatchComposer({ type: 'hold_move', gesture: 'send' });
      setCancelHint(dy > 30);
    }
  }, [voice]);

  const handleHoldEnd = useCallback(() => {
    setCancelHint(false);
    if (cancelledRef.current) return;
    if (!voiceGestureActiveRef.current) return;
    voiceGestureActiveRef.current = false;
    dispatchComposer({ type: 'hold_release' });
    void Promise.resolve(voice.stopAndTranscribe())
      .finally(() => dispatchComposer({ type: 'hold_transcribed' }));
  }, [voice]);

  const handleHoldTerminate = useCallback(() => {
    if (!voiceGestureActiveRef.current) return;
    cancelledRef.current = true;
    voiceGestureActiveRef.current = false;
    setCancelHint(false);
    dispatchComposer({ type: 'hold_move', gesture: 'cancel' });
    void Promise.resolve(voice.cancelRecording())
      .finally(() => dispatchComposer({ type: 'hold_cancel' }));
  }, [voice]);

  const handleHoldStartEvent = useCallback((event: any) => {
    handleHoldStart(event.nativeEvent.pageX ?? 0, event.nativeEvent.pageY ?? 0);
  }, [handleHoldStart]);

  const handleHoldMoveEvent = useCallback((event: any) => {
    handleHoldMove(event.nativeEvent.pageX ?? 0, event.nativeEvent.pageY ?? 0);
  }, [handleHoldMove]);

  const handleVoiceModeToggle = useCallback(async () => {
    const state = composerRef.current;
    if (
      isStreaming
      || state.phase === 'hold_starting'
      || state.phase === 'hold_recording'
      || state.phase === 'hold_transcribing'
      || state.phase === 'submitting'
    ) return;
    if (state.phase === 'live_dictating' && !dictationNativeActiveRef.current) {
      return;
    }
    if (state.phase === 'live_dictating' || dictationNativeActiveRef.current) {
      await stopDictationRef.current();
      dispatchComposer({ type: 'dictation_stop' });
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    dispatchComposer({ type: 'toggle_mode' });
    if (state.mode === 'text') {
      textInputRef.current?.blur();
      Keyboard.dismiss();
    } else {
      setTimeout(() => textInputRef.current?.focus(), 30);
    }
  }, [isStreaming]);

  React.useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'background' && nextState !== 'inactive') return;
      const phase = composerRef.current.phase;
      cancelledRef.current = true;
      voiceGestureActiveRef.current = false;
      setCancelHint(false);
      dispatchComposer({ type: 'background' });
      void (async () => {
        if (phase === 'live_dictating' || dictationNativeActiveRef.current) {
          await cancelDictationRef.current();
        }
        if (
          phase === 'hold_starting'
          || phase === 'hold_recording'
          || phase === 'hold_transcribing'
          || voiceNativeActiveRef.current
        ) {
          await cancelVoiceRef.current();
        }
      })();
    });
    return () => subscription.remove();
  }, []);

  React.useEffect(() => () => {
    if (justSentTimerRef.current) clearTimeout(justSentTimerRef.current);
  }, []);

  const focusTextInput = useCallback(() => {
    if (composerRef.current.mode === 'hold') {
      dispatchComposer({ type: 'toggle_mode' });
    }
    textInputRef.current?.focus();
  }, []);

  const handleInputChange = useCallback((text: string) => {
    inputChannelRef.current = 'typed';
    setInput(text);
  }, []);

  const handlePickImage = useCallback(async () => { setShowMenu(false); await pickImage(); }, [pickImage]);
  const handleTakePhoto = useCallback(async () => { setShowMenu(false); await takePhoto(); }, [takePhoto]);
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

  return (
    <>
      {/* 图片预览 */}
      {pendingImages.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.previewBar} contentContainerStyle={styles.previewContent}>
          {pendingImages.map((img, i) => (
            <View key={img.uri} style={styles.previewItem}>
              <Image source={{ uri: img.uri }} style={styles.previewImg} />
              <TouchableOpacity style={styles.previewRemove} onPress={() => { void removeImage(i); }} hitSlop={6}>
                <Ionicons name="close-circle" size={18} color={revaSemantic.risk.fg} />
              </TouchableOpacity>
            </View>
          ))}
          {pendingImages.length < 9 && (
            <TouchableOpacity style={styles.previewAddBtn} onPress={pickImage}>
              <Ionicons name="add" size={20} color={C.ink2} />
            </TouchableOpacity>
          )}
          <Text style={styles.previewCount}>{pendingImages.length}/9</Text>
        </ScrollView>
      )}

      {/* 录音中全屏蒙层 */}
      {holdRecordingActive && (
        <View testID="wechat-recording-overlay" style={styles.recordingOverlay}>
          <View style={styles.wechatVoiceBubble}>
            {voice.partialText.trim() ? (
              <View
                style={styles.wechatVoiceTextPreview}
                accessible
                accessibilityLabel="实时语音转文字预览"
              >
                <Text style={styles.wechatVoiceTextPreviewText} numberOfLines={2}>
                  {voice.partialText.trim()}
                </Text>
              </View>
            ) : (
              <View style={styles.wechatWaveRow}>
                {VOICE_WAVE_BARS.map((bar) => (
                  <View
                    key={bar}
                    style={[
                      styles.wechatWaveBar,
                      { height: 8 + ((bar * 7) % 18) },
                      bar > 18 && styles.wechatWaveBarLoud,
                    ]}
                  />
                ))}
              </View>
            )}
            <View style={styles.wechatBubbleTail} />
          </View>
          <Text style={styles.recordingDuration}>
            {Math.floor(voice.durationMs / 1000)}″
          </Text>
          <View style={styles.wechatVoiceActions}>
            <View style={[styles.wechatVoiceActionPill, voiceGesture === 'cancel' && styles.wechatVoiceActionActive]}>
              <Text style={[styles.wechatVoiceActionText, voiceGesture === 'cancel' && styles.wechatVoiceActionTextActive]}>
                取消
              </Text>
            </View>
            <View style={[styles.wechatVoiceActionPill, voiceGesture === 'text' && styles.wechatVoiceActionActive]}>
              <Text style={[styles.wechatVoiceActionText, voiceGesture === 'text' && styles.wechatVoiceActionTextActive]}>
                滑到这里 转文字
              </Text>
            </View>
          </View>
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
            onPress={handleVoiceModeToggle}
            style={({ pressed }) => [
              styles.voiceModeBtn,
              (pressed || isVoiceMode) && styles.voiceModeBtnActive,
            ]}
            hitSlop={COMPOSER_HIT_SLOP}
            accessibilityRole="button"
            accessibilityLabel={voiceModeToggleLabel}
            accessibilityHint={isVoiceMode ? '切换回键盘文字输入' : '切换到按住说话'}
          >
            {isVoiceMode ? (
              <WeChatKeyboardIcon />
            ) : (
              <Ionicons name="volume-medium-outline" size={25} color={COMPOSER_ICON} />
            )}
          </Pressable>

          {isVoiceMode ? (
            <Pressable
              testID="wechat-hold-to-talk-surface"
              onPressIn={(event) => handleHoldStartEvent(event)}
              onMoveShouldSetResponder={() => true}
              onResponderMove={handleHoldMoveEvent}
              onTouchMove={handleHoldMoveEvent}
              onPressOut={handleHoldEnd}
              onTouchCancel={handleHoldTerminate}
              style={({ pressed }) => [
                styles.holdToTalkSurface,
                (pressed || voiceGesture != null) && styles.holdToTalkSurfaceActive,
              ]}
              accessibilityRole="button"
              accessibilityLabel="按住说话"
              accessibilityHint="按住开始语音输入，左滑取消，右滑转文字"
            >
              <Text style={styles.holdToTalkText}>按住 说话</Text>
            </Pressable>
          ) : (
            <Pressable
              testID="wechat-composer-input"
              style={({ pressed }) => [
                styles.inputWrap,
                realtimeActive && styles.inputWrapDictating,
                pressed && styles.inputWrapPressed,
              ]}
              onPress={focusTextInput}
              accessibilityRole="button"
              accessibilityLabel="消息输入框容器"
              accessibilityHint="点击输入文字，点右侧麦克风实时转文字"
            >
              <TextInput
                ref={textInputRef}
                style={[styles.textInput, { pointerEvents: 'auto' }]}
                placeholder={COMPOSER_PLACEHOLDER}
                placeholderTextColor={C.ink3}
                value={input}
                onChangeText={handleInputChange}
                onKeyPress={handleTextInputKeyPress}
                onSubmitEditing={handleSubmitComposer}
                returnKeyType="send"
                submitBehavior="submit"
                selectionColor={C.greenBright}
                multiline
                maxLength={2000}
                accessibilityLabel="消息输入框"
              />
              {!shouldHideInlineMicAfterSend && realtimeActive && (
                <View style={styles.dictationStatusPill}>
                  <Text
                    style={styles.dictationStatusText}
                    numberOfLines={1}
                    accessibilityLabel="正在听写"
                  >
                    正在听写
                  </Text>
                </View>
              )}
              {!shouldHideInlineMicAfterSend && (
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
              )}
            </Pressable>
          )}

          {!isVoiceMode && canSend ? (
            <TouchableOpacity onPress={handleSubmitComposer} style={styles.sendBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="发送消息">
              <Ionicons name="arrow-up" size={20} color="#fff" />
            </TouchableOpacity>
          ) : !isVoiceMode && justSent ? (
            <View style={[styles.sendBtn, { opacity: 0.4 }]}>
              <Ionicons name="checkmark" size={20} color="#fff" />
            </View>
          ) : (
            <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="附件菜单">
              <Ionicons name={showMenu ? 'close' : 'add'} size={28} color={COMPOSER_ICON} />
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
              <AttachmentGridItem icon="camera-outline" label="拍照" desc="食物/数据" onPress={handleTakePhoto} />
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
// 录音蒙层的红色/灰色为固定 mic 录音态语义, 不走主题 token.
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
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 10,
    paddingTop: 9,
    paddingBottom: 9,
    backgroundColor: COMPOSER_BAR_BG,
  },
  voiceModeBtn: {
    width: 42, height: 42, borderRadius: 21,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.lineStrong,
    backgroundColor: COMPOSER_BUTTON_BG,
    alignItems: 'center', justifyContent: 'center',
  },
  voiceModeBtnActive: {
    borderColor: C.green500,
    backgroundColor: COMPOSER_BUTTON_BG_ACTIVE,
  },
  wechatKeyboardIcon: {
    width: 22,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wechatKeyboardIconFrame: {
    width: 19,
    height: 15,
    borderWidth: 1.8,
    borderColor: COMPOSER_ICON,
    borderRadius: 2.5,
    paddingHorizontal: 2,
    paddingTop: 2,
    paddingBottom: 1.5,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  wechatKeyboardGrid: {
    width: 13,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: 1.5,
  },
  wechatKeyboardKey: {
    width: 2.6,
    height: 2.6,
    borderRadius: 0.5,
    backgroundColor: COMPOSER_ICON,
  },
  wechatKeyboardBottomRow: {
    width: 13,
    alignItems: 'center',
  },
  wechatKeyboardSpaceKey: {
    width: 8,
    height: 2,
    borderRadius: 1,
    backgroundColor: COMPOSER_ICON,
  },
  plusBtn: {
    width: 42, height: 42, borderRadius: 21,
    backgroundColor: COMPOSER_BUTTON_BG,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    minHeight: 48,
    flex: 1, flexDirection: 'row', alignItems: 'center',
    backgroundColor: COMPOSER_INPUT_BG, borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.line,
    paddingLeft: 16, paddingRight: 5, paddingVertical: 4,
  },
  inputWrapPressed: {
    backgroundColor: COMPOSER_INPUT_BG_PRESSED,
    borderColor: C.lineStrong,
  },
  inputWrapDictating: {
    backgroundColor: COMPOSER_INPUT_BG_ACTIVE,
    borderColor: C.greenBright,
  },
  holdToTalkSurface: {
    minHeight: 48,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COMPOSER_INPUT_BG,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 18,
  },
  holdToTalkSurfaceActive: {
    backgroundColor: C.green50,
    borderColor: C.green500,
  },
  holdToTalkText: {
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '600',
    color: C.ink1,
    letterSpacing: 0,
  },
  textInput: {
    flex: 1, fontFamily: revaFonts.sans, fontSize: 16, maxHeight: 96, color: C.ink1,
    paddingTop: 8, paddingBottom: 8,
  },
  dictationStatusPill: {
    minWidth: 62,
    minHeight: 28,
    borderRadius: 14,
    paddingHorizontal: 9,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green100,
    marginLeft: 6,
  },
  dictationStatusPillDisabled: {
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  dictationStatusText: {
    fontSize: 12,
    lineHeight: 15,
    fontWeight: '600',
    color: C.green700,
  },
  dictationStatusTextDisabled: {
    color: C.ink3,
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
    position: 'absolute', top: RECORDING_OVERLAY_TOP_INSET, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.78)',
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
    minWidth: 210,
    minHeight: 92,
    borderRadius: 20,
    backgroundColor: '#45C681',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 30,
    marginBottom: 18,
  },
  wechatVoiceTextPreview: {
    maxWidth: 280,
    minWidth: 190,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wechatVoiceTextPreviewText: {
    fontFamily: revaFonts.sans,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
    color: '#115738',
    textAlign: 'center',
  } as TextStyle,
  wechatBubbleTail: {
    position: 'absolute',
    bottom: -10,
    width: 20,
    height: 20,
    borderRadius: 4,
    backgroundColor: '#45C681',
    transform: [{ rotate: '45deg' }],
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
    backgroundColor: 'rgba(11,87,51,0.55)',
  },
  wechatWaveBarLoud: {
    backgroundColor: 'rgba(11,87,51,0.75)',
  },
  recordingDuration: {
    fontFamily: revaFonts.mono, fontSize: 20, fontWeight: '700', color: '#EDEDED',
    marginBottom: 170,
  } as TextStyle,
  wechatVoiceActions: {
    position: 'absolute',
    left: 18,
    right: 18,
    bottom: 116,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  wechatVoiceActionPill: {
    minWidth: 132,
    minHeight: 62,
    borderRadius: 31,
    backgroundColor: '#222222',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
    transform: [{ rotate: '-7deg' }],
  },
  wechatVoiceActionActive: {
    backgroundColor: '#303A34',
    borderWidth: 1,
    borderColor: C.greenBright,
  },
  wechatVoiceActionText: {
    fontFamily: revaFonts.sans,
    fontSize: 16,
    color: '#EDEDED',
    fontWeight: '700',
  } as TextStyle,
  wechatVoiceActionTextActive: {
    color: C.greenBright,
  } as TextStyle,
  wechatReleaseDock: {
    position: 'absolute',
    left: -30,
    right: -30,
    bottom: 0,
    minHeight: 88,
    borderTopLeftRadius: 120,
    borderTopRightRadius: 120,
    backgroundColor: 'rgba(240,240,240,0.82)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: 10,
  },
  wechatReleaseText: {
    fontFamily: revaFonts.sans,
    fontSize: 18,
    color: '#111111',
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
  menuLabel: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '500', color: C.ink1 } as TextStyle,
  menuDesc: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, marginTop: 1 } as TextStyle,
});
