'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, subDays, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Legend
} from 'recharts';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

// 运动类型配置
const WORKOUT_TYPES = {
  running: { name: '跑步', icon: '🏃', color: '#ef4444' },
  cycling: { name: '骑行', icon: '🚴', color: '#3b82f6' },
  swimming: { name: '游泳', icon: '🏊', color: '#06b6d4' },
  hiit: { name: 'HIIT', icon: '🔥', color: '#f97316' },
  cardio: { name: '有氧', icon: '❤️', color: '#ec4899' },
  strength: { name: '力量', icon: '💪', color: '#8b5cf6' },
  yoga: { name: '瑜伽', icon: '🧘', color: '#10b981' },
  walking: { name: '步行', icon: '🚶', color: '#84cc16' },
  hiking: { name: '徒步', icon: '⛰️', color: '#a855f7' },
  other: { name: '其他', icon: '🏅', color: '#6b7280' },
};

// 心率区间颜色
const HR_ZONE_COLORS = ['#94a3b8', '#22c55e', '#eab308', '#f97316', '#ef4444'];

interface WorkoutSummary {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  calories: number | null;
  feeling: string | null;
  has_ai_analysis: boolean;
}

interface WorkoutStats {
  total_workouts: number;
  total_duration_minutes: number;
  total_distance_km: number;
  total_calories: number;
  avg_duration_minutes: number;
  avg_distance_km: number;
  workouts_by_type: Record<string, { count: number; duration_minutes: number }>;
  recent_trend: string;
}

interface WorkoutDetail {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  calories: number | null;
  avg_pace_seconds_per_km: number | null;
  training_effect_aerobic: number | null;
  training_effect_anaerobic: number | null;
  hr_zone_1_seconds: number | null;
  hr_zone_2_seconds: number | null;
  hr_zone_3_seconds: number | null;
  hr_zone_4_seconds: number | null;
  hr_zone_5_seconds: number | null;
  ai_analysis: string | null;
  heart_rate_data: string | null;
  source: string;
  external_id: string | null;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '--:--';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatPace(secondsPerKm: number | null): string {
  if (!secondsPerKm) return '--\'--"';
  const mins = Math.floor(secondsPerKm / 60);
  const secs = secondsPerKm % 60;
  return `${mins}'${secs.toString().padStart(2, '0')}"`;
}

function formatDistance(meters: number | null): string {
  if (!meters) return '--';
  return (meters / 1000).toFixed(2);
}

function WorkoutContent() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [selectedWorkout, setSelectedWorkout] = useState<number | null>(null);
  const [days, setDays] = useState(30);
  const [syncDays, setSyncDays] = useState(7);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 获取运动记录列表
  const { data: workouts, isLoading: loadingWorkouts } = useQuery<WorkoutSummary[]>({
    queryKey: ['workouts', days],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取运动记录失败');
      return res.json();
    },
    enabled: !!token,
  });

  // 获取统计数据
  const { data: stats, isLoading: loadingStats } = useQuery<WorkoutStats>({
    queryKey: ['workout-stats', days],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me/stats?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取统计数据失败');
      return res.json();
    },
    enabled: !!token,
  });

  // 获取运动详情
  const { data: workoutDetail, isLoading: loadingDetail } = useQuery<WorkoutDetail>({
    queryKey: ['workout-detail', selectedWorkout],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me/${selectedWorkout}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取运动详情失败');
      return res.json();
    },
    enabled: !!token && !!selectedWorkout,
  });

  // 同步Garmin活动
  const syncMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me/sync-garmin?days=${syncDays}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '同步失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
      queryClient.invalidateQueries({ queryKey: ['workout-stats'] });
      setMessage({ type: 'success', text: `✓ ${data.message}` });
      setTimeout(() => setMessage(null), 3000);
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: `✗ ${error.message}` });
      setTimeout(() => setMessage(null), 5000);
    },
  });

  // AI分析
  const analyzeMutation = useMutation({
    mutationFn: async (workoutId: number) => {
      const res = await fetch(`${API_BASE}/workout/me/${workoutId}/analyze`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '分析失败');
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workout-detail', selectedWorkout] });
      queryClient.invalidateQueries({ queryKey: ['workouts'] });
      setMessage({ type: 'success', text: '✓ AI分析完成' });
      setTimeout(() => setMessage(null), 3000);
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: `✗ ${error.message}` });
      setTimeout(() => setMessage(null), 5000);
    },
  });

  // 刷新心率数据
  const refreshHRMutation = useMutation({
    mutationFn: async (workoutId: number) => {
      const res = await fetch(`${API_BASE}/workout/me/${workoutId}/refresh-hr`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '刷新失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workout-detail', selectedWorkout] });
      setMessage({ type: 'success', text: `✓ ${data.message}` });
      setTimeout(() => setMessage(null), 3000);
    },
    onError: (error: Error) => {
      setMessage({ type: 'error', text: `✗ ${error.message}` });
      setTimeout(() => setMessage(null), 5000);
    },
  });

  // 准备心率区间图表数据
  const hrZoneData = workoutDetail ? [
    { name: '热身区', value: workoutDetail.hr_zone_1_seconds || 0, color: HR_ZONE_COLORS[0] },
    { name: '燃脂区', value: workoutDetail.hr_zone_2_seconds || 0, color: HR_ZONE_COLORS[1] },
    { name: '有氧区', value: workoutDetail.hr_zone_3_seconds || 0, color: HR_ZONE_COLORS[2] },
    { name: '阈值区', value: workoutDetail.hr_zone_4_seconds || 0, color: HR_ZONE_COLORS[3] },
    { name: '极限区', value: workoutDetail.hr_zone_5_seconds || 0, color: HR_ZONE_COLORS[4] },
  ].filter(d => d.value > 0) : [];

  // 准备运动类型分布数据
  const typeDistribution = stats?.workouts_by_type
    ? Object.entries(stats.workouts_by_type).map(([type, data]) => ({
        name: WORKOUT_TYPES[type as keyof typeof WORKOUT_TYPES]?.name || type,
        count: data.count,
        duration: data.duration_minutes,
        color: WORKOUT_TYPES[type as keyof typeof WORKOUT_TYPES]?.color || '#6b7280',
      }))
    : [];

  // 解析心率曲线数据
  const heartRateChartData = workoutDetail?.heart_rate_data
    ? (() => {
        try {
          const data = JSON.parse(workoutDetail.heart_rate_data);
          return data.map((p: { time: number; hr: number }) => ({
            time: Math.floor(p.time / 60),
            hr: p.hr,
          }));
        } catch {
          return [];
        }
      })()
    : [];

  return (
    <main className="min-h-screen p-4 md:p-8 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-20 md:pt-24">
      <div className="max-w-7xl mx-auto">
        {/* 页面标题 */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-2">
              <span>🏋️</span> 运动训练
            </h1>
            <p className="text-gray-400 mt-1">记录和分析您的每次训练</p>
          </div>
          
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 text-sm"
            >
              <option value={7}>最近7天</option>
              <option value={30}>最近30天</option>
              <option value={90}>最近90天</option>
              <option value={365}>最近1年</option>
            </select>
            
            <div className="flex items-center gap-2">
              <select
                value={syncDays}
                onChange={(e) => setSyncDays(Number(e.target.value))}
                className="px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 text-sm"
              >
                <option value={3}>同步3天</option>
                <option value={7}>同步7天</option>
                <option value={14}>同步14天</option>
                <option value={30}>同步30天</option>
              </select>
              <button
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
              >
                {syncMutation.isPending ? '同步中...' : '🔄 同步Garmin'}
              </button>
            </div>
          </div>
        </div>

        {/* 消息提示 */}
        {message && (
          <div className={`mb-4 p-4 rounded-xl ${
            message.type === 'success' 
              ? 'bg-green-900/50 text-green-300 border border-green-700' 
              : 'bg-red-900/50 text-red-300 border border-red-700'
          }`}>
            {message.text}
          </div>
        )}

        {/* 统计卡片 */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-slate-800/60 rounded-xl p-4 border border-slate-700">
              <div className="text-gray-400 text-sm">总训练次数</div>
              <div className="text-2xl font-bold text-white mt-1">{stats.total_workouts}</div>
              <div className="text-xs text-gray-500 mt-1">
                趋势: {stats.recent_trend === 'improving' ? '📈 上升' : stats.recent_trend === 'declining' ? '📉 下降' : '➡️ 稳定'}
              </div>
            </div>
            <div className="bg-slate-800/60 rounded-xl p-4 border border-slate-700">
              <div className="text-gray-400 text-sm">总训练时长</div>
              <div className="text-2xl font-bold text-white mt-1">{Math.floor(stats.total_duration_minutes / 60)}h {stats.total_duration_minutes % 60}m</div>
              <div className="text-xs text-gray-500 mt-1">平均 {stats.avg_duration_minutes.toFixed(0)}分钟/次</div>
            </div>
            <div className="bg-slate-800/60 rounded-xl p-4 border border-slate-700">
              <div className="text-gray-400 text-sm">总距离</div>
              <div className="text-2xl font-bold text-white mt-1">{stats.total_distance_km.toFixed(1)} km</div>
              <div className="text-xs text-gray-500 mt-1">平均 {stats.avg_distance_km.toFixed(1)}km/次</div>
            </div>
            <div className="bg-slate-800/60 rounded-xl p-4 border border-slate-700">
              <div className="text-gray-400 text-sm">总消耗</div>
              <div className="text-2xl font-bold text-orange-400 mt-1">{stats.total_calories.toLocaleString()} kcal</div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 运动记录列表 */}
          <div className="lg:col-span-1 bg-slate-800/60 rounded-xl p-4 border border-slate-700">
            <h2 className="text-lg font-bold text-white mb-4">训练记录</h2>
            
            {loadingWorkouts ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              </div>
            ) : workouts && workouts.length > 0 ? (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {workouts.map((w) => {
                  const typeConfig = WORKOUT_TYPES[w.workout_type as keyof typeof WORKOUT_TYPES] || WORKOUT_TYPES.other;
                  return (
                    <div
                      key={w.id}
                      onClick={() => setSelectedWorkout(w.id)}
                      className={`p-3 rounded-lg cursor-pointer transition-all ${
                        selectedWorkout === w.id
                          ? 'bg-blue-600/30 border border-blue-500'
                          : 'bg-slate-700/50 hover:bg-slate-700 border border-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xl">{typeConfig.icon}</span>
                          <div>
                            <div className="text-white font-medium text-sm">
                              {w.workout_name || typeConfig.name}
                            </div>
                            <div className="text-gray-400 text-xs">
                              {format(parseISO(w.workout_date), 'MM月dd日 EEEE', { locale: zhCN })}
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-white text-sm font-mono">{formatDuration(w.duration_seconds)}</div>
                          {w.distance_meters && (
                            <div className="text-gray-400 text-xs">{formatDistance(w.distance_meters)} km</div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                        {w.avg_heart_rate && <span>❤️ {w.avg_heart_rate}bpm</span>}
                        {w.calories && <span>🔥 {w.calories}kcal</span>}
                        {w.has_ai_analysis && <span className="text-green-400">🤖 已分析</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-400">
                <div className="text-4xl mb-2">🏃</div>
                <p>暂无运动记录</p>
                <p className="text-sm mt-1">点击"同步Garmin"获取数据</p>
              </div>
            )}
          </div>

          {/* 运动详情 */}
          <div className="lg:col-span-2 space-y-6">
            {selectedWorkout && workoutDetail ? (
              <>
                {/* 详情头部 */}
                <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-3xl">
                          {WORKOUT_TYPES[workoutDetail.workout_type as keyof typeof WORKOUT_TYPES]?.icon || '🏅'}
                        </span>
                        <div>
                          <h3 className="text-xl font-bold text-white">
                            {workoutDetail.workout_name || WORKOUT_TYPES[workoutDetail.workout_type as keyof typeof WORKOUT_TYPES]?.name || '运动'}
                          </h3>
                          <p className="text-gray-400 text-sm">
                            {format(parseISO(workoutDetail.workout_date), 'yyyy年MM月dd日 EEEE', { locale: zhCN })}
                          </p>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => analyzeMutation.mutate(workoutDetail.id)}
                      disabled={analyzeMutation.isPending}
                      className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors text-sm"
                    >
                      {analyzeMutation.isPending ? '分析中...' : '🤖 AI分析'}
                    </button>
                  </div>

                  {/* 核心数据 */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-slate-700/50 rounded-lg p-3">
                      <div className="text-gray-400 text-xs">时长</div>
                      <div className="text-xl font-bold text-white font-mono">
                        {formatDuration(workoutDetail.duration_seconds)}
                      </div>
                    </div>
                    {workoutDetail.distance_meters && (
                      <div className="bg-slate-700/50 rounded-lg p-3">
                        <div className="text-gray-400 text-xs">距离</div>
                        <div className="text-xl font-bold text-white">
                          {formatDistance(workoutDetail.distance_meters)} <span className="text-sm">km</span>
                        </div>
                      </div>
                    )}
                    {workoutDetail.avg_pace_seconds_per_km && (
                      <div className="bg-slate-700/50 rounded-lg p-3">
                        <div className="text-gray-400 text-xs">平均配速</div>
                        <div className="text-xl font-bold text-white font-mono">
                          {formatPace(workoutDetail.avg_pace_seconds_per_km)}
                        </div>
                      </div>
                    )}
                    <div className="bg-slate-700/50 rounded-lg p-3">
                      <div className="text-gray-400 text-xs">消耗</div>
                      <div className="text-xl font-bold text-orange-400">
                        {workoutDetail.calories || '--'} <span className="text-sm">kcal</span>
                      </div>
                    </div>
                  </div>

                  {/* 心率数据 */}
                  {(workoutDetail.avg_heart_rate || workoutDetail.max_heart_rate) && (
                    <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="bg-red-900/30 rounded-lg p-3 border border-red-800/50">
                        <div className="text-red-400 text-xs">平均心率</div>
                        <div className="text-xl font-bold text-red-400">
                          {workoutDetail.avg_heart_rate || '--'} <span className="text-sm">bpm</span>
                        </div>
                      </div>
                      <div className="bg-red-900/30 rounded-lg p-3 border border-red-800/50">
                        <div className="text-red-400 text-xs">最高心率</div>
                        <div className="text-xl font-bold text-red-400">
                          {workoutDetail.max_heart_rate || '--'} <span className="text-sm">bpm</span>
                        </div>
                      </div>
                      {workoutDetail.training_effect_aerobic && (
                        <div className="bg-green-900/30 rounded-lg p-3 border border-green-800/50">
                          <div className="text-green-400 text-xs">有氧训练效果</div>
                          <div className="text-xl font-bold text-green-400">
                            {workoutDetail.training_effect_aerobic.toFixed(1)}
                          </div>
                        </div>
                      )}
                      {workoutDetail.training_effect_anaerobic && (
                        <div className="bg-orange-900/30 rounded-lg p-3 border border-orange-800/50">
                          <div className="text-orange-400 text-xs">无氧训练效果</div>
                          <div className="text-xl font-bold text-orange-400">
                            {workoutDetail.training_effect_anaerobic.toFixed(1)}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* 心率曲线图 */}
                <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-white">❤️ 心率曲线</h3>
                    {workoutDetail && workoutDetail.source === 'garmin' && (
                      <button
                        onClick={() => refreshHRMutation.mutate(workoutDetail.id)}
                        disabled={refreshHRMutation.isPending}
                        className="px-3 py-1 bg-blue-600/80 text-white text-xs rounded hover:bg-blue-600 disabled:opacity-50 transition-colors"
                      >
                        {refreshHRMutation.isPending ? '加载中...' : '🔄 刷新数据'}
                      </button>
                    )}
                  </div>
                  {heartRateChartData.length > 0 ? (
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={heartRateChartData}>
                          <defs>
                            <linearGradient id="hrGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis dataKey="time" stroke="#9ca3af" tickFormatter={(v) => `${v}分`} />
                          <YAxis stroke="#9ca3af" domain={['dataMin - 10', 'dataMax + 10']} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                            labelFormatter={(v) => `${v}分钟`}
                            formatter={(v: number) => [`${v} bpm`, '心率']}
                          />
                          <Area type="monotone" dataKey="hr" stroke="#ef4444" fill="url(#hrGradient)" strokeWidth={2} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="h-64 flex flex-col items-center justify-center text-gray-400">
                      <div className="text-4xl mb-3">📉</div>
                      <p className="text-lg">暂无心率曲线数据</p>
                      {workoutDetail?.source === 'garmin' && (
                        <p className="text-sm mt-1">点击"刷新数据"尝试获取</p>
                      )}
                    </div>
                  )}
                </div>

                {/* 心率区间分布 */}
                {hrZoneData.length > 0 && (
                  <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                    <h3 className="text-lg font-bold text-white mb-4">📊 心率区间分布</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={hrZoneData}
                              dataKey="value"
                              nameKey="name"
                              cx="50%"
                              cy="50%"
                              innerRadius={40}
                              outerRadius={70}
                              paddingAngle={2}
                            >
                              {hrZoneData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip
                              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                              formatter={(v: number) => [formatDuration(v), '时长']}
                            />
                            <Legend />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="space-y-2">
                        {hrZoneData.map((zone, idx) => {
                          const total = hrZoneData.reduce((sum, z) => sum + z.value, 0);
                          const percent = total > 0 ? ((zone.value / total) * 100).toFixed(1) : 0;
                          return (
                            <div key={idx} className="flex items-center gap-2">
                              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: zone.color }}></div>
                              <span className="text-gray-400 text-sm flex-1">{zone.name}</span>
                              <span className="text-white text-sm font-mono">{formatDuration(zone.value)}</span>
                              <span className="text-gray-500 text-xs">({percent}%)</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}

                {/* AI分析结果 */}
                {workoutDetail.ai_analysis && (
                  <div className="bg-gradient-to-br from-purple-900/40 to-slate-800/60 rounded-xl p-6 border border-purple-700/50">
                    <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                      🤖 AI训练分析
                    </h3>
                    <div className="text-gray-300 whitespace-pre-wrap leading-relaxed">
                      {(() => {
                        try {
                          const analysis = JSON.parse(workoutDetail.ai_analysis);
                          return (
                            <div className="space-y-4">
                              {analysis.ai_enhanced_insights && (
                                <div className="text-gray-300 whitespace-pre-wrap">
                                  {analysis.ai_enhanced_insights}
                                </div>
                              )}
                              {analysis.key_insights && (
                                <div>
                                  <div className="text-sm font-medium text-purple-400 mb-2">💡 关键洞察</div>
                                  <ul className="list-disc list-inside space-y-1 text-sm">
                                    {analysis.key_insights.map((insight: string, idx: number) => (
                                      <li key={idx}>{insight}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {analysis.improvement_tips && (
                                <div>
                                  <div className="text-sm font-medium text-green-400 mb-2">📈 改进建议</div>
                                  <ul className="list-disc list-inside space-y-1 text-sm">
                                    {analysis.improvement_tips.map((tip: string, idx: number) => (
                                      <li key={idx}>{tip}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {analysis.recovery_recommendation && (
                                <div className="bg-slate-700/50 rounded-lg p-3">
                                  <div className="text-sm font-medium text-blue-400 mb-1">🛌 恢复建议</div>
                                  <div className="text-sm">{analysis.recovery_recommendation}</div>
                                </div>
                              )}
                            </div>
                          );
                        } catch {
                          return workoutDetail.ai_analysis;
                        }
                      })()}
                    </div>
                  </div>
                )}
              </>
            ) : (
              /* 运动类型分布 */
              typeDistribution.length > 0 && (
                <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                  <h3 className="text-lg font-bold text-white mb-4">📊 运动类型分布</h3>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={typeDistribution} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#9ca3af" />
                        <YAxis type="category" dataKey="name" stroke="#9ca3af" width={60} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                          formatter={(v: number, name: string) => [
                            name === 'count' ? `${v}次` : `${v}分钟`,
                            name === 'count' ? '次数' : '时长'
                          ]}
                        />
                        <Bar dataKey="count" fill="#3b82f6" name="次数" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )
            )}

            {/* 未选择运动时的提示 */}
            {!selectedWorkout && (!typeDistribution || typeDistribution.length === 0) && (
              <div className="bg-slate-800/60 rounded-xl p-12 border border-slate-700 text-center">
                <div className="text-6xl mb-4">👈</div>
                <p className="text-gray-400 text-lg">选择一条训练记录查看详情</p>
                <p className="text-gray-500 text-sm mt-2">或点击"同步Garmin"获取运动数据</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

export default function WorkoutPage() {
  return (
    <ProtectedRoute>
      <WorkoutContent />
    </ProtectedRoute>
  );
}

