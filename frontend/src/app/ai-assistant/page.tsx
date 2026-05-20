'use client';

/**
 * /ai-assistant —— Web 智能助理对话页 (2026-05-12 重建, 2026-05-13 切 agentApi).
 *
 * 之前用 openclawApi (独立 LLM key, 双倍成本). 改用 agentApi → /agent/stream
 * 跟 mobile chat tab 同管道, 共享 LLM_PROVIDER (默认 TokenPlan).
 *
 * 历史: 该路由从 nav / dashboard / footer / 测试里被引, 但 page.tsx 一直缺,
 * 用户访问就 404. 此页用 Agent stream + ChatView 渲染.
 */

import { useEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  MessageSquarePlus,
  PanelLeft,
  Sparkles,
} from 'lucide-react';
import { ChatMessage, Conversation, agentApi } from '@/services/api/ai';
import ChatView from '@/components/assistant/ChatView';
import LlmModelPicker, { ModelOption } from '@/components/assistant/LlmModelPicker';
import ConversationHistoryRail from '@/components/assistant/ConversationHistoryRail';
import { api } from '@/services/api/client';

const DEFAULT_SUGGESTIONS = [
  '分析我最近的代谢健康',
  '今天怎么安排训练和恢复',
  '结合基因和体检给我建议',
  '帮我复盘最近的睡眠质量',
];

export default function AIAssistantPage() {
  const [activeConvId, setActiveConvId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [doneIds, setDoneIds] = useState<Set<number>>(new Set());
  // 2026-05-13: 当前用户偏好的 LLM 模型 (顶部 chip 用)
  const [llmPref, setLlmPref] = useState<{ label: string | null; model_id: string | null }>({
    label: null, model_id: null,
  });
  const [llmOptions, setLlmOptions] = useState<ModelOption[]>([]);
  const [llmSaving, setLlmSaving] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [starterSuggestions, setStarterSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streaming]);

  // 拉当前 LLM 偏好显示在顶部
  useEffect(() => {
    let cancelled = false;
    api.get('/me/llm-preference').then(r => {
      if (cancelled) return;
      const id = r.data?.model_id as string | null;
      const opt = id ? r.data?.options?.find((o: any) => o.id === id) : null;
      setLlmOptions(r.data?.options || []);
      setLlmPref({ label: opt?.label || (id ? id : null), model_id: id });
    }).catch(() => { /* 401/403 静默 */ });
    return () => { cancelled = true; };
  }, []);

  const selectModel = async (modelId: string | null) => {
    if (llmPref.model_id === modelId || llmSaving) return;
    setLlmSaving(modelId || '__default__');
    setLlmError(null);
    try {
      const res = await api.put('/me/llm-preference', { model_id: modelId });
      const options = (res.data?.options || []) as ModelOption[];
      const activeId = res.data?.model_id as string | null;
      const active = activeId ? options.find(o => o.id === activeId) : null;
      setLlmOptions(options);
      setLlmPref({ model_id: activeId, label: active?.label || (activeId ? activeId : null) });
    } catch (e: any) {
      setLlmError(e?.response?.data?.detail || e?.message || '模型切换失败');
    } finally {
      setLlmSaving(null);
    }
  };

  const refreshConversations = async () => {
    setHistoryLoading(true);
    try {
      const res = await agentApi.getConversations(50);
      setConversations(res.data || []);
    } catch {
      setConversations([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    refreshConversations();
  }, []);

  const refreshConversationStarters = async () => {
    try {
      const res = await api.get('/agent/conversation-starters');
      const items = res.data?.suggestions;
      if (Array.isArray(items) && items.length > 0) {
        setStarterSuggestions(items.slice(0, 4));
      } else {
        setStarterSuggestions(DEFAULT_SUGGESTIONS);
      }
    } catch {
      setStarterSuggestions(DEFAULT_SUGGESTIONS);
    }
  };

  useEffect(() => {
    // Only needed for the empty-state new conversation page.
    if (messages.length !== 0 || streaming) return;
    refreshConversationStarters();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConvId]);

  const sendMessage = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    setInput('');
    setStreaming(true);

    // 本地先插用户消息 + assistant 占位
    const tempUserId = -Date.now();
    const tempAssistantId = -Date.now() - 1;
    const now = new Date().toISOString();
    setMessages(prev => [
      ...prev,
      { id: tempUserId, role: 'user', content: text, created_at: now },
      { id: tempAssistantId, role: 'assistant', content: '', created_at: now },
    ]);

    let assistantBuf = '';
    let realConvId = activeConvId;

    try {
      for await (const evt of agentApi.streamMessage(text, activeConvId)) {
        if (!evt) continue;
        // /agent/stream event shape: { event, data: {content, conversation_id, ...} }
        const type = evt.event ?? evt.type;
        const data = evt.data ?? {};
        if (type === 'token' && typeof data.content === 'string') {
          assistantBuf += data.content;
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
          );
        } else if (type === 'tool_call') {
          // 用户感知: 显示"调用工具中"提示一行 (灰色 italic), 不污染主回答
        } else if (type === 'done') {
          if (data.conversation_id) realConvId = data.conversation_id;
          // 2026-05-13: 写性能字段, ChatView footer 显示
          const perf = {
            elapsed_ms: typeof data.elapsed_ms === 'number' ? data.elapsed_ms : undefined,
            llm_ms: typeof data.llm_ms === 'number' ? data.llm_ms : undefined,
            llm_rounds: typeof data.llm_rounds === 'number' ? data.llm_rounds : undefined,
            llm_rounds_ms: Array.isArray(data.llm_rounds_ms) ? data.llm_rounds_ms : undefined,
            model: typeof data.model === 'string' ? data.model : undefined,
            // 2026-05-14 #4: 可解释性 sources
            sources_used: Array.isArray(data.sources_used) ? data.sources_used : undefined,
          };
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, ...perf } : m)),
          );
          setDoneIds(prev => new Set(prev).add(tempAssistantId));
        } else if (type === 'error') {
          const errMsg = data.message || data.content || evt.message || '未知错误';
          assistantBuf += `\n\n_出错: ${errMsg}_`;
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
          );
        }
      }
    } catch (e: any) {
      assistantBuf += `\n\n_连接中断: ${e?.message || ''}_`;
      setMessages(prev =>
        prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
      );
    } finally {
      setStreaming(false);
      if (!activeConvId && realConvId) {
        setActiveConvId(realConvId);
      }
      refreshConversations();
    }
  };

  const startNewConversation = () => {
    setActiveConvId(undefined);
    setMessages([]);
    refreshConversationStarters();
  };

  const loadConversation = async (conversationId: number) => {
    if (streaming) return;
    const res = await agentApi.getConversation(conversationId);
    const loaded = (res.data.messages || []).map((m: any) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      created_at: m.created_at,
      image_preview: normalizeImagePreview(m.image_url),
      elapsed_ms: m.meta?.elapsed_ms,
      llm_ms: m.meta?.llm_ms,
      llm_rounds: m.meta?.llm_rounds,
      llm_rounds_ms: m.meta?.llm_rounds_ms,
      model: m.meta?.model,
      sources_used: m.meta?.sources_used,
    })) as ChatMessage[];
    setActiveConvId(conversationId);
    setMessages(loaded);
    setDoneIds(new Set(loaded.filter(m => m.role === 'assistant').map(m => m.id)));
  };

  const deleteConversation = async (conversationId: number) => {
    if (!window.confirm('删除这条对话？')) return;
    await agentApi.deleteConversation(conversationId);
    setConversations(prev => prev.filter(c => c.id !== conversationId));
    if (activeConvId === conversationId) {
      startNewConversation();
    }
  };

  const renameConversation = async (conversationId: number, title: string) => {
    const res = await agentApi.updateConversationTitle(conversationId, title);
    const updated = res.data;
    setConversations(prev =>
      prev.map(conv =>
        conv.id === conversationId
          ? { ...conv, title: updated.title, updated_at: updated.updated_at || conv.updated_at }
          : conv,
      ),
    );
  };

  const submitSuggestion = (text: string) => {
    if (streaming) return;
    sendMessage(text);
  };

  return (
    <main className="fixed inset-0 z-40 flex flex-col overflow-hidden bg-[#212121] text-zinc-100">
      <header className="relative z-[70] shrink-0 overflow-visible border-b border-white/[0.08] bg-[#212121]/95 px-3 py-2.5 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1">
            <button
              onClick={() => setHistoryOpen(open => !open)}
              className="mr-1 flex h-9 w-9 items-center justify-center rounded-xl text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-zinc-100"
              title="打开/收起历史记录"
            >
              <PanelLeft className="h-4.5 w-4.5" />
            </button>
            <LlmModelPicker
              currentLabel={llmPref.label || '系统默认'}
              currentModelId={llmPref.model_id}
              options={llmOptions}
              savingModelId={llmSaving}
              disabled={streaming}
              error={llmError}
              onSelect={selectModel}
            />
          </div>
          <button
            onClick={startNewConversation}
            className="inline-flex h-9 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-3 text-sm font-medium text-zinc-100 transition-colors hover:bg-white/[0.1]"
          >
            <MessageSquarePlus className="h-4 w-4" />
            <span className="hidden sm:inline">新对话</span>
          </button>
        </div>
      </header>

      <section className="relative z-0 flex min-h-0 flex-1">
        {historyOpen && (
          <ConversationHistoryRail
            conversations={conversations}
            activeConvId={activeConvId}
            loading={historyLoading}
            onLoad={loadConversation}
            onDelete={deleteConversation}
            onNew={startNewConversation}
            onRename={renameConversation}
          />
        )}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 pb-32 pt-8 sm:px-6">
            {messages.length === 0 && !streaming ? (
              <div className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-500/15 text-teal-300 ring-1 ring-teal-300/15">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h1 className="mt-5 text-2xl font-semibold tracking-tight text-zinc-50 sm:text-3xl">
                  今天想了解什么？
                </h1>
                <div className="mt-8 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
                  {starterSuggestions.map(item => (
                    <button
                      key={item}
                      onClick={() => submitSuggestion(item)}
                      className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left text-sm text-zinc-300 transition-colors hover:border-teal-300/30 hover:bg-white/[0.07] hover:text-zinc-50"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ChatView
                messages={messages}
                loading={streaming}
                doneMessageIds={doneIds}
                messageFeedback={{}}
                onFeedback={() => {}}
              />
            )}
          </div>

          {/* 输入区 */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-[#212121] via-[#212121] to-transparent px-3 pb-4 pt-10 sm:px-6">
            <form
              id="ai-assistant-composer"
              onSubmit={e => {
                e.preventDefault();
                sendMessage();
              }}
              className="pointer-events-auto mx-auto flex max-w-3xl items-end gap-2 rounded-[1.7rem] border border-white/10 bg-[#2f2f2f] p-2 shadow-2xl shadow-black/30"
            >
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  // IME composition (拼音/日文/韩文) 中按 Enter 是确认候选词,不是发送
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder={streaming ? '回答中…' : '发消息 (Enter 发送, Shift+Enter 换行)'}
                disabled={streaming}
                rows={1}
                className="max-h-36 min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-zinc-100 placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || streaming}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-zinc-950 transition-colors hover:bg-white disabled:bg-zinc-600 disabled:text-zinc-400"
                title="发送"
              >
                <ArrowUp className="h-5 w-5" />
              </button>
            </form>
            <p className="pointer-events-none mx-auto mt-2 max-w-3xl text-center text-[11px] text-zinc-600">
              健康建议不能替代医生诊断；紧急或明显异常请及时就医。
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

function normalizeImagePreview(imageUrl?: string | null): string | undefined {
  if (!imageUrl) return undefined;
  try {
    const parsed = JSON.parse(imageUrl);
    if (Array.isArray(parsed)) return parsed[0];
  } catch {
    return imageUrl || undefined;
  }
  return imageUrl || undefined;
}
