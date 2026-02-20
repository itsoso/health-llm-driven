'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';

interface PlanItem {
  id: string;
  emoji: string;
  text: string;
  done: boolean;
}

const EMOJI_OPTIONS = [
  '📚', '🏃', '🏊', '🎨', '🎵', '🍎',
  '💤', '🦷', '🛁', '📝', '⚽', '🎯',
  '🍱', '🎮', '🧩', '🌈', '✏️', '🎭',
];

export default function KidsPlanPage() {
  const { user } = useAuth();
  const theme = useKidsTheme();
  const today = new Date().toISOString().split('T')[0];
  const storageKey = `kids_plan_${user?.id || 'guest'}_${today}`;

  const [items, setItems] = useState<PlanItem[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [modalEmoji, setModalEmoji] = useState('📝');
  const [modalText, setModalText] = useState('');

  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try { setItems(JSON.parse(saved)); } catch { /* ignore */ }
    }
  }, [storageKey]);

  const saveItems = useCallback((newItems: PlanItem[]) => {
    setItems(newItems);
    localStorage.setItem(storageKey, JSON.stringify(newItems));
  }, [storageKey]);

  const toggleDone = (id: string) => {
    saveItems(items.map(item => item.id === id ? { ...item, done: !item.done } : item));
  };

  const deleteItem = (id: string) => {
    saveItems(items.filter(item => item.id !== id));
  };

  const openAdd = () => {
    setEditingId(null);
    setModalEmoji('📝');
    setModalText('');
    setShowModal(true);
  };

  const openEdit = (item: PlanItem) => {
    setEditingId(item.id);
    setModalEmoji(item.emoji);
    setModalText(item.text);
    setShowModal(true);
  };

  const handleSave = () => {
    if (!modalText.trim()) return;
    if (editingId) {
      saveItems(items.map(item =>
        item.id === editingId ? { ...item, emoji: modalEmoji, text: modalText.trim() } : item
      ));
    } else {
      saveItems([...items, { id: Date.now().toString(), emoji: modalEmoji, text: modalText.trim(), done: false }]);
    }
    setShowModal(false);
  };

  const doneCount = items.filter(i => i.done).length;
  const total = items.length;
  const dateStr = new Date().toLocaleDateString('zh-CN', {
    month: 'long', day: 'numeric', weekday: 'long',
  });

  return (
    <div className="flex flex-col h-full">
      {/* 顶栏 */}
      <div className={`px-6 py-4 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="flex items-center justify-between max-w-2xl mx-auto">
          <div>
            <h1 className={`text-2xl font-bold ${theme.accent} flex items-center gap-2`}>
              <span>📋</span> 今日计划
            </h1>
            <p className="text-gray-400 text-sm mt-0.5">{dateStr}</p>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-bold ${doneCount === total && total > 0 ? 'text-green-500' : theme.accent}`}>
              {doneCount}/{total}
            </div>
            <div className="text-gray-400 text-xs">已完成</div>
          </div>
        </div>

        {/* 进度条 */}
        {total > 0 && (
          <div className="max-w-2xl mx-auto mt-3">
            <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full bg-gradient-to-r ${theme.btnGrad} transition-all duration-500`}
                style={{ width: `${total > 0 ? (doneCount / total) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* 计划列表 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-2xl mx-auto space-y-3">
          {items.length === 0 ? (
            <div className="text-center py-16">
              <div className="text-7xl mb-4">📋</div>
              <p className="text-xl text-gray-400 font-medium">今天还没有计划哦~</p>
              <p className="text-base text-gray-400 mt-1">点下面的按钮来添加吧！</p>
            </div>
          ) : (
            items.map(item => (
              <div
                key={item.id}
                className={`flex items-center gap-4 p-4 rounded-2xl border-2 bg-white shadow-sm transition-all ${
                  item.done ? 'border-green-200 bg-green-50' : `${theme.cardBorder}`
                }`}
              >
                {/* 完成按钮 */}
                <button
                  onClick={() => toggleDone(item.id)}
                  className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all active:scale-90 ${
                    item.done
                      ? 'bg-green-400 text-white shadow-md'
                      : `border-2 border-gray-300 ${theme.cardHoverBorder}`
                  }`}
                >
                  {item.done && <span className="text-xl font-bold">✓</span>}
                </button>

                {/* 表情 + 文字（点击编辑） */}
                <button
                  onClick={() => !item.done && openEdit(item)}
                  disabled={item.done}
                  className="flex-1 flex items-center gap-3 text-left"
                >
                  <span className="text-3xl flex-shrink-0">{item.emoji}</span>
                  <span className={`text-lg font-medium leading-snug ${
                    item.done ? 'line-through text-gray-400' : 'text-gray-700'
                  }`}>
                    {item.text}
                  </span>
                </button>

                {/* 删除按钮 */}
                <button
                  onClick={() => deleteItem(item.id)}
                  className="w-8 h-8 rounded-full bg-red-50 hover:bg-red-100 flex items-center justify-center text-red-300 hover:text-red-400 transition-all flex-shrink-0 text-xl leading-none"
                >
                  ×
                </button>
              </div>
            ))
          )}

          {/* 全部完成庆祝 */}
          {total > 0 && doneCount === total && (
            <div className="text-center py-8">
              <div className="text-7xl mb-3 animate-bounce">🎉</div>
              <p className="text-2xl font-bold text-green-500">今天的计划全完成啦！</p>
              <p className="text-base text-gray-400 mt-1">太厉害了，继续加油！</p>
            </div>
          )}
        </div>
      </div>

      {/* 添加按钮 */}
      <div className={`px-6 py-4 bg-white/80 backdrop-blur-sm border-t-2 ${theme.navBorder} flex-shrink-0`}>
        <button
          onClick={openAdd}
          className={`w-full max-w-2xl mx-auto flex items-center justify-center gap-2 py-4 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white text-xl font-bold shadow-lg hover:shadow-xl active:scale-95 transition-all`}
        >
          <span className="text-2xl font-light">+</span>
          添加计划
        </button>
      </div>

      {/* 添加/编辑弹窗 */}
      {showModal && (
        <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center bg-black/30 px-0 sm:px-4">
          <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 shadow-2xl w-full sm:max-w-sm">
            <h3 className={`text-2xl font-bold ${theme.accent} text-center mb-5`}>
              {editingId ? '✏️ 修改计划' : '➕ 添加计划'}
            </h3>

            {/* 表情选择器 */}
            <p className="text-sm text-gray-500 mb-2 font-medium">选个表情：</p>
            <div className="grid grid-cols-6 gap-2 mb-5">
              {EMOJI_OPTIONS.map(emoji => (
                <button
                  key={emoji}
                  onClick={() => setModalEmoji(emoji)}
                  className={`text-2xl p-2 rounded-xl transition-all active:scale-90 ${
                    modalEmoji === emoji
                      ? `bg-gradient-to-br ${theme.btnGrad} shadow-md scale-110`
                      : 'hover:bg-gray-100'
                  }`}
                >
                  {emoji}
                </button>
              ))}
            </div>

            {/* 文字输入 */}
            <p className="text-sm text-gray-500 mb-2 font-medium">计划内容：</p>
            <div className="flex items-center gap-3 mb-6">
              <span className="text-3xl flex-shrink-0">{modalEmoji}</span>
              <input
                type="text"
                value={modalText}
                onChange={e => setModalText(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleSave();
                  if (e.key === 'Escape') setShowModal(false);
                }}
                placeholder="比如：读书30分钟"
                className={`flex-1 px-4 py-3 border-2 ${theme.inputBorder} rounded-2xl text-lg focus:outline-none ${theme.inputFocus}`}
                autoFocus
                maxLength={20}
              />
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-3">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 py-3 rounded-2xl border-2 border-gray-200 text-lg font-bold text-gray-500 hover:bg-gray-50 active:scale-95 transition-all"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={!modalText.trim()}
                className={`flex-1 py-3 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-lg font-bold text-white shadow-md hover:shadow-lg active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {editingId ? '保存' : '添加'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
