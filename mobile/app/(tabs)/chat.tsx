import React, { useState, useRef, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, TextStyle, Image,
  Alert, Modal, Pressable, Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { Audio } from 'expo-av';
import Markdown from 'react-native-markdown-display';
import { streamChat, type ChatMessage } from '@/services/chat';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function BrandCircle({ size, children, style }: { size: number; children: React.ReactNode; style?: any }) {
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }, style]}>
      {children}
    </View>
  );
}

interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  imageUri?: string;
}

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }

const SUGGESTIONS = [
  { icon: 'pulse-outline' as const, text: '今天的健康状况如何？' },
  { icon: 'moon-outline' as const, text: '分析我的睡眠质量' },
  { icon: 'fitness-outline' as const, text: '给我运动建议' },
  { icon: 'trending-up-outline' as const, text: 'HRV趋势分析' },
];

export default function ChatScreen() {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingImage, setPendingImage] = useState<{ uri: string; base64: string; type: string } | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const flatListRef = useRef<FlatList>(null);
  const plusRotation = useRef(new Animated.Value(0)).current;

  const toggleMenu = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const toOpen = !showMenu;
    setShowMenu(toOpen);
    Animated.spring(plusRotation, { toValue: toOpen ? 1 : 0, useNativeDriver: true, friction: 8 }).start();
  };

  // ── Send ──
  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text || input).trim();
    const hasImage = !!pendingImage;
    if (!msg && !hasImage) return;
    if (isStreaming) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    setInput('');
    const finalMsg = msg || (hasImage ? '请分析这张图片' : '');
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: finalMsg, imageUri: pendingImage?.uri };
    const assistantId = nextId();
    const assistantMsg: UIMessage = { id: assistantId, role: 'assistant', content: '', streaming: true };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);
    const imgData = pendingImage;
    setPendingImage(null);

    try {
      for await (const token of streamChat(finalMsg, undefined, imgData?.base64, imgData?.type)) {
        setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: m.content + token } : m));
      }
    } catch (err: any) {
      setMessages(prev => prev.map(m =>
        m.id === assistantId ? { ...m, content: m.content || `[错误] ${err?.message || '请求失败'}` } : m
      ));
    } finally {
      setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, streaming: false } : m));
      setIsStreaming(false);
    }
  }, [input, isStreaming, pendingImage]);

  // ── Media Actions ──
  const pickImage = useCallback(async () => {
    setShowMenu(false);
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], base64: true, quality: 0.8 });
    if (!result.canceled && result.assets[0]) {
      const a = result.assets[0];
      setPendingImage({ uri: a.uri, base64: a.base64 || '', type: a.mimeType?.split('/')[1] || 'jpeg' });
    }
  }, []);

  const takePhoto = useCallback(async () => {
    setShowMenu(false);
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { Alert.alert('需要相机权限'); return; }
    const result = await ImagePicker.launchCameraAsync({ base64: true, quality: 0.8 });
    if (!result.canceled && result.assets[0]) {
      const a = result.assets[0];
      setPendingImage({ uri: a.uri, base64: a.base64 || '', type: a.mimeType?.split('/')[1] || 'jpeg' });
    }
  }, []);

  const pickFile = useCallback(async () => {
    setShowMenu(false);
    const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true });
    if (!result.canceled && result.assets[0]) {
      setInput(`请分析文件：${result.assets[0].name}`);
    }
  }, []);

  // ── Voice — long press to record, release to send ──
  const startRecording = useCallback(async () => {
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) { Alert.alert('需要麦克风权限'); return; }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recordingRef.current = recording;
      setIsRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch { Alert.alert('录音启动失败'); }
  }, []);

  const stopRecordingAndSend = useCallback(async () => {
    if (!isRecording || !recordingRef.current) return;
    setIsRecording(false);
    try {
      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();
      recordingRef.current = null;
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (uri) {
        // TODO: send audio to speech-to-text API, for now send as text indicator
        sendMessage('[语音消息]');
      }
    } catch { /* ignore */ }
  }, [isRecording, sendMessage]);

  // ── Render Message ──
  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
        {!isUser && (
          <BrandCircle size={30} style={{ marginRight: 8 }}>
            <Ionicons name="sparkles" size={14} color="#fff" />
          </BrandCircle>
        )}
        {isUser ? (
          <View style={[styles.bubble, styles.bubbleUser, { backgroundColor: colors.brand }]}>
            {item.imageUri && <Image source={{ uri: item.imageUri }} style={styles.msgImage} resizeMode="cover" />}
            <Text style={txt.bubbleUser}>{item.content}</Text>
          </View>
        ) : (
          <View style={[styles.bubble, styles.bubbleAI]}>
            <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
            {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 6, alignSelf: 'flex-start' }} />}
          </View>
        )}
      </View>
    );
  }, []);

  const canSend = (input.trim() || pendingImage) && !isStreaming;
  const rotate = plusRotation.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '45deg'] });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Ionicons name="sparkles" size={18} color={colors.brand} />
        <Text style={txt.headerTitle}>AI 健康助理</Text>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={90}>
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
          ListEmptyComponent={
            <View style={styles.welcome}>
              <BrandCircle size={72} style={{ marginBottom: 16 }}>
                <Ionicons name="sparkles" size={32} color="#fff" />
              </BrandCircle>
              <Text style={txt.welcomeTitle}>AI 健康助理</Text>
              <Text style={txt.welcomeSub}>我可以帮你分析数据、解答疑问、提供建议</Text>
              <View style={styles.sugGrid}>
                {SUGGESTIONS.map(s => (
                  <TouchableOpacity key={s.text} style={styles.sugCard} onPress={() => sendMessage(s.text)} activeOpacity={0.7}>
                    <Ionicons name={s.icon} size={18} color={colors.brand} />
                    <Text style={txt.sugText}>{s.text}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          }
        />

        {/* Pending image preview */}
        {pendingImage && (
          <View style={styles.previewBar}>
            <Image source={{ uri: pendingImage.uri }} style={styles.previewImg} />
            <Text style={txt.previewText}>图片已选择</Text>
            <TouchableOpacity onPress={() => setPendingImage(null)}>
              <Ionicons name="close-circle" size={22} color={colors.red} />
            </TouchableOpacity>
          </View>
        )}

        {/* Recording indicator — shows above input bar */}
        {isRecording && (
          <View style={styles.recordingBar}>
            <View style={styles.recordingDot} />
            <Text style={txt.recordingText}>正在录音，松手发送...</Text>
          </View>
        )}

        {/* Input Bar — ChatGPT style: + button | input | voice/send */}
        <View style={styles.inputBar}>
          {/* Plus button */}
          <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn} activeOpacity={0.6}>
            <Animated.View style={{ transform: [{ rotate }] }}>
              <Ionicons name="add" size={24} color={colors.labelPrimary} />
            </Animated.View>
          </TouchableOpacity>

          {/* Text input */}
          <TextInput
            style={styles.textInput}
            placeholder="有问题，尽管问"
            placeholderTextColor={colors.labelTertiary}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => sendMessage()}
            returnKeyType="send"
            multiline
            maxLength={2000}
          />

          {/* Right: voice or send */}
          {canSend ? (
            <TouchableOpacity onPress={() => sendMessage()} style={styles.sendBtn}>
              <BrandCircle size={32}>
                <Ionicons name="arrow-up" size={16} color="#fff" />
              </BrandCircle>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              onLongPress={startRecording}
              onPressOut={stopRecordingAndSend}
              delayLongPress={150}
              style={[styles.voiceBtn, isRecording && styles.voiceBtnActive]}
              activeOpacity={0.6}
            >
              <Ionicons name={isRecording ? 'mic' : 'headset-outline'} size={22} color={isRecording ? '#fff' : colors.labelSecondary} />
            </TouchableOpacity>
          )}
        </View>

        {/* Bottom spacer for tab bar */}
        <View style={{ height: 83 }} />
      </KeyboardAvoidingView>

      {/* Plus Menu Bottom Sheet */}
      <Modal visible={showMenu} transparent animationType="slide" onRequestClose={toggleMenu}>
        <Pressable style={styles.menuOverlay} onPress={toggleMenu}>
          <Pressable style={styles.menuSheet} onPress={e => e.stopPropagation()}>
            <View style={styles.menuHandle} />
            <MenuItem icon="camera-outline" label="拍照" desc="拍摄食物或健康数据" onPress={takePhoto} />
            <MenuItem icon="image-outline" label="相册" desc="选择图片发送分析" onPress={pickImage} />
            <MenuItem icon="document-outline" label="添加文件" desc="上传文档或报告" onPress={pickFile} />
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

function MenuItem({ icon, label, desc, onPress }: { icon: any; label: string; desc: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.menuItem} onPress={onPress} activeOpacity={0.6}>
      <View style={styles.menuIconWrap}>
        <Ionicons name={icon} size={22} color={colors.labelPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={txt.menuLabel}>{label}</Text>
        <Text style={txt.menuDesc}>{desc}</Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={colors.labelTertiary} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  messageList: { padding: spacing.lg, paddingBottom: 8 },
  msgRow: { flexDirection: 'row', marginBottom: spacing.md, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '78%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleUser: { borderBottomRightRadius: 4 },
  bubbleAI: { backgroundColor: '#fff', borderBottomLeftRadius: 4, ...shadows.subtle },
  msgImage: { width: 180, height: 135, borderRadius: 12, marginBottom: 6 },

  // Input bar
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: colors.bgPrimary,
  },
  plusBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.separator,
    alignItems: 'center', justifyContent: 'center',
  },
  textInput: {
    flex: 1, backgroundColor: colors.bgCard, borderRadius: 20,
    paddingHorizontal: 14, paddingTop: 9, paddingBottom: 9,
    fontSize: 15, maxHeight: 100, color: colors.labelPrimary,
    borderWidth: 1, borderColor: colors.separator,
  },
  sendBtn: { marginBottom: 2 },
  voiceBtn: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
  },
  voiceBtnActive: {
    backgroundColor: '#FF453A',
    transform: [{ scale: 1.2 }],
  },

  // Preview & recording
  previewBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    backgroundColor: colors.bgCard,
  },
  previewImg: { width: 40, height: 40, borderRadius: 8 },
  recordingBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: spacing.lg, paddingVertical: 8,
    backgroundColor: '#FFF0F0',
  },
  recordingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#FF453A' },

  // Plus menu
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
    flexDirection: 'row', alignItems: 'center', gap: 14,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  menuIconWrap: {
    width: 40, height: 40, borderRadius: 12, backgroundColor: colors.bgPrimary,
    alignItems: 'center', justifyContent: 'center',
  },

  // Welcome
  welcome: { alignItems: 'center', paddingTop: 60 },
  sugGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xxl, paddingHorizontal: spacing.lg },
  sugCard: {
    width: '47%', backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, gap: 6, ...shadows.subtle,
  },
});

const txt = {
  headerTitle: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  welcomeTitle: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4, textAlign: 'center' } as TextStyle,
  sugText: { fontSize: 13, color: colors.labelPrimary, lineHeight: 18 } as TextStyle,
  previewText: { fontSize: 13, color: colors.labelSecondary, flex: 1 } as TextStyle,
  recordingText: { fontSize: 14, color: '#FF453A', flex: 1 } as TextStyle,
  recordingStop: { fontSize: 14, fontWeight: '600', color: '#FF453A' } as TextStyle,
  menuLabel: { fontSize: 16, fontWeight: '500', color: colors.labelPrimary } as TextStyle,
  menuDesc: { fontSize: 12, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 22, color: colors.labelPrimary },
  heading1: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary, marginTop: 8, marginBottom: 4 },
  heading2: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, marginTop: 6, marginBottom: 4 },
  heading3: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 4, marginBottom: 2 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 4 },
  ordered_list: { marginVertical: 4 },
  list_item: { flexDirection: 'row', marginVertical: 2 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 4, fontFamily: 'Menlo', fontSize: 13, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 8, padding: 10, fontFamily: 'Menlo', fontSize: 13, marginVertical: 6 },
  code_block: { backgroundColor: '#F2F2F7', borderRadius: 8, padding: 10, fontFamily: 'Menlo', fontSize: 13, marginVertical: 6 },
  blockquote: { borderLeftWidth: 3, borderLeftColor: colors.brand, paddingLeft: 10, marginVertical: 4, opacity: 0.8 },
  hr: { backgroundColor: colors.separator, height: 1, marginVertical: 8 },
  paragraph: { marginVertical: 2 },
  link: { color: colors.brand },
  table: { borderWidth: 0.5, borderColor: colors.separator, borderRadius: 6, marginVertical: 6 },
  th: { padding: 6, fontWeight: '600', backgroundColor: '#F2F2F7' },
  td: { padding: 6 },
  tr: { borderBottomWidth: 0.5, borderColor: colors.separator },
});
