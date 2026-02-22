'use client';

import { useState, useEffect, useCallback } from 'react';
import ProtectedRoute from '@/components/ProtectedRoute';
import { activityStatusApi, ActivityStatusData, ActivityTimelineItem, ActivityStatsData } from '@/services/api';

const CATEGORIES = [
  { value: 'studying', label: '学习', emoji: '📚', color: 'bg-blue-500' },
  { value: 'working', label: '工作', emoji: '💼', color: 'bg-purple-500' },
  { value: 'exercising', label: '运动', emoji: '🏃', color: 'bg-green-500' },
  { value: 'resting', label: '休息', emoji: '😴', color: 'bg-yellow-500' },
  { value: 'entertainment', label: '娱乐', emoji: '🎮', color: 'bg-pink-500' },
  { value: 'other', label: '其他', emoji: '📋', color: 'bg-gray-500' },
];

const DEFAULT_DURATIONS: Record<string, number> = {
  studying: 120,
  working: 120,
  exercising: 60,
  resting: 30,
  entertainment: 60,
  other: 60,
};

function getCategoryInfo(category: string) {
  return CATEGORIES.find(c => c.value === category) || CATEGORIES[5];
}

function formatDuration(minutes: number | null | undefined): string {
  if (!minutes) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) return `${h}小时${m}分钟`;
  if (h > 0) return `${h}小时`;
  return `${m}分钟`;
}

function formatTime(timeStr: string): string {
  return new Date(timeStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function getElapsedMinutes(startTime: string): number {
  const start = new Date(startTime).getTime();
  const now = Date.now();
  return Math.max(0, Math.floor((now - start) / 60000));
}

export default function ActivityStatusPage() {
  const [currentStatus, setCurrentStatus] = useState<ActivityStatusData | null>(null);
  const [timeline, setTimeline] = useState<ActivityTimelineItem[]>([]);
  const [stats, setStats] = useState<ActivityStatsData | null>(null);
  const [tab, setTab] = useState<'current' | 'stats'>('current');
  const [loading, setLoading] = useState(true);
  const [customName, setCustomName] = useState('');
  const [customCategory, setCustomCategory] = useState('other');
  const [customDuration, setCustomDuration] = useState(60);
  const [showCustom, setShowCustom] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const loadData = useCallback(async () => {
    try {
      const [statusRes, timelineRes] = await Promise.all([
        activityStatusApi.getCurrentStatus(),
        activityStatusApi.getTodayTimeline(),
      ]);
      setCurrentStatus(statusRes.data);
      setTimeline(timelineRes.data);
      if (statusRes.data) {
        setElapsed(getElapsedMinutes(statusRes.data.start_time));
      }
    } catch (err) {
      console.error('加载数据失败', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const res = await activityStatusApi.getStats(7);
      setStats(res.data);
    } catch (err) {
      console.error('加载统计失败', err);
    }
  }, []);

  useEffect(() => {
    loadData();
    // 请求通知权限（用于活动超时提醒）
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, [loadData]);

  useEffect(() => {
    if (tab === 'stats') loadStats();
  }, [tab, loadStats]);

  // 倒计时更新 + 超时提醒
  const [reminded, setReminded] = useState(false);
  useEffect(() => {
    if (!currentStatus) { setReminded(false); return; }
    const timer = setInterval(() => {
      const mins = getElapsedMinutes(currentStatus.start_time);
      setElapsed(mins);
      // 到达预估时长时发送通知提醒
      if (!reminded && currentStatus.estimated_duration_minutes && mins >= currentStatus.estimated_duration_minutes) {
        setReminded(true);
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification(`${currentStatus.status_text} - 休息提醒`, {
            body: `已经${formatDuration(mins)}了，该休息一下，看看远方，活动活动身体吧！`,
          });
        }
      }
    }, 60000);
    return () => clearInterval(timer);
  }, [currentStatus, reminded]);

  const startActivity = async (category: string, name?: string) => {
    try {
      const cat = getCategoryInfo(category);
      await activityStatusApi.createRecord({
        status_text: name || cat.label,
        category,
        estimated_duration_minutes: DEFAULT_DURATIONS[category] || 60,
      });
      await loadData();
    } catch (err) {
      console.error('开始活动失败', err);
    }
  };

  const startCustomActivity = async () => {
    if (!customName.trim()) return;
    try {
      await activityStatusApi.createRecord({
        status_text: customName.trim(),
        category: customCategory,
        estimated_duration_minutes: customDuration,
      });
      setCustomName('');
      setShowCustom(false);
      await loadData();
    } catch (err) {
      console.error('开始活动失败', err);
    }
  };

  const endActivity = async () => {
    if (!currentStatus) return;
    try {
      await activityStatusApi.endRecord(currentStatus.id);
      await loadData();
    } catch (err) {
      console.error('结束活动失败', err);
    }
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4 pb-24">
        <h1 className="text-xl font-bold mb-4">活动状态</h1>

        {/* Tab 切换 */}
        <div className="flex gap-2 mb-4">
          {(['current', 'stats'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-full text-sm ${tab === t ? 'bg-cyan-600 text-white' : 'bg-white/10 text-white/60'}`}
            >
              {t === 'current' ? '当前状态' : '活动统计'}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center text-white/50 py-8">加载中...</div>
        ) : tab === 'current' ? (
          <>
            {/* 当前状态卡片 */}
            {currentStatus ? (
              <div className="bg-gradient-to-r from-cyan-600/30 to-blue-600/30 border border-cyan-500/30 rounded-xl p-5 mb-6">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl">{getCategoryInfo(currentStatus.category).emoji}</span>
                    <div>
                      <div className="text-lg font-bold">{currentStatus.status_text}</div>
                      <div className="text-white/50 text-sm">{getCategoryInfo(currentStatus.category).label}</div>
                    </div>
                  </div>
                  <button
                    onClick={endActivity}
                    className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm hover:bg-red-500/30"
                  >
                    结束
                  </button>
                </div>
                <div className="flex items-center gap-4 text-sm text-white/60">
                  <span>开始: {formatTime(currentStatus.start_time)}</span>
                  <span>已进行: {formatDuration(elapsed)}</span>
                  {currentStatus.estimated_duration_minutes && (
                    <span>
                      预计: {formatDuration(currentStatus.estimated_duration_minutes)}
                      {elapsed > currentStatus.estimated_duration_minutes && (
                        <span className="text-yellow-400 ml-1">(已超时)</span>
                      )}
                    </span>
                  )}
                </div>
                {/* 进度条 */}
                {currentStatus.estimated_duration_minutes && (
                  <div className="mt-3 bg-white/10 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        elapsed > currentStatus.estimated_duration_minutes ? 'bg-yellow-400' : 'bg-cyan-400'
                      }`}
                      style={{ width: `${Math.min(100, (elapsed / currentStatus.estimated_duration_minutes) * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-6 text-center text-white/40">
                当前没有进行中的活动
              </div>
            )}

            {/* 快速开始 */}
            <div className="mb-6">
              <h2 className="text-sm text-white/50 mb-3">快速开始</h2>
              <div className="grid grid-cols-3 gap-3">
                {CATEGORIES.map(cat => (
                  <button
                    key={cat.value}
                    onClick={() => startActivity(cat.value)}
                    className="bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl p-4 text-center transition-colors"
                  >
                    <div className="text-2xl mb-1">{cat.emoji}</div>
                    <div className="text-sm">{cat.label}</div>
                    <div className="text-xs text-white/40 mt-1">{DEFAULT_DURATIONS[cat.value]}分钟</div>
                  </button>
                ))}
              </div>
            </div>

            {/* 自定义活动 */}
            {!showCustom ? (
              <button
                onClick={() => setShowCustom(true)}
                className="w-full bg-white/5 border border-dashed border-white/20 rounded-xl p-3 text-white/40 text-sm mb-6"
              >
                + 自定义活动
              </button>
            ) : (
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 mb-6">
                <input
                  type="text"
                  value={customName}
                  onChange={e => setCustomName(e.target.value)}
                  placeholder="活动名称"
                  className="w-full bg-white/10 rounded-lg px-3 py-2 text-sm mb-3 outline-none"
                />
                <div className="flex gap-2 mb-3">
                  {CATEGORIES.map(cat => (
                    <button
                      key={cat.value}
                      onClick={() => {
                        setCustomCategory(cat.value);
                        setCustomDuration(DEFAULT_DURATIONS[cat.value]);
                      }}
                      className={`px-3 py-1 rounded-full text-xs ${
                        customCategory === cat.value ? 'bg-cyan-600' : 'bg-white/10'
                      }`}
                    >
                      {cat.emoji} {cat.label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm text-white/50">预计时长:</span>
                  <input
                    type="number"
                    value={customDuration}
                    onChange={e => setCustomDuration(Number(e.target.value))}
                    className="w-20 bg-white/10 rounded-lg px-3 py-1 text-sm outline-none"
                    min={1}
                    max={720}
                  />
                  <span className="text-sm text-white/50">分钟</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={startCustomActivity}
                    className="flex-1 bg-cyan-600 rounded-lg py-2 text-sm"
                  >
                    开始
                  </button>
                  <button
                    onClick={() => setShowCustom(false)}
                    className="px-4 bg-white/10 rounded-lg py-2 text-sm"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}

            {/* 今日时间线 */}
            {timeline.length > 0 && (
              <div>
                <h2 className="text-sm text-white/50 mb-3">今日时间线</h2>
                <div className="space-y-2">
                  {timeline.map(item => {
                    const cat = getCategoryInfo(item.category);
                    return (
                      <div
                        key={item.id}
                        className={`flex items-center gap-3 bg-white/5 rounded-xl p-3 ${item.is_active ? 'border border-cyan-500/30' : ''}`}
                      >
                        <div className={`w-8 h-8 rounded-full ${cat.color} flex items-center justify-center text-sm`}>
                          {cat.emoji}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{item.status_text}</div>
                          <div className="text-xs text-white/40">
                            {formatTime(item.start_time)}
                            {item.end_time && ` - ${formatTime(item.end_time)}`}
                            {item.is_active && ' - 进行中'}
                          </div>
                        </div>
                        <div className="text-sm text-white/50">
                          {item.duration_minutes != null ? formatDuration(item.duration_minutes) : ''}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        ) : (
          /* 统计视图 */
          <div>
            {stats ? (
              <>
                <div className="grid grid-cols-2 gap-3 mb-6">
                  <div className="bg-white/5 rounded-xl p-4">
                    <div className="text-white/40 text-xs mb-1">总记录数</div>
                    <div className="text-2xl font-bold">{stats.total_records}</div>
                  </div>
                  <div className="bg-white/5 rounded-xl p-4">
                    <div className="text-white/40 text-xs mb-1">总活动时间</div>
                    <div className="text-2xl font-bold">{formatDuration(stats.total_active_minutes)}</div>
                  </div>
                </div>

                {stats.category_distribution.length > 0 && (
                  <div className="bg-white/5 rounded-xl p-4">
                    <h3 className="text-sm text-white/50 mb-3">时间分布 (近7天)</h3>
                    <div className="space-y-3">
                      {stats.category_distribution.map(item => {
                        const cat = getCategoryInfo(item.category);
                        return (
                          <div key={item.category}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm">{cat.emoji} {cat.label}</span>
                              <span className="text-sm text-white/50">
                                {formatDuration(item.total_minutes)} ({item.percentage}%)
                              </span>
                            </div>
                            <div className="bg-white/10 rounded-full h-2 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${cat.color}`}
                                style={{ width: `${item.percentage}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-white/40 py-8">加载统计中...</div>
            )}
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}
