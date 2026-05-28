import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  Platform, TextStyle,
  Alert, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { useBottomTabBarHeight } from '@react-navigation/bottom-tabs';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router, useFocusEffect } from 'expo-router';
import { deleteConversation, getConversations, updateConversationTitle } from '../../services/chat';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import ChatInputBar from '../../components/chat/ChatInputBar';
import ChatBubble from '../../components/chat/ChatBubble';
import ConversationSheet from '../../components/chat/ConversationSheet';
import OpenerCard from '../../components/chat/OpenerCard';
import LlmModelPicker from '../../components/chat/LlmModelPicker';
import {
  buildConversationOpenerReplyContext,
  buildConversationOpenerReplyMessage,
  fetchConversationStarters,
  type ConversationOpener,
} from '../../services/conversationOpener';
import { fetchMemoryOpener, type MemoryOpenerItem } from '../../services/memoryOpener';
import { getLlmPreference, updateLlmPreference, type ModelOption } from '../../services/llmPreference';
import { recordCardAdherence, recordCardDecision } from '../../services/actionCards';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { sharePlainText } from '../../utils/share';
import { buildSelectedChatShareMessage, isShareableChatMessage } from '../../utils/chatShareSelection';

type SuggestionCard = { icon: keyof typeof Ionicons.glyphMap; text: string };

const SUGGESTIONS: SuggestionCard[] = [
  { icon: 'pulse-outline', text: '今天的健康状况如何？' },
  { icon: 'moon-outline', text: '分析我的睡眠质量' },
  { icon: 'fitness-outline', text: '给我运动建议' },
  { icon: 'trending-up-outline', text: 'HRV趋势分析' },
];

function guessSuggestionIcon(text: string): SuggestionCard['icon'] {
  if (/体检|化验|指标|LDL|HbA1c|尿酸|血压|血脂|血糖/i.test(text)) return 'document-text-outline';
  if (/睡眠|打鼾|鼻塞|血氧|SpO2|HRV|静息心率|恢复/i.test(text)) return 'moon-outline';
  if (/训练|运动|跑步|骑行|力量|有氧|恢复/i.test(text)) return 'fitness-outline';
  if (/补剂|维生素|鱼油|叶酸|镁|药/i.test(text)) return 'medical-outline';
  if (/趋势|复盘|分析/i.test(text)) return 'trending-up-outline';
  return 'sparkles-outline';
}

function decorateSuggestions(texts: string[] | null | undefined): SuggestionCard[] | null {
  if (!texts || !Array.isArray(texts) || texts.length === 0) return null;
  return texts
    .map((text) => ({ text: String(text), icon: guessSuggestionIcon(String(text)) }))
    .filter((s) => s.text.trim().length > 0)
    .slice(0, 4);
}

function formatMemoryOpenerText(items: MemoryOpenerItem[]): string {
  return items
    .map(item => item.content.trim().replace(/\s+/g, ' '))
    .filter(Boolean)
    .slice(0, 2)
    .join(' · ');
}

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
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [historyVisible, setHistoryVisible] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [llmModelId, setLlmModelId] = useState<string | null>(null);
  const [llmOptions, setLlmOptions] = useState<ModelOption[]>([]);
  const [llmSaving, setLlmSaving] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedMessageIds, setSelectedMessageIds] = useState<Set<string>>(new Set());
  const [sharing, setSharing] = useState(false);
  const [toolMenuVisible, setToolMenuVisible] = useState(false);

  // Context from alert / push / Siri deep-link. Read ONCE on first mount, then cleared.
  // autoSend=1 (from Siri HealthAnalysisOpenIntent) → directly send instead of prefilling.
  // context (JSON string) → 注入到 LLM system prompt 作为深化基础, 不展示在 user 消息里
  const params = useLocalSearchParams<{ prompt?: string; badge?: string; autoSend?: string; context?: string; newChat?: string }>();
  const [contextBadge, setContextBadge] = useState<string | null>(null);
  const [initialInput, setInitialInput] = useState<string | undefined>(undefined);
  const lastContextKey = useRef<string | null>(null);

  // P1: opener — chat tab mount 时拉一次, 用户发了第一条 message 后自动隐藏.
  // null = 还没拉到 / 无信号; 退化到默认 SUGGESTIONS chip.
  const [opener, setOpener] = useState<ConversationOpener | null>(null);
  const [starterSuggestions, setStarterSuggestions] = useState<SuggestionCard[]>(SUGGESTIONS);
  const refreshConversationStarters = useCallback(async (shouldSkip?: () => boolean) => {
    const { opener: newOpener, suggestions } = await fetchConversationStarters();
    if (shouldSkip?.()) return;
    setOpener(newOpener);
    const decorated = decorateSuggestions(suggestions);
    setStarterSuggestions(decorated || SUGGESTIONS);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void refreshConversationStarters(() => cancelled);
    return () => { cancelled = true; };
  }, [refreshConversationStarters]);

  // P3-3: 拉 top 1-2 条 memory, 显示在 opener 上方"我记得你: <X>"
  const [memoryOpener, setMemoryOpener] = useState<MemoryOpenerItem[]>([]);
  const refreshMemoryOpener = useCallback(async (shouldSkip?: () => boolean) => {
    const items = await fetchMemoryOpener(2);
    if (!shouldSkip?.()) setMemoryOpener(items);
  }, []);

  const refreshCoachHomeState = useCallback(async () => {
    await Promise.all([
      refreshConversationStarters(),
      refreshMemoryOpener(),
    ]);
  }, [refreshConversationStarters, refreshMemoryOpener]);

  useEffect(() => {
    let cancelled = false;
    void refreshMemoryOpener(() => cancelled);
    return () => { cancelled = true; };
  }, [refreshMemoryOpener]);

  useEffect(() => {
    let cancelled = false;
    getLlmPreference().then(pref => {
      if (cancelled) return;
      setLlmModelId(pref.model_id);
      setLlmOptions(pref.options || []);
      setLlmError(null);
    }).catch(() => {
      if (!cancelled) setLlmError('模型列表加载失败');
    });
    return () => { cancelled = true; };
  }, []);

  const handleSelectModel = useCallback(async (modelId: string | null) => {
    if (llmSaving || llmModelId === modelId) return;
    setLlmSaving(modelId || '__default__');
    setLlmError(null);
    try {
      const pref = await updateLlmPreference(modelId);
      setLlmModelId(pref.model_id);
      setLlmOptions(pref.options || []);
    } catch (e: any) {
      setLlmError(e?.response?.data?.detail || e?.message || '模型切换失败');
    } finally {
      setLlmSaving(null);
    }
  }, [llmModelId, llmSaving]);

  useEffect(() => {
    if (params.prompt || params.badge || params.context) {
      const contextKey = JSON.stringify({
        prompt: params.prompt ?? '',
        badge: params.badge ?? '',
        autoSend: params.autoSend ?? '',
        context: params.context ?? '',
        newChat: params.newChat ?? '',
      });
      if (lastContextKey.current === contextKey) return;
      lastContextKey.current = contextKey;
      const forceNewConversation = params.newChat === '1';
      if (forceNewConversation) {
        newChat();
      }
      if (params.badge) setContextBadge(params.badge);
      if (params.prompt) {
        if (params.autoSend === '1') {
          sendMessage(params.prompt, null, { fromSiri: true, extraContext: params.context, forceNewConversation });
        } else if (params.context) {
          // 有 context 但不 autoSend: 用户点了"详细聊"入口, prompt 是预填问题, 跟 context 一起发
          sendMessage(params.prompt, null, { extraContext: params.context, forceNewConversation });
        } else {
          setInitialInput(params.prompt);
        }
      }
      try { router.setParams({ prompt: undefined, badge: undefined, autoSend: undefined, context: undefined, newChat: undefined } as any); } catch {}
    } else {
      lastContextKey.current = null;
    }
  }, [newChat, params.prompt, params.badge, params.autoSend, params.context, params.newChat, sendMessage]);

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
    const showSub = Keyboard.addListener('keyboardDidShow', (event) => {
      setKeyboardVisible(true);
      setKeyboardHeight(event.endCoordinates?.height || 0);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => {
      setKeyboardVisible(false);
      setKeyboardHeight(0);
    });
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  const handleSend = useCallback((text: string, images?: any) => {
    isNearBottom.current = true;
    sendMessage(text, images);
    setContextBadge(null);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [sendMessage]);

  const handleOpenerQuickReply = useCallback((text: string) => {
    isNearBottom.current = true;
    const activeOpener = opener;
    if (activeOpener) setOpener(null);
    const extraContext = activeOpener ? buildConversationOpenerReplyContext(activeOpener, text) : undefined;
    const adherence = activeOpener?.source === 'action_card_due'
      ? getSelfReportedAdherence(text)
      : null;
    const sideEffects: Promise<unknown>[] = [];
    if (activeOpener?.source === 'action_card_due' && activeOpener.source_id != null) {
      const cardId = Number(activeOpener.source_id);
      if (adherence !== null) {
        sideEffects.push(recordCardAdherence(cardId, adherence, 'self_reported'));
      } else if (/调整/.test(text)) {
        sideEffects.push(recordCardDecision(cardId, 'adjusted', 'opener_quick_reply_adjust'));
      }
    }
    if (sideEffects.length > 0) {
      Promise.allSettled(sideEffects)
        .then(results => {
          results.forEach(result => {
            if (result.status === 'rejected') {
              console.warn('[chat] opener feedback 回写失败', result.reason);
            }
          });
        })
        .finally(() => {
          refreshCoachHomeState().catch(err => console.warn('[chat] opener 刷新失败', err));
        });
    } else {
      refreshCoachHomeState().catch(err => console.warn('[chat] opener 刷新失败', err));
    }
    const messageText = activeOpener ? buildConversationOpenerReplyMessage(activeOpener, text) : text;
    sendMessage(messageText, null, extraContext ? { extraContext } : undefined);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [opener, refreshCoachHomeState, sendMessage]);

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
    setToolMenuVisible(false);
    setHistoryVisible(true);
    loadConversationHistory();
  }, [loadConversationHistory]);

  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedMessageIds(new Set());
  }, []);

  const handleNewChat = useCallback(() => {
    setToolMenuVisible(false);
    exitSelectionMode();
    setContextBadge(null);
    newChat();
    void refreshCoachHomeState();
  }, [exitSelectionMode, newChat, refreshCoachHomeState]);

  const handleDeleteCurrentConversation = useCallback(() => {
    setToolMenuVisible(false);
    if (!conversationId) return;
    Alert.alert('删除对话', '确定删除当前对话？', [
      { text: '取消', style: 'cancel' },
      { text: '删除', style: 'destructive', onPress: async () => {
        await deleteConversation(conversationId);
        handleNewChat();
      }},
    ]);
  }, [conversationId, handleNewChat]);

  const handleSelectConversation = useCallback(async (id: number) => {
    await loadConversation(id);
    isNearBottom.current = true;
    setContextBadge(null);
    setSelectionMode(false);
    setSelectedMessageIds(new Set());
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: false }), 120);
  }, [loadConversation]);

  const handleDeleteConversation = useCallback(async (id: number) => {
    const ok = await deleteConversation(id);
    if (!ok) {
      setHistoryError('删除失败，请稍后重试');
      return;
    }
    setConversations(prev => prev.filter(item => item.id !== id));
    if (conversationId === id) {
      handleNewChat();
    }
  }, [conversationId, handleNewChat]);

  const handleRenameConversation = useCallback(async (id: number, title: string) => {
    const updated = await updateConversationTitle(id, title);
    if (!updated) {
      setHistoryError('重命名失败，请稍后重试');
      throw new Error('rename conversation failed');
    }
    setConversations(prev => prev.map(item => (
      item.id === id
        ? { ...item, title: updated.title, updated_at: updated.updated_at || item.updated_at }
        : item
    )));
  }, []);

  const toggleMessageSelection = useCallback((id: string) => {
    setSelectedMessageIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const shareSelectedMessages = useCallback(async () => {
    const message = buildSelectedChatShareMessage(messages, selectedMessageIds);
    if (!message || sharing) return;
    setSharing(true);
    try {
      await sharePlainText({ title: '健康 Agent · 对话节选', message });
      exitSelectionMode();
    } catch {
      Alert.alert('分享失败', '请稍后重试');
    } finally {
      setSharing(false);
    }
  }, [exitSelectionMode, messages, selectedMessageIds, sharing]);

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => (
    <ChatBubble
      item={item}
      onViewImage={setViewingImage}
      selectionMode={selectionMode && isShareableChatMessage(item)}
      selected={selectedMessageIds.has(item.id)}
      onToggleSelected={toggleMessageSelection}
    />
  ), [selectedMessageIds, selectionMode, toggleMessageSelection]);

  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const tabBarHeight = useBottomTabBarHeight();
  const bottomSpacerHeight = keyboardVisible
    ? (Platform.OS === 'ios' ? keyboardHeight : 0)
    : tabBarHeight;
  const activeLlmLabel = llmModelId
    ? llmOptions.find(option => option.id === llmModelId)?.label || llmModelId
    : '系统默认';
  const headerLlmLabel = isStreaming ? '正在回复' : compactLlmHeaderLabel(activeLlmLabel);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <LlmModelPicker
          variant="header"
          currentLabel={headerLlmLabel}
          currentModelId={llmModelId}
          options={llmOptions}
          savingModelId={llmSaving}
          disabled={isStreaming}
          error={llmError}
          onSelect={handleSelectModel}
        />
        <TouchableOpacity
          onPress={() => router.push({
            pathname: '/voice-chat',
            params: conversationId ? { conversation_id: String(conversationId) } : {},
          } as any)}
          hitSlop={8}
          style={styles.voiceConversationAction}
          accessibilityLabel="开始语音对话"
          accessibilityHint="进入连续语音对话，AI 会听你说并用语音回复"
          accessibilityRole="button"
        >
          <Ionicons name="call" size={18} color="#FFFFFF" />
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setToolMenuVisible(true)}
          hitSlop={8}
          style={styles.headerMenuAction}
          accessibilityLabel="更多会诊操作"
          accessibilityRole="button"
        >
          <Ionicons name="ellipsis-horizontal" size={20} color={c.labelSecondary} />
        </TouchableOpacity>
      </View>

      <View style={{ flex: 1 }}>
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
                <Pressable
                  style={({ pressed }) => [styles.memoryOpener, pressed && styles.memoryOpenerPressed]}
                  onPress={() => router.push('/memory')}
                  accessibilityRole="button"
                  accessibilityLabel="查看和校准 AI 记忆"
                >
                  <View style={styles.memoryIconWrap}>
                    <Ionicons name="bookmark-outline" size={14} color={c.brand} />
                  </View>
                  <View style={styles.memoryTextWrap}>
                    <View style={styles.memoryHeader}>
                      <Text style={txt.memoryLabel}>记忆线索</Text>
                      <Text style={txt.memoryAction}>校准</Text>
                    </View>
                    <Text style={txt.memoryBody} numberOfLines={3}>
                      {formatMemoryOpenerText(memoryOpener)}
                    </Text>
                  </View>
                </Pressable>
              )}
              {opener && (
                <OpenerCard
                  opener={opener}
                  onQuickReply={handleOpenerQuickReply}
                />
              )}
              <View style={styles.welcome}>
                <View style={styles.welcomeInline}>
                  <Ionicons name="sparkles" size={14} color={c.brand} />
                  <Text style={txt.welcomeInline} numberOfLines={1}>
                    健康 Agent · {opener ? '或者问我别的' : '会带上你的健康上下文'}
                  </Text>
                </View>
                <View style={styles.sugGrid}>
                  {starterSuggestions.map(s => (
                    <TouchableOpacity
                      key={s.text}
                      style={styles.sugChip}
                      onPress={() => handleSend(s.text, null)}
                      activeOpacity={0.72}
                      accessibilityRole="button"
                      accessibilityLabel={`向健康 Agent 提问: ${s.text}`}
                    >
                      <Ionicons name={s.icon} size={13} color={c.brand} />
                      <Text style={txt.sugChipText} numberOfLines={1}>{s.text}</Text>
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

        {selectionMode && (
          <View style={styles.shareBar}>
            <View style={{ flex: 1 }}>
              <Text style={txt.shareBarTitle}>已选择 {selectedMessageIds.size} 条</Text>
              <Text style={txt.shareBarSub}>按当前对话顺序生成分享链接</Text>
            </View>
            <TouchableOpacity
              onPress={shareSelectedMessages}
              disabled={selectedMessageIds.size === 0 || sharing}
              style={[styles.shareButton, (selectedMessageIds.size === 0 || sharing) && styles.shareButtonDisabled]}
              accessibilityLabel="分享已选消息"
              accessibilityRole="button"
            >
              <Ionicons name="share-outline" size={16} color="#fff" />
              <Text style={txt.shareButton}>{sharing ? '生成中' : '分享'}</Text>
            </TouchableOpacity>
          </View>
        )}
        <ChatInputBar onSend={handleSend} isStreaming={isStreaming} initialText={initialInput} conversationId={conversationId} />
        <View testID="chat-bottom-spacer" style={{ height: bottomSpacerHeight }} />
      </View>

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
      <Modal visible={toolMenuVisible} transparent animationType="fade" onRequestClose={() => setToolMenuVisible(false)}>
        <Pressable style={styles.menuOverlay} onPress={() => setToolMenuVisible(false)}>
          <Pressable style={styles.toolSheet}>
            <View style={styles.toolSheetHeader}>
              <View>
                <Text style={txt.toolSheetTitle}>会诊工具</Text>
                <Text style={txt.toolSheetSub}>把低频操作收在这里</Text>
              </View>
              <TouchableOpacity onPress={() => setToolMenuVisible(false)} hitSlop={8} accessibilityLabel="关闭会诊工具">
                <Ionicons name="close" size={22} color={c.labelSecondary} />
              </TouchableOpacity>
            </View>
            <ToolMenuRow icon="time-outline" label="对话历史" onPress={openHistory} />
            <ToolMenuRow icon="create-outline" label="新建对话" onPress={handleNewChat} />
            {messages.some(isShareableChatMessage) && (
              <ToolMenuRow
                icon={selectionMode ? 'close' : 'checkbox-outline'}
                label={selectionMode ? '取消多选' : '选择多条分享'}
                onPress={() => {
                  setToolMenuVisible(false);
                  if (selectionMode) exitSelectionMode();
                  else setSelectionMode(true);
                }}
              />
            )}
            {conversationId && messages.length > 0 && (
              <ToolMenuRow
                icon="trash-outline"
                label="删除当前对话"
                destructive
                onPress={handleDeleteCurrentConversation}
              />
            )}
          </Pressable>
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
        onRenameConversation={handleRenameConversation}
        loading={historyLoading}
        error={historyError}
        onRetry={loadConversationHistory}
      />
    </SafeAreaView>
  );
}

function compactLlmHeaderLabel(label: string): string {
  return label
    .split(' · ')[0]
    .replace(/\s+(推理|均衡|快速)$/u, '')
    .trim();
}

function ToolMenuRow({
  icon,
  label,
  destructive,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  destructive?: boolean;
  onPress: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const color = destructive ? c.red : c.labelPrimary;
  return (
    <TouchableOpacity
      onPress={onPress}
      style={styles.toolMenuRow}
      activeOpacity={0.72}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={18} color={color} />
      <Text style={[txt.toolMenuText, { color }]}>{label}</Text>
      <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} style={{ marginLeft: 'auto' }} />
    </TouchableOpacity>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  voiceConversationAction: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brand,
  },
  headerMenuAction: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.bgCard,
  },
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
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: c.bgCard,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radii.lg,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    ...shadows.subtle,
  },
  memoryOpenerPressed: { opacity: 0.72 },
  memoryIconWrap: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brandLight,
  },
  memoryTextWrap: {
    flex: 1,
    minWidth: 0,
  },
  memoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 3,
  },
  imageViewerOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center', alignItems: 'center',
  },
  imageViewerClose: { position: 'absolute', top: 60, right: 20 },
  menuOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.28)',
    justifyContent: 'flex-start',
    paddingHorizontal: spacing.lg,
    paddingTop: 82,
  },
  toolSheet: {
    backgroundColor: c.bgPrimary,
    borderRadius: radii.xl,
    padding: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    ...shadows.heavy,
  },
  toolSheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingBottom: spacing.sm,
  },
  toolMenuRow: {
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  welcome: { paddingTop: spacing.md, paddingHorizontal: spacing.lg, gap: spacing.sm },
  welcomeInline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
  },
  sugGrid: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  sugChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: radii.full,
    backgroundColor: c.bgCard,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    maxWidth: '100%',
  },
  contextBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginHorizontal: spacing.lg, marginBottom: 4,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    backgroundColor: c.brandLight, borderRadius: radii.md,
  },
  shareBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginHorizontal: spacing.lg,
    marginBottom: 8,
    padding: spacing.md,
    borderRadius: radii.lg,
    backgroundColor: c.bgCard,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    ...shadows.subtle,
  },
  shareButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radii.full,
    backgroundColor: c.brand,
  },
  shareButtonDisabled: {
    opacity: 0.45,
  },
  });
}

function createTxt(c: ColorPalette) {
  return {
  headerTitle: { fontSize: 20, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  headerMeta: { fontSize: 12, color: c.labelTertiary, marginTop: 2, fontWeight: '600' } as TextStyle,
  welcomeInline: { fontSize: 12, color: c.labelSecondary, fontWeight: '700', flexShrink: 1 } as TextStyle,
  sugChipText: { fontSize: 12, color: c.labelPrimary, fontWeight: '600', flexShrink: 1 } as TextStyle,
  contextBanner: { fontSize: 12, color: c.brand, flex: 1, fontWeight: '500' } as TextStyle,
  historyAction: { fontSize: 12, color: c.labelSecondary, fontWeight: '600' } as TextStyle,
  memoryLabel: { fontSize: 11, color: c.labelTertiary, fontWeight: '700' } as TextStyle,
  memoryAction: { fontSize: 11, color: c.brand, fontWeight: '700' } as TextStyle,
  memoryBody: { fontSize: 13, color: c.labelSecondary, lineHeight: 18 } as TextStyle,
  shareBarTitle: { fontSize: 13, color: c.labelPrimary, fontWeight: '700' } as TextStyle,
  shareBarSub: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  shareButton: { fontSize: 13, color: '#fff', fontWeight: '700' } as TextStyle,
  toolSheetTitle: { fontSize: 17, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  toolSheetSub: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  toolMenuText: { fontSize: 15, fontWeight: '700' } as TextStyle,
  };
}
