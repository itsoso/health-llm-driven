import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, Text,
  Modal, Pressable, ActivityIndicator, TextStyle, ScrollView,
  Alert, Keyboard,
} from 'react-native';
import { Image } from 'expo-image';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import ReAnimated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming } from 'react-native-reanimated';
import { useMediaPicker, type PendingImage } from '../../hooks/useMediaPicker';
import { useVoiceRecording } from '../../hooks/useVoiceRecording';
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
const COMPOSER_HIT_SLOP = { top: 6, right: 6, bottom: 6, left: 6 };

export interface ChatInputSendOptions {
  extraContext?: string;
}

// 2026-07-05 founder: 删掉「日常/深思/识图」三模式段。日常=无操作(默认);
// 深思/识图的 instruction 之前经 extra_context 落到后端「入口上下文(用户正在
// 看的具体方案)」注入点(那是给 SNP/饮食 deeplink「详细聊」用的),被错误框成
// 「别重新生成方案」——与深思本意相反, 效果garbled;识图更是冗余(带图自动走
// 视觉路径)。深浅由 agent 从问题判断, 不靠藏在附件菜单里的隐藏开关。
const COMPOSER_PLACEHOLDER = '问小巴';

// 2026-07-06 founder: 参考微信输入框重设计。旧方案在同一个面上叠「点按打字 +
// 长按录音」(靠 pointerEvents:none 把戏), 短按聚焦在真机上不可靠 —— 改成微信
// 式显式双模态: 文本态 = 纯原生 TextInput(点按 100% 可靠); 语音态 = 整条
// 「按住 说话」大按压面(按住录音/上滑取消/**轻点切回键盘**)。左侧一颗
// 模式切换钮, 模式记忆到 AsyncStorage(微信同款: 记住你上次用哪种)。
const COMPOSER_MODE_KEY = 'chat_composer_mode';
// pressOut 距 pressIn 小于该值视为「轻点」→ 切回键盘, 不算一次录音。
const VOICE_BAR_TAP_MS = 250;

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
  // 微信式双模态: 'text' = 键盘打字, 'voice' = 按住说话大按压面。
  const [composerMode, setComposerMode] = useState<'text' | 'voice'>('text');
  const composerModeRef = useRef<'text' | 'voice'>('text');
  composerModeRef.current = composerMode;
  const [cancelHint, setCancelHint] = useState(false);
  const [justSent, setJustSent] = useState(false);  // 刚发送, 按钮停留 1s 避免误切 mic
  const { pendingImages, removeImage, clearImages, pickImage, takePhoto } = useMediaPicker();
  const textInputRef = useRef<TextInput>(null);
  const lastKeyboardSubmitAtRef = useRef(0);
  const canSend = (!!input.trim() || pendingImages.length > 0) && !isStreaming;

  React.useEffect(() => {
    if (initialText == null) return;
    setInput(prev => (prev === initialText ? prev : initialText));
  }, [initialText, initialTextKey]);

  // 恢复上次的输入模式(微信同款记忆);读失败静默留在文本态 — 纯偏好, 不值得打扰。
  useEffect(() => {
    AsyncStorage.getItem(COMPOSER_MODE_KEY)
      .then(v => { if (v === 'voice') setComposerMode('voice'); })
      .catch(() => {});
  }, []);

  const switchComposerMode = useCallback((mode: 'text' | 'voice', opts?: { focus?: boolean }) => {
    setComposerMode(mode);
    AsyncStorage.setItem(COMPOSER_MODE_KEY, mode).catch(() => {});
    if (mode === 'voice') {
      Keyboard.dismiss();
    } else if (opts?.focus) {
      // 等 TextInput 挂载完成再聚焦(模式切换是条件渲染)
      setTimeout(() => textInputRef.current?.focus(), 50);
    }
  }, []);

  const toggleComposerMode = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    switchComposerMode(composerModeRef.current === 'text' ? 'voice' : 'text', { focus: true });
  }, [switchComposerMode]);

  // GPT/Gemini 式默认唤起键盘: chat.tsx 在「空对话获得焦点」时递增 token。
  // (2026-07-04 founder 拍板反转旧「不 auto-focus」设计 — 仅限空对话, 回到有
  //  历史的对话不弹, 不打断阅读。)延迟等 tab 过渡完成; 流式/语音时不抢焦点。
  React.useEffect(() => {
    if (!autoFocusToken) return;
    if (isStreaming) return;
    const t = setTimeout(() => {
      // 用户偏好语音态时不抢着弹键盘
      if (composerModeRef.current === 'voice') return;
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

  const handleKeyboardSubmit = useCallback(() => {
    if (!canSend) return;
    const now = Date.now();
    if (now - lastKeyboardSubmitAtRef.current < 250) return;
    lastKeyboardSubmitAtRef.current = now;
    handleSend();
  }, [canSend, handleSend]);

  const handleTextInputKeyPress = useCallback((event: any) => {
    const key = event?.nativeEvent?.key;
    if (key === 'Enter' || key === 'Return' || key === '\n') {
      handleKeyboardSubmit();
    }
  }, [handleKeyboardSubmit]);

  const voice = useVoiceRecording({
    onTranscript: (text) => {
      setInput(prev => prev ? prev + ' ' + text : text);
      // 转写结果落进输入框后切到文本态给用户过目/编辑(发送键此时可见),
      // 但不 auto-focus — 避免软键盘弹出打断, 用户直接点发送即可。
      setComposerMode('text');
    },
  });

  const cancelledRef = useRef(false);
  const startYRef = useRef(0);

  const handleHoldStart = useCallback((pageY: number) => {
    cancelledRef.current = false;
    startYRef.current = pageY;
    setCancelHint(false);
    voice.startRecording();
  }, [voice]);

  const handleHoldMove = useCallback((pageY: number) => {
    if (!voice.isRecording || cancelledRef.current) return;
    const dy = startYRef.current - pageY;
    if (dy > CANCEL_THRESHOLD) {
      cancelledRef.current = true;
      setCancelHint(false);
      voice.cancelRecording();
    } else {
      setCancelHint(dy > 30);
    }
  }, [voice]);

  const handleHoldEnd = useCallback(() => {
    setCancelHint(false);
    if (cancelledRef.current) return;
    voice.stopAndTranscribe();
  }, [voice]);

  // ── 语音态「按住 说话」大按压面 ──
  // 按下即录(专用面, 无需长按延迟); 松手: <250ms 视为轻点 → 取消录音并切回
  // 键盘聚焦(founder: 「长按语音, 短按要支持文本」), 否则正常转文字。
  const voiceBarPressInAtRef = useRef(0);

  const handleVoiceBarPressIn = useCallback((pageY: number) => {
    if (isStreaming) return;
    voiceBarPressInAtRef.current = Date.now();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    handleHoldStart(pageY);
  }, [handleHoldStart, isStreaming]);

  const handleVoiceBarPressOut = useCallback(() => {
    if (!voiceBarPressInAtRef.current) return;
    const heldMs = Date.now() - voiceBarPressInAtRef.current;
    voiceBarPressInAtRef.current = 0;
    if (cancelledRef.current) { setCancelHint(false); return; } // 上滑取消已处理
    if (heldMs < VOICE_BAR_TAP_MS) {
      cancelledRef.current = true;
      setCancelHint(false);
      voice.cancelRecording();
      switchComposerMode('text', { focus: true });
      return;
    }
    handleHoldEnd();
  }, [handleHoldEnd, switchComposerMode, voice]);

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
          <View style={styles.recordingCenter}>
            {cancelHint ? (
              <View style={styles.cancelCircle}>
                <Ionicons name="close" size={36} color="#fff" />
              </View>
            ) : (
              <View style={styles.micCircle}>
                <PulsingRing />
                <Ionicons name="mic" size={36} color="#fff" />
              </View>
            )}
            <Text style={styles.recordingDuration}>
              {Math.floor(voice.durationMs / 1000)}″
            </Text>
            {!cancelHint && !!voice.partialText && (
              <Text style={styles.recordingPartial} numberOfLines={2}>
                {voice.partialText}
              </Text>
            )}
            <Text style={[styles.recordingHint, cancelHint && styles.recordingHintCancel]}>
              {cancelHint ? '松手取消' : '松手转文字，上滑取消'}
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
          {/* 左:语音/键盘模式切换(微信位) */}
          <TouchableOpacity
            onPress={toggleComposerMode}
            style={styles.modeBtn}
            hitSlop={COMPOSER_HIT_SLOP}
            accessibilityLabel={composerMode === 'text' ? '切换语音输入' : '切换键盘输入'}
          >
            {composerMode === 'text' ? (
              <Ionicons name="mic-outline" size={23} color={C.ink1} />
            ) : (
              <MaterialCommunityIcons name="keyboard-outline" size={23} color={C.ink1} />
            )}
          </TouchableOpacity>

          {composerMode === 'voice' ? (
            /* 语音态:整条「按住 说话」大按压面 — 按住录音, 上滑取消, 轻点切回键盘 */
            <Pressable
              testID="composer-voice-bar"
              style={({ pressed }) => [styles.voiceBar, pressed && styles.voiceBarPressed]}
              onPressIn={(e) => handleVoiceBarPressIn(e.nativeEvent.pageY)}
              onPressOut={handleVoiceBarPressOut}
              onTouchMove={(e) => {
                if (voice.isRecording) handleHoldMove(e.nativeEvent.pageY);
              }}
              accessibilityRole="button"
              accessibilityLabel="按住说话"
              accessibilityHint="按住录音松手转文字，上滑取消，轻点切回键盘输入"
            >
              <Text style={styles.voiceBarText}>按住 说话</Text>
            </Pressable>
          ) : (
            /* 文本态:纯原生 TextInput — 点按聚焦 100% 可靠, 不再叠长按手势
               (旧 pointerEvents:none 把戏在真机上短按不可靠, 已废) */
            <View testID="composer-input-wrap" style={styles.inputWrap}>
              <TextInput
                ref={textInputRef}
                style={styles.textInput}
                placeholder={COMPOSER_PLACEHOLDER}
                placeholderTextColor={C.ink3}
                value={input}
                onChangeText={setInput}
                onKeyPress={handleTextInputKeyPress}
                onSubmitEditing={handleKeyboardSubmit}
                returnKeyType="send"
                submitBehavior="submit"
                multiline
                maxLength={2000}
                accessibilityLabel="消息输入框"
              />
            </View>
          )}

          {/* 右:有内容 → 发送(微信「发送」位);刚发完停留 1s 对勾;否则附件 + */}
          {canSend ? (
            <TouchableOpacity onPress={() => handleSend()} style={styles.sendBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="发送消息">
              <Ionicons name="arrow-up" size={20} color="#fff" />
            </TouchableOpacity>
          ) : justSent ? (
            <View style={[styles.sendBtn, { opacity: 0.4 }]}>
              <Ionicons name="checkmark" size={20} color="#fff" />
            </View>
          ) : (
            <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="附件菜单">
              <Ionicons name={showMenu ? 'close' : 'add'} size={22} color={C.ink1} />
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
    marginHorizontal: revaSpacing.s3,
    marginTop: 3,
    marginBottom: 2,
    borderRadius: 22,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 5,
    paddingHorizontal: 7,
    paddingTop: 6,
    paddingBottom: 6,
    backgroundColor: 'transparent',
  },
  plusBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: C.paper2, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    // 2026-07-05 founder: 拇指工学对齐 GPT(场高 ~48-52pt; 旧 32 低于 HIG 44pt)
    minHeight: 48,
    flex: 1, flexDirection: 'row', alignItems: 'flex-end',
    backgroundColor: C.paper, borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.lineStrong,
    paddingHorizontal: 14, paddingVertical: 5,
  },
  modeBtn: {
    width: 40, height: 40, borderRadius: 20,
    alignItems: 'center', justifyContent: 'center',
  },
  voiceBar: {
    minHeight: 48,
    flex: 1, alignItems: 'center', justifyContent: 'center',
    backgroundColor: C.paper, borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.lineStrong,
  },
  voiceBarPressed: {
    backgroundColor: C.paper2,
    borderColor: C.green100,
  },
  voiceBarText: {
    fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600',
    color: C.ink1, letterSpacing: 1,
  } as TextStyle,
  textInput: {
    flex: 1, fontFamily: revaFonts.sans, fontSize: 16, maxHeight: 96, color: C.ink1,
    paddingTop: 8, paddingBottom: 8,
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
    backgroundColor: 'rgba(0,0,0,0.5)',
    zIndex: 100,
    alignItems: 'center', justifyContent: 'center',
  },
  recordingCenter: {
    alignItems: 'center',
  },
  micCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: '#FF453A',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 16,
  },
  cancelCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: '#999',
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 16,
  },
  pulsingRing: {
    position: 'absolute',
    width: 80, height: 80, borderRadius: 40,
    borderWidth: 3, borderColor: 'rgba(255,69,58,0.4)',
  },
  recordingDuration: {
    fontFamily: revaFonts.mono, fontSize: 28, fontWeight: '700', color: '#fff',
    marginBottom: 8,
  } as TextStyle,
  recordingPartial: {
    fontFamily: revaFonts.sans, fontSize: 16, color: '#fff',
    textAlign: 'center', maxWidth: 280, marginBottom: 8,
  } as TextStyle,
  recordingHint: {
    fontFamily: revaFonts.sans, fontSize: 14, color: 'rgba(255,255,255,0.7)',
  } as TextStyle,
  recordingHintCancel: {
    color: '#FF453A', fontWeight: '600',
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
