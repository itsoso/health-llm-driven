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
import { ChatMessage, agentApi } from '@/services/api/ai';
import ChatView from '@/components/assistant/ChatView';
import { api } from '@/services/api/client';

export default function AIAssistantPage() {
  const [activeConvId, setActiveConvId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [doneIds, setDoneIds] = useState<Set<number>>(new Set());
  // 2026-05-13: 当前用户偏好的 LLM 模型 (顶部 chip 用)
  const [llmPref, setLlmPref] = useState<{ label: string | null; model_id: string | null }>({
    label: null, model_id: null,
  });
  const scrollRef = useRef<HTMLDivElement | null>(null);

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
      setLlmPref({ label: opt?.label || (id ? id : null), model_id: id });
    }).catch(() => { /* 401/403 静默 */ });
    return () => { cancelled = true; };
  }, []);

  const sendMessage = async () => {
    const text = input.trim();
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
    }
  };

  const startNewConversation = () => {
    setActiveConvId(undefined);
    setMessages([]);
  };

  return (
    <main className="flex h-screen bg-slate-950 text-slate-100">
      {/* 主区: 消息流 + 输入 */}
      <section className="flex-1 flex flex-col min-w-0">
        <div className="px-4 py-3 border-b border-slate-800/60 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <h2 className="text-sm font-semibold text-slate-300 shrink-0">智能助理</h2>
            {/* 2026-05-13: 当前模型 chip — 点开跳到 /llm-preference 切换 */}
            <a
              href="/llm-preference"
              className="hidden sm:inline-flex items-center gap-1 rounded-full border border-slate-700/60 bg-slate-800/40 px-2 py-0.5 text-[11px] text-slate-400 hover:text-emerald-300 hover:border-emerald-500/40 truncate max-w-[14rem]"
              title="点击切换 AI 模型偏好"
            >
              <svg className="h-3 w-3 shrink-0" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.09 6.26L20.18 9l-5 4.09L16.82 20 12 16.54 7.18 20l1.64-6.91L3.82 9l6.09-.74L12 2z" /></svg>
              <span className="truncate">{llmPref.label || '默认模型'}</span>
            </a>
          </div>
          <button
            onClick={startNewConversation}
            className="rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium px-2.5 py-1.5 shrink-0"
          >
            + 新对话
          </button>
        </div>
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6">
          {messages.length === 0 && !streaming ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <svg className="h-10 w-10 mb-3 text-emerald-400/60" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2l2.09 6.26L20.18 9l-5 4.09L16.82 20 12 16.54 7.18 20l1.64-6.91L3.82 9l6.09-.74L12 2z" />
              </svg>
              <p className="text-sm">和你的健康助理说点什么</p>
              <p className="mt-1 text-xs text-slate-600">
                例如 "今天血氧怎么样" / "帮我看看最近化验" / "明天该怎么训练"
              </p>
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
        <div className="border-t border-slate-800/60 bg-slate-900/60 px-4 py-3">
          <div className="mx-auto max-w-4xl flex gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder={streaming ? '回答中…' : '发消息 (Enter 发送, Shift+Enter 换行)'}
              disabled={streaming}
              rows={1}
              className="flex-1 resize-none rounded-xl bg-slate-800/60 border border-slate-700/60 px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500/50 disabled:opacity-50 max-h-32"
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || streaming}
              className="rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-sm font-medium px-5"
            >
              发送
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
