'use client';

import { KeyboardEvent, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  MessageSquarePlus,
  Pencil,
  Trash2,
  X,
} from 'lucide-react';
import { Conversation } from '@/services/api/ai';
import { relativeTime } from '@/utils/timeFormat';

interface ConversationHistoryRailProps {
  conversations: Conversation[];
  activeConvId?: number;
  loading: boolean;
  onLoad: (id: number) => void;
  onDelete: (id: number) => void;
  onNew: () => void;
  onRename: (id: number, title: string) => Promise<void> | void;
  page?: number;          // 当前页(1-based)
  totalPages?: number;    // 总页数
  onPrevPage?: () => void;
  onNextPage?: () => void;
}

export default function ConversationHistoryRail({
  conversations,
  activeConvId,
  loading,
  onLoad,
  onDelete,
  onNew,
  onRename,
  page = 1,
  totalPages = 1,
  onPrevPage,
  onNextPage,
}: ConversationHistoryRailProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [savingId, setSavingId] = useState<number | null>(null);
  const [errorId, setErrorId] = useState<number | null>(null);

  const startEdit = (conv: Conversation) => {
    setEditingId(conv.id);
    setDraftTitle(conv.title || '');
    setErrorId(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraftTitle('');
    setErrorId(null);
  };

  const saveTitle = async (conv: Conversation) => {
    const nextTitle = draftTitle.trim();
    if (!nextTitle || savingId) return;
    setSavingId(conv.id);
    setErrorId(null);
    try {
      await onRename(conv.id, nextTitle);
      cancelEdit();
    } catch {
      setErrorId(conv.id);
    } finally {
      setSavingId(null);
    }
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>, conv: Conversation) => {
    // IME composition 中 Enter 是确认拼音候选词,不应触发保存
    if (event.nativeEvent.isComposing || event.keyCode === 229) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      saveTitle(conv);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelEdit();
    }
  };

  return (
    <aside className="hidden w-64 shrink-0 border-r border-[#E5E1D5] bg-[#F0EDE4] p-3 md:flex md:flex-col">
      <button
        onClick={onNew}
        className="mb-3 flex h-10 items-center justify-center gap-2 rounded-[10px] border border-[#D8D3C4] bg-[#FCFBF7] text-[13.5px] font-medium text-[#29261F] transition-colors hover:border-[#C96442]"
      >
        <MessageSquarePlus className="h-4 w-4" />
        新对话
      </button>
      <div className="mb-2 flex items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-[0.09em] text-[#948F80]">
        <Clock3 className="h-3.5 w-3.5" />
        历史记录
        {loading && <span className="ml-auto text-[11px] normal-case tracking-normal">加载中</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {conversations.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#D8D3C4] px-3 py-8 text-center text-xs text-[#948F80]">
            暂无历史对话
          </div>
        ) : (
          <div className="space-y-1">
            {conversations.map(conv => {
              const isEditing = editingId === conv.id;
              return (
                <div
                  key={conv.id}
                  className={`group rounded-lg px-2 py-2 transition-colors ${
                    conv.id === activeConvId ? 'bg-[#F3E4DC]' : 'hover:bg-[#E8E4D8]'
                  }`}
                >
                  {isEditing ? (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1">
                        <input
                          aria-label="对话标题"
                          value={draftTitle}
                          onChange={event => setDraftTitle(event.target.value)}
                          onKeyDown={event => handleInputKeyDown(event, conv)}
                          autoFocus
                          disabled={savingId === conv.id}
                          className="h-8 min-w-0 flex-1 rounded-lg border border-[#C96442]/50 bg-[#FCFBF7] px-2 text-sm text-[#29261F] outline-none placeholder:text-[#948F80] focus:border-[#C96442]"
                          placeholder="输入标题"
                        />
                        <button
                          onClick={() => saveTitle(conv)}
                          disabled={!draftTitle.trim() || savingId === conv.id}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-[#C96442] transition-colors hover:bg-[#F3E4DC] disabled:text-[#B4AF9F]"
                          aria-label="保存标题"
                          title="保存标题"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-[#948F80] transition-colors hover:bg-[#E8E4D8] hover:text-[#29261F]"
                          aria-label="取消重命名"
                          title="取消"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      {errorId === conv.id && (
                        <div className="px-1 text-[11px] text-[#B4573A]">重命名失败，请重试</div>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-start gap-2">
                      <button onClick={() => onLoad(conv.id)} className="min-w-0 flex-1 text-left">
                        <div className={`truncate text-[13px] ${conv.id === activeConvId ? 'font-medium text-[#C96442]' : 'text-[#29261F]'}`}>
                          {conv.title || '新对话'}
                        </div>
                        <div className="mt-0.5 truncate text-[11.5px] text-[#948F80]">
                          {conv.last_message || relativeTime(conv.updated_at)}
                        </div>
                      </button>
                      <button
                        onClick={() => startEdit(conv)}
                        className="mt-0.5 rounded-lg p-1.5 text-[#948F80] opacity-0 transition-all hover:bg-[#E8E4D8] hover:text-[#29261F] group-hover:opacity-100"
                        aria-label="重命名对话"
                        title="重命名对话"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(conv.id)}
                        className="mt-0.5 rounded-lg p-1.5 text-[#948F80] opacity-0 transition-all hover:bg-[#C96442]/10 hover:text-[#B4573A] group-hover:opacity-100"
                        title="删除对话"
                        aria-label="删除对话"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      {totalPages > 1 && (
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-[#E5E1D5] px-1 pt-2">
          <button
            onClick={onPrevPage}
            disabled={page <= 1 || loading}
            className="flex h-8 items-center gap-1 rounded-lg px-2 text-[11.5px] text-[#6B665A] transition-colors hover:bg-[#E8E4D8] disabled:cursor-not-allowed disabled:text-[#B4AF9F] disabled:hover:bg-transparent"
            aria-label="上一页"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            上一页
          </button>
          <span className="text-[11px] tabular-nums text-[#948F80]">
            第 {page} / {totalPages} 页
          </span>
          <button
            onClick={onNextPage}
            disabled={page >= totalPages || loading}
            className="flex h-8 items-center gap-1 rounded-lg px-2 text-[11.5px] text-[#6B665A] transition-colors hover:bg-[#E8E4D8] disabled:cursor-not-allowed disabled:text-[#B4AF9F] disabled:hover:bg-transparent"
            aria-label="下一页"
          >
            下一页
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </aside>
  );
}
