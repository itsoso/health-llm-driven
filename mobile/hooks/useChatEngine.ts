import { useState, useRef, useCallback, useEffect } from 'react';
import { AppState } from 'react-native';
import * as Haptics from 'expo-haptics';
import NetInfo from '@react-native-community/netinfo';
import { streamChat, getConversations, getConversationMessages, deleteConversation, type ChatMessage, type StreamEvent } from '../services/chat';
import { dispatchCard, renderServerCards } from '../components/chat/cards';
import api, { BASE_URL } from '../services/api';

const IMAGE_HOST = BASE_URL.replace(/\/api$/, '');

export interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  imageUris?: string[];
  isBriefing?: boolean;
  cardType?: string;
  cardData?: any;
  createdAt?: string;
}

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }

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

  // Clean up abort controller on unmount only — don't abort on background
  // iOS gives ~30s background execution, enough for most LLM responses
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  // AppState: App 回前台时, 如果当前消息有 streaming 态但 iOS 已切到 background
  // 30s+ 把 stream 杀掉了, 客户端本地是残缺消息. 服务端 stream 到 OpenClaw 后端
  // 会持续跑并把最终 message 写 conversation. 这里 active 时重新拉服务端最新消息
  // 把断掉的 AI 回复补齐.
  const appStateRef = useRef(AppState.currentState);
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next) => {
      const prev = appStateRef.current;
      appStateRef.current = next;
      // 从 background/inactive 回到 active, 且有当前对话 → 重新拉消息
      if ((prev === 'background' || prev === 'inactive') && next === 'active' && conversationId) {
        reloadCurrentFromServer();
      }
    });
    return () => sub.remove();
  }, [conversationId]);

  const reloadCurrentFromServer = useCallback(async () => {
    if (!conversationId) return;
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(
        conversationId, { days: windowDays || DEFAULT_WINDOW_DAYS }
      );
      setHasMoreHistory(total_messages > msgs.length);
      if (msgs.length === 0) return;
      const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
        id: `hist-${m.id || i}`,
        role: m.role,
        content: m.content,
        createdAt: m.created_at,
        imageUris: m.image_url ? JSON.parse(m.image_url).map((u: string) => `${IMAGE_HOST}${u}`) : undefined,
      }));
      setMessages(restored);
      setIsStreaming(false);  // 清掉 streaming 残留态
    } catch {
      // 网络失败不影响现有 UI
    }
  }, [conversationId, windowDays]);

  const loadLatestConversation = useCallback(async () => {
    try {
      // 1. 优先找"每日健康简报"对话
      let convs = await getConversations(BRIEFING_CONVERSATION_TITLE);
      // 按 updated_at 倒序，确保选到最近一次刷新的简报
      convs = [...convs].sort((a: any, b: any) =>
        ((b as any).updated_at || b.created_at || '').localeCompare(
          ((a as any).updated_at || a.created_at || '') as string
        )
      );
      // 2. fallback：任意最近对话
      if (convs.length === 0) convs = await getConversations();
      if (convs.length === 0) return;

      const latestId = convs[0].id;
      setConversationId(latestId);
      const { messages: msgs, total_messages } = await getConversationMessages(latestId, { days: DEFAULT_WINDOW_DAYS });
      setWindowDays(DEFAULT_WINDOW_DAYS);
      setHasMoreHistory(total_messages > msgs.length);
      if (msgs.length > 0) {
        const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
          id: `hist-${m.id || i}`,
          role: m.role,
          content: m.content,
          createdAt: m.created_at,
          imageUris: m.image_url ? JSON.parse(m.image_url).map((u: string) => `${IMAGE_HOST}${u}`) : undefined,
        }));
        setMessages(restored);
        restoreCards(restored);
      }
    } catch { console.warn('Failed to load latest conversation'); }
  }, []);

  const loadConversation = useCallback(async (id: number) => {
    setConversationId(id);
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(id, { days: DEFAULT_WINDOW_DAYS });
      setWindowDays(DEFAULT_WINDOW_DAYS);
      setHasMoreHistory(total_messages > msgs.length);
      const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
        id: `h-${m.id || i}`, role: m.role, content: m.content, createdAt: m.created_at,
        imageUris: m.image_url ? JSON.parse(m.image_url).map((u: string) => `${IMAGE_HOST}${u}`) : undefined,
      }));
      setMessages(restored);
      restoreCards(restored);
    } catch { throw new Error('加载对话失败'); }
  }, []);

  const loadMoreHistory = useCallback(async () => {
    if (!conversationId || !hasMoreHistory) return;
    const nextDays = (windowDays || DEFAULT_WINDOW_DAYS) + 14;
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(conversationId, { days: nextDays });
      setWindowDays(nextDays);
      setHasMoreHistory(total_messages > msgs.length);
      const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
        id: `h-${m.id || i}`, role: m.role, content: m.content, createdAt: m.created_at,
        imageUris: m.image_url ? JSON.parse(m.image_url).map((u: string) => `${IMAGE_HOST}${u}`) : undefined,
      }));
      setMessages(restored);
      restoreCards(restored);
    } catch { console.warn('loadMoreHistory failed'); }
  }, [conversationId, hasMoreHistory, windowDays]);

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

  const sendMessage = useCallback(async (
    text: string,
    pendingImages?: { uri: string; base64?: string; type?: string }[] | null,
  ) => {
    const msg = text.trim();
    const hasImages = pendingImages && pendingImages.length > 0;
    if (!msg && !hasImages) return;
    if (isStreaming) return;

    const net = await NetInfo.fetch();
    if (!net.isConnected) {
      const errMsg: UIMessage = { id: nextId(), role: 'assistant', content: '⚠️ 网络不可用，请检查网络连接后重试' };
      setMessages(prev => [...prev, { id: nextId(), role: 'user', content: msg || '(图片)', imageUris: hasImages ? pendingImages.map(i => i.uri) : undefined }, errMsg]);
      return;
    }

    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const finalMsg = msg || (hasImages ? '请分析这些图片' : '');
    const uris = hasImages ? pendingImages.map(i => i.uri) : undefined;
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: finalMsg, imageUris: uris };
    const aId = nextId();
    const aiMsg: UIMessage = { id: aId, role: 'assistant', content: '', streaming: true };

    setMessages(prev => [...prev, userMsg, aiMsg]);
    setIsStreaming(true);

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
      for await (const evt of streamChat(finalMsg, conversationId, hasImages ? pendingImages : undefined, ac.signal)) {
        if (evt.type === 'token' || evt.type === 'tool') {
          if (!gotFirstToken) { gotFirstToken = true; clearTimeout(slowTimer); setMessages(prev => prev.map(m => m.id === aId && m.content === '⏳ AI 正在思考中...' ? { ...m, content: '' } : m)); }
          setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content.replace('⏳ AI 正在思考中...', '') + (evt.content || '') } : m));
          if (evt.toolName) toolsUsed.add(evt.toolName);
        } else if (evt.type === 'done') {
          if (evt.conversationId && !conversationId) setConversationId(evt.conversationId);
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
          setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content + `\n❌ ${evt.content}` } : m));
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
