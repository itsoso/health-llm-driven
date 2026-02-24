'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage } from '@/services/api';

interface KidsChatBubbleProps {
  message: ChatMessage;
  avatarUrl?: string | null;
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msgDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.floor((today.getTime() - msgDay.getTime()) / 86400000);
  const timeStr = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  if (diffDays === 0) return timeStr;
  if (diffDays === 1) return `昨天 ${timeStr}`;
  if (diffDays < 7) return `${['周日','周一','周二','周三','周四','周五','周六'][d.getDay()]} ${timeStr}`;
  return `${d.getMonth() + 1}/${d.getDate()} ${timeStr}`;
}

export default function KidsChatBubble({ message, avatarUrl }: KidsChatBubbleProps) {
  const isUser = message.role === 'user';
  const timeLabel = formatTime(message.created_at);

  return (
    <div className={`flex flex-col mb-4 ${isUser ? 'items-end' : 'items-start'}`}>
      {timeLabel && (
        <div className="text-xs text-gray-400 mb-1 px-14">{timeLabel}</div>
      )}
      <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-pink-300 to-purple-300 flex items-center justify-center flex-shrink-0 shadow-md">
          <span className="text-2xl">🌟</span>
        </div>
      )}
      <div className={`max-w-[75%] rounded-3xl px-5 py-4 shadow-md ${
        isUser
          ? 'bg-gradient-to-r from-pink-400 to-purple-400 text-white'
          : 'bg-white border-2 border-pink-100 text-gray-800'
      }`}>
        {isUser ? (
          <div className="text-lg whitespace-pre-wrap">{message.content}</div>
        ) : (
          <div className="text-lg leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-3 last:mb-0 whitespace-pre-wrap">{children}</p>,
                ul: ({ children }) => <ul className="list-disc ml-5 mb-3 space-y-1.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal ml-5 mb-3 space-y-1.5">{children}</ol>,
                li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                h1: ({ children }) => <h1 className="text-2xl font-bold mb-3 mt-4 first:mt-0 text-purple-600">{children}</h1>,
                h2: ({ children }) => <h2 className="text-xl font-bold mb-2 mt-4 first:mt-0 text-purple-600">{children}</h2>,
                h3: ({ children }) => <h3 className="text-lg font-bold mb-2 mt-3 first:mt-0 text-purple-500">{children}</h3>,
                strong: ({ children }) => <strong className="font-bold text-pink-600">{children}</strong>,
                em: ({ children }) => <em className="italic text-gray-600">{children}</em>,
                code: ({ node, ...props }: any) => {
                  const inline = !props.className?.includes('language-');
                  return inline ? (
                    <code className="px-1.5 py-0.5 bg-pink-50 rounded text-purple-600 font-mono text-base" {...props} />
                  ) : (
                    <code className="block px-4 py-3 bg-gray-50 rounded-lg overflow-x-auto font-mono text-base my-2" {...props} />
                  );
                },
                pre: ({ children }) => <pre className="bg-gray-50 rounded-xl p-4 overflow-x-auto my-3">{children}</pre>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-pink-300 pl-4 py-2 my-3 italic text-gray-600 bg-pink-50/50 rounded-r-xl">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-3">
                    <table className="min-w-full border-collapse border border-pink-200 rounded-lg overflow-hidden">
                      {children}
                    </table>
                  </div>
                ),
                thead: ({ children }) => <thead className="bg-pink-50">{children}</thead>,
                tbody: ({ children }) => <tbody className="bg-white">{children}</tbody>,
                tr: ({ children }) => <tr className="border-b border-pink-100 last:border-0">{children}</tr>,
                th: ({ children }) => <th className="border border-pink-200 px-3 py-2 text-left font-semibold text-purple-600">{children}</th>,
                td: ({ children }) => <td className="border border-pink-200 px-3 py-2">{children}</td>,
                hr: () => <hr className="my-4 border-pink-200" />,
                a: ({ children, href }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="text-purple-500 hover:text-purple-400 underline">
                    {children}
                  </a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-300 to-cyan-300 flex items-center justify-center flex-shrink-0 shadow-md overflow-hidden">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            <span className="text-2xl">👧</span>
          )}
        </div>
      )}
    </div>
    </div>
  );
}
