import { useState, useRef, useCallback, useEffect } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';
import * as Haptics from 'expo-haptics';
import NetInfo from '@react-native-community/netinfo';
import { streamChat, getConversations, getConversationMessages, deleteConversation, type ChatMessage } from '../services/chat';
import { dispatchCard, renderServerCards } from '../components/chat/cards';
import api, { BASE_URL } from '../services/api';
import { emitClientEvent } from '../services/clientEvents';

const IMAGE_HOST = BASE_URL.replace(/\/api$/, '');

export interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  imageUris?: string[];
  isBriefing?: boolean;
  cardType?: string;
  cardData?: any;
  createdAt?: string;
  fromSiri?: boolean;
  // 2026-05-13: 性能可观测 — done 事件的耗时 + 模型名, 渲染在 assistant 气泡底部
  elapsedMs?: number;
  llmMs?: number;
  llmRounds?: number;
  model?: string;
  // 2026-05-14 #4: 可解释性 — AI 用了什么数据
  sourcesUsed?: string[];
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
    model: typeof meta.model === 'string' ? meta.model : undefined,
    sourcesUsed: Array.isArray(meta.sources_used) ? meta.sources_used : undefined,
  };
}

function parseHistoryImageUris(raw: any, imageHost: string): string[] | undefined {
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return undefined;
    return parsed.map((u: string) => `${imageHost}${u}`);
  } catch {
    return undefined;
  }
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

  const loadLatestConversation = useCallback(async (options?: { preferBriefing?: boolean }) => {
    if (streamingRef.current) return;
    try {
      const preferBriefing = options?.preferBriefing ?? true;
      // 默认进入 chat tab 时优先打开"每日健康简报"；但从后台/其它 tab 恢复未完成新会话时,
      // 必须按真实最近对话找，否则会被旧简报抢走，导致用户看不到刚才那次 Agent 回复。
      let convs = preferBriefing ? await getConversations(BRIEFING_CONVERSATION_TITLE) : [];
      if (convs.length === 0) convs = await getConversations();
      convs = [...convs].sort((a: any, b: any) =>
        ((b as any).updated_at || b.created_at || '').localeCompare(
          ((a as any).updated_at || a.created_at || '') as string
        )
      );
      if (convs.length === 0) return;
      if (streamingRef.current) return;

      const latestId = convs[0].id;
      setConversationId(latestId);
      const { messages: msgs, total_messages } = await getConversationMessages(latestId, { days: DEFAULT_WINDOW_DAYS });
      if (streamingRef.current) return;
      setWindowDays(DEFAULT_WINDOW_DAYS);
      setHasMoreHistory(total_messages > msgs.length);
      if (msgs.length > 0) {
        const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'hist');
        setMessages(restored);
        restoreCards(restored);
      }
    } catch { console.warn('Failed to load latest conversation'); }
  }, [restoreCards]);

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
    setConversationId(id);
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(id, { days: DEFAULT_WINDOW_DAYS });
      setWindowDays(DEFAULT_WINDOW_DAYS);
      setHasMoreHistory(total_messages > msgs.length);
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'h');
      setMessages(restored);
      restoreCards(restored);
    } catch { throw new Error('加载对话失败'); }
  }, [restoreCards]);

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
    sendOpts?: { fromSiri?: boolean; extraContext?: string },
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

    const finalMsg = msg || (hasImages ? '请分析这些图片' : '');
    const uris = hasImages ? pendingImages.map(i => i.uri) : undefined;
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: finalMsg, imageUris: uris, fromSiri: sendOpts?.fromSiri };
    const aId = nextId();
    const aiMsg: UIMessage = { id: aId, role: 'assistant', content: '', streaming: true };

    setMessages(prev => [...prev, userMsg, aiMsg]);
    setIsStreaming(true);
    streamingRef.current = true;

    const ac = new AbortController();
    abortRef.current = ac;

    let gotFirstToken = false;
    const slowTimer = setTimeout(() => {
      if (!gotFirstToken) {
        setMessages(prev => prev.map(m => m.id === aId && !m.content ? { ...m, content: '⏳ AI 正在思考中...' } : m));
      }
    }, 8000);

    try {
      const toolsUsed: Set<string> = new Set();
      for await (const evt of streamChat(finalMsg, conversationId, hasImages ? pendingImages : undefined, ac.signal, sendOpts?.extraContext)) {
        if (evt.type === 'start') {
          if (evt.conversationId && !conversationId) setConversationId(evt.conversationId);
        } else if (evt.type === 'token' || evt.type === 'tool') {
          if (!gotFirstToken) { gotFirstToken = true; clearTimeout(slowTimer); setMessages(prev => prev.map(m => m.id === aId && m.content === '⏳ AI 正在思考中...' ? { ...m, content: '' } : m)); }
          setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content.replace('⏳ AI 正在思考中...', '') + (evt.content || '') } : m));
          if (evt.toolName) toolsUsed.add(evt.toolName);
        } else if (evt.type === 'done') {
          if (evt.conversationId && !conversationId) setConversationId(evt.conversationId);
          // 把耗时 + 模型名写入当前 assistant 消息 (ChatBubble 渲染 footer)
          setMessages(prev => prev.map(m => m.id === aId ? {
            ...m,
            elapsedMs: evt.elapsedMs,
            llmMs: evt.llmMs,
            llmRounds: evt.llmRounds,
            model: evt.model,
            sourcesUsed: evt.sourcesUsed,
          } : m));
          const serverCards = renderServerCards((evt as any).cards);
          if (serverCards.length > 0) {
            const single = serverCards.length === 1 ? serverCards[0] : { type: 'cards_group', data: { cards: serverCards } };
            setMessages(prev => [...prev, { id: nextId(), role: 'assistant' as const, content: '', cardType: single.type, cardData: single.data }]);
          } else {
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
          const errMsg = (evt.content || '').trim() || '请求出错，请稍后再试';
          setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content + `\n❌ ${errMsg}` } : m));
        }
      }
    } catch (err: any) {
      const isAbort = err?.message === 'aborted';
      setMessages(prev => prev.map(m => m.id === aId ? {
        ...m,
        content: m.content
          ? (isAbort ? m.content + '\n\n[回复中断，已保留已接收内容]' : m.content + `\n❌ ${err?.message || '请求失败'}`)
          : (isAbort ? '[App 切换到后台，回复中断。请重新提问]' : `[错误] ${err?.message || '请求失败'}`),
      } : m));
    } finally {
      clearTimeout(slowTimer);
      abortRef.current = null;
      streamingRef.current = false;
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, streaming: false } : m));
      setIsStreaming(false);
    }
  }, [isStreaming, conversationId, opts.contextData]);

  const newChat = useCallback(() => {
    setMessages([]);
    setConversationId(undefined);
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
