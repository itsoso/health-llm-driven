import React, { useCallback, useRef, useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, Text,
  Modal, Pressable, ActivityIndicator, TextStyle, ScrollView,
  Alert, Keyboard,
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
  executeMedicalExamImportSkillForDocumentAsset,
  type ChatMedicalExamImportSkillResult,
} from '../../services/chatMedicalExamImportSkill';
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
const WECHAT_BAR_BG = '#1F1F1F';
const WECHAT_INPUT_BG = '#2B2B2B';
const WECHAT_INPUT_BG_ACTIVE = '#303631';
const WECHAT_ICON = '#D7D7D7';
const VOICE_WAVE_BARS = Array.from({ length: 28 }, (_, i) => i);

export interface ChatInputSendOptions {
  extraContext?: string;
}

// 2026-07-05 founder: 删掉「日常/深思/识图」三模式段。日常=无操作(默认);
// 深思/识图的 instruction 之前经 extra_context 落到后端「入口上下文(用户正在
// 看的具体方案)」注入点(那是给 SNP/饮食 deeplink「详细聊」用的),被错误框成
// 「别重新生成方案」——与深思本意相反, 效果garbled;识图更是冗余(带图自动走
// 视觉路径)。深浅由 agent 从问题判断, 不靠藏在附件菜单里的隐藏开关。
const COMPOSER_PLACEHOLDER = '问小巴';

// 2026-07-06 founder: 完全按微信输入栏复刻。左侧喇叭先切到「按住说话」,
// 语音模式左侧变键盘;文本模式框内右侧麦克风负责实时听写。
type ComposerInputMode = 'text' | 'voice';

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
  onSend: (text: string, images?: PendingImage[] | null, options?: ChatInputSendOptions) => void;
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
}

export default function ChatInputBar({ onSend, isStreaming, initialText, initialTextKey, onMedicalExamImportResult, autoFocusToken }: Props) {
  const [input, setInput] = useState(initialText ?? '');
  const [showMenu, setShowMenu] = useState(false);
  const [showMedicalImportMenu, setShowMedicalImportMenu] = useState(false);
  const [medicalImportBusy, setMedicalImportBusy] = useState(false);
  const [cancelHint, setCancelHint] = useState(false);
  const [inputMode, setInputMode] = useState<ComposerInputMode>('text');
  const [voiceGesture, setVoiceGesture] = useState<'send' | 'text' | 'cancel' | null>(null);
  const [justSent, setJustSent] = useState(false);  // 刚发送, 按钮停留 1s 避免误切 mic
  const { pendingImages, removeImage, clearImages, pickImage, takePhoto } = useMediaPicker();
  const textInputRef = useRef<TextInput>(null);
  const lastKeyboardSubmitAtRef = useRef(0);
  const holdStartXRef = useRef(0);
  const voiceGestureActiveRef = useRef(false);
  const voiceCommitModeRef = useRef<'send' | 'text'>('send');
  const realtimeBaseInputRef = useRef('');
  const canSend = (!!input.trim() || pendingImages.length > 0) && !isStreaming;

  React.useEffect(() => {
    if (initialText == null) return;
    setInputMode('text');
    setInput(prev => (prev === initialText ? prev : initialText));
  }, [initialText, initialTextKey]);

  // GPT/Gemini 式默认唤起键盘: chat.tsx 在「空对话获得焦点」时递增 token。
  // (2026-07-04 founder 拍板反转旧「不 auto-focus」设计 — 仅限空对话, 回到有
  //  历史的对话不弹, 不打断阅读。)延迟等 tab 过渡完成; 流式时不抢焦点。
  React.useEffect(() => {
    if (!autoFocusToken) return;
    if (isStreaming) return;
    setInputMode('text');
    const t = setTimeout(() => {
      textInputRef.current?.focus();
    }, 380);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFocusToken]);

  const handleSend = useCallback((text?: string) => {
    const msg = (text || input).trim();
    if (!msg && pendingImages.length === 0) return;
    onSend(
      msg || '请分析这些图片',
      pendingImages.length > 0 ? pendingImages : null,
    );
    setInput('');
    clearImages();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setJustSent(true);
    setTimeout(() => setJustSent(false), 1000);
  }, [input, pendingImages, onSend, clearImages]);

  const handleRealtimeTranscript = useCallback((text: string) => {
    const clean = text.trim();
    const base = realtimeBaseInputRef.current.trim();
    setInput(base ? `${base} ${clean}` : clean);
  }, []);

  const realtimeDictation = useRealtimeDictation({
    onTranscript: handleRealtimeTranscript,
  });

  const handleRealtimeMicPress = useCallback(() => {
    if (isStreaming) return;
    if (realtimeDictation.isDictating) {
      void realtimeDictation.stopDictation();
      return;
    }
    realtimeBaseInputRef.current = input.trim();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    void realtimeDictation.startDictation();
  }, [input, isStreaming, realtimeDictation]);

  const handleKeyboardSubmit = useCallback(() => {
    if (!canSend) return;
    const now = Date.now();
    if (now - lastKeyboardSubmitAtRef.current < 250) return;
    lastKeyboardSubmitAtRef.current = now;
    if (realtimeDictation.isDictating) {
      void realtimeDictation.stopDictation();
    }
    handleSend();
  }, [canSend, handleSend, realtimeDictation]);

  const handleTextInputKeyPress = useCallback((event: any) => {
    const key = event?.nativeEvent?.key;
    if (key === 'Enter' || key === 'Return' || key === '\n') {
      handleKeyboardSubmit();
    }
  }, [handleKeyboardSubmit]);

  const voice = useVoiceRecording({
    onTranscript: (text) => {
      const clean = text.trim();
      if (!clean) return;
      if (!isStreaming && voiceCommitModeRef.current === 'send') {
        handleSend(clean);
        return;
      }
      setInputMode('text');
      setInput(prev => prev ? `${prev.trim()} ${clean}` : clean);
      setTimeout(() => textInputRef.current?.focus(), 30);
    },
  });

  const cancelledRef = useRef(false);
  const startYRef = useRef(0);

  const handleHoldStart = useCallback((pageX: number, pageY: number) => {
    if (realtimeDictation.isDictating) {
      void realtimeDictation.stopDictation();
    }
    cancelledRef.current = false;
    voiceGestureActiveRef.current = true;
    voiceCommitModeRef.current = 'send';
    holdStartXRef.current = pageX;
    startYRef.current = pageY;
    setVoiceGesture('send');
    setCancelHint(false);
    voice.startRecording();
  }, [realtimeDictation, voice]);

  const handleHoldMove = useCallback((pageX: number, pageY: number) => {
    if (!voiceGestureActiveRef.current || cancelledRef.current) return;
    const dy = startYRef.current - pageY;
    const dx = pageX - holdStartXRef.current;
    if (dy > CANCEL_THRESHOLD || dx < -VOICE_SLIDE_THRESHOLD) {
      cancelledRef.current = true;
      voiceGestureActiveRef.current = false;
      setVoiceGesture('cancel');
      setCancelHint(false);
      void voice.cancelRecording();
    } else if (dx > VOICE_SLIDE_THRESHOLD) {
      voiceCommitModeRef.current = 'text';
      setVoiceGesture('text');
      setCancelHint(false);
    } else {
      voiceCommitModeRef.current = 'send';
      setVoiceGesture('send');
      setCancelHint(dy > 30);
    }
  }, [voice]);

  const handleHoldEnd = useCallback(() => {
    setCancelHint(false);
    setVoiceGesture(null);
    if (cancelledRef.current) return;
    if (!voiceGestureActiveRef.current) return;
    voiceGestureActiveRef.current = false;
    void voice.stopAndTranscribe();
  }, [voice]);

  const switchToVoiceMode = useCallback(() => {
    if (realtimeDictation.isDictating) {
      void realtimeDictation.stopDictation();
    }
    textInputRef.current?.blur();
    Keyboard.dismiss();
    setInputMode('voice');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  }, [realtimeDictation]);

  const switchToTextMode = useCallback(() => {
    setInputMode('text');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setTimeout(() => textInputRef.current?.focus(), 30);
  }, []);

  const focusTextInput = useCallback(() => {
    setInputMode('text');
    textInputRef.current?.focus();
  }, []);

  const handlePickImage = useCallback(async () => { setShowMenu(false); await pickImage(); }, [pickImage]);
  const handleTakePhoto = useCallback(async () => { setShowMenu(false); await takePhoto(); }, [takePhoto]);
  const handlePickFile = useCallback(async () => {
    setShowMenu(false);
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true });
      if (!result.canceled && result.assets[0]) setInput(`请分析文件：${result.assets[0].name}`);
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
              <TouchableOpacity style={styles.previewRemove} onPress={() => removeImage(i)} hitSlop={6}>
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
      {voice.isRecording && (
        <View style={styles.recordingOverlay}>
          <View style={styles.wechatVoiceBubble}>
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
      {voice.isTranscribing && (
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
            onPress={inputMode === 'text' ? switchToVoiceMode : switchToTextMode}
            style={({ pressed }) => [
              styles.voiceModeBtn,
              pressed && styles.voiceModeBtnPressed,
            ]}
            hitSlop={COMPOSER_HIT_SLOP}
            accessibilityRole="button"
            accessibilityLabel={inputMode === 'text' ? '切换到按住说话' : '切换到键盘输入'}
            accessibilityHint={inputMode === 'text' ? '点击切换为微信式按住说话' : '点击回到文字输入'}
          >
            <Ionicons name={inputMode === 'text' ? 'volume-medium-outline' : 'keypad-outline'} size={25} color={WECHAT_ICON} />
          </Pressable>

          {inputMode === 'voice' ? (
            <Pressable
              testID="wechat-hold-to-talk-surface"
              onPressIn={(e) => handleHoldStart(e.nativeEvent.pageX, e.nativeEvent.pageY)}
              onTouchMove={(e) => handleHoldMove(e.nativeEvent.pageX, e.nativeEvent.pageY)}
              onPressOut={handleHoldEnd}
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
                realtimeDictation.isDictating && styles.inputWrapDictating,
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
                placeholderTextColor="#7F7F7F"
                value={input}
                onChangeText={setInput}
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
                style={[styles.inlineMicBtn, realtimeDictation.isDictating && styles.inlineMicBtnActive]}
                hitSlop={COMPOSER_HIT_SLOP}
                activeOpacity={0.72}
                accessibilityRole="button"
                accessibilityState={{ selected: realtimeDictation.isDictating }}
                accessibilityLabel={realtimeDictation.isDictating ? '停止实时语音转文字' : '实时语音转文字'}
              >
                {realtimeDictation.isDictating && <PulsingRing />}
                <Ionicons name="mic" size={21} color={realtimeDictation.isDictating ? '#FFFFFF' : WECHAT_ICON} />
              </TouchableOpacity>
            </Pressable>
          )}

          {inputMode === 'text' && canSend ? (
            <TouchableOpacity onPress={() => handleSend()} style={styles.sendBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="发送消息">
              <Ionicons name="arrow-up" size={20} color="#fff" />
            </TouchableOpacity>
          ) : inputMode === 'text' && justSent ? (
            <View style={[styles.sendBtn, { opacity: 0.4 }]}>
              <Ionicons name="checkmark" size={20} color="#fff" />
            </View>
          ) : (
            <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="附件菜单">
              <Ionicons name={showMenu ? 'close' : 'add'} size={28} color={WECHAT_ICON} />
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
    backgroundColor: WECHAT_BAR_BG,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#2A2A2A',
  },
  inputBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 10,
    paddingTop: 9,
    paddingBottom: 9,
    backgroundColor: WECHAT_BAR_BG,
  },
  voiceModeBtn: {
    width: 42, height: 42, borderRadius: 21,
    borderWidth: 2, borderColor: WECHAT_ICON,
    backgroundColor: '#171717',
    alignItems: 'center', justifyContent: 'center',
  },
  voiceModeBtnPressed: {
    backgroundColor: '#242424',
    borderColor: '#EFEFEF',
  },
  plusBtn: {
    width: 42, height: 42, borderRadius: 21,
    backgroundColor: '#171717', borderWidth: 2, borderColor: WECHAT_ICON,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    minHeight: 48,
    flex: 1, flexDirection: 'row', alignItems: 'center',
    backgroundColor: WECHAT_INPUT_BG, borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth, borderColor: '#343434',
    paddingLeft: 16, paddingRight: 5, paddingVertical: 4,
  },
  inputWrapPressed: {
    backgroundColor: '#303030',
    borderColor: '#3B3B3B',
  },
  inputWrapDictating: {
    backgroundColor: WECHAT_INPUT_BG_ACTIVE,
    borderColor: C.greenBright,
  },
  holdToTalkSurface: {
    minHeight: 48,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: WECHAT_INPUT_BG,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#343434',
    paddingHorizontal: 18,
  },
  holdToTalkSurfaceActive: {
    backgroundColor: '#333333',
    borderColor: '#3F3F3F',
  },
  holdToTalkText: {
    fontFamily: revaFonts.sans,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '700',
    color: '#F2F2F2',
    letterSpacing: 0,
  },
  textInput: {
    flex: 1, fontFamily: revaFonts.sans, fontSize: 16, maxHeight: 96, color: '#F5F5F5',
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
  sendBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: C.green500,
    alignItems: 'center', justifyContent: 'center',
    ...revaShadows.sm,
  },

  /* ── 录音中蒙层 ── */
  recordingOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
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
