'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import { kidsPlanApi, KidsPlanItem, KidsPlanDaySummary } from '@/services/api';

interface PlanItem extends KidsPlanItem {}

const EMOJI_OPTIONS = [
  '📚', '🏃', '🏊', '🎨', '🎵', '🍎',
  '💤', '🦷', '🛁', '📝', '⚽', '🎯',
  '🍱', '🎮', '🧩', '🌈', '✏️', '🎭',
];

const DURATION_OPTIONS = [
  { label: '15分钟', value: 15 },
  { label: '30分钟', value: 30 },
  { label: '45分钟', value: 45 },
  { label: '1小时', value: 60 },
  { label: '1.5小时', value: 90 },
  { label: '2小时', value: 120 },
];

function computeEndTime(start: string, durationMinutes: number): string {
  if (!start || !durationMinutes) return '';
  const [h, m] = start.split(':').map(Number);
  const total = h * 60 + m + durationMinutes;
  const endH = Math.floor(total / 60) % 24;
  const endM = total % 60;
  return `${endH.toString().padStart(2, '0')}:${endM.toString().padStart(2, '0')}`;
}

function getLocalDateStr(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// localStorage 缓存 key
function getCacheKey(userId: number | string, dateStr: string) {
  return `kids_plan_cache_${userId}_${dateStr}`;
}

// 骨架屏占位
function SkeletonItem({ theme }: { theme: { cardBorder: string } }) {
  return (
    <div className={`flex items-center gap-4 p-4 rounded-2xl border-2 bg-white shadow-sm ${theme.cardBorder} animate-pulse`}>
      <div className="w-10 h-10 rounded-full bg-gray-100 flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-gray-100 rounded-full w-3/4" />
        <div className="h-3 bg-gray-100 rounded-full w-1/3" />
      </div>
      <div className="w-8 h-8 rounded-full bg-gray-100 flex-shrink-0" />
    </div>
  );
}

export default function KidsPlanPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { theme, points, addPoints } = useKidsTheme();
  const userId = user?.id || 'guest';
  const today = getLocalDateStr(new Date());

  const [items, setItems] = useState<PlanItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [modalEmoji, setModalEmoji] = useState('📝');
  const [modalText, setModalText] = useState('');
  const [modalHasTime, setModalHasTime] = useState(false);
  const [modalStartTime, setModalStartTime] = useState('');
  const [modalDuration, setModalDuration] = useState(0);
  const [showCopied, setShowCopied] = useState(false);
  const [pointsToast, setPointsToast] = useState(0);
  const [weekHistory, setWeekHistory] = useState<KidsPlanDaySummary[]>([]);

  // debounce save timer
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 1. 立即从 localStorage 缓存恢复，避免白屏等待
  useEffect(() => {
    if (!user) return;
    const cacheKey = getCacheKey(user.id, today);
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      try {
        const parsed = JSON.parse(cached) as PlanItem[];
        if (parsed.length > 0) {
          setItems(parsed);
          setLoading(false); // 有缓存就立即显示
        }
      } catch { /* ignore */ }
    }
  }, [user, today]);

  // 2. 并行加载：getPlan + getHistory 同时发出，减少等待时间
  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    const loadAll = async () => {
      try {
        // 两个请求并行发出
        const [planRes, historyRes] = await Promise.all([
          kidsPlanApi.getPlan(today),
          kidsPlanApi.getHistory('week').catch(() => null), // history 失败不影响主流程
        ]);

        if (cancelled) return;

        // 更新周历史
        if (historyRes) {
          setWeekHistory(historyRes.data.days || []);
        }

        const serverItems = planRes.data.items || [];

        // localStorage 迁移（旧版数据）
        if (serverItems.length === 0) {
          const legacyKey = `kids_plan_${userId}_${today}`;
          const legacyData = localStorage.getItem(legacyKey);
          if (legacyData) {
            try {
              const parsed = JSON.parse(legacyData) as PlanItem[];
              if (parsed.length > 0) {
                setItems(parsed);
                setLoading(false);
                await kidsPlanApi.savePlan(today, parsed);
                localStorage.removeItem(legacyKey);
                // 写入新缓存
                localStorage.setItem(getCacheKey(user.id, today), JSON.stringify(parsed));
                return;
              }
            } catch { /* ignore */ }
          }
        }

        setItems(serverItems);
        // 写入缓存供下次快速加载
        if (serverItems.length > 0) {
          localStorage.setItem(getCacheKey(user.id, today), JSON.stringify(serverItems));
        }
      } catch (err) {
        console.error('Failed to load plan:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadAll();
    return () => { cancelled = true; };
  }, [today, user, userId]);

  // Debounced save to server
  const debouncedSave = useCallback((newItems: PlanItem[]) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      try {
        const res = await kidsPlanApi.savePlan(today, newItems);
        const { points_awarded } = res.data;
        // 同步更新缓存
        localStorage.setItem(getCacheKey(userId, today), JSON.stringify(newItems));
        if (points_awarded > 0) {
          addPoints(points_awarded);
          setPointsToast(points_awarded);
          setTimeout(() => setPointsToast(0), 2500);
        }
      } catch (err) {
        console.error('Failed to save plan:', err);
      }
    }, 500);
  }, [today, userId, addPoints]);

  const saveItems = useCallback((newItems: PlanItem[]) => {
    setItems(newItems);
    debouncedSave(newItems);
  }, [debouncedSave]);

  const toggleDone = (id: string) => {
    const newItems = items.map(item => item.id === id ? { ...item, done: !item.done } : item);
    saveItems(newItems);
  };

  const deleteItem = (id: string) => {
    saveItems(items.filter(item => item.id !== id));
  };

  const openAdd = () => {
    setEditingId(null);
    setModalEmoji('📝');
    setModalText('');
    setModalHasTime(false);
    setModalStartTime('');
    setModalDuration(0);
    setShowModal(true);
  };

  const openEdit = (item: PlanItem) => {
    setEditingId(item.id);
    setModalEmoji(item.emoji);
    setModalText(item.text);
    setModalHasTime(!!item.startTime);
    setModalStartTime(item.startTime || '');
    if (item.startTime && item.endTime) {
      const [sh, sm] = item.startTime.split(':').map(Number);
      const [eh, em] = item.endTime.split(':').map(Number);
      const dur = (eh * 60 + em) - (sh * 60 + sm);
      setModalDuration(dur > 0 ? dur : 0);
    } else {
      setModalDuration(0);
    }
    setShowModal(true);
  };

  const handleSave = () => {
    if (!modalText.trim()) return;
    const startTime = modalHasTime && modalStartTime ? modalStartTime : undefined;
    const endTime = startTime && modalDuration > 0 ? computeEndTime(startTime, modalDuration) : undefined;
    const updates = { emoji: modalEmoji, text: modalText.trim(), startTime, endTime };

    if (editingId) {
      saveItems(items.map(item => item.id === editingId ? { ...item, ...updates } : item));
    } else {
      saveItems([...items, { id: Date.now().toString(), ...updates, done: false }]);
    }
    setShowModal(false);
  };

  const copyToTomorrow = async () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = getLocalDateStr(tomorrow);
    try {
      await kidsPlanApi.copyPlan(today, tomorrowStr);
      setShowCopied(true);
      setTimeout(() => setShowCopied(false), 2500);
    } catch (err) {
      console.error('Failed to copy plan:', err);
    }
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
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/kids/plan/history')}
              className={`px-3 py-2 rounded-xl border-2 ${theme.cardBorder} text-lg active:scale-95 transition-all`}
              title="计划回顾"
            >
              📊
            </button>
            <div className="text-right">
              <div className={`text-3xl font-bold ${doneCount === total && total > 0 ? 'text-green-500' : theme.accent}`}>
                {total > 0 ? `${doneCount}/${total}` : (loading ? '…' : '0/0')}
              </div>
              <div className="flex items-center justify-end gap-1 mt-0.5">
                <span className="text-amber-400 text-sm font-bold">⭐{points}</span>
                <span className="text-gray-400 text-xs">积分</span>
              </div>
            </div>
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

      {/* 最近7天完成情况（懒渲染，不阻塞主内容） */}
      {weekHistory.length > 0 && (
        <button
          onClick={() => router.push('/kids/plan/history')}
          className={`mx-6 mt-3 p-3 rounded-2xl border-2 ${theme.cardBorder} bg-white/60 flex-shrink-0 active:scale-[0.98] transition-all`}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-gray-500">最近7天</span>
            <span className="text-xs text-gray-400">查看更多 ›</span>
          </div>
          <div className="flex gap-1.5">
            {weekHistory.slice(-7).map((day) => {
              const weekday = ['日', '一', '二', '三', '四', '五', '六'][new Date(day.plan_date + 'T00:00:00').getDay()];
              const isToday = day.plan_date === today;
              let bgColor = 'bg-gray-100';
              if (day.total_items > 0) {
                if (day.completion_rate >= 0.8) bgColor = 'bg-green-400';
                else if (day.completion_rate >= 0.5) bgColor = 'bg-yellow-400';
                else if (day.completion_rate > 0) bgColor = 'bg-orange-300';
                else bgColor = 'bg-red-300';
              }
              return (
                <div key={day.plan_date} className="flex-1 flex flex-col items-center gap-1">
                  <span className={`text-[10px] ${isToday ? 'font-bold ' + theme.accent : 'text-gray-400'}`}>
                    {isToday ? '今' : weekday}
                  </span>
                  <div className={`w-full aspect-square rounded-lg ${bgColor} flex items-center justify-center ${isToday ? 'ring-2 ring-offset-1 ring-blue-400' : ''}`}>
                    {day.total_items > 0 ? (
                      <span className="text-[10px] font-bold text-white">{day.done_count}/{day.total_items}</span>
                    ) : (
                      <span className="text-[10px] text-gray-300">-</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </button>
      )}

      {/* 计划列表 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-2xl mx-auto space-y-3">
          {/* 加载中：骨架屏（不阻塞整个页面） */}
          {loading && items.length === 0 && (
            <>
              <SkeletonItem theme={theme} />
              <SkeletonItem theme={theme} />
              <SkeletonItem theme={theme} />
            </>
          )}

          {!loading && items.length === 0 && (
            <div className="text-center py-16">
              <div className="text-7xl mb-4">📋</div>
              <p className="text-xl text-gray-400 font-medium">今天还没有计划哦~</p>
              <p className="text-base text-gray-400 mt-1">点下面的按钮来添加吧！</p>
            </div>
          )}

          {items.map(item => (
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

              {/* 表情 + 文字 + 时间（点击编辑） */}
              <button
                onClick={() => !item.done && openEdit(item)}
                disabled={item.done}
                className="flex-1 flex items-start gap-3 text-left min-w-0"
              >
                <span className="text-3xl flex-shrink-0">{item.emoji}</span>
                <div className="flex flex-col min-w-0">
                  <span className={`text-lg font-medium leading-snug ${
                    item.done ? 'line-through text-gray-400' : 'text-gray-700'
                  }`}>
                    {item.text}
                  </span>
                  {(item.startTime || item.endTime) && (
                    <span className="text-xs text-gray-400 mt-0.5">
                      ⏰ {item.startTime}{item.endTime ? ` → ${item.endTime}` : ''}
                    </span>
                  )}
                </div>
              </button>

              {/* 删除按钮 */}
              <button
                onClick={() => deleteItem(item.id)}
                className="w-8 h-8 rounded-full bg-red-50 hover:bg-red-100 flex items-center justify-center text-red-300 hover:text-red-400 transition-all flex-shrink-0 text-xl leading-none"
              >
                ×
              </button>
            </div>
          ))}

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

      {/* 底部按钮区 */}
      <div className={`px-6 py-4 bg-white/80 backdrop-blur-sm border-t-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="max-w-2xl mx-auto flex gap-3">
          {items.length > 0 && (
            <button
              onClick={copyToTomorrow}
              className={`flex items-center justify-center gap-2 px-4 py-4 rounded-2xl border-2 ${theme.navBorder} text-gray-600 font-bold hover:bg-gray-50 active:scale-95 transition-all flex-shrink-0 text-sm`}
            >
              <span>📋</span>
              <span>复制到明天</span>
            </button>
          )}
          <button
            onClick={openAdd}
            className={`flex-1 flex items-center justify-center gap-2 py-4 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white text-xl font-bold shadow-lg hover:shadow-xl active:scale-95 transition-all`}
          >
            <span className="text-2xl font-light">+</span>
            添加计划
          </button>
        </div>
      </div>

      {/* 复制到明天 Toast */}
      {showCopied && (
        <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] bg-black/70 text-white px-6 py-4 rounded-2xl text-xl font-bold pointer-events-none">
          📋 已复制到明天
        </div>
      )}

      {/* 积分奖励 Toast */}
      {pointsToast > 0 && (
        <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[300] bg-black/70 text-white px-8 py-5 rounded-2xl text-center pointer-events-none">
          <div className="text-5xl mb-2">⭐</div>
          <div className="text-2xl font-bold">获得 {pointsToast} 积分！</div>
          <div className="text-sm opacity-80 mt-1">计划完成奖励</div>
        </div>
      )}

      {/* 添加/编辑弹窗 */}
      {showModal && (
        <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center bg-black/30 px-0 sm:px-4">
          <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 shadow-2xl w-full sm:max-w-sm max-h-[90vh] overflow-y-auto">
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
            <div className="flex items-center gap-3 mb-4">
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
                className={`flex-1 px-4 py-3 border-2 ${theme.inputBorder} rounded-2xl text-lg text-gray-800 placeholder-gray-400 focus:outline-none ${theme.inputFocus}`}
                autoFocus
                maxLength={20}
              />
            </div>

            {/* 时间设置 */}
            <div className="mb-5">
              <button
                onClick={() => {
                  setModalHasTime(!modalHasTime);
                  if (modalHasTime) { setModalStartTime(''); setModalDuration(0); }
                }}
                className="flex items-center gap-2 text-sm font-medium text-gray-600 mb-3"
              >
                <span className={`w-5 h-5 rounded-md flex items-center justify-center border-2 transition-all ${
                  modalHasTime
                    ? `bg-gradient-to-br ${theme.btnGrad} border-transparent`
                    : 'border-gray-300'
                }`}>
                  {modalHasTime && <span className="text-white text-xs font-bold">✓</span>}
                </span>
                ⏰ 设置时间
              </button>

              {modalHasTime && (
                <div className="space-y-3 pl-1">
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-500 w-14 flex-shrink-0">开始时间</span>
                    <input
                      type="time"
                      value={modalStartTime}
                      onChange={e => setModalStartTime(e.target.value)}
                      className={`flex-1 px-3 py-2 border-2 ${theme.inputBorder} rounded-xl text-gray-800 focus:outline-none ${theme.inputFocus}`}
                    />
                  </div>

                  <div>
                    <span className="text-sm text-gray-500 block mb-2">持续时长</span>
                    <div className="flex gap-2 flex-wrap">
                      {DURATION_OPTIONS.map(opt => (
                        <button
                          key={opt.value}
                          onClick={() => setModalDuration(modalDuration === opt.value ? 0 : opt.value)}
                          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all active:scale-95 ${
                            modalDuration === opt.value
                              ? `bg-gradient-to-r ${theme.btnGrad} text-white shadow-sm`
                              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {modalStartTime && modalDuration > 0 && (
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-gray-500 w-14 flex-shrink-0">结束时间</span>
                      <span className={`text-lg font-bold ${theme.accent}`}>
                        {computeEndTime(modalStartTime, modalDuration)}
                      </span>
                    </div>
                  )}
                </div>
              )}
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
