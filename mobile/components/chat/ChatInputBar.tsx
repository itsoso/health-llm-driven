import React, { useCallback, useRef, useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, Text,
  Modal, Pressable, ActivityIndicator, TextStyle, ScrollView,
  Alert,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
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

type ChatAgentMode = 'daily' | 'deep' | 'vision';

export interface ChatInputSendOptions {
  extraContext?: string;
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
  daily: '问小巴，或按住说话',
  deep: '让小巴深思一个计划',
  vision: '拍照/报告后问小巴',
};

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
  const [agentMode, setAgentMode] = useState<ChatAgentMode>('daily');
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

  // GPT/Gemini 式默认唤起键盘: chat.tsx 在「空对话获得焦点」时递增 token。
  // (2026-07-04 founder 拍板反转旧「不 auto-focus」设计 — 仅限空对话, 回到有
  //  历史的对话不弹, 不打断阅读。)延迟等 tab 过渡完成; 流式/语音时不抢焦点。
  React.useEffect(() => {
    if (!autoFocusToken) return;
    if (isStreaming) return;
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
      buildAgentModeOptions(agentMode),
    );
    setInput('');
    clearImages();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setJustSent(true);
    setTimeout(() => setJustSent(false), 1000);
  }, [agentMode, input, pendingImages, onSend, clearImages]);

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
      // 不 auto-focus TextInput — 避免触发软键盘弹出, 让用户直接点右侧发送按钮
      // (之前为了"按 return 发送"加过 focus, 但实际用户按发送按钮即可, 软键盘是多余的)
    },
  });

  const cancelledRef = useRef(false);
  const startYRef = useRef(0);
  const inputHoldActiveRef = useRef(false);

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

  const focusTextInput = useCallback(() => {
    textInputRef.current?.focus();
  }, []);

  const handleInputLongPress = useCallback((pageY: number) => {
    if (canSend || isStreaming) return;
    inputHoldActiveRef.current = true;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    handleHoldStart(pageY);
  }, [canSend, handleHoldStart, isStreaming]);

  const handleInputPressOut = useCallback(() => {
    if (!inputHoldActiveRef.current) return;
    inputHoldActiveRef.current = false;
    handleHoldEnd();
  }, [handleHoldEnd]);

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
          <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="附件菜单">
            <Ionicons name={showMenu ? 'close' : 'add'} size={22} color={C.ink1} />
          </TouchableOpacity>

          {/* 文本输入框 — 语音走「长按输入框」(placeholder 已提示「或按住说话」),
              不再有右侧独立麦克风按钮(founder 2026-07-05: Claude 式极简, 去冗余)。 */}
          <Pressable
            style={({ pressed }) => [
              styles.inputWrap,
              pressed && styles.inputWrapPressed,
            ]}
            onPress={focusTextInput}
            onLongPress={(e) => handleInputLongPress(e.nativeEvent.pageY)}
            onPressOut={handleInputPressOut}
            onTouchMove={(e) => {
              if (inputHoldActiveRef.current) handleHoldMove(e.nativeEvent.pageY);
            }}
            delayLongPress={260}
            accessibilityRole="button"
            accessibilityLabel="消息输入框，长按语音输入"
            accessibilityHint="点击输入文字，长按录音并转成文字"
          >
            <TextInput
              ref={textInputRef}
              style={styles.textInput}
              placeholder={MODE_PLACEHOLDER[agentMode]}
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
          </Pressable>

          {/* 右侧发送按钮 — 只在有内容时出现;刚发送 (justSent) 停留 1s 显示对勾。
              空态不占位, 输入框自动占满(Claude 式:不放常驻麦克风冗余按钮)。 */}
          {canSend ? (
            <TouchableOpacity onPress={() => handleSend()} style={styles.sendBtn} hitSlop={COMPOSER_HIT_SLOP} accessibilityLabel="发送消息">
              <Ionicons name="arrow-up" size={20} color="#fff" />
            </TouchableOpacity>
          ) : justSent ? (
            <View style={[styles.sendBtn, { opacity: 0.4 }]}>
              <Ionicons name="checkmark" size={20} color="#fff" />
            </View>
          ) : null}
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
  inputWrapPressed: {
    backgroundColor: C.paper2,
    borderColor: C.green100,
  },
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
