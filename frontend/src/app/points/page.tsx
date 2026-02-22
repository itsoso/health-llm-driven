'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import ProtectedRoute from '@/components/ProtectedRoute';
import { dailyPointsApi, PointItemData } from '@/services/api';

const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  exercise: { label: '运动', color: '#f97316', icon: '🏃' },
  sleep: { label: '睡眠', color: '#8b5cf6', icon: '😴' },
  water: { label: '饮水', color: '#3b82f6', icon: '💧' },
  checkin: { label: '打卡', color: '#22c55e', icon: '✅' },
};

function PointCircle({ points, maxLabel }: { points: number; maxLabel?: string }) {
  const size = 140;
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  // 假设每日满分约100分
  const pct = Math.min(points / 100, 1);
  const offset = c - pct * c;
  const color = points >= 80 ? '#22c55e' : points >= 50 ? '#eab308' : points >= 20 ? '#f97316' : '#94a3b8';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={8} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={8}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-bold text-white">{points}</span>
        <span className="text-xs text-gray-400 mt-1">{maxLabel || '积分'}</span>
      </div>
    </div>
  );
}

function PointItemCard({ item }: { item: PointItemData }) {
  const cfg = CATEGORY_CONFIG[item.category] || { label: item.category, color: '#64748b', icon: '📋' };
  const earned = item.points > 0;

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
      earned ? 'bg-white/5 border border-white/10' : 'bg-white/[0.02] border border-white/5 opacity-60'
    }`}>
      <span className="text-2xl flex-shrink-0">{cfg.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">{item.name}</span>
          <span className={`text-sm font-bold ${earned ? 'text-green-400' : 'text-gray-500'}`}>
            +{item.points}/{item.max_points}
          </span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5 truncate">{item.detail}</p>
      </div>
    </div>
  );
}

function PointsContent() {
  const [historyDays, setHistoryDays] = useState(7);

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['points-summary'],
    queryFn: async () => {
      const res = await dailyPointsApi.getSummary();
      return res.data;
    },
  });

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['points-history', historyDays],
    queryFn: async () => {
      const res = await dailyPointsApi.getHistory(historyDays);
      return res.data;
    },
  });

  const isLoading = summaryLoading || historyLoading;

  if (isLoading) {
    return (
      <main className="min-h-screen bg-[#0f0b18] pt-4 pb-8 px-4">
        <div className="max-w-2xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500 mx-auto mb-4" />
          <p className="text-gray-400 text-lg">加载积分数据...</p>
        </div>
      </main>
    );
  }

  const todayItems = summary?.today_detail?.items || [];

  // 按类别分组
  const exerciseItems = todayItems.filter(i => i.category === 'exercise');
  const sleepItems = todayItems.filter(i => i.category === 'sleep');
  const waterItems = todayItems.filter(i => i.category === 'water');
  const checkinItems = todayItems.filter(i => i.category === 'checkin');

  // 各类别积分
  const categoryPoints = [
    { name: '运动', points: exerciseItems.reduce((s, i) => s + i.points, 0), max: exerciseItems.reduce((s, i) => s + i.max_points, 0), color: '#f97316' },
    { name: '睡眠', points: sleepItems.reduce((s, i) => s + i.points, 0), max: sleepItems.reduce((s, i) => s + i.max_points, 0), color: '#8b5cf6' },
    { name: '饮水', points: waterItems.reduce((s, i) => s + i.points, 0), max: waterItems.reduce((s, i) => s + i.max_points, 0), color: '#3b82f6' },
    { name: '打卡', points: checkinItems.reduce((s, i) => s + i.points, 0), max: checkinItems.reduce((s, i) => s + i.max_points, 0), color: '#22c55e' },
  ];

  // 历史图表数据
  const chartData = (history || []).slice().reverse().map(h => ({
    date: h.date.slice(5), // MM-DD
    points: h.total_points,
  }));

  return (
    <main className="min-h-screen bg-[#0f0b18] pt-4 pb-8 px-4">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* 头部 */}
        <h1 className="text-2xl font-bold text-white">每日健康积分</h1>

        {/* 总览卡片 */}
        <div className="bg-gradient-to-br from-purple-900/40 to-indigo-900/40 rounded-2xl p-6 border border-purple-500/20">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-400">本周积分</p>
                  <p className="text-2xl font-bold text-white">{summary?.week_points || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">本月积分</p>
                  <p className="text-2xl font-bold text-white">{summary?.month_points || 0}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-xs text-gray-400">连续获得积分</p>
                  <p className="text-lg font-bold text-amber-400">{summary?.streak_days || 0} 天</p>
                </div>
              </div>
            </div>
            <PointCircle points={summary?.today_points || 0} maxLabel="今日积分" />
          </div>
        </div>

        {/* 类别积分柱状 */}
        <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
          <h2 className="text-sm font-medium text-gray-300 mb-3">今日各类别积分</h2>
          <div className="space-y-3">
            {categoryPoints.map(cp => (
              <div key={cp.name} className="flex items-center gap-3">
                <span className="text-sm text-gray-400 w-10">{cp.name}</span>
                <div className="flex-1 bg-white/5 rounded-full h-6 overflow-hidden relative">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: cp.max > 0 ? `${Math.min((cp.points / cp.max) * 100, 100)}%` : '0%',
                      backgroundColor: cp.color,
                      minWidth: cp.points > 0 ? '20px' : '0',
                    }}
                  />
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white">
                    {cp.points}/{cp.max}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 今日积分详情 */}
        <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
          <h2 className="text-sm font-medium text-gray-300 mb-3">今日积分明细</h2>
          <div className="space-y-2">
            {todayItems.length > 0 ? (
              todayItems.map((item, idx) => (
                <PointItemCard key={`${item.category}-${item.name}-${idx}`} item={item} />
              ))
            ) : (
              <p className="text-center text-gray-500 py-4">暂无数据</p>
            )}
          </div>
        </div>

        {/* 历史趋势 */}
        <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-gray-300">积分趋势</h2>
            <div className="flex gap-2">
              {[7, 14, 30].map(d => (
                <button
                  key={d}
                  onClick={() => setHistoryDays(d)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                    historyDays === d
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/5 text-gray-400 hover:bg-white/10'
                  }`}
                >
                  {d}天
                </button>
              ))}
            </div>
          </div>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e1b2e', border: '1px solid rgba(139,92,246,0.3)', borderRadius: '8px', color: '#fff' }}
                  labelStyle={{ color: '#9ca3af' }}
                  formatter={(value: number) => [`${value} 分`, '积分']}
                />
                <Bar dataKey="points" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={entry.points >= 80 ? '#22c55e' : entry.points >= 50 ? '#eab308' : entry.points >= 20 ? '#f97316' : '#64748b'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-center text-gray-500 py-8">暂无历史数据</p>
          )}
        </div>
      </div>
    </main>
  );
}

export default function PointsPage() {
  return (
    <ProtectedRoute>
      <PointsContent />
    </ProtectedRoute>
  );
}
