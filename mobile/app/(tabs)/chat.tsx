import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  Platform, TextStyle,
  Alert, Dimensions, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router, useFocusEffect } from 'expo-router';
import { deleteConversation, getConversationsPage, updateConversationTitle } from '../../services/chat';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import ChatInputBar, { type ChatInputSendOptions } from '../../components/chat/ChatInputBar';
import ChatBubble from '../../components/chat/ChatBubble';
import ConversationSheet from '../../components/chat/ConversationSheet';
import ChatHeader from '../../components/chat/ChatHeader';
import BriefingStrip from '../../components/chat/BriefingStrip';
import TodayContent from '../../components/home/TodayContent';
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
import { getLlmPreference, updateLlmPreference, type ModelOption } from '../../services/llmPreference';
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
import { sharePlainText } from '../../utils/share';
import { buildSelectedChatShareMessage, isShareableChatMessage } from '../../utils/chatShareSelection';
import type { ChatMedicalExamImportSkillResult } from '../../services/chatMedicalExamImportSkill';

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
const CHAT_BOTTOM_BREATHING_SPACE = 28;

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

export default function ChatScreen() {
  const chat = useChatEngine();
  const {
    messages,
    isStreaming,
    conversationId,
    sendMessage,
    newChat,
    loadLatestConversation,
    loadConversation,
    setMessages,
    setPerMessageModelId,
  } = chat;
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  // 今日简报条：真实数字来自 /timeline/today（待办 / 已完成计数），不伪造指标。
  const todayTimeline = useTodayTimeline();
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
  const [historySearch, setHistorySearch] = useState(''); // 会话搜索词(标题+内容)
  // fetch 回调用 ref 读到最新搜索词(避免 stale 闭包 + 反复重建 callback)
  const historySearchRef = useRef('');
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
  const params = useLocalSearchParams<{ prompt?: string; badge?: string; autoSend?: string; context?: string; newChat?: string; promptNonce?: string }>();
  const [contextBadge, setContextBadge] = useState<string | null>(null);
  const [initialInput, setInitialInput] = useState<string | undefined>(undefined);
  const [initialInputKey, setInitialInputKey] = useState(0);
  const lastContextKey = useRef<string | null>(null);

  // P1: opener — chat tab mount 时拉一次, 用户发了第一条 message 后自动隐藏.
  // null = 还没拉到 / 无信号; 退化到默认 SUGGESTIONS chip.
  const [opener, setOpener] = useState<ConversationOpener | null>(null);
  const [starterSuggestions, setStarterSuggestions] = useState<SuggestionCard[]>(SUGGESTIONS);
  const [startersReady, setStartersReady] = useState(false);
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
      // 选择器显示什么模型, 消息就用什么模型: 恢复的档案选择也按显式 model_id
      // 逐条消息下发 (显式选择不被快路由覆盖); null=系统默认(智能路由)。
      setPerMessageModelId(pref.model_id);
    }).catch(() => {
      if (!cancelled) setLlmError('模型列表加载失败');
    });
    return () => { cancelled = true; };
  }, [setPerMessageModelId]);

  const handleSelectModel = useCallback(async (modelId: string | null) => {
    if (llmSaving || llmModelId === modelId) return;
    setLlmSaving(modelId || '__default__');
    setLlmError(null);
    try {
      const pref = await updateLlmPreference(modelId);
      setLlmModelId(pref.model_id);
      setLlmOptions(pref.options || []);
      setPerMessageModelId(pref.model_id);
    } catch (e: any) {
      setLlmError(e?.response?.data?.detail || e?.message || '模型切换失败');
    } finally {
      setLlmSaving(null);
    }
  }, [llmModelId, llmSaving, setPerMessageModelId]);

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

  useEffect(() => { loadLatestConversation(); }, [loadLatestConversation]);

  // 点"小巴" tab 进来时滚到对话最后, 方便看最新消息.
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
    // 豆包等第三方输入法首次唤起:键盘扩展进程冷启动,didShow 先报一个未装载完
    // 的高度,装载完成后只发 (will|did)ChangeFrame **不再发 didShow** —— 只抓一次
    // didShow 的高度会停在旧值,输入栏被压在键盘底下(founder 实锤截图)。
    // 修:持续跟 frame 事件走。有 screenY 时用「窗口高 - 键盘顶边」的重叠高度
    // (隐藏帧 screenY≥窗口高 → 0,天然处理 hide);无 screenY(测试/老事件)退回 height。
    const applyKeyboardFrame = (event: any) => {
      const end = event?.endCoordinates;
      if (!end) return;
      const windowH = Dimensions.get('window').height;
      const height = typeof end.screenY === 'number'
        ? Math.max(0, Math.round(windowH - end.screenY))
        : Math.max(0, Math.round(end.height || 0));
      setKeyboardVisible(height > 0);
      setKeyboardHeight(height);
    };
    const subs = [
      Keyboard.addListener('keyboardDidShow', (event) => {
        applyKeyboardFrame(event);
        setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
      }),
      Keyboard.addListener('keyboardWillChangeFrame', applyKeyboardFrame),
      Keyboard.addListener('keyboardDidChangeFrame', applyKeyboardFrame),
      Keyboard.addListener('keyboardDidHide', () => {
        setKeyboardVisible(false);
        setKeyboardHeight(0);
      }),
    ];
    return () => { subs.forEach(s => s.remove()); };
  }, []);

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
    setBriefingExpanded(false); // 发消息即收起今日面板,回到对话流
    injectOpeningContinuity(openerRef.current);
    sendMessage(text, images, options?.extraContext ? { extraContext: options.extraContext } : undefined);
    setContextBadge(null);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [injectOpeningContinuity, sendMessage]);

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
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 80);
  }, [setMessages]);

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
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [opener, injectOpeningContinuity, refreshCoachHomeState, sendMessage]);

  // 加载第一页 (打开 sheet / 重试 / 搜索变化时调用) — 重置所有分页状态。
  const loadConversationHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    setHistoryLoadMoreError(false);
    try {
      const { items, total } = await getConversationsPage({
        offset: 0, limit: HISTORY_PAGE_SIZE, search: historySearchRef.current,
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
        search: historySearchRef.current,
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

  const openHistory = useCallback(() => {
    setToolMenuVisible(false);
    // 每次打开清空搜索,始终从全量历史开始(ref 同步清,openHistory 拉取读到空)
    historySearchRef.current = '';
    setHistorySearch('');
    setHistoryVisible(true);
    loadConversationHistory();
  }, [loadConversationHistory]);

  // 搜索词变化:同步更新 ref(fetch 回调读它)+ 受控 state。
  const onHistorySearchChange = useCallback((v: string) => {
    historySearchRef.current = v;
    setHistorySearch(v);
  }, []);

  // 搜索防抖:仅 historySearch 变化触发(不依赖 historyVisible,避免开 sheet 时
  // 与 openHistory 的即时拉取双拉)。sheet 未开时早退。
  useEffect(() => {
    if (!historyVisible) return;
    const t = setTimeout(() => { loadConversationHistory(); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historySearch]);

  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedMessageIds(new Set());
  }, []);

  // 今日简报条可见性: 冷启显示; 用户点 X 或新建对话后隐藏(founder: 新窗口要干净画布)。
  const [briefingHidden, setBriefingHidden] = useState(false);
  // agent-native:今日在对话页内联展开(动态 UI 面板),不跳独立 sheet 页。
  const [briefingExpanded, setBriefingExpanded] = useState(false);

  const handleNewChat = useCallback(() => {
    setToolMenuVisible(false);
    exitSelectionMode();
    setContextBadge(null);
    setBriefingHidden(true);
    setComposerFocusToken((n) => n + 1);
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

  // 微信式: 长按某条消息 → 进入多选模式并默认选中该条.
  const enterSelectionWith = useCallback((id: string) => {
    setSelectionMode(true);
    setSelectedMessageIds(new Set([id]));
  }, []);

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

  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const shareable = isShareableChatMessage(item);
    return (
      <ChatBubble
        item={item}
        onViewImage={setViewingImage}
        selectionMode={selectionMode && shareable}
        selected={selectedMessageIds.has(item.id)}
        onToggleSelected={toggleMessageSelection}
        onEnterSelection={!selectionMode && shareable ? enterSelectionWith : undefined}
      />
    );
  }, [selectedMessageIds, selectionMode, toggleMessageSelection, enterSelectionWith]);

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

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
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

      {/* 今日简报条(agent-native):点按在对话页内联展开「今日」动态 UI 面板，不跳独立页。 */}
      {!briefingHidden && (
        <BriefingStrip
          timeline={todayTimeline.data}
          expanded={briefingExpanded}
          onPress={() => setBriefingExpanded(v => !v)}
          onDismiss={briefingExpanded ? undefined : () => setBriefingHidden(true)}
        />
      )}

      <View style={{ flex: 1 }}>
        {/* 展开态：今日以内联面板呈现在对话页（占据消息区），composer 仍在下方；收起回到对话。 */}
        {briefingExpanded ? (
          <View testID="chat-today-inline-panel" style={{ flex: 1 }}>
            <TodayContent mode="inline" />
          </View>
        ) : (
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
            <EmptyStateHome
              memoryOpener={memoryOpener}
              opener={opener}
              onOpenMemory={() => router.push('/memory')}
              onOpenerQuickReply={handleOpenerQuickReply}
              onboarding={startersOnboarding}
              onQuickAction={handleQuickAction}
            />
          }
        />
        )}

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
        {messages.length === 0 && !selectionMode && (
          <ComposerSuggestionsRow
            suggestions={starterSuggestions}
            onCapturePhoto={() => router.push('/diet?capture=photo' as any)}
            onSuggestionPress={handleStarterPress}
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
        />
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
                <Text style={txt.toolSheetSub}>个人中心、分享、删除等低频操作</Text>
              </View>
              <TouchableOpacity onPress={() => setToolMenuVisible(false)} hitSlop={8} accessibilityLabel="关闭会诊工具">
                <Ionicons name="close" size={22} color={C.ink2} />
              </TouchableOpacity>
            </View>
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
        onRetry={loadConversationHistory}
        hasMore={conversations.length < historyTotal}
        loadingMore={historyLoadingMore}
        loadMoreError={historyLoadMoreError}
        onLoadMore={loadMoreConversations}
        total={historyTotal}
        searchValue={historySearch}
        onSearchChange={onHistorySearchChange}
      />
    </SafeAreaView>
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
  messageList: { padding: revaSpacing.s4, paddingBottom: 8 },
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
  contextBanner: { fontFamily: revaFonts.sans, fontSize: 12, color: C.green500, flex: 1, fontWeight: '500' } as TextStyle,
  shareBarTitle: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1, fontWeight: '700' } as TextStyle,
  shareBarSub: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 2 } as TextStyle,
  cancelSelectionButton: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, fontWeight: '700' } as TextStyle,
  shareButton: { fontFamily: revaFonts.sans, fontSize: 13, color: '#fff', fontWeight: '700' } as TextStyle,
  toolSheetTitle: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '800', color: C.ink1 } as TextStyle,
  toolSheetSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 2 } as TextStyle,
  toolMenuText: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '700' } as TextStyle,
};
