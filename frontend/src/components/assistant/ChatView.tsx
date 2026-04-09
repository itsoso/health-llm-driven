'use client';

import { ChatMessage } from '@/services/api';
import MarkdownRenderer from '@/components/assistant/MarkdownRenderer';

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
  doneMessageIds: Set<number>;
  messageFeedback: Record<number, 1 | 5>;
  onFeedback: (msgId: number, rating: 1 | 5) => void;
}

const STYLE = {
  badgeClass: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100',
  bubbleClass: 'bg-slate-900/80 border border-emerald-400/15 text-white shadow-[0_24px_80px_rgba(4,120,87,0.12)]',
  userBubbleClass: 'bg-gradient-to-br from-emerald-500 via-cyan-500 to-sky-500 text-white shadow-[0_20px_50px_rgba(20,184,166,0.35)]',
};

export default function ChatView({ messages, loading, doneMessageIds, messageFeedback, onFeedback }: ChatViewProps) {
  const visibleMessages = messages.filter(m => !(m.role === 'assistant' && !m.content));

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {visibleMessages.map(msg => (
        <div key={msg.id} className={`group flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          {msg.role === 'assistant' && (
            <div className={`mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[18px] ${STYLE.badgeClass}`}>
              <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.09 6.26L20.18 9l-5 4.09L16.82 20 12 16.54 7.18 20l1.64-6.91L3.82 9l6.09-.74L12 2z" /></svg>
            </div>
          )}
          {msg.role === 'user' && msg.created_at && (
            <span className="self-center text-[11px] text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 select-none shrink-0">
              {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
            </span>
          )}
          <div className={`max-w-[min(100%,48rem)] rounded-[28px] px-5 py-4 ${msg.role === 'user' ? STYLE.userBubbleClass : STYLE.bubbleClass}`}>
            {msg.role === 'assistant' ? (
              <div className="text-sm leading-8 text-white"><MarkdownRenderer content={msg.content} variant="dark" /></div>
            ) : (
              <div>
                {msg.image_preview && <img src={msg.image_preview} alt="上传图片" className="mb-3 max-h-56 max-w-xs rounded-2xl object-cover" />}
                {msg.file_name && (
                  <div className="mb-3 flex items-center gap-2 rounded-2xl bg-white/10 px-3 py-2 text-sm">
                    <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                    <span className="truncate">{msg.file_name}</span>
                  </div>
                )}
                <div className="whitespace-pre-wrap leading-7">{msg.content}</div>
              </div>
            )}
          </div>
          {msg.role === 'assistant' && msg.created_at && (
            <span className="self-end text-[11px] text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 select-none shrink-0 ml-1 mb-1">
              {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
            </span>
          )}
          {msg.role === 'assistant' && msg.content && doneMessageIds.has(msg.id) && (
            <div className="ml-1 mt-1 flex items-center gap-1 self-end">
              <button onClick={() => onFeedback(msg.id, 5)} className={`rounded-full p-1.5 transition-all ${messageFeedback[msg.id] === 5 ? 'bg-white/20 text-emerald-300' : 'text-white/30 hover:bg-white/10 hover:text-white/60'}`} title="helpful">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z" /></svg>
              </button>
              <button onClick={() => onFeedback(msg.id, 1)} className={`rounded-full p-1.5 transition-all ${messageFeedback[msg.id] === 1 ? 'bg-white/20 text-red-300' : 'text-white/30 hover:bg-white/10 hover:text-white/60'}`} title="not helpful">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z" /></svg>
              </button>
            </div>
          )}
        </div>
      ))}
      {loading && (
        <div className="flex gap-4">
          <div className={`mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[18px] ${STYLE.badgeClass}`}>
            <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.09 6.26L20.18 9l-5 4.09L16.82 20 12 16.54 7.18 20l1.64-6.91L3.82 9l6.09-.74L12 2z" /></svg>
          </div>
          <div className={`rounded-[28px] px-5 py-4 ${STYLE.bubbleClass}`}>
            <div className="flex gap-2">
              <div className="h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300" style={{ animationDelay: '0ms' }} />
              <div className="h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300" style={{ animationDelay: '150ms' }} />
              <div className="h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
