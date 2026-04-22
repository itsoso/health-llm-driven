import { useState, useRef, useCallback, useEffect } from 'react';
import { AppState } from 'react-native';
import * as Haptics from 'expo-haptics';
import { streamChat, getConversations, getConversationMessages, deleteConversation, type ChatMessage, type StreamEvent } from '@/services/chat';
import { dispatchCard, renderServerCards } from '@/components/chat/cards';
import api, { BASE_URL } from '@/services/api';

const IMAGE_HOST = BASE_URL.replace(/\/api$/, '');

export interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  imageUri?: string;
  isBriefing?: boolean;
  cardType?: string;
  cardData?: any;
}

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }

interface UseChatEngineOptions {
  contextData?: Record<string, any>;
}

export function useChatEngine(opts: UseChatEngineOptions = {}) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>(undefined);
  const briefingInjected = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // Abort streaming when app goes to background
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'background' && abortRef.current) {
        abortRef.current.abort();
      }
    });
    return () => sub.remove();
  }, []);

  const loadLatestConversation = useCallback(async () => {
    try {
      const convs = await getConversations();
      if (convs.length > 0) {
        const latestId = convs[0].id;
        setConversationId(latestId);
        const msgs = await getConversationMessages(latestId);
        if (msgs.length > 0) {
          const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
            id: `hist-${m.id || i}`,
            role: m.role,
            content: m.content,
            imageUri: m.image_url ? `${IMAGE_HOST}${m.image_url}` : undefined,
          }));
          setMessages(restored);
          restoreCards(restored);
        }
      }
    } catch { console.warn('Failed to load latest conversation'); }
  }, []);

  const loadConversation = useCallback(async (id: number) => {
    setConversationId(id);
    try {
      const msgs = await getConversationMessages(id);
      const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
        id: `h-${m.id || i}`, role: m.role, content: m.content,
        imageUri: m.image_url ? `${IMAGE_HOST}${m.image_url}` : undefined,
      }));
      setMessages(restored);
      restoreCards(restored);
    } catch { throw new Error('加载对话失败'); }
  }, []);

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
    pendingImage?: { uri: string; base64?: string; type?: string } | null,
  ) => {
    const msg = text.trim();
    const hasImage = !!pendingImage;
    if (!msg && !hasImage) return;
    if (isStreaming) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const finalMsg = msg || (hasImage ? '请分析这张图片' : '');
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: finalMsg, imageUri: pendingImage?.uri };
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
      for await (const evt of streamChat(finalMsg, conversationId, pendingImage?.base64, pendingImage?.type, ac.signal)) {
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
    deleteCurrentConversation,
    setMessages,
  };
}
