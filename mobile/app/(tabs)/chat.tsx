import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, TextStyle,
  Alert, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router, useFocusEffect } from 'expo-router';
import { deleteConversation, getConversations } from '../../services/chat';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import ChatInputBar from '../../components/chat/ChatInputBar';
import BrandCircle from '../../components/chat/BrandCircle';
import ChatBubble from '../../components/chat/ChatBubble';
import ConversationSheet from '../../components/chat/ConversationSheet';
import OpenerCard from '../../components/chat/OpenerCard';
import {
  buildConversationOpenerReplyContext,
  buildConversationOpenerReplyMessage,
  fetchConversationOpener,
  type ConversationOpener,
} from '../../services/conversationOpener';
import { fetchMemoryOpener, type MemoryOpenerItem } from '../../services/memoryOpener';
import { recordCardAdherence } from '../../services/actionCards';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

const SUGGESTIONS = [
  { icon: 'pulse-outline' as const, text: '今天的健康状况如何？' },
  { icon: 'moon-outline' as const, text: '分析我的睡眠质量' },
  { icon: 'fitness-outline' as const, text: '给我运动建议' },
  { icon: 'trending-up-outline' as const, text: 'HRV趋势分析' },
];

function getSelfReportedAdherence(reply: string): number | null {
  if (/没做|未做|没有做|不算/.test(reply)) return 0;
  if (/做到|完成|已做|做了/.test(reply)) return 70;
  return null;
}

export default function ChatScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const chat = useChatEngine();
  const {
    messages,
    isStreaming,
    conversationId,
    sendMessage,
    newChat,
    loadLatestConversation,
    loadConversation,
  } = chat;
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [historyVisible, setHistoryVisible] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Context from alert / push / Siri deep-link. Read ONCE on first mount, then cleared.
  // autoSend=1 (from Siri HealthAnalysisOpenIntent) → directly send instead of prefilling.
  // context (JSON string) → 注入到 LLM system prompt 作为深化基础, 不展示在 user 消息里
  const params = useLocalSearchParams<{ prompt?: string; badge?: string; autoSend?: string; context?: string }>();
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

  // P3-3: 拉 top 1-2 条 memory, 显示在 opener 上方"我记得你: <X>"
  const [memoryOpener, setMemoryOpener] = useState<MemoryOpenerItem[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetchMemoryOpener(2).then(items => {
      if (!cancelled) setMemoryOpener(items);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (contextConsumed.current) return;
    if (params.prompt || params.badge || params.context) {
      contextConsumed.current = true;
      if (params.badge) setContextBadge(params.badge);
      if (params.prompt) {
        if (params.autoSend === '1') {
          sendMessage(params.prompt, null, { fromSiri: true, extraContext: params.context });
        } else if (params.context) {
          // 有 context 但不 autoSend: 用户点了"详细聊"入口, prompt 是预填问题, 跟 context 一起发
          sendMessage(params.prompt, null, { extraContext: params.context });
        } else {
          setInitialInput(params.prompt);
        }
      }
      try { router.setParams({ prompt: undefined, badge: undefined, autoSend: undefined, context: undefined } as any); } catch {}
    }
  }, [params.prompt, params.badge, params.autoSend, params.context, sendMessage]);

  useEffect(() => { loadLatestConversation(); }, [loadLatestConversation]);

  // 点"私教" tab 进来时滚到对话最后, 方便看最新消息.
  // useFocusEffect 在每次 tab 获得 focus 时触发 (包括首次 mount).
  // 用 setTimeout 推迟一帧, 等 FlatList 排版完才能滚到正确位置.
  useFocusEffect(
    useCallback(() => {
      const t = setTimeout(() => {
        try { flatListRef.current?.scrollToEnd({ animated: false }); } catch {}
      }, 120);
      return () => clearTimeout(t);
    }, [])
  );

  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => {
      setKeyboardVisible(true);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  const handleSend = useCallback((text: string, images?: any) => {
    isNearBottom.current = true;
    sendMessage(text, images);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [sendMessage]);

  const handleOpenerQuickReply = useCallback((text: string) => {
    isNearBottom.current = true;
    const extraContext = opener ? buildConversationOpenerReplyContext(opener, text) : undefined;
    const adherence = opener?.source === 'action_card_due'
      ? getSelfReportedAdherence(text)
      : null;
    if (adherence !== null && opener?.source_id != null) {
      recordCardAdherence(Number(opener.source_id), adherence, 'self_reported').catch(err => {
        console.warn('[chat] action card adherence 回写失败', err);
      });
    }
    const messageText = opener ? buildConversationOpenerReplyMessage(opener, text) : text;
    sendMessage(messageText, null, extraContext ? { extraContext } : undefined);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [opener, sendMessage]);

  const loadConversationHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const items = await getConversations();
      setConversations(items);
    } catch {
      setHistoryError('加载历史对话失败');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const openHistory = useCallback(() => {
    setHistoryVisible(true);
    loadConversationHistory();
  }, [loadConversationHistory]);

  const handleSelectConversation = useCallback(async (id: number) => {
    await loadConversation(id);
    isNearBottom.current = true;
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: false }), 120);
  }, [loadConversation]);

  const handleDeleteConversation = useCallback(async (id: number) => {
    const ok = await deleteConversation(id);
    if (!ok) {
      setHistoryError('删除失败，请稍后重试');
      return;
    }
    setConversations(prev => prev.filter(item => item.id !== id));
    if (conversationId === id) newChat();
  }, [conversationId, newChat]);

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => (
    <ChatBubble item={item} onViewImage={setViewingImage} />
  ), []);

  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const kbOffset = 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Ionicons name="sparkles" size={18} color={c.brand} />
        <Text style={txt.headerTitle}>健康 Agent</Text>
        <View style={{ flex: 1 }} />
        <TouchableOpacity
          onPress={openHistory}
          hitSlop={8}
          style={styles.historyAction}
          accessibilityLabel="对话历史"
          accessibilityRole="button"
        >
          <Ionicons name="time-outline" size={21} color={c.labelSecondary} />
          <Text style={txt.historyAction}>历史</Text>
        </TouchableOpacity>
        {/* P7 (2026-05-04): voice 入口升级为填充 mic-circle (从 outline 改) +
            尺寸 24, 视觉对比度更高. 让用户清楚有 voice 这条主路径. */}
        <TouchableOpacity
          onPress={() => router.push({
            pathname: '/voice-chat',
            params: conversationId ? { conversation_id: String(conversationId) } : {},
          } as any)}
          hitSlop={8}
          style={styles.headerAction}
          accessibilityLabel="语音对话"
          accessibilityRole="button"
        >
          <Ionicons name="mic-circle" size={26} color={c.brand} />
        </TouchableOpacity>
        <TouchableOpacity onPress={newChat} hitSlop={8} accessibilityLabel="新建对话" accessibilityRole="button">
          <Ionicons name="create-outline" size={20} color={c.labelSecondary} />
        </TouchableOpacity>
        {conversationId && messages.length > 0 && (
          <TouchableOpacity onPress={() => {
            Alert.alert('删除对话', '确定删除当前对话？', [
              { text: '取消', style: 'cancel' },
              { text: '删除', style: 'destructive', onPress: async () => {
                await deleteConversation(conversationId);
                newChat();
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
          data={messages}
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
              {memoryOpener.length > 0 && (
                <View style={styles.memoryOpener}>
                  <Ionicons name="bookmark-outline" size={14} color={c.brand} />
                  <Text style={styles.memoryOpenerText}>
                    我记得你
                    {memoryOpener.map(m => `: ${m.content}`).join(' /')}
                  </Text>
                </View>
              )}
              {opener && (
                <OpenerCard
                  opener={opener}
                  onQuickReply={handleOpenerQuickReply}
                />
              )}
              <View style={styles.welcome}>
                <BrandCircle size={72} style={{ marginBottom: 16 }}>
                  <Ionicons name="sparkles" size={32} color="#fff" />
                </BrandCircle>
                <Text style={txt.welcomeTitle}>健康 Agent</Text>
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

        <ChatInputBar onSend={handleSend} isStreaming={isStreaming} initialText={initialInput} conversationId={conversationId} />
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
      <ConversationSheet
        visible={historyVisible}
        onClose={() => setHistoryVisible(false)}
        conversations={conversations}
        setConversations={setConversations}
        currentConversationId={conversationId}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        loading={historyLoading}
        error={historyError}
        onRetry={loadConversationHistory}
      />
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  headerAction: { marginRight: 12 },
  historyAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginRight: 12,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: radii.sm,
    backgroundColor: c.bgCard,
  },
  messageList: { padding: spacing.lg, paddingBottom: 8 },
  // P3-3: 会诊页 opener "我记得你 X" banner
  memoryOpener: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    backgroundColor: c.brandLight,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.md,
    marginBottom: spacing.md,
  },
  memoryOpenerText: { flex: 1, color: c.brand, fontSize: 12, lineHeight: 17 },
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
  historyAction: { fontSize: 12, color: c.labelSecondary, fontWeight: '600' } as TextStyle,
  };
}
