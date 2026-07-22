import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  Platform, TextStyle, AppState, type AppStateStatus,
  ActivityIndicator, Alert, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router, useFocusEffect } from 'expo-router';
import { deleteConversation, getConversationsPage, updateConversationTitle } from '../../services/chat';
import { useChatEngine } from '../../hooks/useChatEngine';
import ChatInputBar, { type ChatInputSendOptions } from '../../components/chat/ChatInputBar';
import ChatBubble from '../../components/chat/ChatBubble';
import ConversationSheet from '../../components/chat/ConversationSheet';
import ChatHeader from '../../components/chat/ChatHeader';
import ChatTodayFocusCard from '../../components/chat/ChatTodayFocusCard';
import { buildTodayFocusModel } from '../../components/chat/todayFocus';
import {
  buildMessageTimeDividerItems,
  type ChatMessageListItem,
} from '../../components/chat/messageTime';
import EmptyStateHome, {
  greetingForHour,
  formatMemoryOpenerText,
  type EmptyStateSuggestion,
} from '../../components/chat/EmptyStateHome';
import ComposerSuggestionsRow from '../../components/chat/ComposerSuggestionsRow';
import { formatOpenerText } from '../../components/chat/OpenerCard';
import {
  buildConversationOpenerReplyContext,
  buildConversationOpenerReplyMessage,
  fetchConversationStarters,
  type ConversationOpener,
  type QuickReplyAction,
  type SuggestionMeta,
} from '../../services/conversationOpener';
import { navigateForQuickReplyAction } from '../../utils/quickReplyAction';
import { emitClientEvent } from '../../services/clientEvents';
import { fetchMemoryOpener, type MemoryOpenerItem } from '../../services/memoryOpener';
import { updateLlmPreference, type ModelOption } from '../../services/llmPreference';
import { recordCardAdherence, recordCardDecision } from '../../services/actionCards';
import { useTodayTimeline } from '../../hooks/useTodayTimeline';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';
import { sharePlainText, shareLocalImage } from '../../utils/share';
import { buildSelectedChatShareMessage, isShareableChatMessage } from '../../utils/chatShareSelection';
import { captureRef } from 'react-native-view-shot';
import ConversationShareImage, { type ShareImageMessage } from '../../components/chat/ConversationShareImage';
import type { ChatMedicalExamImportSkillResult } from '../../services/chatMedicalExamImportSkill';
import { loadAgentHomeBootstrap } from '../../services/agentHomeBootstrap';
import { useAuth } from '../../hooks/useAuth';
import { buildChatImageSource } from '../../utils/chatImageSource';
import { saveChatImageToLibrary } from '../../services/chatImageSave';
import {
  cancelChatScrollOnUserDrag,
  shouldForceScrollAfterHydration,
  shouldScrollChatToEnd,
} from '../../utils/chatScroll';

type SuggestionCard = {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
  key: string;       // generator identity for CTR analytics ("default" for static fallback)
  priority: number;
};

const SUGGESTIONS: SuggestionCard[] = [
  { icon: 'pulse-outline', text: '今天的健康状况如何？', key: 'default', priority: 0 },
  { icon: 'moon-outline', text: '分析我的睡眠质量', key: 'default', priority: 0 },
  { icon: 'fitness-outline', text: '给我运动建议', key: 'default', priority: 0 },
  { icon: 'trending-up-outline', text: 'HRV趋势分析', key: 'default', priority: 0 },
];

// 悬浮输入栏: home indicator 安全区之上再抬起, 不贴屏幕最下缘。
// founder 2026-07-05: 12 太贴底(拇指要够到屏幕最下缘反而累), 抬进舒适拇指弧区。
const CHAT_BOTTOM_BREATHING_SPACE = 12;

// 对话历史无限下拉每页条数 (后端 limit 上限 100)
const HISTORY_PAGE_SIZE = 20;

function guessSuggestionIcon(text: string): SuggestionCard['icon'] {
  if (/体检|化验|指标|LDL|HbA1c|尿酸|血压|血脂|血糖/i.test(text)) return 'document-text-outline';
  if (/睡眠|打鼾|鼻塞|血氧|SpO2|HRV|静息心率|恢复/i.test(text)) return 'moon-outline';
  if (/训练|运动|跑步|骑行|力量|有氧|恢复/i.test(text)) return 'fitness-outline';
  if (/补剂|维生素|鱼油|叶酸|镁|药/i.test(text)) return 'medical-outline';
  if (/趋势|复盘|分析/i.test(text)) return 'trending-up-outline';
  return 'sparkles-outline';
}

function decorateSuggestions(items: SuggestionMeta[] | null | undefined): SuggestionCard[] | null {
  if (!items || !Array.isArray(items) || items.length === 0) return null;
  const decorated = items
    .filter((s) => s && typeof s.text === 'string' && s.text.trim().length > 0)
    .map((s) => ({
      text: s.text,
      icon: guessSuggestionIcon(s.text),
      key: s.key || 'unknown',
      priority: s.priority ?? 0,
    }))
    .slice(0, 4);
  return decorated.length > 0 ? decorated : null;
}

function getSelfReportedAdherence(reply: string): number | null {
  if (/没做|未做|没有做|不算/.test(reply)) return 0;
  if (/做到|完成|已做|做了/.test(reply)) return 70;
  return null;
}

/**
 * State A「小巴先开口」连续性: 把发送第一条消息时可见的开场气泡文本融成一句,
 * 作为合成 assistant 消息注入到流顶。opener 优先, 退化到记忆-only 气泡文本。
 * 返回 null → 当时没有可见开场(纯问候块) → 不注入。
 */
function buildOpeningContinuityText(
  opener: ConversationOpener | null,
  memoryOpener: MemoryOpenerItem[],
): string | null {
  const greeting = greetingForHour(new Date().getHours());
  if (opener) {
    return `${greeting}。${formatOpenerText(opener.text)}`;
  }
  const memoryText = formatMemoryOpenerText(memoryOpener);
  if (memoryText.length > 0) {
    return `${greeting}。${memoryText}`;
  }
  return null;
}

function ChatTimeDivider({ label }: { label: string }) {
  return (
    <View testID="message-time-divider" style={styles.timeDivider}>
      <Text style={txt.timeDivider}>{label}</Text>
    </View>
  );
}

export default function ChatScreen() {
  const { token: authToken } = useAuth();
  const chat = useChatEngine();
  const {
    messages,
    isStreaming,
    activeTurn,
    conversationId,
    sendMessage,
    stopStreaming,
    newChat,
    loadLatestConversation,
    loadConversation,
    setMessages,
  } = chat;
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  const forceScrollPending = useRef(false);
  const previousMessageCountRef = useRef(messages.length);
  const scrollTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  // 对话页只消费明确、及时的 timeline 状态；完整计划留在 Today surface。
  const todayTimeline = useTodayTimeline();
  const todayFocusModel = useMemo(
    () => buildTodayFocusModel({
      timeline: todayTimeline.data,
    }),
    [todayTimeline.data],
  );
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const [viewingImage, setViewingImage] = useState<string | null>(null);
  const [historyVisible, setHistoryVisible] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [historyLoadMoreError, setHistoryLoadMoreError] = useState(false);
  // 对话历史搜索(标题∪内容)。historySearch = 输入框受控值;ref = 当前生效检索词,
  // 供 loadMore 分页读到最新词(避免闭包读旧值);debounce ref 折叠连续输入的重拉。
  const [historySearch, setHistorySearch] = useState('');
  const historySearchRef = useRef('');
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [llmModelId, setLlmModelId] = useState<string | null>(null);
  const [llmOptions, setLlmOptions] = useState<ModelOption[]>([]);
  const [llmSaving, setLlmSaving] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedMessageIds, setSelectedMessageIds] = useState<Set<string>>(new Set());
  const [sharing, setSharing] = useState(false);
  // 「选一段对话成图」离屏渲染层的数据 + 截图 ref(非空时挂载 ConversationShareImage)。
  const [imageExportMessages, setImageExportMessages] = useState<ShareImageMessage[] | null>(null);
  const shareImageRef = useRef<View>(null);
  const [toolMenuVisible, setToolMenuVisible] = useState(false);
  const [dismissedTodayFocusKey, setDismissedTodayFocusKey] = useState<string | null>(null);

  const saveViewingImage = useCallback(async (uri: string) => {
    const source = buildChatImageSource(uri, authToken);
    if (!source) {
      Alert.alert('无法保存', '请重新登录后再试。');
      return;
    }
    try {
      await saveChatImageToLibrary(source);
      Alert.alert('已保存到相册');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || '');
      if (message === 'photo_permission_denied') {
        Alert.alert('需要照片权限', '请在 iPhone 设置中允许小巴添加照片。');
      } else {
        Alert.alert('保存失败', '请稍后重试。');
      }
    }
  }, [authToken]);

  const handleViewingImageLongPress = useCallback(() => {
    if (!viewingImage) return;
    Alert.alert('图片', undefined, [
      { text: '保存到相册', onPress: () => { void saveViewingImage(viewingImage); } },
      { text: '取消', style: 'cancel' },
    ]);
  }, [saveViewingImage, viewingImage]);

  // Context from alert / push / Siri deep-link. Read ONCE on first mount, then cleared.
  // autoSend=1 (from Siri HealthAnalysisOpenIntent) → directly send instead of prefilling.
  // context (JSON string) → 注入到 LLM system prompt 作为深化基础, 不展示在 user 消息里
  const params = useLocalSearchParams<{ prompt?: string; badge?: string; autoSend?: string; context?: string; newChat?: string; promptNonce?: string }>();
  const [contextBadge, setContextBadge] = useState<string | null>(null);
  const [initialInput, setInitialInput] = useState<string | undefined>(undefined);
  const [initialInputKey, setInitialInputKey] = useState(0);
  const [captureMealPhotoToken, setCaptureMealPhotoToken] = useState(0);
  const lastContextKey = useRef<string | null>(null);

  // P1: opener — chat tab mount 时拉一次, 用户发了第一条 message 后自动隐藏.
  // null = 还没拉到 / 无信号; 退化到默认 SUGGESTIONS chip.
  const [opener, setOpener] = useState<ConversationOpener | null>(null);
  const [starterSuggestions, setStarterSuggestions] = useState<SuggestionCard[]>(SUGGESTIONS);
  const [startersReady, setStartersReady] = useState(false);
  const [bootstrapReady, setBootstrapReady] = useState(false);
  // 冷启动 (零信号新用户): 后端带 onboarding=true。此时禁止把 starters 回落成
  // DEFAULT_SUGGESTIONS(那些假设有历史数据)——原样渲染后端返回的 onboarding chips。
  const [startersOnboarding, setStartersOnboarding] = useState(false);
  const refreshConversationStarters = useCallback(async (shouldSkip?: () => boolean) => {
    const { opener: newOpener, suggestions, onboarding } = await fetchConversationStarters();
    if (shouldSkip?.()) return;
    setOpener(newOpener);
    setStartersOnboarding(onboarding);
    const decorated = decorateSuggestions(suggestions);
    // 冷启动: 用后端返回的 starters 原样渲染(哪怕为空也不回注默认); 老用户: 保持默认兜底。
    setStarterSuggestions(decorated || (onboarding ? [] : SUGGESTIONS));
    setStartersReady(true);
  }, []);

  // 曝光埋点 (CTR 分母): 空状态 chips 真正展示给用户时发一次, 按 key 集合去重.
  // 只在 fetch 落定后发, 避免统计到拉取前默认 chips 的一闪. messages 非空时重置,
  // 这样新建对话回到空状态会重新计一次曝光.
  const shownStarterSigRef = useRef<string | null>(null);
  useEffect(() => {
    if (!startersReady || messages.length > 0) {
      if (messages.length > 0) shownStarterSigRef.current = null;
      return;
    }
    const keys = starterSuggestions.map(s => s.key);
    const sig = keys.join(',');
    if (!sig || sig === shownStarterSigRef.current) return;
    shownStarterSigRef.current = sig;
    void emitClientEvent('starter_chips_shown', { keys, source: 'chat' });
  }, [startersReady, messages.length, starterSuggestions]);

  // P3-3: 拉 top 1-2 条 memory, 显示在 opener 上方"我记得你: <X>"
  const [memoryOpener, setMemoryOpener] = useState<MemoryOpenerItem[]>([]);
  const refreshMemoryOpener = useCallback(async (shouldSkip?: () => boolean) => {
    const items = await fetchMemoryOpener(2);
    if (!shouldSkip?.()) setMemoryOpener(items);
  }, []);

  // Refs mirror current opener/memory/messages-empty so 值 can be read inside
  // 空依赖回调(键盘礼仪 focus 回调 + State A 连续性注入)。每渲染同步。
  const openerRef = useRef<ConversationOpener | null>(null);
  openerRef.current = opener;
  const memoryOpenerRef = useRef<MemoryOpenerItem[]>([]);
  memoryOpenerRef.current = memoryOpener;
  const messagesEmptyRef = useRef(true);
  messagesEmptyRef.current = messages.length === 0;

  const refreshCoachHomeState = useCallback(async () => {
    await Promise.all([
      refreshConversationStarters(),
      refreshMemoryOpener(),
    ]);
  }, [refreshConversationStarters, refreshMemoryOpener]);

  useEffect(() => {
    let cancelled = false;
    void loadAgentHomeBootstrap({ loadLatestConversation }).then(snapshot => {
      if (cancelled) return;
      setOpener(snapshot.opener);
      setStartersOnboarding(snapshot.onboarding);
      const decorated = decorateSuggestions(snapshot.suggestions);
      setStarterSuggestions(decorated || (snapshot.onboarding ? [] : SUGGESTIONS));
      setMemoryOpener(snapshot.memory);
      setLlmModelId(snapshot.llmPreference.model_id);
      setLlmOptions(snapshot.llmPreference.options || []);
      setLlmError(snapshot.errors.includes('llm_preference') ? '模型列表加载失败' : null);
      setStartersReady(true);
      setBootstrapReady(true);
    }).catch(() => {
      if (cancelled) return;
      setStartersReady(true);
      setBootstrapReady(true);
      setLlmError('模型列表加载失败');
    });
    return () => { cancelled = true; };
  }, [loadLatestConversation]);

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
        promptNonce: params.promptNonce ?? '',
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
          setInitialInputKey(key => key + 1);
        }
      }
      try { router.setParams({ prompt: undefined, badge: undefined, autoSend: undefined, context: undefined, newChat: undefined, promptNonce: undefined } as any); } catch {}
    } else {
      lastContextKey.current = null;
    }
  }, [newChat, params.prompt, params.badge, params.autoSend, params.context, params.newChat, params.promptNonce, sendMessage]);

  const clearChatScrollTimers = useCallback(() => {
    scrollTimersRef.current.forEach(clearTimeout);
    scrollTimersRef.current = [];
  }, []);

  // Markdown/card/image layout can settle in several passes. Keep a forced scroll
  // pending until the final retry, while ignoring non-user initial onScroll events.
  // A real drag cancels this flag immediately so history reading is never hijacked.
  const scheduleScrollToEnd = useCallback((options: { force?: boolean; animated?: boolean } = {}) => {
    const force = options.force ?? false;
    const animated = options.animated ?? false;
    if (force) {
      forceScrollPending.current = true;
      isNearBottom.current = true;
    } else if (!shouldScrollChatToEnd({
      forcePending: forceScrollPending.current,
      isNearBottom: isNearBottom.current,
    })) {
      return;
    }

    clearChatScrollTimers();
    const delays = [0, 80, 220, 480, 900];
    scrollTimersRef.current = delays.map((delay, index) => setTimeout(() => {
      if (!shouldScrollChatToEnd({
        forcePending: forceScrollPending.current,
        isNearBottom: isNearBottom.current,
      })) return;
      try { flatListRef.current?.scrollToEnd({ animated }); } catch {}
      if (index === delays.length - 1) forceScrollPending.current = false;
    }, delay));
  }, [clearChatScrollTimers]);

  useEffect(() => {
    const previousCount = previousMessageCountRef.current;
    if (shouldForceScrollAfterHydration(previousCount, messages.length)) {
      scheduleScrollToEnd({ force: true });
    }
    previousMessageCountRef.current = messages.length;
  }, [messages.length, scheduleScrollToEnd]);

  const cancelForcedScrollOnUserDrag = useCallback(() => {
    const state = {
      forcePending: forceScrollPending.current,
      isNearBottom: isNearBottom.current,
    };
    cancelChatScrollOnUserDrag(state);
    forceScrollPending.current = state.forcePending;
  }, []);

  useEffect(() => () => {
    clearChatScrollTimers();
    forceScrollPending.current = false;
  }, [clearChatScrollTimers]);

  // Page focus and app foreground both mean the user expects the newest answer.
  // Content-size changes continue the same request while streamed Markdown settles.
  useFocusEffect(
    useCallback(() => {
      scheduleScrollToEnd({ force: true });
      return clearChatScrollTimers;
    }, [clearChatScrollTimers, scheduleScrollToEnd])
  );

  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      const previousState = appStateRef.current;
      appStateRef.current = nextState;
      if ((previousState === 'background' || previousState === 'inactive') && nextState === 'active') {
        scheduleScrollToEnd({ force: true });
      }
    });
    return () => subscription.remove();
  }, [scheduleScrollToEnd]);

  // 「小巴先开口」键盘礼仪 (State A, 2026-07):
  // 只在小巴没话可说时(无 opener 且无记忆)才默认唤起键盘 —— 小巴有开场消息时
  // 不抢键盘, 让话先被看见(点输入框/chip 照常唤起)。有历史的对话也不弹。
  // opener fetch 是异步的: 首次 focus 时可能还没落定, 用 startersReady flag 推迟 bump 决定;
  // fetch 出错 → treat as blank → 照旧 bump。键盘已弹起后 opener 才到达 → 不回收(无 dismiss jank)。
  const [composerFocusToken, setComposerFocusToken] = useState(0);
  // startersReady 镜像成 ref, 供 focus 回调读(空依赖)。opener/memory/messages-empty
  // refs 已在上方声明。
  const startersReadyRef = useRef(false);
  startersReadyRef.current = startersReady;
  // 单次触发守卫: 每个 focus 会话只 bump 一次(blur 清理时复位)。
  // 也防测试环境 useFocusEffect mock 每渲染重跑导致 setState 死循环。
  const focusBumpedRef = useRef(false);
  // 有话可说(opener 或记忆)→ 抑制键盘; 没话(空 + fetch 已落定)→ 唤起。
  const shouldBumpKeyboard = useCallback(() => {
    if (!messagesEmptyRef.current) return false;
    if (openerRef.current) return false;
    if (memoryOpenerRef.current.length > 0) return false;
    return true;
  }, []);
  useFocusEffect(
    useCallback(() => {
      // fetch 还没落定 → 先不决定, 等 startersReady 那个 effect 补 bump。
      if (!focusBumpedRef.current && startersReadyRef.current && shouldBumpKeyboard()) {
        focusBumpedRef.current = true;
        setComposerFocusToken((n) => n + 1);
      }
      return () => { focusBumpedRef.current = false; };
    }, [shouldBumpKeyboard])
  );

  // opener fetch 落定后补一次 bump 决定: 若 focus 时 fetch 还没回、这里落定后
  // 判定小巴确实没话 → 唤起键盘。落定后有 opener/记忆 → 保持不弹。
  useEffect(() => {
    if (!startersReady) return;
    if (!focusBumpedRef.current && shouldBumpKeyboard()) {
      focusBumpedRef.current = true;
      setComposerFocusToken((n) => n + 1);
    }
  }, [startersReady, shouldBumpKeyboard]);

  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', (event) => {
      setKeyboardVisible(true);
      setKeyboardHeight(event.endCoordinates?.height || 0);
      scheduleScrollToEnd({ animated: true });
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => {
      setKeyboardVisible(false);
      setKeyboardHeight(0);
    });
    return () => { showSub.remove(); hideSub.remove(); };
  }, [scheduleScrollToEnd]);

  // State A: 用户发第一条消息时(空状态 + 有可见开场气泡), 把开场文本作为
  // 合成 assistant 消息注入到流顶, 让被回答的那句话不随空状态卸载而消失。
  // 只在 messages 为空时注入(prev.length===0 双保险); 合成消息 localOnly, 不落后端历史。
  // React 会把这次 setMessages 与紧随的 sendMessage 内部 setMessages 批处理:
  // [synthetic] → [synthetic, userMsg, aiMsg]。
  const injectOpeningContinuity = useCallback((activeOpener: ConversationOpener | null) => {
    if (messagesEmptyRef.current !== true) return;
    const text = buildOpeningContinuityText(activeOpener, memoryOpenerRef.current);
    if (!text) return;
    setMessages(prev => {
      if (prev.length > 0) return prev;
      return [{
        id: `opening-${Date.now()}`,
        role: 'assistant',
        content: text,
        localOnly: true,
        completionStatus: 'complete',
      }, ...prev];
    });
  }, [setMessages]);

  const handleSend = useCallback((text: string, images?: any, options?: ChatInputSendOptions) => {
    isNearBottom.current = true;
    injectOpeningContinuity(openerRef.current);
    scheduleScrollToEnd({ force: true, animated: true });
    return new Promise<boolean>((resolve) => {
      let settled = false;
      const resolveOnce = (accepted: boolean) => {
        if (settled) return;
        settled = true;
        if (accepted) setContextBadge(null);
        resolve(accepted);
      };
      void Promise.resolve(sendMessage(text, images, {
        ...(options?.extraContext ? { extraContext: options.extraContext } : {}),
        ...(options?.channel ? { channel: options.channel } : {}),
        onAccepted: resolveOnce,
      })).then(resolveOnce).catch(() => resolveOnce(false));
    });
  }, [injectOpeningContinuity, scheduleScrollToEnd, sendMessage]);

  const handleStarterPress = useCallback((s: EmptyStateSuggestion, position: number) => {
    // 点击埋点 (CTR 分子) — 旁路, 不阻塞发送
    void emitClientEvent('starter_chip_clicked', {
      key: s.key,
      priority: s.priority,
      position,
      source: 'chat',
    });
    handleSend(s.text, null);
  }, [handleSend]);

  // 冷启动 quick reply / Quick Start 卡的 action → 本地导航(不发文本)。
  // 埋点旁路, 不阻塞导航。路由映射的唯一真源在 utils/quickReplyAction.ts。
  const handleQuickAction = useCallback((action: QuickReplyAction) => {
    void emitClientEvent('cold_start_action_clicked', { action, source: 'chat' });
    navigateForQuickReplyAction(action);
  }, []);

  const handleMedicalExamImportResult = useCallback((result: ChatMedicalExamImportSkillResult) => {
    isNearBottom.current = true;
    setMessages(prev => [
      ...prev,
      {
        id: `medical-exam-import-${Date.now()}`,
        role: 'assistant',
        content: '',
        cardType: result.card.type,
        cardData: result.card.data,
        toolsUsed: [result.skillId],
      },
    ]);
    setContextBadge('体检导入结果');
    try {
      void emitClientEvent('chat_runtime_skill_completed', {
        skill_id: result.skillId,
        card_type: result.card.type,
      });
    } catch { /* noop */ }
    scheduleScrollToEnd({ animated: true });
  }, [scheduleScrollToEnd, setMessages]);

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
    injectOpeningContinuity(activeOpener);
    sendMessage(messageText, null, extraContext ? { extraContext } : undefined);
    scheduleScrollToEnd({ animated: true });
  }, [opener, injectOpeningContinuity, refreshCoachHomeState, scheduleScrollToEnd, sendMessage]);

  // 加载第一页 (打开 sheet / 重试 / 搜索变化时调用) — 重置所有分页状态。
  // search 可显式传入(搜索变化);缺省(如 onRetry 传进来的按压事件对象)→ 读 ref 里的生效词。
  const loadConversationHistory = useCallback(async (search?: string) => {
    const q = (typeof search === 'string' ? search : historySearchRef.current).trim();
    historySearchRef.current = q;
    setHistoryLoading(true);
    setHistoryError(null);
    setHistoryLoadMoreError(false);
    try {
      const { items, total } = await getConversationsPage({
        offset: 0, limit: HISTORY_PAGE_SIZE, search: q || undefined,
      });
      setConversations(items);
      setHistoryTotal(total);
    } catch {
      setHistoryError('加载历史对话失败');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // 下拉到底 → 追加下一页。按 id 去重, 不打乱已有顺序 (并发保护)。
  const loadMoreConversations = useCallback(async () => {
    if (historyLoading || historyLoadingMore) return;
    // 用函数式读到当前长度, 避免闭包读到旧的 conversations
    let currentLen = 0;
    setConversations(prev => { currentLen = prev.length; return prev; });
    if (currentLen >= historyTotal) return;
    setHistoryLoadingMore(true);
    setHistoryLoadMoreError(false);
    try {
      const { items, total } = await getConversationsPage({
        offset: currentLen,
        limit: HISTORY_PAGE_SIZE,
        search: historySearchRef.current || undefined,
      });
      setHistoryTotal(total);
      setConversations(prev => {
        const seen = new Set(prev.map((c: any) => c.id));
        const appended = items.filter((c: any) => !seen.has(c.id));
        return appended.length > 0 ? [...prev, ...appended] : prev;
      });
    } catch {
      setHistoryLoadMoreError(true);
    } finally {
      setHistoryLoadingMore(false);
    }
  }, [historyLoading, historyLoadingMore, historyTotal]);

  // 搜索输入变化:立即更新受控值(输入跟手),debounce 300ms 后按新词重拉第一页。
  const handleHistorySearchChange = useCallback((text: string) => {
    setHistorySearch(text);
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      loadConversationHistory(text);
    }, 300);
  }, [loadConversationHistory]);

  const openHistory = useCallback(() => {
    setToolMenuVisible(false);
    setHistoryVisible(true);
    // 每次打开清空上次检索词,回到"全部对话"起点(避免复用旧过滤困惑用户)。
    setHistorySearch('');
    historySearchRef.current = '';
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    loadConversationHistory('');
  }, [loadConversationHistory]);

  // 卸载时清掉未触发的 debounce timer,避免对已卸载组件 setState。
  useEffect(() => () => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
  }, []);

  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedMessageIds(new Set());
  }, []);

  const handleNewChat = useCallback(() => {
    setToolMenuVisible(false);
    exitSelectionMode();
    setContextBadge(null);
    setComposerFocusToken((n) => n + 1);
    newChat();
    void refreshCoachHomeState();
  }, [exitSelectionMode, newChat, refreshCoachHomeState]);

  const handleOpenToday = useCallback(() => {
    router.navigate('/(tabs)/today');
  }, []);

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
    scheduleScrollToEnd({ force: true });
    setContextBadge(null);
    setSelectionMode(false);
    setSelectedMessageIds(new Set());
  }, [loadConversation, scheduleScrollToEnd]);

  const handleDeleteConversation = useCallback(async (id: number) => {
    const ok = await deleteConversation(id);
    if (!ok) {
      setHistoryError('删除失败，请稍后重试');
      return;
    }
    setConversations(prev => {
      const next = prev.filter(item => item.id !== id);
      if (next.length !== prev.length) setHistoryTotal(t => Math.max(0, t - 1));
      return next;
    });
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
    // 先算出下一个 Set 再 setState — updater 内不做副作用 (setSelectionMode),
    // 避免并发渲染下 updater 重放导致 double-fire.
    const next = new Set(selectedMessageIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedMessageIds(next);
    if (next.size === 0) {
      setSelectionMode(false);
    }
  }, [selectedMessageIds]);

  // 微信式: 气泡长按先出操作区; 点"选择"后进入多选并默认选中该条.
  const enterSelectionWith = useCallback((id: string) => {
    setSelectionMode(true);
    setSelectedMessageIds(new Set([id]));
  }, []);

  const sendSuggestedPrompt = useCallback((prompt: string) => {
    if (isStreaming) return;
    void sendMessage(prompt, null);
  }, [isStreaming, sendMessage]);

  const shareSelectedMessages = useCallback(async () => {
    const message = buildSelectedChatShareMessage(messages, selectedMessageIds);
    if (!message || sharing) return;
    setSharing(true);
    try {
      await sharePlainText({ title: '小巴 · 对话节选', message });
      exitSelectionMode();
    } catch {
      Alert.alert('分享失败', '请稍后重试');
    } finally {
      setSharing(false);
    }
  }, [exitSelectionMode, messages, selectedMessageIds, sharing]);

  // 「选一段对话成图」:把选中消息渲染进离屏品牌长图 → captureRef 截 PNG → 分享/存图。
  const exportSelectedImage = useCallback(async () => {
    if (sharing) return;
    const selected: ShareImageMessage[] = messages
      .filter((m) => selectedMessageIds.has(m.id) && isShareableChatMessage(m))
      .map((m) => ({ id: m.id, role: m.role, content: m.content, imageUris: m.imageUris }));
    if (selected.length === 0) return;
    setSharing(true);
    setImageExportMessages(selected);
    // 等离屏层排版完(markdown/长内容异步),再截。捕获后清理离屏层。
    setTimeout(async () => {
      try {
        if (!shareImageRef.current) throw new Error('share image not mounted');
        const uri = await captureRef(shareImageRef.current, {
          format: 'png', quality: 1, result: 'tmpfile',
        });
        await shareLocalImage(uri);
        exitSelectionMode();
      } catch {
        Alert.alert('生成长图失败', '请稍后重试');
      } finally {
        setImageExportMessages(null);
        setSharing(false);
      }
    }, 280);
  }, [exitSelectionMode, messages, selectedMessageIds, sharing]);

  const renderMessage = useCallback(({ item }: { item: ChatMessageListItem }) => {
    if (item.type === 'divider') {
      return <ChatTimeDivider label={item.label} />;
    }
    const message = item.message;
    const shareable = isShareableChatMessage(message);
    return (
      <ChatBubble
        item={message}
        onViewImage={setViewingImage}
        imageAuthToken={authToken}
        selectionMode={selectionMode && shareable}
        selected={selectedMessageIds.has(message.id)}
        onToggleSelected={toggleMessageSelection}
        onEnterSelection={!selectionMode && shareable ? enterSelectionWith : undefined}
        onSendSuggestedPrompt={sendSuggestedPrompt}
        onStopStreaming={stopStreaming}
      />
    );
  }, [authToken, selectedMessageIds, selectionMode, toggleMessageSelection, enterSelectionWith, sendSuggestedPrompt, stopStreaming]);

  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  // 小巴是 agent-native 主屏,没有底部 Tab Bar。键盘弹起时直接为键盘留位;
  // 收起时 = 底部安全区(SafeAreaView 只包 top, home indicator 由这里补) + 呼吸空间,
  // 输入栏悬浮在 home indicator 之上而非压进去(founder 2026-07-05: 参考阿福)。
  const bottomSpacerHeight = keyboardVisible
    ? (Platform.OS === 'ios' ? keyboardHeight : 0)
    : insets.bottom + CHAT_BOTTOM_BREATHING_SPACE;
  const activeLlmLabel = llmModelId
    ? llmOptions.find(option => option.id === llmModelId)?.label || llmModelId
    : '系统默认';
  const activeTurnVisible = activeTurn.phase !== 'idle' && activeTurn.phase !== 'completed';
  const currentTurnUserMessage = [...messages].reverse().find(message => (
    message.role === 'user'
    && (!activeTurn.turnId || message.sourceTurnId === activeTurn.turnId)
  ));
  const retryableTextMessage = currentTurnUserMessage
    && !!currentTurnUserMessage.content?.trim()
    && currentTurnUserMessage.content !== '(图片)'
    && (!currentTurnUserMessage.imageUris || currentTurnUserMessage.imageUris.length === 0)
    ? currentTurnUserMessage
    : undefined;
  const turnStatus = activeTurnVisible
    ? {
        label: activeTurn.label || (
          activeTurn.phase === 'failed' || activeTurn.phase === 'interrupted'
            ? '上一轮未完成，内容已保留'
            : '小巴正在处理…'
        ),
        tone: activeTurn.phase === 'failed' || activeTurn.phase === 'interrupted'
          ? 'error' as const
          : 'active' as const,
        retryable: !!(
          activeTurn.recoverable
          && retryableTextMessage
          && !isStreaming
          && (activeTurn.phase === 'failed' || activeTurn.phase === 'interrupted')
        ),
      }
    : undefined;
  const visibleTodayFocusModel = todayFocusModel.contextStrip?.key === dismissedTodayFocusKey
    ? { ...todayFocusModel, contextStrip: null }
    : todayFocusModel;
  const messageListItems = useMemo(
    () => buildMessageTimeDividerItems(messages),
    [messages],
  );
  const retryLastTextTurn = () => {
    if (!retryableTextMessage || isStreaming) return;
    void sendMessage(retryableTextMessage.content, null);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" backgroundColor={C.paper} translucent={false} />
      <ChatHeader
        activeLlmLabel={activeLlmLabel}
        llmModelId={llmModelId}
        llmOptions={llmOptions}
        llmSaving={llmSaving}
        llmError={llmError}
        isStreaming={isStreaming}
        onSelectModel={handleSelectModel}
        onNewChat={handleNewChat}
        onOpenHistory={openHistory}
        onOpenToolMenu={() => setToolMenuVisible(true)}
      />

      <ChatTodayFocusCard
        model={visibleTodayFocusModel}
        turnStatus={turnStatus}
        onRetry={turnStatus?.retryable ? retryLastTextTurn : undefined}
        onOpenToday={handleOpenToday}
        onDismiss={visibleTodayFocusModel.contextStrip
          ? () => setDismissedTodayFocusKey(visibleTodayFocusModel.contextStrip?.key ?? null)
          : undefined}
      />

      <View style={{ flex: 1 }}>
        <FlatList
          ref={flatListRef}
          testID="chat-message-list"
          style={styles.messageListViewport}
          data={messageListItems}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          contentContainerStyle={styles.messageList}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="always"
          onContentSizeChange={() => {
            if (shouldScrollChatToEnd({
              forcePending: forceScrollPending.current,
              isNearBottom: isNearBottom.current,
            })) {
              try { flatListRef.current?.scrollToEnd({ animated: true }); } catch {}
            }
          }}
          onScrollBeginDrag={cancelForcedScrollOnUserDrag}
          onScroll={(e) => {
            // The first layout can emit an offset=0 scroll event before the forced
            // opening scroll runs. It is not user intent and must not cancel it.
            if (forceScrollPending.current) return;
            const { layoutMeasurement, contentOffset, contentSize } = e.nativeEvent;
            isNearBottom.current = contentSize.height - contentOffset.y - layoutMeasurement.height < 120;
          }}
          scrollEventThrottle={100}
          ListEmptyComponent={
            bootstrapReady ? (
              <EmptyStateHome
                memoryOpener={memoryOpener}
                opener={opener}
                onOpenMemory={() => router.push('/memory')}
                onOpenerQuickReply={handleOpenerQuickReply}
                onboarding={startersOnboarding}
                onQuickAction={handleQuickAction}
              />
            ) : <AgentHomeBootstrapLoading />
          }
        />

        {contextBadge && (
          <View style={styles.contextBanner}>
            <Ionicons name="link-outline" size={13} color={C.green500} />
            <Text style={txt.contextBanner} numberOfLines={1}>
              基于 {contextBadge}
            </Text>
            <TouchableOpacity onPress={() => setContextBadge(null)} hitSlop={8}>
              <Ionicons name="close" size={14} color={C.ink3} />
            </TouchableOpacity>
          </View>
        )}

        {selectionMode && (
          <View style={styles.shareBar}>
            <TouchableOpacity
              onPress={exitSelectionMode}
              hitSlop={8}
              style={styles.cancelSelectionButton}
              accessibilityLabel="取消多选"
              accessibilityRole="button"
            >
              <Ionicons name="close" size={16} color={C.ink2} />
              <Text style={txt.cancelSelectionButton}>取消</Text>
            </TouchableOpacity>
            <View style={{ flex: 1 }}>
              <Text style={txt.shareBarTitle}>已选择 {selectedMessageIds.size} 条</Text>
              <Text style={txt.shareBarSub}>按当前对话顺序生成分享链接</Text>
            </View>
            <TouchableOpacity
              onPress={exportSelectedImage}
              disabled={selectedMessageIds.size === 0 || sharing}
              style={[styles.cancelSelectionButton, (selectedMessageIds.size === 0 || sharing) && styles.shareButtonDisabled]}
              accessibilityLabel="选中消息生成长图"
              accessibilityRole="button"
            >
              <Ionicons name="image-outline" size={16} color={C.green500} />
              <Text style={txt.cancelSelectionButton}>长图</Text>
            </TouchableOpacity>
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

        {/* 「选一段对话成图」离屏渲染层 —— 非空时挂载, captureRef 截图后清空。off-screen
            定位(不遮挡 UI)但完整排版, captureRef 拿全高长图。 */}
        {imageExportMessages && (
          <View style={styles.offscreenCapture} pointerEvents="none">
            <ConversationShareImage
              ref={shareImageRef}
              messages={imageExportMessages}
              dateLabel={new Date().toLocaleDateString('zh-CN')}
            />
          </View>
        )}
        {bootstrapReady && messages.length === 0 && !selectionMode && (
          <ComposerSuggestionsRow
            suggestions={starterSuggestions}
            onCapturePhoto={() => setCaptureMealPhotoToken(token => token + 1)}
            onSuggestionPress={handleStarterPress}
            showCapturePhoto={!startersOnboarding}
          />
        )}
        <ChatInputBar
          onSend={handleSend}
          isStreaming={isStreaming}
          initialText={initialInput}
          initialTextKey={initialInputKey}
          conversationId={conversationId}
          onMedicalExamImportResult={handleMedicalExamImportResult}
          autoFocusToken={composerFocusToken}
          captureMealPhotoToken={captureMealPhotoToken}
        />
        <View testID="chat-bottom-spacer" style={{ height: bottomSpacerHeight }} />
      </View>

      <Modal visible={!!viewingImage} transparent animationType="fade" onRequestClose={() => setViewingImage(null)}>
        <Pressable style={styles.imageViewerOverlay} onPress={() => setViewingImage(null)}>
          {viewingImage && (
            <Pressable
              onPress={(event) => event.stopPropagation()}
              onLongPress={handleViewingImageLongPress}
              accessibilityRole="imagebutton"
              accessibilityLabel="预览图片，长按可保存"
            >
              <Image
                source={buildChatImageSource(viewingImage, authToken)}
                style={{ width: windowWidth - 32, height: windowHeight * 0.7 }}
                contentFit="contain"
              />
            </Pressable>
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
                <Text style={txt.toolSheetTitle}>更多操作</Text>
                <Text style={txt.toolSheetSub}>个人中心、分享与对话管理</Text>
              </View>
              <TouchableOpacity onPress={() => setToolMenuVisible(false)} hitSlop={8} accessibilityLabel="关闭更多操作">
                <Ionicons name="close" size={22} color={C.ink2} />
              </TouchableOpacity>
            </View>
            <ToolMenuRow
              icon="calendar-outline"
              label="今日计划"
              onPress={() => {
                setToolMenuVisible(false);
                handleOpenToday();
              }}
            />
            <ToolMenuRow
              icon="person-circle-outline"
              label="我 · 个人中心与设置"
              onPress={() => {
                setToolMenuVisible(false);
                router.navigate('/(tabs)/me');
              }}
            />
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
        onRetry={() => loadConversationHistory()}
        hasMore={conversations.length < historyTotal}
        loadingMore={historyLoadingMore}
        loadMoreError={historyLoadMoreError}
        onLoadMore={loadMoreConversations}
        total={historyTotal}
        searchValue={historySearch}
        onSearchChange={handleHistorySearchChange}
      />
    </SafeAreaView>
  );
}

function AgentHomeBootstrapLoading() {
  return (
    <View accessibilityLabel="正在准备小巴" style={styles.bootstrapLoading}>
      <ActivityIndicator size="small" color={C.green500} />
      <Text style={txt.bootstrapLoading}>正在准备小巴…</Text>
    </View>
  );
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
  const color = destructive ? revaSemantic.risk.fg : C.ink1;
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
      <Ionicons name="chevron-forward" size={14} color={C.ink3} style={{ marginLeft: 'auto' }} />
    </TouchableOpacity>
  );
}

// Reva 设计语言: 暖白 paper 屏底 / surface 卡 / green500 主色 / r-lg 18 / 软阴影. 文字走 Manrope.
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  messageListViewport: { flex: 1, minHeight: 0 },
  messageList: { padding: revaSpacing.s4, paddingBottom: 8 },
  timeDivider: {
    alignSelf: 'center',
    marginTop: 2,
    marginBottom: 12,
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  bootstrapLoading: {
    minHeight: 112,
    alignItems: 'center',
    justifyContent: 'center',
    gap: revaSpacing.s2,
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
    paddingHorizontal: revaSpacing.s4,
    paddingTop: 82,
  },
  toolSheet: {
    backgroundColor: C.paper,
    borderRadius: revaRadii.xl,
    padding: revaSpacing.s3,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.lg,
  },
  toolSheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: revaSpacing.s3,
    paddingBottom: revaSpacing.s2,
  },
  toolMenuRow: {
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  contextBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginHorizontal: revaSpacing.s4, marginBottom: 4,
    paddingHorizontal: revaSpacing.s3, paddingVertical: 6,
    backgroundColor: C.green50, borderRadius: revaRadii.md,
  },
  offscreenCapture: {
    position: 'absolute',
    left: -10000,
    top: 0,
  },
  shareBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s3,
    marginHorizontal: revaSpacing.s4,
    marginBottom: 8,
    padding: revaSpacing.s3,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  cancelSelectionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  shareButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green500,
  },
  shareButtonDisabled: {
    opacity: 0.45,
  },
});

const txt = {
  bootstrapLoading: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, fontWeight: '700' } as TextStyle,
  timeDivider: { fontFamily: revaFonts.mono, fontSize: 10.5, lineHeight: 14, color: C.ink3, fontWeight: '700' } as TextStyle,
  contextBanner: { fontFamily: revaFonts.sans, fontSize: 12, color: C.green500, flex: 1, fontWeight: '500' } as TextStyle,
  shareBarTitle: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1, fontWeight: '700' } as TextStyle,
  shareBarSub: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 2 } as TextStyle,
  cancelSelectionButton: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, fontWeight: '700' } as TextStyle,
  shareButton: { fontFamily: revaFonts.sans, fontSize: 13, color: '#fff', fontWeight: '700' } as TextStyle,
  toolSheetTitle: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '800', color: C.ink1 } as TextStyle,
  toolSheetSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 2 } as TextStyle,
  toolMenuText: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '700' } as TextStyle,
};
