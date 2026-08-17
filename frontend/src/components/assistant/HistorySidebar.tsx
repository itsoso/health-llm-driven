'use client';

import { useState } from 'react';
import { Conversation } from '@/services/api/ai';
import { relativeTime } from '@/utils/timeFormat';

interface HistorySidebarProps {
  conversations: Conversation[];
  currentConversationId?: number;
  onLoadConversation: (convId: number) => void;
  onNewChat: () => void;
  onClose: () => void;
  onDelete: (convId: number) => void;
  onShare: (convId: number) => void;
}

const BRIEFING_PREFIX = '每日健康简报';
const WEEKLY_PREFIX = '每周健康周报';
const isBriefingTitle = (t: string) => t === BRIEFING_PREFIX || t.startsWith(BRIEFING_PREFIX + ' ');
const isWeeklyTitle = (t: string) => t === WEEKLY_PREFIX || t.startsWith(WEEKLY_PREFIX + ' ');


export default function HistorySidebar({
  conversations,
  currentConversationId,
  onLoadConversation,
  onNewChat,
  onClose,
  onDelete,
  onShare,
}: HistorySidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const filtered = conversations.filter(
    (c) =>
      c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.last_message && c.last_message.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // The API owns ordering. Do not pin system-generated briefings by title:
  // background refreshes must not make them appear as the user's latest chat.
  const sorted = filtered;

  const totalPages = Math.ceil(sorted.length / itemsPerPage);
  const paginated = sorted.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  return (
    <aside className="flex w-[330px] shrink-0 flex-col border-r border-gray-200 bg-white/95 backdrop-blur-xl">
      {/* Top section */}
      <div className="border-b border-gray-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            onClick={onNewChat}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-medium text-white transition-all hover:bg-emerald-600 active:scale-[0.98] shadow-sm"
          >
            <span className="text-lg leading-none">+</span> 新建对话
          </button>
          <button
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-gray-50 text-gray-400 transition-all hover:bg-gray-100 hover:text-gray-600"
            title="收起侧边栏"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
            </svg>
          </button>
        </div>
        <div className="relative mt-3">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
            placeholder="搜索对话..."
            className="w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-2.5 pl-10 text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400"
          />
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {conversations.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-6 py-10 text-center text-gray-400">
            <div className="text-4xl">💬</div>
            <div className="mt-3 text-sm">还没有历史对话</div>
          </div>
        ) : paginated.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-6 py-10 text-center text-gray-400">
            <div className="text-4xl">🔍</div>
            <div className="mt-3 text-sm">没有找到匹配结果</div>
          </div>
        ) : (
          <div className="space-y-1.5">
            {paginated.map((conv) => {
              const isBriefing = isBriefingTitle(conv.title);
              const isWeekly = isWeeklyTitle(conv.title);
              const isActive = conv.id === currentConversationId;
              return (
                <button
                  key={conv.id}
                  onClick={() => onLoadConversation(conv.id)}
                  className={`group w-full rounded-2xl border px-3.5 py-3 text-left transition-all ${
                    isActive
                      ? 'border-emerald-200 bg-emerald-50 shadow-sm'
                      : isBriefing
                        ? 'border-amber-100 bg-amber-50/60 hover:border-amber-200 hover:bg-amber-50'
                        : isWeekly
                          ? 'border-purple-100 bg-purple-50/60 hover:border-purple-200 hover:bg-purple-50'
                          : 'border-transparent bg-transparent hover:border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
                        isBriefing ? 'bg-amber-100' : isWeekly ? 'bg-purple-100' : 'bg-emerald-100'
                      }`}
                    >
                      <span className="text-sm">{isBriefing ? '🌅' : isWeekly ? '📊' : '💬'}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div
                        className={`flex items-center gap-2 text-sm font-medium leading-6 ${
                          isBriefing ? 'text-amber-700' : isWeekly ? 'text-purple-700' : 'text-gray-800'
                        }`}
                      >
                        <span className="line-clamp-1">{conv.title}</span>
                        {isBriefing && (
                          <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-600">
                            每日
                          </span>
                        )}
                        {isWeekly && (
                          <span className="shrink-0 rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-600">
                            周报
                          </span>
                        )}
                      </div>
                      {conv.last_message && (
                        <div className="mt-0.5 text-xs leading-5 text-gray-500 truncate">
                          {conv.last_message.length > 30
                            ? conv.last_message.slice(0, 30) + '...'
                            : conv.last_message}
                        </div>
                      )}
                      {conv.updated_at && (
                        <div className="mt-0.5 text-[11px] text-gray-400">{relativeTime(conv.updated_at)}</div>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-[11px] text-gray-400">
                      {isBriefing ? '📊 日报' : isWeekly ? '📈 周报' : `#${conv.id}`}
                    </span>
                    <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onShare(conv.id);
                        }}
                        className="text-xs text-gray-400 transition-colors hover:text-gray-700"
                        title="分享对话"
                      >
                        分享
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(conv.id);
                        }}
                        className="text-xs text-gray-400 transition-colors hover:text-red-500"
                        title="删除对话"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {sorted.length > itemsPerPage && (
        <div className="border-t border-gray-100 px-4 py-3">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="rounded-full border border-gray-200 px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              上一页
            </button>
            <span>
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="rounded-full border border-gray-200 px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
