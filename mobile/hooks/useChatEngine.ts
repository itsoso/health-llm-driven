import { useState, useRef, useCallback, useEffect } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';
import * as Haptics from 'expo-haptics';
import NetInfo from '@react-native-community/netinfo';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { streamChat, getConversations, getConversationMessages, deleteConversation, type ChatMessage, type LlmUsageProfile, type AgentPerfProfile } from '../services/chat';
import { dispatchCard, renderServerCards } from '../components/chat/cards';
import type { ChatCardActionDescriptor, ServerCardDescriptor } from '../components/chat/cards/types';
import api, { BASE_URL } from '../services/api';
import { emitClientEvent } from '../services/clientEvents';
import { sanitizeChatErrorMessage } from '../utils/chatErrorMessage';

function normalizeImageHost(baseUrl: string): string {
  return String(baseUrl || '').replace(/\/+$/, '').replace(/\/api(?:\/v\d+)?$/, '');
}

const IMAGE_HOST = normalizeImageHost(BASE_URL);

export interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  thinkingSteps?: string[];
  imageUris?: string[];
  isBriefing?: boolean;
  cardType?: string;
  cardData?: any;
  cardActions?: ChatCardActionDescriptor[];
  createdAt?: string;
  fromSiri?: boolean;
  // 2026-05-13: 性能可观测 — done 事件的耗时 + 模型名, 渲染在 assistant 气泡底部
  elapsedMs?: number;
  llmMs?: number;
  llmRounds?: number;
  llmRoundsMs?: number[];
  model?: string;
  llmUsage?: LlmUsageProfile;
  perf?: AgentPerfProfile;
  // 2026-05-14 #4: 可解释性 — AI 用了什么数据
  sourcesUsed?: string[];
  // 2026-06-12: 本轮调用的 Skill / 工具名 (后端 done.tools_used / meta.tools_used), 对齐 mac/web
  toolsUsed?: string[];
  completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
}

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }

/** 2026-05-14 FIX-7: 把 message.meta (后端持久化的性能/可解释性 JSON)
 * 映射到 UIMessage 字段, 让 reload 也能恢复 chat bubble footer. */
function applyMeta(msg: any): Partial<UIMessage> {
  const meta = msg?.meta;
  if (!meta || typeof meta !== 'object') return {};
  return {
    elapsedMs: typeof meta.elapsed_ms === 'number' ? meta.elapsed_ms : undefined,
    llmMs: typeof meta.llm_ms === 'number' ? meta.llm_ms : undefined,
    llmRounds: typeof meta.llm_rounds === 'number' ? meta.llm_rounds : undefined,
    llmRoundsMs: Array.isArray(meta.llm_rounds_ms) ? meta.llm_rounds_ms : undefined,
    model: typeof meta.model === 'string' ? meta.model : undefined,
    llmUsage: meta.llm_usage && typeof meta.llm_usage === 'object' ? meta.llm_usage : undefined,
    perf: meta.perf && typeof meta.perf === 'object' ? meta.perf : undefined,
    sourcesUsed: Array.isArray(meta.sources_used) ? meta.sources_used : undefined,
    toolsUsed: Array.isArray(meta.tools_used) ? meta.tools_used : undefined,
    completionStatus: typeof meta.completion_status === 'string' ? meta.completion_status : undefined,
  };
}

function absolutizeHistoryImageUri(uri: string, imageHost: string): string | undefined {
  const value = String(uri || '').trim();
  if (!value) return undefined;
  if (/^(https?:|file:|data:)/i.test(value)) return value;
  const host = normalizeImageHost(imageHost);
  if (!host) return value;
  return value.startsWith('/') ? `${host}${value}` : `${host}/${value}`;
}

function parseHistoryImageUris(raw: any, imageHost: string): string[] | undefined {
  if (!raw) return undefined;
  let parsed: any = raw;
  try {
    if (typeof raw === 'string') {
      parsed = JSON.parse(raw);
    }
  } catch {
    parsed = raw;
  }
  const values = Array.isArray(parsed) ? parsed : (typeof parsed === 'string' ? [parsed] : []);
  const uris = values
    .filter((u: any): u is string => typeof u === 'string')
    .map((u: string) => absolutizeHistoryImageUri(u, imageHost))
    .filter((u: string | undefined): u is string => !!u);
  return uris.length > 0 ? uris : undefined;
}

/** Restore durable chat messages plus server-rendered cards from history.
 *
 * Live streams render cards from the `done.cards` payload. The backend also
 * persists the same descriptors under assistant `message.meta.cards`; history
 * reloads must flatten those descriptors back into card messages or cards will
 * disappear after reopening a conversation.
 */
export function restoreMessagesFromHistory(
  msgs: any[],
  imageHost: string = IMAGE_HOST,
  idPrefix: string = 'hist',
): UIMessage[] {
  const restored: UIMessage[] = [];
  (msgs || []).forEach((m: any, i: number) => {
    const baseId = `${idPrefix}-${m.id || i}`;
    restored.push({
      id: baseId,
      role: m.role,
      content: m.content,
      createdAt: m.created_at,
      imageUris: parseHistoryImageUris(m.image_url, imageHost),
      ...applyMeta(m),
    });

    const serverCards = renderServerCards(m?.meta?.cards);
    serverCards.forEach((card, cardIndex) => {
      restored.push({
        id: `${baseId}-card-${cardIndex}`,
        role: 'assistant',
        content: '',
        cardType: card.type,
        cardData: card.data,
        cardActions: card.actions,
        createdAt: m.created_at,
      });
    });
  });
  return restored;
}

interface UseChatEngineOptions {
  contextData?: Record<string, any>;
}

const BRIEFING_CONVERSATION_TITLE = '每日健康简报';
const DEFAULT_WINDOW_DAYS = 7;
const LAST_CONVERSATION_ID_KEY = 'chat:last_conversation_id:v1';
const PENDING_STREAM_STARTED_AT_KEY = 'chat:pending_stream_started_at:v1';
const PENDING_STREAM_TTL_MS = 10 * 60 * 1000;
const THINKING_PLACEHOLDER = '⏳ AI 正在思考中...';
const MAX_THINKING_STEPS = 8;

function stripThinkingPlaceholder(content: string): string {
  return content.replace(THINKING_PLACEHOLDER, '');
}

function mergeAssistantStreamContent(current: string, incoming: string): string {
  if (!incoming) return current;
  return stripThinkingPlaceholder(current) + incoming;
}

function appendThinkingStep(current: string[] | undefined, next: string | undefined): string[] | undefined {
  const normalized = (next || '').trim();
  if (!normalized) return current;
  const existing = Array.isArray(current) ? current : [];
  if (existing[existing.length - 1] === normalized) return existing;
  return [...existing, normalized].slice(-MAX_THINKING_STEPS);
}

function serverCardKey(card: Pick<ServerCardDescriptor, 'type' | 'data' | 'actions'>): string {
  try {
    return JSON.stringify([card.type, card.data ?? {}, card.actions ?? []]);
  } catch {
    return `${card.type}:${Date.now()}`;
  }
}

function insertCardMessagesAfterAssistant(
  messages: UIMessage[],
  assistantId: string,
  cards: ServerCardDescriptor[],
): UIMessage[] {
  if (cards.length === 0) return messages;
  const insertAtBase = messages.findIndex(m => m.id === assistantId);
  let insertAt = insertAtBase >= 0 ? insertAtBase + 1 : messages.length;
  while (insertAt < messages.length && messages[insertAt]?.role === 'assistant' && !!messages[insertAt]?.cardType) {
    insertAt += 1;
  }
  const cardMessages = cards.map((card) => ({
    id: nextId(),
    role: 'assistant' as const,
    content: '',
    cardType: card.type,
    cardData: card.data,
    cardActions: card.actions,
  }));
  return [...messages.slice(0, insertAt), ...cardMessages, ...messages.slice(insertAt)];
}

async function readStoredConversationId(): Promise<number | null> {
  try {
    const raw = await AsyncStorage.getItem(LAST_CONVERSATION_ID_KEY);
    const id = raw ? Number(raw) : NaN;
    return Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

async function rememberConversationId(id: number | undefined | null): Promise<void> {
  if (!id) return;
  try { await AsyncStorage.setItem(LAST_CONVERSATION_ID_KEY, String(id)); } catch {}
}

async function forgetConversationId(): Promise<void> {
  try { await AsyncStorage.removeItem(LAST_CONVERSATION_ID_KEY); } catch {}
}

async function markPendingStream(): Promise<void> {
  try { await AsyncStorage.setItem(PENDING_STREAM_STARTED_AT_KEY, String(Date.now())); } catch {}
}

async function clearPendingStream(): Promise<void> {
  try { await AsyncStorage.removeItem(PENDING_STREAM_STARTED_AT_KEY); } catch {}
}

async function hasFreshPendingStream(): Promise<boolean> {
  try {
    const raw = await AsyncStorage.getItem(PENDING_STREAM_STARTED_AT_KEY);
    const startedAt = raw ? Number(raw) : NaN;
    return Number.isFinite(startedAt) && Date.now() - startedAt < PENDING_STREAM_TTL_MS;
  } catch {
    return false;
  }
}

export function useChatEngine(opts: UseChatEngineOptions = {}) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>(undefined);
  const [windowDays, setWindowDays] = useState<number | undefined>(DEFAULT_WINDOW_DAYS);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const briefingInjected = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // 2026-05-14: 标记是否有正在进行的 stream — 离开页面回来时, 如果还在 stream
  // 后端 G-W9 bg task 还在跑), 重新 fetch 拉服务端最新消息.
  const streamingRef = useRef(false);

  // 2026-05-16 FIX: messages.length 不能直接进 useFocusEffect/AppState 的 deps.
  // 当 sendMessage 把 [userMsg, aiMsg] push 进 list, length 0→2 → callback 重建 →
  // useFocusEffect 紧接着触发 reloadCurrentFromServer → 服务端那时还没写完 AI 响应,
  // 只有 user 消息, 把本地的 streaming aiMsg 整个覆盖掉, UI 永远停在"只有用户气泡".
  // 用 ref 读取最新 length, 让 effect 只在 focus / app-state 切换时触发.
  const messagesLengthRef = useRef(0);
  useEffect(() => { messagesLengthRef.current = messages.length; }, [messages.length]);

  // 2026-05-14 FIX-4: 不在 unmount 时 abort.
  // 用户切 tab / 进 SNP 详情时, useChatEngine 的 host (chat tab) 可能 unmount,
  // 之前 cleanup 会 abort SSE, 后端 G-W9 bg task 也跟着断 (HTTPClient 已断流).
  // 改为: 让 fetch promise 自然完成, 依靠 navigation focus 回来时 reloadCurrentFromServer
  // 把后端写入的最终消息拉回前端显示.
  useEffect(() => () => { /* no-op: 不在 unmount 时 abort */ }, []);

  const reloadCurrentFromServer = useCallback(async () => {
    if (!conversationId) return;
    if (streamingRef.current) return;
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(
        conversationId, { days: windowDays || DEFAULT_WINDOW_DAYS }
      );
      if (streamingRef.current) return;
      setHasMoreHistory(total_messages > msgs.length);
      if (msgs.length === 0) return;
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'hist');
      setMessages(restored);
      setIsStreaming(false);  // 清掉 streaming 残留态
    } catch {
      // 网络失败不影响现有 UI
    }
  }, [conversationId, windowDays]);

  const restoreCards = useCallback(async (restored: UIMessage[]) => {
    const userMsgs = restored.filter(m => m.role === 'user' && m.content);
    for (const um of userMsgs) {
      try {
        const card = await dispatchCard({
          query: um.content,
          query_lower: um.content.toLowerCase(),
          toolsUsed: new Set(),
          data: {},
          api,
        });
        if (card) {
          setMessages(prev => {
            const idx = prev.findIndex(m => m.id === um.id);
            if (idx < 0 || prev.find((m, j) => j > idx && m.cardType)) return prev;
            const cardMsg: UIMessage = { id: `card-${um.id}`, role: 'assistant', content: '', cardType: card.type, cardData: card.data };
            const insertAt = Math.min(idx + 2, prev.length);
            return [...prev.slice(0, insertAt), cardMsg, ...prev.slice(insertAt)];
          });
        }
      } catch { console.warn('Card dispatch failed for restored message'); }
    }
  }, []);

  const recoverConversationFromServer = useCallback(async (id: number) => {
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(
        id,
        { days: windowDays || DEFAULT_WINDOW_DAYS },
      );
      const hasAssistantAnswer = msgs.some((m: any) =>
        m?.role === 'assistant' && typeof m.content === 'string' && m.content.trim().length > 0
      );
      if (!hasAssistantAnswer) return false;

      setConversationId(id);
      void rememberConversationId(id);
      setHasMoreHistory(total_messages > msgs.length);
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'hist');
      setMessages(restored);
      restoreCards(restored);
      return true;
    } catch {
      return false;
    }
  }, [restoreCards, windowDays]);

  const loadConversationFromServer = useCallback(async (id: number, idPrefix: string = 'hist') => {
    const { messages: msgs, total_messages } = await getConversationMessages(id, { days: DEFAULT_WINDOW_DAYS });
    setWindowDays(DEFAULT_WINDOW_DAYS);
    setHasMoreHistory(total_messages > msgs.length);
    if (msgs.length === 0 && total_messages === 0) return false;

    setConversationId(id);
    void rememberConversationId(id);
    const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, idPrefix);
    setMessages(restored);
    restoreCards(restored);
    return true;
  }, [restoreCards]);

  const loadLatestConversation = useCallback(async (options?: { preferBriefing?: boolean }) => {
    if (streamingRef.current) return;
    try {
      const preferBriefing = options?.preferBriefing ?? true;
      const storedConversationId = await readStoredConversationId();
      if (storedConversationId) {
        const restoredStoredConversation = await loadConversationFromServer(storedConversationId, 'hist');
        if (restoredStoredConversation || streamingRef.current) return;
        await forgetConversationId();
      }

      const shouldPreferRecent = await hasFreshPendingStream();
      // 默认进入 chat tab 时优先打开"每日健康简报"；但从后台/其它 tab 恢复未完成新会话时,
      // 必须按真实最近对话找，否则会被旧简报抢走，导致用户看不到刚才那次 Agent 回复。
      let convs = preferBriefing && !shouldPreferRecent ? await getConversations(BRIEFING_CONVERSATION_TITLE) : [];
      if (convs.length === 0) convs = await getConversations();
      convs = [...convs].sort((a: any, b: any) =>
        ((b as any).updated_at || b.created_at || '').localeCompare(
          ((a as any).updated_at || a.created_at || '') as string
        )
      );
      if (convs.length === 0) return;
      if (streamingRef.current) return;

      const latestId = convs[0].id;
      await loadConversationFromServer(latestId, 'hist');
    } catch { console.warn('Failed to load latest conversation'); }
  }, [loadConversationFromServer]);

  // AppState: App 回前台时, 如果当前消息有 streaming 态但 iOS 已切到 background
  // 30s+ 把 stream 杀掉了, 客户端本地是残缺消息. 服务端 stream 到 OpenClaw 后端
  // 会持续跑并把最终 message 写 conversation. 这里 active 时重新拉服务端最新消息
  // 把断掉的 AI 回复补齐.
  const appStateRef = useRef(AppState.currentState);
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next) => {
      const prev = appStateRef.current;
      appStateRef.current = next;
      if ((prev === 'background' || prev === 'inactive') && next === 'active') {
        if (streamingRef.current) return;
        if (conversationId) {
          reloadCurrentFromServer();
        } else if (streamingRef.current || messagesLengthRef.current > 0) {
          loadLatestConversation({ preferBriefing: false });
        }
      }
    });
    return () => sub.remove();
  }, [conversationId, loadLatestConversation, reloadCurrentFromServer]);

  // 2026-05-14 FIX-4 / 2026-05-15 resume: chat tab 重获 focus 时拉最新.
  // 新会话首次发送时 conversationId 可能在 done 前尚未回填；这种情况下按"最近对话"
  // 拉取, 避免用户切走后后台 task 已落库但 UI 永远停在本地 streaming placeholder。
  useFocusEffect(
    useCallback(() => {
      if (streamingRef.current) {
        return () => { /* active stream owns local state; avoid overwriting it with partial server history */ };
      }
      if (conversationId) {
        reloadCurrentFromServer().finally(() => { streamingRef.current = false; });
      } else if (streamingRef.current || messagesLengthRef.current > 0) {
        loadLatestConversation({ preferBriefing: false }).finally(() => { streamingRef.current = false; });
      }
      return () => { /* unfocus 时不动 */ };
    }, [conversationId, loadLatestConversation, reloadCurrentFromServer])
  );

  const loadConversation = useCallback(async (id: number) => {
    try {
      const loaded = await loadConversationFromServer(id, 'h');
      if (!loaded) throw new Error('加载对话失败');
    } catch { throw new Error('加载对话失败'); }
  }, [loadConversationFromServer]);

  const loadMoreHistory = useCallback(async () => {
    if (!conversationId || !hasMoreHistory) return;
    const nextDays = (windowDays || DEFAULT_WINDOW_DAYS) + 14;
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(conversationId, { days: nextDays });
      setWindowDays(nextDays);
      setHasMoreHistory(total_messages > msgs.length);
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'h');
      setMessages(restored);
      restoreCards(restored);
    } catch { console.warn('loadMoreHistory failed'); }
  }, [conversationId, hasMoreHistory, restoreCards, windowDays]);

  const sendMessage = useCallback(async (
    text: string,
    pendingImages?: { uri: string; base64?: string; type?: string }[] | null,
    sendOpts?: { fromSiri?: boolean; extraContext?: string; forceNewConversation?: boolean },
  ) => {
    const msg = text.trim();
    const hasImages = pendingImages && pendingImages.length > 0;
    if (!msg && !hasImages) return;
    if (isStreaming) return;

    const net = await NetInfo.fetch();
    if (!net.isConnected) {
      const errMsg: UIMessage = { id: nextId(), role: 'assistant', content: '⚠️ 网络不可用，请检查网络连接后重试' };
      setMessages(prev => [...prev, { id: nextId(), role: 'user', content: msg || '(图片)', imageUris: hasImages ? pendingImages.map(i => i.uri) : undefined, fromSiri: sendOpts?.fromSiri }, errMsg]);
      return;
    }

    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    // Phase 0.4: 埋点 — 用户实际发出的对话, 区分入口 (siri vs chat)
    try {
      emitClientEvent('chat_message_sent', {
        source: sendOpts?.fromSiri ? 'siri' : 'chat',
        has_image: !!hasImages,
      });
    } catch { /* noop */ }

    const forceNewConversation = !!sendOpts?.forceNewConversation;
    const targetConversationId = forceNewConversation ? undefined : conversationId;
    if (forceNewConversation) {
      setConversationId(undefined);
      void forgetConversationId();
      void clearPendingStream();
      briefingInjected.current = false;
    }

    const finalMsg = msg || (hasImages ? '请分析这些图片' : '');
    const uris = hasImages ? pendingImages.map(i => i.uri) : undefined;
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: finalMsg, imageUris: uris, fromSiri: sendOpts?.fromSiri };
    const aId = nextId();
    const aiMsg: UIMessage = {
      id: aId,
      role: 'assistant',
      content: THINKING_PLACEHOLDER,
      streaming: true,
      thinkingSteps: ['正在理解你的问题'],
    };

    setMessages(prev => forceNewConversation ? [userMsg, aiMsg] : [...prev, userMsg, aiMsg]);
    setIsStreaming(true);
    streamingRef.current = true;
    void markPendingStream();

    const ac = new AbortController();
    abortRef.current = ac;

    let gotFirstToken = false;
    const slowTimer = setTimeout(() => {
      if (!gotFirstToken) {
        setMessages(prev => prev.map(m => m.id === aId && !m.content ? { ...m, content: THINKING_PLACEHOLDER } : m));
      }
    }, 8000);

    let streamConversationId = targetConversationId;

    // Token 攒批: 快路由 (deepseek-v4-flash) 后每个 SSE chunk 到达快得多, 逐 chunk
    // setMessages 全数组 map 是热点. 累积到缓冲, 每 ~80ms flush 一次; done/error/card/
    // 循环结束/异常 前都强制 flush → 不丢字、不改消息顺序 (缓冲按到达顺序追加, 整块合并).
    // 声明在 try 外, 让 catch 也能收尾 flush 已接收内容 (避免异常吞掉最后一批).
    let pendingTokenText = '';
    let tokenFlushTimer: ReturnType<typeof setTimeout> | null = null;
    const flushTokenBuffer = () => {
      if (tokenFlushTimer) { clearTimeout(tokenFlushTimer); tokenFlushTimer = null; }
      if (!pendingTokenText) return;
      const batch = pendingTokenText;
      pendingTokenText = '';
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: mergeAssistantStreamContent(m.content, batch) } : m));
    };

    try {
      const toolsUsed: Set<string> = new Set();
      const streamedCardKeys: Set<string> = new Set();
      let sawDone = false;
      for await (const evt of streamChat(finalMsg, targetConversationId, hasImages ? pendingImages : undefined, ac.signal, sendOpts?.extraContext)) {
        if (evt.thought) {
          setMessages(prev => prev.map(m => m.id === aId ? {
            ...m,
            thinkingSteps: appendThinkingStep(m.thinkingSteps, evt.thought),
          } : m));
        }
        if (evt.type === 'start') {
          if (evt.conversationId) {
            streamConversationId = evt.conversationId;
            if (!targetConversationId) setConversationId(evt.conversationId);
            void rememberConversationId(evt.conversationId);
          }
        } else if (evt.type === 'token' || evt.type === 'tool') {
          const incoming = sanitizeChatErrorMessage(evt.content || '', '');
          if (incoming) {
            if (!gotFirstToken) { gotFirstToken = true; clearTimeout(slowTimer); }
            pendingTokenText += incoming;
            if (!tokenFlushTimer) {
              tokenFlushTimer = setTimeout(flushTokenBuffer, 80);
            }
          }
          if (evt.toolName) toolsUsed.add(evt.toolName);
        } else if (evt.type === 'card') {
          flushTokenBuffer();
          const serverCards = renderServerCards(evt.card ? [evt.card] : []);
          const uniqueCards = serverCards.filter((card) => {
            const key = serverCardKey(card);
            if (streamedCardKeys.has(key)) return false;
            streamedCardKeys.add(key);
            return true;
          });
          if (uniqueCards.length > 0) {
            setMessages(prev => insertCardMessagesAfterAssistant(prev, aId, uniqueCards));
          }
        } else if (evt.type === 'done') {
          sawDone = true;
          flushTokenBuffer();
          if (evt.conversationId) {
            streamConversationId = evt.conversationId;
            if (!targetConversationId) setConversationId(evt.conversationId);
            void rememberConversationId(evt.conversationId);
          }
          // 把耗时 + 模型名写入当前 assistant 消息 (ChatBubble 渲染 footer)
          setMessages(prev => prev.map(m => m.id === aId ? {
            ...m,
            elapsedMs: evt.elapsedMs,
            llmMs: evt.llmMs,
            llmRounds: evt.llmRounds,
            llmRoundsMs: evt.llmRoundsMs,
            model: evt.model,
            llmUsage: evt.llmUsage,
            perf: evt.perf,
            sourcesUsed: evt.sourcesUsed,
            toolsUsed: evt.toolsUsed,
            completionStatus: evt.completionStatus,
          } : m));
          const rawDoneCards = Array.isArray((evt as any).cards) ? (evt as any).cards : [];
          const serverCards = renderServerCards(rawDoneCards).filter((card) => {
            const key = serverCardKey(card);
            if (streamedCardKeys.has(key)) return false;
            streamedCardKeys.add(key);
            return true;
          });
          if (serverCards.length > 0) {
            const single = serverCards.length === 1 ? serverCards[0] : { type: 'cards_group', data: { cards: serverCards }, actions: [] };
            setMessages(prev => [...prev, {
              id: nextId(),
              role: 'assistant' as const,
              content: '',
              cardType: single.type,
              cardData: single.data,
              cardActions: single.actions,
            }]);
          } else if (rawDoneCards.length === 0) {
            const card = await dispatchCard({
              query: finalMsg,
              query_lower: finalMsg.toLowerCase(),
              toolsUsed,
              data: opts.contextData || {},
              api,
            });
            if (card) {
              setMessages(prev => [...prev, { id: nextId(), role: 'assistant', content: '', cardType: card.type, cardData: card.data }]);
            }
          }
        } else if (evt.type === 'error') {
          flushTokenBuffer();
          const errMsg = sanitizeChatErrorMessage(evt.content, '请求出错，请稍后再试');
          setMessages(prev => prev.map(m => m.id === aId ? {
            ...m,
            completionStatus: 'error',
            content: stripThinkingPlaceholder(m.content)
              ? stripThinkingPlaceholder(m.content) + `\n❌ ${errMsg}`
              : `❌ ${errMsg}`,
          } : m));
        }
      }
      flushTokenBuffer();
      if (!sawDone) {
        setMessages(prev => prev.map(m => m.id === aId ? {
          ...m,
          completionStatus: 'interrupted',
          content: stripThinkingPlaceholder(m.content)
            ? `${stripThinkingPlaceholder(m.content)}\n\n[回复中断，已保留已接收内容]`
            : '[回复中断，请重新提问]',
        } : m));
      }
    } catch (err: any) {
      flushTokenBuffer();
      const isAbort = err?.message === 'aborted';
      if (!isAbort && streamConversationId) {
        const recovered = await recoverConversationFromServer(streamConversationId);
        if (recovered) return;
      }
      setMessages(prev => prev.map(m => m.id === aId ? {
        ...m,
        completionStatus: isAbort ? 'interrupted' : 'error',
        content: stripThinkingPlaceholder(m.content)
          ? (isAbort ? stripThinkingPlaceholder(m.content) + '\n\n[回复中断，已保留已接收内容]' : stripThinkingPlaceholder(m.content) + `\n❌ ${sanitizeChatErrorMessage(err?.message, '请求失败')}`)
          : (isAbort ? '[App 切换到后台，回复中断。请重新提问]' : `[错误] ${sanitizeChatErrorMessage(err?.message, '请求失败')}`),
      } : m));
    } finally {
      flushTokenBuffer(); // 收尾: 清残留 timer + 保证最后一批不丢字 (幂等)
      clearTimeout(slowTimer);
      abortRef.current = null;
      streamingRef.current = false;
      void clearPendingStream();
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, streaming: false } : m));
      setIsStreaming(false);
    }
  }, [isStreaming, conversationId, opts.contextData, recoverConversationFromServer]);

  const newChat = useCallback(() => {
    setMessages([]);
    setConversationId(undefined);
    void forgetConversationId();
    void clearPendingStream();
    briefingInjected.current = false;
  }, []);

  const deleteCurrentConversation = useCallback(async () => {
    if (!conversationId) return;
    await deleteConversation(conversationId);
    newChat();
  }, [conversationId, newChat]);

  return {
    messages,
    isStreaming,
    conversationId,
    sendMessage,
    newChat,
    loadLatestConversation,
    loadConversation,
    loadMoreHistory,
    hasMoreHistory,
    deleteCurrentConversation,
    setMessages,
  };
}
