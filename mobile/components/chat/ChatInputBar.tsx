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
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

const CANCEL_THRESHOLD = 80;

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
  onSend: (text: string, images?: PendingImage[] | null) => void;
  isStreaming: boolean;
  /** Populated once on first mount; subsequent changes are ignored. */
  initialText?: string;
  /** Reserved for callers that keep composer API aligned with chat-level voice entry. */
  conversationId?: number;
  onMedicalExamImportResult?: (result: ChatMedicalExamImportSkillResult) => void;
}

export default function ChatInputBar({ onSend, isStreaming, initialText, onMedicalExamImportResult }: Props) {
  const [input, setInput] = useState(initialText ?? '');
  const [showMenu, setShowMenu] = useState(false);
  const [showMedicalImportMenu, setShowMedicalImportMenu] = useState(false);
  const [medicalImportBusy, setMedicalImportBusy] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [cancelHint, setCancelHint] = useState(false);
  const [justSent, setJustSent] = useState(false);  // 刚发送, 按钮停留 1s 避免误切 mic
  const { pendingImages, removeImage, clearImages, pickImage, takePhoto } = useMediaPicker();
  const textInputRef = useRef<TextInput>(null);

  const handleSend = useCallback((text?: string) => {
    const msg = (text || input).trim();
    if (!msg && pendingImages.length === 0) return;
    onSend(msg || '请分析这些图片', pendingImages.length > 0 ? pendingImages : null);
    setInput('');
    clearImages();
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setJustSent(true);
    setTimeout(() => setJustSent(false), 1000);
  }, [input, pendingImages, onSend, clearImages]);

  const voice = useVoiceRecording({
    onTranscript: (text) => {
      setInput(prev => prev ? prev + ' ' + text : text);
      setVoiceMode(false);
      // 不 auto-focus TextInput — 避免触发软键盘弹出, 让用户直接点右侧发送按钮
      // (之前为了"按 return 发送"加过 focus, 但实际用户按发送按钮即可, 软键盘是多余的)
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

  const startVoiceInput = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setVoiceMode(true);
  }, []);

  const stopVoiceInput = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setVoiceMode(false);
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
        Alert.alert('需要相机权限', '请在系统设置中允许阿衡使用相机。');
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
        Alert.alert('需要相册权限', '请在系统设置中允许阿衡访问照片。');
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

  const canSend = (input.trim() || pendingImages.length > 0) && !isStreaming;

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
              {cancelHint ? '松手取消' : '上滑取消发送'}
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

      {/* 输入栏 */}
      <View style={styles.inputBar}>
        <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} accessibilityLabel="附件菜单">
          <Ionicons name={showMenu ? 'close' : 'add'} size={22} color={C.ink1} />
        </TouchableOpacity>

        {voiceMode && !canSend ? (
          /* 语音模式：按住说话按钮 */
          <Pressable
            onPressIn={(e) => handleHoldStart(e.nativeEvent.pageY)}
            onPressOut={handleHoldEnd}
            onTouchMove={(e) => handleHoldMove(e.nativeEvent.pageY)}
            style={({ pressed }) => [
              styles.holdToTalkBtn,
              pressed && styles.holdToTalkBtnActive,
              voice.isRecording && styles.holdToTalkBtnRecording,
            ]}
            accessibilityLabel="按住说话"
          >
            <Ionicons
              name="mic"
              size={18}
              color={voice.isRecording ? '#FF453A' : C.ink2}
              style={{ marginRight: 4 }}
            />
            <Text style={[
              styles.holdToTalkText,
              voice.isRecording && styles.holdToTalkTextRecording,
            ]}>
              {voice.isRecording ? '松开 结束' : '按住 说话'}
            </Text>
          </Pressable>
        ) : (
          /* 键盘模式：文本输入框 */
          <View style={styles.inputWrap}>
            <TextInput
              ref={textInputRef}
              style={styles.textInput}
              placeholder="有问题，尽管问"
              placeholderTextColor={C.ink3}
              value={input}
              onChangeText={setInput}
              onSubmitEditing={() => handleSend()}
              returnKeyType="send"
              multiline
              maxLength={2000}
              accessibilityLabel="消息输入框"
            />
          </View>
        )}

        {/* 右侧按钮：发送 / 语音切换
            刚发送 (justSent) 时保持发送按钮样式 disabled 1s, 避免立即切回 mic 导致误触再次录音 */}
        {canSend ? (
          <TouchableOpacity onPress={() => handleSend()} style={styles.sendBtn} accessibilityLabel="发送消息">
            <Ionicons name="arrow-up" size={20} color="#fff" />
          </TouchableOpacity>
        ) : justSent ? (
          <View style={[styles.sendBtn, { opacity: 0.4 }]}>
            <Ionicons name="checkmark" size={20} color="#fff" />
          </View>
        ) : (
          <TouchableOpacity
            onPress={voiceMode ? stopVoiceInput : startVoiceInput}
            style={voiceMode ? styles.keyboardBtn : styles.voiceInputBtn}
            accessibilityLabel={voiceMode ? '切回键盘输入' : '语音输入'}
            accessibilityHint={voiceMode ? '回到文字输入框' : '切换到按住说话，将语音转成文字'}
          >
            <Ionicons
              name={voiceMode ? 'keypad-outline' : 'mic-outline'}
              size={20}
              color={voiceMode ? C.ink1 : C.green500}
            />
          </TouchableOpacity>
        )}
      </View>

      {/* 附件菜单 */}
      <Modal visible={showMenu} transparent animationType="slide" onRequestClose={toggleMenu}>
        <Pressable style={styles.menuOverlay} onPress={toggleMenu}>
          <Pressable
            testID="attachment-menu-sheet"
            style={styles.menuSheet}
            onPress={e => e.stopPropagation()}
          >
            <View style={styles.menuHandle} />
            <MenuItem icon="camera-outline" label="拍照" desc="拍摄食物或健康数据" onPress={handleTakePhoto} />
            <MenuItem icon="image-outline" label="相册" desc="选择多张图片（最多9张）" onPress={handlePickImage} />
            <MenuItem icon="document-outline" label="文件" desc="上传文档或报告" onPress={handlePickFile} />
            <MenuItem
              icon="document-text-outline"
              label="导入体检报告"
              desc={medicalImportBusy ? '正在写入体检基线' : 'PDF/图片入库并生成动态卡片'}
              onPress={() => {
                setShowMenu(false);
                setShowMedicalImportMenu(true);
              }}
            />
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
            <View style={styles.menuHandle} />
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
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 6,
    paddingHorizontal: revaSpacing.s2, paddingVertical: 8,
    backgroundColor: C.paper,
  },
  plusBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: C.surface, borderWidth: 1, borderColor: C.line,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    flex: 1, flexDirection: 'row', alignItems: 'flex-end',
    backgroundColor: C.surface, borderRadius: 18,
    borderWidth: 1, borderColor: C.line,
    paddingHorizontal: 12, paddingVertical: 4,
  },
  textInput: {
    flex: 1, fontFamily: revaFonts.sans, fontSize: 15, maxHeight: 90, color: C.ink1,
    paddingTop: 6, paddingBottom: 6,
  },
  sendBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: C.green500,
    alignItems: 'center', justifyContent: 'center',
  },
  modeBtn: {
    width: 32, height: 32, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center',
  },
  voiceInputBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: C.surface,
    borderWidth: 1,
    borderColor: C.green500,
    alignItems: 'center', justifyContent: 'center',
  },
  keyboardBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: C.surface,
    borderWidth: 1,
    borderColor: C.line,
    alignItems: 'center', justifyContent: 'center',
  },

  /* ── 按住说话按钮（微信风格） ── */
  holdToTalkBtn: {
    flex: 1, height: 36, borderRadius: 20,
    backgroundColor: C.surface,
    borderWidth: 1, borderColor: C.line,
    flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center',
  },
  holdToTalkBtnActive: {
    backgroundColor: '#E8E8E8',
    transform: [{ scale: 0.98 }],
  },
  holdToTalkBtnRecording: {
    backgroundColor: '#FFF0F0',
    borderColor: '#FFD0D0',
  },
  holdToTalkText: {
    fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '500', color: C.ink2,
  } as TextStyle,
  holdToTalkTextRecording: {
    color: '#FF453A',
  } as TextStyle,

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
    paddingHorizontal: revaSpacing.s5, paddingBottom: 40, paddingTop: 8,
  },
  menuHandle: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: C.ink4,
    alignSelf: 'center', marginBottom: revaSpacing.s4,
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
  menuLabel: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '500', color: C.ink1 } as TextStyle,
  menuDesc: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, marginTop: 1 } as TextStyle,
});
