'use client';

import { useState } from 'react';
import { Bookmark, Copy, Sparkles, ThumbsDown, ThumbsUp } from 'lucide-react';
import { ChatMessage } from '@/services/api/ai';
import MarkdownRenderer from '@/components/assistant/MarkdownRenderer';
import { renderCard } from '@/components/assistant/inlineCards';

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
  doneMessageIds: Set<number>;
  messageFeedback: Record<number, 1 | 5>;
  onFeedback: (msgId: number, rating: 1 | 5) => void;
  onPinMessage?: (content: string, msgId: number) => void;
}

const STYLE = {
  badgeClass: 'bg-teal-500/15 text-teal-300 ring-1 ring-teal-300/15',
  assistantTextClass: 'text-zinc-100',
  userBubbleClass: 'bg-[#2f2f2f] text-zinc-50',
};

export default function ChatView({ messages, loading, doneMessageIds, messageFeedback, onFeedback, onPinMessage }: ChatViewProps) {
  // 允许空内容但是有卡片的消息显示
  const visibleMessages = messages.filter(m => !(m.role === 'assistant' && !m.content && !m.card_type));

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      {visibleMessages.map(msg => {
        // 动态卡片消息 - 独立分支, 气泡外直接贴卡片
        if (msg.card_type && msg.card_data) {
          const cardEl = renderCard({ type: msg.card_type, data: msg.card_data });
          if (cardEl) {
            return (
              <div key={msg.id} className="flex gap-3 justify-start">
                <div className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${STYLE.badgeClass}`}>
                  <Sparkles className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">{cardEl}</div>
              </div>
            );
          }
        }
        return (
        <div key={msg.id} className={`group flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          {msg.role === 'assistant' && (
            <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${STYLE.badgeClass}`}>
              <Sparkles className="h-4 w-4" />
            </div>
          )}
          {msg.role === 'user' && msg.created_at && (
            <span className="self-center select-none text-[11px] text-zinc-600 opacity-0 transition-opacity group-hover:opacity-100 shrink-0">
              {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
          )}
          <div className={`${msg.role === 'user' ? 'max-w-[min(80%,34rem)] rounded-[1.35rem] px-4 py-2.5 shadow-sm' : 'min-w-0 flex-1'} ${msg.role === 'user' ? STYLE.userBubbleClass : STYLE.assistantTextClass}`}>
            {msg.role === 'assistant' ? (
              <div>
                <div className="text-[15px] leading-7"><MarkdownRenderer content={msg.content} variant="dark" /></div>
                {/* 2026-05-13 性能 footer: 耗时 + 模型 + 每轮 ms */}
                {doneMessageIds.has(msg.id) && (msg.elapsed_ms != null || msg.model || (msg.sources_used && msg.sources_used.length > 0)) && (
                  <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-white/[0.08] pt-2 text-[11px] tabular-nums text-zinc-600">
                    {msg.elapsed_ms != null && (
                      <span className="inline-flex items-center gap-1" title="总耗时">
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        {(msg.elapsed_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                    {msg.llm_ms != null && msg.elapsed_ms != null && msg.llm_ms !== msg.elapsed_ms && (
                      <span title="LLM 推理耗时">LLM {(msg.llm_ms / 1000).toFixed(1)}s</span>
                    )}
                    {msg.llm_rounds != null && msg.llm_rounds > 1 && (
                      <span title="LLM 工具调用轮数">{msg.llm_rounds} 轮</span>
                    )}
                    {msg.llm_rounds_ms && msg.llm_rounds_ms.length > 1 && (
                      <span title="每轮耗时" className="text-zinc-700">
                        ({msg.llm_rounds_ms.map(ms => `${ms}ms`).join(' / ')})
                      </span>
                    )}
                    {msg.model && (
                      <span className="ml-auto text-teal-400/70" title="本次回答的模型">· {msg.model}</span>
                    )}
                  </div>
                )}
                {/* 2026-05-14 #4: 可解释性 chip — AI 用了什么数据 */}
                {doneMessageIds.has(msg.id) && msg.sources_used && msg.sources_used.length > 0 && (
                  <SourcesChip sources={msg.sources_used} />
                )}
              </div>
            ) : (
              <div>
                {msg.image_preview && <img src={msg.image_preview} alt="上传图片" className="mb-2 max-h-56 max-w-xs rounded-xl object-cover" />}
                {msg.file_name && (
                  <div className="mb-2 flex items-center gap-2 rounded-xl bg-white/15 px-3 py-1.5 text-sm">
                    <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                    <span className="truncate">{msg.file_name}</span>
                  </div>
                )}
                <div className="whitespace-pre-wrap text-[15px] leading-6">{msg.content}</div>
              </div>
            )}
          </div>
          {msg.role === 'assistant' && msg.created_at && (
            <span className="mb-1 ml-1 self-end select-none text-[11px] text-zinc-600 opacity-0 transition-opacity group-hover:opacity-100 shrink-0">
              {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
          )}
          {msg.role === 'assistant' && msg.content && doneMessageIds.has(msg.id) && (
            <div className="ml-1 mt-1 flex items-center gap-0.5 self-end opacity-0 transition-opacity group-hover:opacity-100">
              <button onClick={() => navigator.clipboard?.writeText(msg.content)} className="rounded-lg p-1.5 text-zinc-500 transition-all hover:bg-white/5 hover:text-zinc-200" title="复制">
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => onFeedback(msg.id, 5)} className={`rounded-lg p-1.5 transition-all ${messageFeedback[msg.id] === 5 ? 'bg-teal-400/15 text-teal-300' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'}`} title="helpful">
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => onFeedback(msg.id, 1)} className={`rounded-lg p-1.5 transition-all ${messageFeedback[msg.id] === 1 ? 'bg-rose-400/15 text-rose-300' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'}`} title="not helpful">
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
              {onPinMessage && (
                <button onClick={() => onPinMessage(msg.content, msg.id)} className="rounded-lg p-1.5 text-zinc-500 transition-all hover:bg-white/5 hover:text-amber-300" title="固化到首页">
                  <Bookmark className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
        );
      })}
      {loading && (
        <div className="flex gap-3">
          <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${STYLE.badgeClass}`}>
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="px-1 py-2.5">
            <div className="flex gap-1.5 rounded-full bg-[#2f2f2f] px-3 py-2">
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-300" style={{ animationDelay: '0ms' }} />
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-300" style={{ animationDelay: '150ms' }} />
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-300" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** 2026-05-14 #4 可解释性 chip — 默认折叠 "🔍 AI 用了什么数据 (N)", 点开列出来. */
function SourcesChip({ sources }: { sources: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-zinc-500 transition-colors hover:border-teal-300/30 hover:text-teal-300"
        title="点击展开 / 折叠"
      >
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        AI 用了 {sources.length} 项数据
        <svg className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <ul className="mt-1.5 ml-3 space-y-0.5 text-[11px] text-zinc-500">
          {sources.map((s, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className="shrink-0 text-teal-400/60">·</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
