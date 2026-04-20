import React, { useCallback, useRef, useState } from 'react';
import {
  View, TextInput, TouchableOpacity, StyleSheet, Image, Text,
  Animated, Modal, Pressable, ActivityIndicator, GestureResponderEvent, TextStyle,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import ReAnimated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming } from 'react-native-reanimated';
import { useMediaPicker } from '@/hooks/useMediaPicker';
import { useVoiceRecording } from '@/hooks/useVoiceRecording';
import { colors, spacing, radii } from '@/constants/theme';

function PulsingDot() {
  const opacity = useSharedValue(1);
  React.useEffect(() => { opacity.value = withRepeat(withTiming(0.3, { duration: 600 }), -1, true); }, [opacity]);
  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return <ReAnimated.View style={[styles.recDot, animStyle]} />;
}

interface Props {
  onSend: (text: string, image?: { uri: string; base64?: string; type?: string } | null) => void;
  isStreaming: boolean;
}

export default function ChatInputBar({ onSend, isStreaming }: Props) {
  const [input, setInput] = useState('');
  const [showMenu, setShowMenu] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const cancelYRef = useRef<number | null>(null);
  const { pendingImage, setPendingImage, pickImage, takePhoto } = useMediaPicker();

  const sendMessageRef = useRef<typeof handleSend>(null!);
  const handleSend = useCallback((text?: string) => {
    const msg = (text || input).trim();
    if (!msg && !pendingImage) return;
    onSend(msg || '请分析这张图片', pendingImage);
    setInput('');
    setPendingImage(null);
  }, [input, pendingImage, onSend]);
  sendMessageRef.current = handleSend;

  const voice = useVoiceRecording({
    onTranscript: (text) => { onSend(text, null); },
  });

  const handleVoicePressIn = useCallback((e: GestureResponderEvent) => {
    cancelYRef.current = e.nativeEvent.pageY;
    voice.startRecording();
  }, [voice]);

  const handleVoicePressOut = useCallback((e: GestureResponderEvent) => {
    const startY = cancelYRef.current;
    const endY = e.nativeEvent.pageY;
    if (startY != null && startY - endY > 60) voice.cancelRecording();
    else voice.stopAndTranscribe();
    cancelYRef.current = null;
  }, [voice]);

  const handlePickImage = useCallback(async () => { setShowMenu(false); await pickImage(); }, [pickImage]);
  const handleTakePhoto = useCallback(async () => { setShowMenu(false); await takePhoto(); }, [takePhoto]);
  const handlePickFile = useCallback(async () => {
    setShowMenu(false);
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true });
      if (!result.canceled && result.assets[0]) setInput(`请分析文件：${result.assets[0].name}`);
    } catch { /* DocumentPicker not available */ }
  }, []);

  const toggleMenu = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setShowMenu(!showMenu);
  };

  const canSend = (input.trim() || pendingImage) && !isStreaming;

  return (
    <>
      {pendingImage && (
        <View style={styles.previewBar}>
          <Image source={{ uri: pendingImage.uri }} style={styles.previewImg} />
          <Text style={styles.previewText}>图片已选择</Text>
          <TouchableOpacity onPress={() => setPendingImage(null)} accessibilityLabel="取消选择图片">
            <Ionicons name="close-circle" size={20} color={colors.red} />
          </TouchableOpacity>
        </View>
      )}

      {voice.isRecording && (
        <View style={styles.recordBar}>
          <PulsingDot />
          <Text style={styles.recText}>{Math.floor(voice.durationMs / 1000)}s · 松手发送，上滑取消</Text>
        </View>
      )}
      {voice.isTranscribing && (
        <View style={styles.recordBar}>
          <ActivityIndicator size="small" color={colors.brand} />
          <Text style={[styles.recText, { color: colors.brand }]}>识别中...</Text>
        </View>
      )}

      <View style={styles.inputBar}>
        <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} accessibilityLabel="附件菜单">
          <Ionicons name={showMenu ? 'close' : 'add'} size={22} color={colors.labelPrimary} />
        </TouchableOpacity>
        <View style={styles.inputWrap}>
          <TextInput
            style={styles.textInput}
            placeholder="有问题，尽管问"
            placeholderTextColor={colors.labelTertiary}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => handleSend()}
            returnKeyType="send"
            multiline
            maxLength={2000}
            accessibilityLabel="消息输入框"
          />
          <View style={styles.inputActions}>
            {canSend ? (
              <TouchableOpacity onPress={() => handleSend()} style={styles.inlineSendBtn} accessibilityLabel="发送消息">
                <Ionicons name="arrow-up-circle" size={28} color={colors.brand} />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                onPressIn={handleVoicePressIn}
                onPressOut={handleVoicePressOut}
                delayLongPress={0}
                style={[styles.inlineVoiceBtn, voice.isRecording && styles.inlineVoiceBtnActive]}
                accessibilityLabel="语音输入"
              >
                <Ionicons name={voice.isRecording ? 'mic' : 'mic-outline'} size={20} color={voice.isRecording ? '#fff' : colors.labelTertiary} />
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>

      <Modal visible={showMenu} transparent animationType="slide" onRequestClose={toggleMenu}>
        <Pressable style={styles.menuOverlay} onPress={toggleMenu}>
          <Pressable style={styles.menuSheet} onPress={e => e.stopPropagation()}>
            <View style={styles.menuHandle} />
            <MenuItem icon="camera-outline" label="拍照" desc="拍摄食物或健康数据" onPress={handleTakePhoto} />
            <MenuItem icon="image-outline" label="相册" desc="选择图片发送分析" onPress={handlePickImage} />
            <MenuItem icon="document-outline" label="文件" desc="上传文档或报告" onPress={handlePickFile} />
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
        <Ionicons name={icon} size={20} color={colors.labelPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.menuLabel}>{label}</Text>
        <Text style={styles.menuDesc}>{desc}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 6, backgroundColor: colors.bgPrimary,
  },
  plusBtn: {
    width: 34, height: 34, borderRadius: 17,
    backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.separator,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    flex: 1, flexDirection: 'row', alignItems: 'flex-end',
    backgroundColor: colors.bgCard, borderRadius: 22,
    borderWidth: 1, borderColor: colors.separator,
    paddingLeft: 14, paddingRight: 4, paddingVertical: 4,
  },
  textInput: {
    flex: 1, fontSize: 15, maxHeight: 90, color: colors.labelPrimary,
    paddingTop: 6, paddingBottom: 6,
  },
  inputActions: { flexDirection: 'row', alignItems: 'center', paddingBottom: 2 },
  inlineSendBtn: { padding: 2 },
  inlineVoiceBtn: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  inlineVoiceBtnActive: { backgroundColor: '#FF453A' },
  previewBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: 4, backgroundColor: colors.bgCard,
  },
  previewImg: { width: 36, height: 36, borderRadius: 6 },
  previewText: { fontSize: 12, color: colors.labelSecondary, flex: 1 } as TextStyle,
  recordBar: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: spacing.lg, paddingVertical: 6, backgroundColor: '#FFF0F0',
  },
  recDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#FF453A' },
  recText: { fontSize: 13, color: '#FF453A', flex: 1 } as TextStyle,
  menuOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'flex-end' },
  menuSheet: {
    backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingHorizontal: spacing.xl, paddingBottom: 40, paddingTop: 8,
  },
  menuHandle: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: colors.labelQuaternary,
    alignSelf: 'center', marginBottom: spacing.lg,
  },
  menuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  menuIconWrap: {
    width: 38, height: 38, borderRadius: 12, backgroundColor: colors.bgPrimary,
    alignItems: 'center', justifyContent: 'center',
  },
  menuLabel: { fontSize: 16, fontWeight: '500', color: colors.labelPrimary } as TextStyle,
  menuDesc: { fontSize: 12, color: colors.labelSecondary, marginTop: 1 } as TextStyle,
});
