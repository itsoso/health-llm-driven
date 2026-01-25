'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, subDays, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import dynamic from 'next/dynamic';
import { workoutGuidanceApi } from '@/services/api';

// 动态导入地图组件（客户端组件）
const WorkoutMap = dynamic(() => import('@/components/WorkoutMap'), {
  ssr: false,
  loading: () => (
    <div className="h-[400px] w-full flex items-center justify-center bg-slate-700/50 rounded-lg">
      <div className="text-gray-400">加载地图中...</div>
    </div>
  ),
});
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
  yoga: { name: '瑜伽/冥想', icon: '🧘', color: '#10b981' },
  walking: { name: '步行', icon: '🚶', color: '#84cc16' },
  hiking: { name: '登山/徒步', icon: '⛰️', color: '#a855f7' },
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

interface LapData {
  lap: number;
  distance?: number;
  duration?: number;
  avg_hr?: number;
  max_hr?: number;
  avg_pace?: number;
  avg_speed?: number;
  elevation_gain?: number;
  elevation_loss?: number;
  calories?: number;
  avg_cadence?: number;
  avg_power?: number;
}

interface WorkoutDetail {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  moving_duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  min_heart_rate: number | null;
  calories: number | null;
  active_calories: number | null;
  avg_pace_seconds_per_km: number | null;
  best_pace_seconds_per_km: number | null;
  avg_speed_kmh: number | null;
  max_speed_kmh: number | null;
  training_effect_aerobic: number | null;
  training_effect_anaerobic: number | null;
  training_load: number | null;
  vo2max: number | null;
  hr_zone_1_seconds: number | null;
  hr_zone_2_seconds: number | null;
  hr_zone_3_seconds: number | null;
  hr_zone_4_seconds: number | null;
  hr_zone_5_seconds: number | null;
  elevation_gain_meters: number | null;
  elevation_loss_meters: number | null;
  min_elevation_meters: number | null;
  max_elevation_meters: number | null;
  steps: number | null;
  avg_cadence: number | null;
  max_cadence: number | null;
  ai_analysis: string | null;
  heart_rate_data: string | null;
  pace_data: string | null;
  elevation_data: string | null;
  lap_data: string | null; // 计圈数据 JSON
  source: string;
  external_id: string | null;
  start_time: string | null;
  end_time: string | null;
  route_data?: string | null; // GPS 路线数据 JSON
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
  const [days, setDays] = useState(7);
  const [syncDays, setSyncDays] = useState(7);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showPostAnalysis, setShowPostAnalysis] = useState(false);
  const [postAnalysis, setPostAnalysis] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'stats' | 'laps' | 'intervals'>('stats');

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
  const { data: workoutDetail, isLoading: loadingDetail, error: detailError } = useQuery<WorkoutDetail>({
    queryKey: ['workout-detail', selectedWorkout],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me/${selectedWorkout}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: '获取运动详情失败' }));
        if (res.status === 404) {
          throw new Error(errorData.detail || '运动记录不存在');
        }
        throw new Error(errorData.detail || `获取运动详情失败 (${res.status})`);
      }
      return res.json();
    },
    enabled: !!token && !!selectedWorkout,
    retry: false, // 404错误不重试
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

  // 运动后科学分析
  const postAnalysisMutation = useMutation({
    mutationFn: ({ workoutId, forceRegenerate = false, cacheOnly = false }: { workoutId: number; forceRegenerate?: boolean; cacheOnly?: boolean }) =>
      workoutGuidanceApi.getPostWorkoutAnalysis(workoutId, forceRegenerate, false, cacheOnly),
    onSuccess: (response, variables) => {
      console.log('📊 科学分析响应:', response);
      console.log('📊 response.data:', response.data);

      // 如果是 cache_only 模式且没有缓存，不显示任何内容
      if (variables.cacheOnly && response.data.success === false) {
        console.log('📊 无缓存的科学分析，等待用户手动请求');
        return;
      }

      setPostAnalysis(response.data);
      setShowPostAnalysis(true);

      // cache_only 模式下静默加载，不显示消息
      if (!variables.cacheOnly) {
        const fromCache = response.data.from_cache;
        setMessage({
          type: 'success',
          text: fromCache ? '✓ 已加载分析结果' : '✓ 科学分析完成'
        });
        setTimeout(() => setMessage(null), 3000);
      }
    },
    onError: (error: any, variables) => {
      console.error('❌ 科学分析失败:', error);
      // cache_only 模式下静默失败，不显示错误消息
      if (!variables.cacheOnly) {
        setMessage({ type: 'error', text: `✗ 分析失败: ${error.message}` });
        setTimeout(() => setMessage(null), 5000);
      }
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

  // 当选择新的运动记录时，重置科学分析状态
  useEffect(() => {
    setShowPostAnalysis(false);
    setPostAnalysis(null);
  }, [selectedWorkout]);

  // 当运动详情加载完成后，自动加载科学分析（仅从缓存加载）
  useEffect(() => {
    if (workoutDetail && workoutDetail.id && !loadingDetail) {
      // 使用 cacheOnly: true 仅加载缓存的结果，不会触发新的分析生成
      postAnalysisMutation.mutate({ workoutId: workoutDetail.id, forceRegenerate: false, cacheOnly: true });
    }
  }, [workoutDetail?.id, loadingDetail]);

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

  // 解析配速/速度数据
  const paceChartData = workoutDetail?.pace_data
    ? (() => {
        try {
          const data = JSON.parse(workoutDetail.pace_data);
          return data.map((p: { time: number; pace: number }) => ({
            time: Math.floor(p.time / 60),
            pace: p.pace,
            speed: p.pace > 0 ? (3600 / p.pace) : 0, // 转换为 km/h
          }));
        } catch {
          return [];
        }
      })()
    : [];

  // 解析 GPS 路线数据（先解析，供海拔数据使用）
  const routeData = workoutDetail?.route_data
    ? (() => {
        try {
          const data = JSON.parse(workoutDetail.route_data);
          // 支持多种格式：{lat, lng} 或 {latitude, longitude} 或 [lat, lng]
          return data.map((p: any) => {
            if (Array.isArray(p)) {
              return { lat: p[0], lng: p[1] };
            }
            return {
              lat: p.lat || p.latitude,
              lng: p.lng || p.longitude,
              elevation: p.elevation || p.elev,
              time: p.time,
            };
          }).filter((p: any) => p.lat && p.lng);
        } catch {
          return [];
        }
      })()
    : [];

  // 解析海拔数据（优先从GPS数据中提取，如果没有则使用elevation_data）
  const elevationChartData = (() => {
    // 首先尝试从GPS路线数据中提取海拔和时间
    if (routeData.length > 0) {
      const gpsElevationData = routeData
        .filter((p: any) => p.elevation !== undefined && p.elevation !== null && p.time !== undefined)
        .map((p: any, idx: number) => ({
          time: Math.floor((p.time || idx * 10) / 60), // 转换为分钟
          elevation: p.elevation,
        }));
      if (gpsElevationData.length > 0) {
        return gpsElevationData;
      }
    }
    
    // 如果没有GPS海拔数据，尝试从elevation_data中提取
    if (workoutDetail?.elevation_data) {
      try {
        const data = JSON.parse(workoutDetail.elevation_data);
        // 如果有time字段，使用time；否则使用distance估算时间
        if (data[0]?.time !== undefined) {
          return data.map((p: { time: number; elevation: number }) => ({
            time: Math.floor(p.time / 60),
            elevation: p.elevation,
          }));
        } else {
          // 使用距离估算时间（假设平均速度）
          const avgSpeed = workoutDetail.avg_speed_kmh || 5; // 默认5km/h
          return data.map((p: { distance: number; elevation: number }, idx: number) => ({
            time: Math.floor((p.distance / 1000 / avgSpeed) * 60),
            elevation: p.elevation,
          }));
        }
      } catch {
        return [];
      }
    }
    return [];
  })();

  return (
    <main className="min-h-screen p-4 md:p-8 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-4 md:pt-4">
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
              <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto">
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
                        {w.has_ai_analysis && <span className="text-green-400">✨ 已分析</span>}
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
            {selectedWorkout && loadingDetail ? (
              <div className="bg-slate-800/60 rounded-xl p-12 border border-slate-700 text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
                <p className="text-gray-400">加载运动详情中...</p>
              </div>
            ) : selectedWorkout && detailError ? (
              <div className="bg-red-900/30 rounded-xl p-8 border border-red-700/50 text-center">
                <div className="text-4xl mb-4">❌</div>
                <h3 className="text-xl font-bold text-red-400 mb-2">加载失败</h3>
                <p className="text-red-300 mb-4">{detailError.message || '获取运动详情失败'}</p>
                <button
                  onClick={() => {
                    queryClient.invalidateQueries({ queryKey: ['workout-detail', selectedWorkout] });
                  }}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                >
                  重试
                </button>
              </div>
            ) : selectedWorkout && workoutDetail ? (
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
                    <div className="flex gap-2">
                      <button
                        onClick={() => analyzeMutation.mutate(workoutDetail.id)}
                        disabled={analyzeMutation.isPending}
                        className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors text-sm"
                      >
                        {analyzeMutation.isPending ? '分析中...' : '✨ AI分析'}
                      </button>
                      <button
                        onClick={() => postAnalysisMutation.mutate({ workoutId: workoutDetail.id, forceRegenerate: false })}
                        disabled={postAnalysisMutation.isPending}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm"
                      >
                        {postAnalysisMutation.isPending ? '分析中...' : '🔬 科学分析'}
                      </button>
                      {postAnalysis && postAnalysis.from_cache && (
                        <button
                          onClick={() => postAnalysisMutation.mutate({ workoutId: workoutDetail.id, forceRegenerate: true })}
                          disabled={postAnalysisMutation.isPending}
                          className="px-3 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors text-xs"
                          title="重新生成分析"
                        >
                          {postAnalysisMutation.isPending ? '生成中...' : '🔄 重新生成'}
                        </button>
                      )}
                    </div>
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

                {/* 地图显示 */}
                {routeData.length > 0 && (
                  <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                    <h3 className="text-lg font-bold text-white mb-4">🗺️ 运动路线</h3>
                    <div className="h-[400px] w-full">
                      <WorkoutMap routeData={routeData} />
                    </div>
                  </div>
                )}

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

                {/* 海拔高度图表 */}
                {elevationChartData.length > 0 && (
                  <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                    <h3 className="text-lg font-bold text-white mb-4">⛰️ 海拔高度</h3>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={elevationChartData}>
                          <defs>
                            <linearGradient id="elevationGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis 
                            dataKey="time" 
                            stroke="#9ca3af" 
                            tickFormatter={(v) => {
                              const hours = Math.floor(v / 60);
                              const minutes = v % 60;
                              return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                            }}
                            label={{ value: '时间', position: 'insideBottom', offset: -5, style: { fill: '#9ca3af' } }}
                          />
                          <YAxis 
                            stroke="#9ca3af" 
                            label={{ value: '海拔(m)', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af' } }}
                            domain={['dataMin - 10', 'dataMax + 10']}
                          />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                            labelFormatter={(v) => {
                              const hours = Math.floor(v / 60);
                              const minutes = v % 60;
                              return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                            }}
                            formatter={(v: number) => [`${v.toFixed(0)}米`, '海拔']}
                          />
                          <Area type="monotone" dataKey="elevation" stroke="#10b981" fill="url(#elevationGradient)" strokeWidth={2} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                    {workoutDetail.elevation_gain_meters && workoutDetail.elevation_loss_meters && (
                      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-green-900/30 rounded-lg p-3 border border-green-800/50">
                          <div className="text-green-400 text-xs">累计爬升</div>
                          <div className="text-lg font-bold text-green-400">
                            {workoutDetail.elevation_gain_meters.toFixed(0)} <span className="text-sm">m</span>
                          </div>
                        </div>
                        <div className="bg-blue-900/30 rounded-lg p-3 border border-blue-800/50">
                          <div className="text-blue-400 text-xs">累计下降</div>
                          <div className="text-lg font-bold text-blue-400">
                            {workoutDetail.elevation_loss_meters.toFixed(0)} <span className="text-sm">m</span>
                          </div>
                        </div>
                        {workoutDetail.min_elevation_meters && (
                          <div className="bg-slate-700/50 rounded-lg p-3">
                            <div className="text-gray-400 text-xs">最低海拔</div>
                            <div className="text-lg font-bold text-white">
                              {workoutDetail.min_elevation_meters.toFixed(0)} <span className="text-sm">m</span>
                            </div>
                          </div>
                        )}
                        {workoutDetail.max_elevation_meters && (
                          <div className="bg-slate-700/50 rounded-lg p-3">
                            <div className="text-gray-400 text-xs">最高海拔</div>
                            <div className="text-lg font-bold text-white">
                              {workoutDetail.max_elevation_meters.toFixed(0)} <span className="text-sm">m</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* 速度图表 */}
                {paceChartData.length > 0 && (
                  <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                    <h3 className="text-lg font-bold text-white mb-4">⚡ 速度</h3>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={paceChartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                          <XAxis 
                            dataKey="time" 
                            stroke="#9ca3af" 
                            tickFormatter={(v) => {
                              const hours = Math.floor(v / 60);
                              const minutes = v % 60;
                              return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                            }}
                            label={{ value: '时间', position: 'insideBottom', offset: -5, style: { fill: '#9ca3af' } }}
                          />
                          <YAxis 
                            stroke="#9ca3af" 
                            label={{ value: '速度(km/h)', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af' } }}
                            domain={[0, 'dataMax + 1']}
                          />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                            labelFormatter={(v) => {
                              const hours = Math.floor(v / 60);
                              const minutes = v % 60;
                              return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                            }}
                            formatter={(v: number) => [`${v.toFixed(1)} 公里/小时`, '速度']}
                          />
                          <Bar dataKey="speed" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    {(workoutDetail.avg_speed_kmh || workoutDetail.max_speed_kmh) && (
                      <div className="mt-4 grid grid-cols-2 gap-4">
                        {workoutDetail.avg_speed_kmh && (
                          <div className="bg-blue-900/30 rounded-lg p-3 border border-blue-800/50">
                            <div className="text-blue-400 text-xs">平均速度</div>
                            <div className="text-lg font-bold text-blue-400">
                              {workoutDetail.avg_speed_kmh.toFixed(1)} <span className="text-sm">km/h</span>
                            </div>
                          </div>
                        )}
                        {workoutDetail.max_speed_kmh && (
                          <div className="bg-purple-900/30 rounded-lg p-3 border border-purple-800/50">
                            <div className="text-purple-400 text-xs">最大速度</div>
                            <div className="text-lg font-bold text-purple-400">
                              {workoutDetail.max_speed_kmh.toFixed(1)} <span className="text-sm">km/h</span>
                            </div>
                          </div>
                        )}
                        {workoutDetail.avg_pace_seconds_per_km && (
                          <div className="bg-slate-700/50 rounded-lg p-3">
                            <div className="text-gray-400 text-xs">平均配速</div>
                            <div className="text-lg font-bold text-white font-mono">
                              {formatPace(workoutDetail.avg_pace_seconds_per_km)}
                            </div>
                          </div>
                        )}
                        {workoutDetail.best_pace_seconds_per_km && (
                          <div className="bg-slate-700/50 rounded-lg p-3">
                            <div className="text-gray-400 text-xs">最佳配速</div>
                            <div className="text-lg font-bold text-white font-mono">
                              {formatPace(workoutDetail.best_pace_seconds_per_km)}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* 详细统计信息 */}
                <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-white">📋 详细数据</h3>
                    <div className="flex gap-2 text-xs">
                      <button 
                        onClick={() => setActiveTab('stats')}
                        className={`px-3 py-1 rounded hover:bg-blue-600 transition-colors ${
                          activeTab === 'stats' ? 'bg-blue-600/80 text-white' : 'bg-slate-700/50 text-gray-400'
                        }`}
                      >
                        统计信息
                      </button>
                      <button 
                        onClick={() => setActiveTab('laps')}
                        className={`px-3 py-1 rounded hover:bg-blue-600 transition-colors ${
                          activeTab === 'laps' ? 'bg-blue-600/80 text-white' : 'bg-slate-700/50 text-gray-400'
                        }`}
                      >
                        计圈
                      </button>
                      <button 
                        onClick={() => setActiveTab('intervals')}
                        className={`px-3 py-1 rounded hover:bg-blue-600 transition-colors ${
                          activeTab === 'intervals' ? 'bg-blue-600/80 text-white' : 'bg-slate-700/50 text-gray-400'
                        }`}
                      >
                        区间用时
                      </button>
                    </div>
                  </div>
                  
                  {/* 统计信息Tab */}
                  {activeTab === 'stats' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* 距离与消耗 */}
                    <div className="space-y-3">
                      <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">距离与消耗</h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">距离</span>
                          <span className="text-white font-medium">{formatDistance(workoutDetail.distance_meters || 0)} km</span>
                        </div>
                        {workoutDetail.calories && workoutDetail.active_calories && (
                          <div className="flex justify-between">
                            <span className="text-gray-400">静息消耗</span>
                            <span className="text-white font-medium">{workoutDetail.calories - workoutDetail.active_calories} kcal</span>
                          </div>
                        )}
                        {workoutDetail.active_calories && (
                          <div className="flex justify-between">
                            <span className="text-gray-400">活动消耗</span>
                            <span className="text-white font-medium">{workoutDetail.active_calories} kcal</span>
                          </div>
                        )}
                        <div className="flex justify-between">
                          <span className="text-gray-400">总消耗</span>
                          <span className="text-white font-medium">{workoutDetail.calories || '--'} kcal</span>
                        </div>
                        <div className="flex justify-between text-gray-500 text-xs pt-2 border-t border-slate-700">
                          <span>已摄入能量</span>
                          <span>--</span>
                        </div>
                        <div className="flex justify-between text-gray-500 text-xs">
                          <span>净消耗</span>
                          <span>{workoutDetail.calories ? `-${workoutDetail.calories}` : '--'} kcal</span>
                        </div>
                        <div className="flex justify-between text-gray-500 text-xs pt-2 border-t border-slate-700">
                          <span>估计汗液流失</span>
                          <span>{workoutDetail.calories ? `${Math.round(workoutDetail.calories * 1.5)} 毫升` : '--'}</span>
                        </div>
                        <div className="flex justify-between text-gray-500 text-xs">
                          <span>已补充水分</span>
                          <span>-- 毫升</span>
                        </div>
                        <div className="flex justify-between text-gray-500 text-xs">
                          <span>净补水量</span>
                          <span>{workoutDetail.calories ? `-${Math.round(workoutDetail.calories * 1.5)} 毫升` : '--'}</span>
                        </div>
                      </div>
                    </div>

                    {/* 训练效果与负荷 */}
                    <div className="space-y-3">
                      <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2 flex items-center gap-2">
                        训练效果与负荷
                        <span className="text-gray-500 text-xs">?</span>
                      </h4>
                      <div className="space-y-2 text-sm">
                        {workoutDetail.training_effect_aerobic && (
                          <div className="flex justify-between items-center">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">有氧效果</span>
                              <span className="text-xs text-gray-500">
                                {workoutDetail.training_effect_aerobic < 1.0 ? '微小作用' : 
                                 workoutDetail.training_effect_aerobic < 2.0 ? '维持' :
                                 workoutDetail.training_effect_aerobic < 3.0 ? '改善' :
                                 workoutDetail.training_effect_aerobic < 4.0 ? '高度改善' : '过度训练'}
                              </span>
                            </div>
                            <span className="text-white font-medium">{workoutDetail.training_effect_aerobic.toFixed(1)}</span>
                          </div>
                        )}
                        {workoutDetail.training_effect_anaerobic && (
                          <div className="flex justify-between items-center">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">无氧效果</span>
                              <span className="text-xs text-gray-500">
                                {workoutDetail.training_effect_anaerobic === 0 ? '无效益' : 
                                 workoutDetail.training_effect_anaerobic < 1.0 ? '微小作用' : '有效'}
                              </span>
                            </div>
                            <span className="text-white font-medium">{workoutDetail.training_effect_anaerobic.toFixed(1)}</span>
                          </div>
                        )}
                        {workoutDetail.training_load && (
                          <div className="flex justify-between items-center">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">运动负荷</span>
                              <span className="text-gray-500 text-xs">?</span>
                            </div>
                            <span className="text-white font-medium">{workoutDetail.training_load}</span>
                          </div>
                        )}
                        {workoutDetail.training_effect_aerobic && (
                          <div className="pt-2 border-t border-slate-700">
                            <div className="text-xs text-gray-500">
                              {workoutDetail.training_effect_aerobic < 1.5 ? '● 恢复(低强度有氧) 主要益处' :
                               workoutDetail.training_effect_aerobic < 2.5 ? '● 基础耐力 主要益处' :
                               workoutDetail.training_effect_aerobic < 3.5 ? '● 有氧能力 主要益处' :
                               '● 高强度训练 主要益处'}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 海拔高度 */}
                    {(workoutDetail.elevation_gain_meters || workoutDetail.elevation_loss_meters || workoutDetail.min_elevation_meters || workoutDetail.max_elevation_meters) && (
                      <div className="space-y-3">
                        <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">海拔高度</h4>
                        <div className="space-y-2 text-sm">
                          {workoutDetail.elevation_gain_meters && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">累计爬升</span>
                              <span className="text-white font-medium">{workoutDetail.elevation_gain_meters.toFixed(0)} 米</span>
                            </div>
                          )}
                          {workoutDetail.elevation_loss_meters && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">累计下降</span>
                              <span className="text-white font-medium">{workoutDetail.elevation_loss_meters.toFixed(0)} 米</span>
                            </div>
                          )}
                          {workoutDetail.min_elevation_meters && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最低海拔</span>
                              <span className="text-white font-medium">{workoutDetail.min_elevation_meters.toFixed(0)} 米</span>
                            </div>
                          )}
                          {workoutDetail.max_elevation_meters && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最高海拔</span>
                              <span className="text-white font-medium">{workoutDetail.max_elevation_meters.toFixed(0)} 米</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 强度活动时间 */}
                    {workoutDetail.duration_seconds && (
                      <div className="space-y-3">
                        <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">强度活动时间</h4>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-gray-400">中度</span>
                            <span className="text-white font-medium">
                              {workoutDetail.duration_seconds ? Math.floor(workoutDetail.duration_seconds * 0.5 / 60) : 0} 分钟
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-400">高强度</span>
                            <span className="text-white font-medium">
                              {workoutDetail.duration_seconds ? `${Math.floor(workoutDetail.duration_seconds * 0.1 / 60)} 分钟 x2` : '0 分钟'}
                            </span>
                          </div>
                          <div className="flex justify-between pt-2 border-t border-slate-700">
                            <span className="text-gray-400">总计</span>
                            <span className="text-white font-medium">
                              {workoutDetail.duration_seconds ? Math.floor(workoutDetail.duration_seconds * 0.6 / 60) : 0} 分钟
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* 心率数据 */}
                    {(workoutDetail.avg_heart_rate || workoutDetail.max_heart_rate || workoutDetail.min_heart_rate) && (
                      <div className="space-y-3">
                        <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">心率</h4>
                        <div className="space-y-2 text-sm">
                          {workoutDetail.avg_heart_rate && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">平均心率</span>
                              <span className="text-white font-medium">{workoutDetail.avg_heart_rate} bpm</span>
                            </div>
                          )}
                          {workoutDetail.max_heart_rate && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最大心率</span>
                              <span className="text-white font-medium">{workoutDetail.max_heart_rate} bpm</span>
                            </div>
                          )}
                          {workoutDetail.min_heart_rate && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最小心率</span>
                              <span className="text-white font-medium">{workoutDetail.min_heart_rate} bpm</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 配速/速度 */}
                    {(workoutDetail.avg_speed_kmh || workoutDetail.max_speed_kmh || workoutDetail.avg_pace_seconds_per_km) && (
                      <div className="space-y-3">
                        <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">配速/速度</h4>
                        <div className="space-y-2 text-sm">
                          {workoutDetail.avg_speed_kmh && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">平均速度</span>
                              <span className="text-white font-medium">{workoutDetail.avg_speed_kmh.toFixed(1)} km/h</span>
                            </div>
                          )}
                          {workoutDetail.max_speed_kmh && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最大速度</span>
                              <span className="text-white font-medium">{workoutDetail.max_speed_kmh.toFixed(1)} km/h</span>
                            </div>
                          )}
                          {workoutDetail.avg_pace_seconds_per_km && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">平均配速</span>
                              <span className="text-white font-mono">{formatPace(workoutDetail.avg_pace_seconds_per_km)}</span>
                            </div>
                          )}
                          {workoutDetail.best_pace_seconds_per_km && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最佳配速</span>
                              <span className="text-white font-mono">{formatPace(workoutDetail.best_pace_seconds_per_km)}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 计时 */}
                    <div className="space-y-3">
                      <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">计时</h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">时间</span>
                          <span className="text-white font-medium font-mono">{formatDuration(workoutDetail.duration_seconds)}</span>
                        </div>
                        {workoutDetail.moving_duration_seconds && (
                          <div className="flex justify-between">
                            <span className="text-gray-400">移动时间</span>
                            <span className="text-white font-medium font-mono">{formatDuration(workoutDetail.moving_duration_seconds)}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 其他数据 */}
                    {(workoutDetail.steps || workoutDetail.avg_cadence) && (
                      <div className="space-y-3">
                        <h4 className="text-sm font-semibold text-gray-300 border-b border-slate-700 pb-2">其他</h4>
                        <div className="space-y-2 text-sm">
                          {workoutDetail.steps && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">步数</span>
                              <span className="text-white font-medium">{workoutDetail.steps.toLocaleString()}</span>
                            </div>
                          )}
                          {workoutDetail.avg_cadence && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">平均步频</span>
                              <span className="text-white font-medium">{workoutDetail.avg_cadence} 步/分钟</span>
                            </div>
                          )}
                          {workoutDetail.max_cadence && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">最大步频</span>
                              <span className="text-white font-medium">{workoutDetail.max_cadence} 步/分钟</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                  )}

                  {/* 计圈Tab */}
                  {activeTab === 'laps' && (() => {
                    const laps: LapData[] = workoutDetail.lap_data ? JSON.parse(workoutDetail.lap_data) : [];
                    if (laps.length === 0) {
                      return (
                        <div className="text-center py-12">
                          <div className="text-6xl mb-4">📈</div>
                          <p className="text-gray-400 text-lg mb-2">暂无计圈数据</p>
                          <p className="text-gray-500 text-sm">Garmin同步的运动会自动包含计圈信息</p>
                        </div>
                      );
                    }

                    return (
                      <div className="space-y-4">
                        {laps.map((lap) => (
                          <div key={lap.lap} className="bg-slate-700/30 rounded-lg p-4 border border-slate-600/50">
                            <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-600">
                              <h4 className="text-lg font-bold text-white">第 {lap.lap} 圈</h4>
                              {lap.duration && (
                                <span className="text-blue-400 font-mono font-semibold">{formatDuration(lap.duration)}</span>
                              )}
                            </div>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                              {lap.distance && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">距离</div>
                                  <div className="text-white font-medium">{formatDistance(lap.distance)} km</div>
                                </div>
                              )}
                              {lap.avg_pace && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">配速</div>
                                  <div className="text-white font-mono">{formatPace(lap.avg_pace)}</div>
                                </div>
                              )}
                              {lap.avg_speed && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">速度</div>
                                  <div className="text-white font-medium">{lap.avg_speed.toFixed(1)} km/h</div>
                                </div>
                              )}
                              {lap.avg_hr && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">平均心率</div>
                                  <div className="text-white font-medium">{lap.avg_hr} bpm</div>
                                </div>
                              )}
                              {lap.max_hr && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">最大心率</div>
                                  <div className="text-white font-medium">{lap.max_hr} bpm</div>
                                </div>
                              )}
                              {lap.elevation_gain && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">爬升</div>
                                  <div className="text-white font-medium">{Math.round(lap.elevation_gain)} m</div>
                                </div>
                              )}
                              {lap.calories && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">卡路里</div>
                                  <div className="text-white font-medium">{lap.calories} kcal</div>
                                </div>
                              )}
                              {lap.avg_cadence && (
                                <div>
                                  <div className="text-gray-400 text-xs mb-1">步频</div>
                                  <div className="text-white font-medium">{lap.avg_cadence} 步/分</div>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    );
                  })()}

                  {/* 区间用时Tab */}
                  {activeTab === 'intervals' && hrZoneData.length > 0 && (() => {
                    const total = hrZoneData.reduce((sum, z) => sum + z.value, 0);
                    const maxHR = workoutDetail?.max_heart_rate || 220;
                    const hrZones = [
                      { zone: 1, name: '热身', range: `${Math.round(maxHR * 0.5)}-${Math.round(maxHR * 0.6)} bpm`, color: HR_ZONE_COLORS[0] },
                      { zone: 2, name: '燃脂', range: `${Math.round(maxHR * 0.6)}-${Math.round(maxHR * 0.7)} bpm`, color: HR_ZONE_COLORS[1] },
                      { zone: 3, name: '有氧', range: `${Math.round(maxHR * 0.7)}-${Math.round(maxHR * 0.8)} bpm`, color: HR_ZONE_COLORS[2] },
                      { zone: 4, name: '临界', range: `${Math.round(maxHR * 0.8)}-${Math.round(maxHR * 0.9)} bpm`, color: HR_ZONE_COLORS[3] },
                      { zone: 5, name: '无氧', range: `> ${Math.round(maxHR * 0.9)} bpm`, color: HR_ZONE_COLORS[4] },
                    ];

                    return (
                      <div className="space-y-4">
                        {hrZones.map((zone, idx) => {
                          const zoneData = hrZoneData[idx];
                          const percentage = total > 0 ? (zoneData.value / total) * 100 : 0;
                          return (
                            <div key={zone.zone} className="space-y-2">
                              <div className="flex items-center justify-between text-sm">
                                <div className="flex items-center gap-2">
                                  <span className="text-white font-medium">区间 {zone.zone}</span>
                                  <span className="text-gray-400 text-xs">{zone.range}</span>
                                  <span className="text-gray-500 text-xs">({zone.name})</span>
                                </div>
                                <div className="flex items-center gap-3">
                                  <span className="text-white font-mono">{formatDuration(zoneData.value)}</span>
                                  <span className="text-gray-400 font-medium">{percentage.toFixed(0)}%</span>
                                </div>
                              </div>
                              <div className="w-full bg-slate-700/30 rounded-full h-3 overflow-hidden">
                                <div 
                                  className="h-full rounded-full transition-all duration-500"
                                  style={{ 
                                    width: `${percentage}%`,
                                    backgroundColor: zone.color
                                  }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </div>

                {/* 心率区间分布（区间用时） - 保留原有的，但只在stats tab时显示 */}
                {activeTab === 'stats' && hrZoneData.length > 0 && (() => {
                  const total = hrZoneData.reduce((sum, z) => sum + z.value, 0);
                  // 计算最大心率（用于计算区间范围）
                  const maxHR = workoutDetail?.max_heart_rate || 220;
                  const hrZones = [
                    { 
                      zone: 1, 
                      name: '热身', 
                      desc: '热身', 
                      range: `${Math.round(maxHR * 0.5)} - ${Math.round(maxHR * 0.6)} bpm`,
                      color: HR_ZONE_COLORS[0],
                      value: workoutDetail?.hr_zone_1_seconds || 0
                    },
                    { 
                      zone: 2, 
                      name: '脂肪燃烧', 
                      desc: '脂肪燃烧', 
                      range: `${Math.round(maxHR * 0.6)} - ${Math.round(maxHR * 0.7)} bpm`,
                      color: HR_ZONE_COLORS[1],
                      value: workoutDetail?.hr_zone_2_seconds || 0
                    },
                    { 
                      zone: 3, 
                      name: '有氧', 
                      desc: '有氧', 
                      range: `${Math.round(maxHR * 0.7)} - ${Math.round(maxHR * 0.8)} bpm`,
                      color: HR_ZONE_COLORS[2],
                      value: workoutDetail?.hr_zone_3_seconds || 0
                    },
                    { 
                      zone: 4, 
                      name: '临界心率', 
                      desc: '临界心率', 
                      range: `${Math.round(maxHR * 0.8)} - ${Math.round(maxHR * 0.9)} bpm`,
                      color: HR_ZONE_COLORS[3],
                      value: workoutDetail?.hr_zone_4_seconds || 0
                    },
                    { 
                      zone: 5, 
                      name: '无氧耐力', 
                      desc: '无氧耐力', 
                      range: `> ${Math.round(maxHR * 0.9)} bpm`,
                      color: HR_ZONE_COLORS[4],
                      value: workoutDetail?.hr_zone_5_seconds || 0
                    },
                  ];
                  
                  return (
                    <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                      <h3 className="text-lg font-bold text-white mb-4">❤️ 心率区间用时</h3>
                      <div className="space-y-4">
                        {hrZones.map((zone) => {
                          const percent = total > 0 ? ((zone.value / total) * 100).toFixed(0) : 0;
                          return (
                            <div key={zone.zone} className="space-y-1">
                              <div className="flex items-center justify-between text-sm">
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-400">区间 {zone.zone}</span>
                                  <span className="text-white font-medium">{zone.range}</span>
                                  <span className="text-gray-500">({zone.desc})</span>
                                </div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-white font-mono">{formatDuration(zone.value)}</span>
                                    <span className="text-gray-500 text-xs w-10 text-right">{percent}%</span>
                                  </div>
                                </div>
                              <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden">
                                <div
                                  className="h-full rounded-full transition-all"
                                  style={{
                                    width: `${percent}%`,
                                    backgroundColor: zone.color,
                                  }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

                {/* AI分析结果 */}
                {workoutDetail.ai_analysis && (
                  <div className="bg-gradient-to-br from-purple-900/40 to-slate-800/60 rounded-xl p-6 border border-purple-700/50">
                    <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                      ✨ AI训练分析
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

                {/* 运动后科学分析 */}
                {console.log('🔍 showPostAnalysis:', showPostAnalysis, 'postAnalysis:', postAnalysis)}
                {showPostAnalysis && postAnalysis && postAnalysis.success && (
                  <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/20 rounded-xl p-6 border border-blue-700/50 mt-6">
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-2xl font-bold text-white flex items-center gap-2">
                        <span>🔬</span> 运动后科学分析
                      </h3>
                      {/* 保存状态提示 */}
                      <div className="flex items-center gap-2">
                        {postAnalysis.from_cache ? (
                          <span className="px-3 py-1 bg-green-500/20 text-green-300 rounded-full text-sm flex items-center gap-1">
                            <span>✓</span> 已保存
                          </span>
                        ) : (
                          <span className="px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full text-sm flex items-center gap-1">
                            <span>✨</span> 新生成
                          </span>
                        )}
                        {postAnalysis.generated_at && (
                          <span className="text-xs text-gray-400">
                            {new Date(postAnalysis.generated_at).toLocaleString('zh-CN', {
                              month: 'numeric',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* 整体评分 */}
                    {postAnalysis.overall_rating && (
                      <div className="bg-slate-800/60 rounded-xl p-6 mb-6 text-center">
                        <div className="text-6xl mb-2">{postAnalysis.overall_rating.emoji}</div>
                        <div className="text-3xl font-bold text-white mb-2">{postAnalysis.overall_rating.rating}</div>
                        <div className="text-lg text-gray-300">{postAnalysis.overall_rating.message}</div>
                        <div className="text-sm text-gray-400 mt-2">评分: {postAnalysis.overall_rating.score}/10</div>
                      </div>
                    )}

                    {/* 训练强度评估 */}
                    {postAnalysis.intensity_assessment && (
                      <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
                        <h4 className="text-xl font-bold text-white mb-4">💪 训练强度评估</h4>
                        <div className="flex items-center gap-4 mb-4">
                          <span className="text-4xl">{postAnalysis.intensity_assessment.emoji}</span>
                          <div>
                            <div className="text-2xl font-bold text-white">{postAnalysis.intensity_assessment.level}</div>
                            <div className="text-sm text-gray-400">评分: {postAnalysis.intensity_assessment.score}/10</div>
                          </div>
                        </div>
                        {postAnalysis.intensity_assessment.factors && (
                          <ul className="space-y-2">
                            {postAnalysis.intensity_assessment.factors.map((factor: string, idx: number) => (
                              <li key={idx} className="text-gray-300 flex items-start gap-2">
                                <span className="text-blue-400">•</span>
                                <span>{factor}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* 心率区间分析 */}
                    {postAnalysis.hr_analysis && postAnalysis.hr_analysis.has_hr_data && (
                      <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
                        <h4 className="text-xl font-bold text-white mb-4">❤️ 心率区间分析</h4>
                        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
                          {Object.entries(postAnalysis.hr_analysis.zones).map(([key, zone]: [string, any]) => (
                            <div key={key} className="bg-slate-700/50 rounded-lg p-3">
                              <div className="text-xs text-gray-400 mb-1">{zone.name}</div>
                              <div className="text-2xl font-bold text-white">{zone.percentage}%</div>
                              <div className="text-xs text-gray-400 mt-1">{Math.floor(zone.seconds / 60)}分钟</div>
                            </div>
                          ))}
                        </div>
                        {postAnalysis.hr_analysis.recommendations && postAnalysis.hr_analysis.recommendations.length > 0 && (
                          <div className="space-y-2">
                            {postAnalysis.hr_analysis.recommendations.map((rec: string, idx: number) => (
                              <div key={idx} className="text-gray-300 flex items-start gap-2">
                                <span>{rec.split(' ')[0]}</span>
                                <span>{rec.substring(rec.indexOf(' ') + 1)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 恢复建议 */}
                    {postAnalysis.recovery_tips && postAnalysis.recovery_tips.length > 0 && (
                      <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
                        <h4 className="text-xl font-bold text-white mb-4">🛀 恢复建议</h4>
                        <div className="space-y-3">
                          {postAnalysis.recovery_tips.map((tip: string, idx: number) => (
                            <div key={idx} className="flex items-start gap-3 bg-slate-700/50 rounded-lg p-3">
                              <span className="text-xl">{tip.split(' ')[0]}</span>
                              <span className="text-gray-200 flex-1">{tip.substring(tip.indexOf(' ') + 1)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 改进建议 */}
                    {postAnalysis.improvement_tips && postAnalysis.improvement_tips.length > 0 && (
                      <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
                        <h4 className="text-xl font-bold text-white mb-4">📈 改进建议</h4>
                        <ul className="space-y-2">
                          {postAnalysis.improvement_tips.map((tip: string, idx: number) => (
                            <li key={idx} className="text-gray-300 flex items-start gap-2">
                              <span className="text-blue-400">→</span>
                              <span>{tip}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  </div>
                )}
              </>
            ) : (
              /* 运动类型分布 */
              typeDistribution.length > 0 && (
                <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
                  <h3 className="text-lg font-bold text-white mb-4">🏃 运动类型分布</h3>
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={typeDistribution} layout="vertical" margin={{ left: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis type="number" stroke="#9ca3af" />
                        <YAxis type="category" dataKey="name" stroke="#9ca3af" width={90} tick={{ fontSize: 12 }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                          formatter={(v: number, name: string) => [
                            name === '次数' ? `${v} 次` : `${Math.floor(v / 60)}小时${v % 60}分钟`,
                            name === '次数' ? '训练次数' : '总时长'
                          ]}
                        />
                        <Legend wrapperStyle={{ color: '#9ca3af' }} />
                        <Bar dataKey="count" fill="#3b82f6" name="次数" radius={[0, 4, 4, 0]} />
                        <Bar dataKey="duration" fill="#10b981" name="时长(分)" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  {/* 详细数据表格 */}
                  <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-3">
                    {typeDistribution.map((item) => (
                      <div key={item.name} className="bg-slate-700/50 rounded-lg p-3 flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                        <div className="flex-1 min-w-0">
                          <div className="text-white text-sm font-medium truncate">{item.name}</div>
                          <div className="text-gray-400 text-xs">
                            {item.count}次 · {Math.floor(item.duration / 60)}h{item.duration % 60}m
                          </div>
                        </div>
                      </div>
                    ))}
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

