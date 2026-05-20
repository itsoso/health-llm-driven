'use client';

import { KeyboardEvent, useState } from 'react';
import {
  Check,
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
}

export default function ConversationHistoryRail({
  conversations,
  activeConvId,
  loading,
  onLoad,
  onDelete,
  onNew,
  onRename,
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
    <aside className="hidden w-72 shrink-0 border-r border-white/[0.08] bg-[#171717] p-3 md:flex md:flex-col">
      <button
        onClick={onNew}
        className="mb-3 flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] text-sm text-zinc-100 transition-colors hover:bg-white/[0.08]"
      >
        <MessageSquarePlus className="h-4 w-4" />
        新对话
      </button>
      <div className="mb-2 flex items-center gap-2 px-2 text-xs font-medium text-zinc-500">
        <Clock3 className="h-3.5 w-3.5" />
        历史记录
        {loading && <span className="ml-auto text-[11px]">加载中</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {conversations.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 px-3 py-8 text-center text-xs text-zinc-600">
            暂无历史对话
          </div>
        ) : (
          <div className="space-y-1">
            {conversations.map(conv => {
              const isEditing = editingId === conv.id;
              return (
                <div
                  key={conv.id}
                  className={`group rounded-xl px-2 py-2 transition-colors ${
                    conv.id === activeConvId ? 'bg-white/[0.09]' : 'hover:bg-white/[0.06]'
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
                          className="h-8 min-w-0 flex-1 rounded-lg border border-teal-300/30 bg-white/[0.08] px-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-teal-300/60"
                          placeholder="输入标题"
                        />
                        <button
                          onClick={() => saveTitle(conv)}
                          disabled={!draftTitle.trim() || savingId === conv.id}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-teal-200 transition-colors hover:bg-teal-400/10 disabled:text-zinc-600"
                          aria-label="保存标题"
                          title="保存标题"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-white/[0.08] hover:text-zinc-200"
                          aria-label="取消重命名"
                          title="取消"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      {errorId === conv.id && (
                        <div className="px-1 text-[11px] text-red-300">重命名失败，请重试</div>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-start gap-2">
                      <button onClick={() => onLoad(conv.id)} className="min-w-0 flex-1 text-left">
                        <div className="truncate text-sm text-zinc-200">{conv.title || '新对话'}</div>
                        <div className="mt-0.5 truncate text-xs text-zinc-600">
                          {conv.last_message || relativeTime(conv.updated_at)}
                        </div>
                      </button>
                      <button
                        onClick={() => startEdit(conv)}
                        className="mt-0.5 rounded-lg p-1.5 text-zinc-600 opacity-0 transition-all hover:bg-white/[0.08] hover:text-zinc-200 group-hover:opacity-100"
                        aria-label="重命名对话"
                        title="重命名对话"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(conv.id)}
                        className="mt-0.5 rounded-lg p-1.5 text-zinc-600 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-300 group-hover:opacity-100"
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
    </aside>
  );
}
