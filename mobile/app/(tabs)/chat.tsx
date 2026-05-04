import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, TextStyle,
  Alert, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router } from 'expo-router';
import { deleteConversation } from '../../services/chat';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import ChatInputBar from '../../components/chat/ChatInputBar';
import BrandCircle from '../../components/chat/BrandCircle';
import ChatBubble from '../../components/chat/ChatBubble';
import OpenerCard from '../../components/chat/OpenerCard';
import { fetchConversationOpener, type ConversationOpener } from '../../services/conversationOpener';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

const SUGGESTIONS = [
  { icon: 'pulse-outline' as const, text: '今天的健康状况如何？' },
  { icon: 'moon-outline' as const, text: '分析我的睡眠质量' },
  { icon: 'fitness-outline' as const, text: '给我运动建议' },
  { icon: 'trending-up-outline' as const, text: 'HRV趋势分析' },
];

export default function ChatScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const chat = useChatEngine();
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [viewingImage, setViewingImage] = useState<string | null>(null);

  // Context from alert / push / Siri deep-link. Read ONCE on first mount, then cleared.
  // autoSend=1 (from Siri HealthAnalysisOpenIntent) → directly send instead of prefilling.
  const params = useLocalSearchParams<{ prompt?: string; badge?: string; autoSend?: string }>();
  const [contextBadge, setContextBadge] = useState<string | null>(null);
  const [initialInput, setInitialInput] = useState<string | undefined>(undefined);
  const contextConsumed = useRef(false);

  // P1: opener — chat tab mount 时拉一次, 用户发了第一条 message 后自动隐藏.
  // null = 还没拉到 / 无信号; 退化到默认 SUGGESTIONS chip.
  const [opener, setOpener] = useState<ConversationOpener | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchConversationOpener().then(o => {
      if (!cancelled) setOpener(o);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (contextConsumed.current) return;
    if (params.prompt || params.badge) {
      contextConsumed.current = true;
      if (params.badge) setContextBadge(params.badge);
      if (params.prompt) {
        if (params.autoSend === '1') {
          chat.sendMessage(params.prompt, null, { fromSiri: true });
        } else {
          setInitialInput(params.prompt);
        }
      }
      try { router.setParams({ prompt: undefined, badge: undefined, autoSend: undefined } as any); } catch {}
    }
  }, [params.prompt, params.badge, params.autoSend]);

  useEffect(() => { chat.loadLatestConversation(); }, []);

  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => {
      setKeyboardVisible(true);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  const handleSend = useCallback((text: string, images?: any) => {
    chat.sendMessage(text, images);
  }, [chat.sendMessage]);

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => (
    <ChatBubble item={item} onViewImage={setViewingImage} />
  ), []);

  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const kbOffset = 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Ionicons name="sparkles" size={18} color={c.brand} />
        <Text style={txt.headerTitle}>AI 健康助理</Text>
        <View style={{ flex: 1 }} />
        {/* P7 (2026-05-04): voice 入口升级为填充 mic-circle (从 outline 改) +
            尺寸 24, 视觉对比度更高. 让用户清楚有 voice 这条主路径. */}
        <TouchableOpacity
          onPress={() => router.push('/voice-chat' as any)}
          hitSlop={8}
          style={{ marginRight: 12 }}
          accessibilityLabel="语音对话"
          accessibilityRole="button"
        >
          <Ionicons name="mic-circle" size={26} color={c.brand} />
        </TouchableOpacity>
        <TouchableOpacity onPress={chat.newChat} hitSlop={8} accessibilityLabel="新建对话" accessibilityRole="button">
          <Ionicons name="create-outline" size={20} color={c.labelSecondary} />
        </TouchableOpacity>
        {chat.conversationId && chat.messages.length > 0 && (
          <TouchableOpacity onPress={() => {
            Alert.alert('删除对话', '确定删除当前对话？', [
              { text: '取消', style: 'cancel' },
              { text: '删除', style: 'destructive', onPress: async () => {
                await deleteConversation(chat.conversationId!);
                chat.newChat();
              }},
            ]);
          }} hitSlop={8} style={{ marginLeft: 12 }} accessibilityLabel="删除当前对话" accessibilityRole="button">
            <Ionicons name="trash-outline" size={18} color={c.red} />
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={kbOffset}>
        <FlatList
          ref={flatListRef}
          data={chat.messages}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => { if (isNearBottom.current) flatListRef.current?.scrollToEnd({ animated: true }); }}
          onScroll={(e) => { const { layoutMeasurement, contentOffset, contentSize } = e.nativeEvent; isNearBottom.current = contentSize.height - contentOffset.y - layoutMeasurement.height < 120; }}
          scrollEventThrottle={100}
          ListEmptyComponent={
            <View>
              {opener && (
                <OpenerCard
                  opener={opener}
                  onQuickReply={(text) => handleSend(text, null)}
                />
              )}
              <View style={styles.welcome}>
                <BrandCircle size={72} style={{ marginBottom: 16 }}>
                  <Ionicons name="sparkles" size={32} color="#fff" />
                </BrandCircle>
                <Text style={txt.welcomeTitle}>AI 健康助理</Text>
                <Text style={txt.welcomeSub}>
                  {opener
                    ? '或者问我别的'
                    : '我可以帮你分析数据、解答疑问、提供建议'}
                </Text>
                <View style={styles.sugGrid}>
                  {SUGGESTIONS.map(s => (
                    <TouchableOpacity key={s.text} style={styles.sugCard} onPress={() => handleSend(s.text, null)} activeOpacity={0.7}>
                      <Ionicons name={s.icon} size={18} color={c.brand} />
                      <Text style={txt.sugText}>{s.text}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>
          }
        />

        {contextBadge && (
          <View style={styles.contextBanner}>
            <Ionicons name="link-outline" size={13} color={c.brand} />
            <Text style={txt.contextBanner} numberOfLines={1}>
              基于 {contextBadge}
            </Text>
            <TouchableOpacity onPress={() => setContextBadge(null)} hitSlop={8}>
              <Ionicons name="close" size={14} color={c.labelTertiary} />
            </TouchableOpacity>
          </View>
        )}

        <ChatInputBar onSend={handleSend} isStreaming={chat.isStreaming} initialText={initialInput} />
        {!keyboardVisible && <View style={{ height: 83 }} />}
      </KeyboardAvoidingView>

      <Modal visible={!!viewingImage} transparent animationType="fade" onRequestClose={() => setViewingImage(null)}>
        <Pressable style={styles.imageViewerOverlay} onPress={() => setViewingImage(null)}>
          {viewingImage && (
            <Image source={{ uri: viewingImage }} style={{ width: windowWidth - 32, height: windowHeight * 0.7 }} contentFit="contain" />
          )}
          <TouchableOpacity style={styles.imageViewerClose} onPress={() => setViewingImage(null)}>
            <Ionicons name="close-circle" size={32} color="#fff" />
          </TouchableOpacity>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  messageList: { padding: spacing.lg, paddingBottom: 8 },
  imageViewerOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center', alignItems: 'center',
  },
  imageViewerClose: { position: 'absolute', top: 60, right: 20 },
  welcome: { alignItems: 'center', paddingTop: 60 },
  sugGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xxl, paddingHorizontal: spacing.lg },
  sugCard: {
    width: '47%', backgroundColor: c.bgCard, borderRadius: radii.md,
    padding: spacing.md, gap: 6, ...shadows.subtle,
  },
  contextBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginHorizontal: spacing.lg, marginBottom: 4,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    backgroundColor: c.brandLight, borderRadius: radii.md,
  },
  });
}

function createTxt(c: ColorPalette) {
  return {
  headerTitle: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  welcomeTitle: { fontSize: 22, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: c.labelSecondary, marginTop: 4, textAlign: 'center' } as TextStyle,
  sugText: { fontSize: 13, color: c.labelPrimary, lineHeight: 18 } as TextStyle,
  contextBanner: { fontSize: 12, color: c.brand, flex: 1, fontWeight: '500' } as TextStyle,
  };
}
