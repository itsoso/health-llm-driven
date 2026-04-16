'use client';
import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface SharedMessage {
  role: string;
  content: string;
  created_at?: string;
}

interface SharedConversation {
  title: string;
  sharer_name?: string;
  messages: SharedMessage[];
  created_at: string;
  source_type: string;
}

export default function SharedConversationPage() {
  const params = useParams();
  const token = params.token as string;
  const [data, setData] = useState<SharedConversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    fetch(`/api/shared/${token}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || '分享链接无效');
        }
        return res.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950/30 to-slate-950 flex items-center justify-center">
        <div className="text-white text-lg animate-pulse">加载中...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950/30 to-slate-950 flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-4">🔗</div>
          <div className="text-white text-xl mb-2">{error || '链接无效'}</div>
          <a
            href="/ai-assistant"
            className="text-purple-400 hover:text-purple-300 underline text-sm"
          >
            前往 AI 助手
          </a>
        </div>
      </div>
    );
  }

  const sourceLabel = data.source_type === 'openclaw' ? 'OpenClaw' : '健康助理';
  const createdDate = data.created_at ? new Date(data.created_at).toLocaleString('zh-CN') : '';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950/30 to-slate-950">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-900/80 backdrop-blur-lg border-b border-white/10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm ${
              data.source_type === 'openclaw' ? 'bg-blue-600/30 text-blue-300' : 'bg-purple-600/30 text-purple-300'
            }`}>
              {data.source_type === 'openclaw' ? '⚡' : '🤖'}
            </div>
            <div className="min-w-0">
              <h1 className="text-white font-medium truncate">{data.title}</h1>
              <div className="text-xs text-slate-400">
                {data.sharer_name && `${data.sharer_name} 分享`}
                {data.sharer_name && ' · '}
                {sourceLabel}
                {createdDate && ` · ${createdDate}`}
              </div>
            </div>
          </div>
          <a
            href="/ai-assistant"
            className="flex-shrink-0 text-xs px-3 py-1.5 rounded-full bg-purple-600/30 text-purple-300 hover:bg-purple-600/50 transition-colors"
          >
            试试 AI 助手
          </a>
        </div>
      </div>

      {/* Messages */}
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
        {data.messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role !== 'user' && (
              <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                data.source_type === 'openclaw' ? 'bg-blue-600/30' : 'bg-purple-600/30'
              }`}>
                {data.source_type === 'openclaw' ? '⚡' : '🤖'}
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-purple-600/40 text-white rounded-br-md'
                  : 'bg-slate-800/60 text-slate-100 rounded-bl-md'
              }`}
            >
              {msg.role === 'user' ? (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</p>
              ) : (
                <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-li:my-0.5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold">
                {data.sharer_name?.[0] || 'U'}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="text-center py-8 text-slate-500 text-xs">
        由 executor.life 健康助理 提供 · {data.messages.length} 条消息
      </div>
    </div>
  );
}
