'use client';

/**
 * /ai-assistant —— Web 智能助理对话页 (2026-05-12 重建).
 *
 * 历史: 该路由从 nav / dashboard / footer / 测试里被引, 但 page.tsx 一直缺,
 * 用户访问就 404. 此页用 OpenClaw stream + ChatView 渲染, 行为对齐 mobile "会诊" Tab.
 */

import { useEffect, useRef, useState } from 'react';
import { ChatMessage, Conversation, openclawApi } from '@/services/api/ai';
import ChatView from '@/components/assistant/ChatView';

export default function AIAssistantPage() {
  const [convos, setConvos] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [doneIds, setDoneIds] = useState<Set<number>>(new Set());
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // 拉历史会话, 选最新一个
  useEffect(() => {
    let cancelled = false;
    openclawApi.getConversations(20).then(({ data }) => {
      if (cancelled) return;
      const list = Array.isArray(data) ? data : [];
      setConvos(list);
      if (list.length > 0) setActiveConvId(list[0].id);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // 切换会话时拉消息
  useEffect(() => {
    if (!activeConvId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    openclawApi.getConversation(activeConvId).then(({ data }) => {
      if (cancelled) return;
      setMessages(data?.messages ?? []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [activeConvId]);

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streaming]);

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
      for await (const evt of openclawApi.streamMessage(text, activeConvId)) {
        if (!evt) continue;
        // 后端事件格式 (parseSimpleSSE): { event, content?, conversation_id?, message_id? }
        const type = evt.event ?? evt.type;
        if (type === 'token' && typeof evt.content === 'string') {
          assistantBuf += evt.content;
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
          );
        } else if (type === 'conversation' && evt.conversation_id) {
          realConvId = evt.conversation_id;
        } else if (type === 'done') {
          setDoneIds(prev => new Set(prev).add(tempAssistantId));
        } else if (type === 'error') {
          assistantBuf += `\n\n_出错: ${evt.content || evt.message || '未知'}_`;
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
      // 如果是新建的会话, 拿到 id 后绑定 + 刷一遍列表
      if (!activeConvId && realConvId) {
        setActiveConvId(realConvId);
        openclawApi.getConversations(20).then(({ data }) => {
          setConvos(Array.isArray(data) ? data : []);
        }).catch(() => {});
      }
    }
  };

  const startNewConversation = () => {
    setActiveConvId(undefined);
    setMessages([]);
  };

  return (
    <main className="flex h-screen bg-slate-950 text-slate-100">
      {/* 侧栏: 会话列表 */}
      <aside className="hidden md:flex w-64 flex-col border-r border-slate-800/60 bg-slate-900/40">
        <div className="px-4 py-4 border-b border-slate-800/60 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">智能助理</h2>
          <button
            onClick={startNewConversation}
            className="rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium px-2.5 py-1.5"
            title="新对话"
          >
            + 新建
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
          {convos.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-slate-500">
              还没有对话, 直接在右侧发消息开始
            </div>
          )}
          {convos.map(c => (
            <button
              key={c.id}
              onClick={() => setActiveConvId(c.id)}
              className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                activeConvId === c.id
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-400 hover:bg-slate-800/60'
              }`}
            >
              <div className="text-sm font-medium truncate">{c.title || '未命名对话'}</div>
              {c.last_message && (
                <div className="mt-0.5 text-[11px] text-slate-500 truncate">
                  {c.last_message}
                </div>
              )}
            </button>
          ))}
        </div>
      </aside>

      {/* 主区: 消息流 + 输入 */}
      <section className="flex-1 flex flex-col min-w-0">
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
