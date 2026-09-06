'use client';
import { fetchWithAiSubject as fetch, requireAiConsent } from '@/services/aiConsent';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { workoutGuidanceApi } from '@/services/api/content';
import { WORKOUT_TYPES, HR_ZONE_COLORS } from './components/workoutUtils';
import { WorkoutSummary, WorkoutStats, WorkoutDetail } from './components/workoutTypes';
import WorkoutList from './components/WorkoutList';
import WorkoutDetailHeader from './components/WorkoutDetailHeader';
import WorkoutCharts from './components/WorkoutCharts';
import WorkoutDetailStats from './components/WorkoutDetailStats';
import WorkoutAnalysis from './components/WorkoutAnalysis';
import WorkoutTypeDistribution from './components/WorkoutTypeDistribution';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

function WorkoutContent() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();

  useEffect(() => { document.title = '运动 | 健康管理'; }, []);
  const [selectedWorkout, setSelectedWorkout] = useState<number | null>(null);
  const [days, setDays] = useState(7);
  const [syncDays, setSyncDays] = useState(7);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showPostAnalysis, setShowPostAnalysis] = useState(false);
  const [postAnalysis, setPostAnalysis] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'stats' | 'laps' | 'intervals'>('stats');

  useEffect(() => {
    const rawId = searchParams.get('id') || searchParams.get('workout_id');
    const parsed = rawId ? Number(rawId) : NaN;
    if (Number.isFinite(parsed) && parsed > 0) {
      setSelectedWorkout(parsed);
    }
  }, [searchParams]);

  // Fetch workout list
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

  // Fetch stats
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

  // Fetch workout detail
  const { data: workoutDetail, isLoading: loadingDetail, error: detailError } = useQuery<WorkoutDetail>({
    queryKey: ['workout-detail', selectedWorkout],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me/${selectedWorkout}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: '获取运动详情失败' }));
        if (res.status === 404) throw new Error(errorData.detail || '运动记录不存在');
        throw new Error(errorData.detail || `获取运动详情失败 (${res.status})`);
      }
      return res.json();
    },
    enabled: !!token && !!selectedWorkout,
    retry: false,
  });

  // Sync Garmin
  const syncMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me/sync-garmin?days=${syncDays}`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { const error = await res.json(); throw new Error(error.detail || '同步失败'); }
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

  // AI Analysis
  const analyzeMutation = useMutation({
    mutationFn: async (workoutId: number) => {
      const aiHeaders = await requireAiConsent();
      const res = await fetch(`${API_BASE}/workout/me/${workoutId}/analyze`, {
        method: 'POST', headers: { ...aiHeaders, Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { const error = await res.json(); throw new Error(error.detail || '分析失败'); }
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

  // Post-workout scientific analysis
  const postAnalysisMutation = useMutation({
    mutationFn: ({ workoutId, forceRegenerate = false, cacheOnly = false }: { workoutId: number; forceRegenerate?: boolean; cacheOnly?: boolean }) =>
      workoutGuidanceApi.getPostWorkoutAnalysis(workoutId, forceRegenerate, false, cacheOnly),
    onSuccess: (response, variables) => {
      console.log('📊 科学分析响应:', response);
      console.log('📊 response.data:', response.data);
      if (variables.cacheOnly && response.data.success === false) {
        console.log('📊 无缓存的科学分析，等待用户手动请求');
        return;
      }
      setPostAnalysis(response.data);
      setShowPostAnalysis(true);
      if (!variables.cacheOnly) {
        const fromCache = response.data.from_cache;
        setMessage({ type: 'success', text: fromCache ? '✓ 已加载分析结果' : '✓ 科学分析完成' });
        setTimeout(() => setMessage(null), 3000);
      }
    },
    onError: (error: any, variables) => {
      console.error('❌ 科学分析失败:', error);
      if (!variables.cacheOnly) {
        setMessage({ type: 'error', text: `✗ 分析失败: ${error.message}` });
        setTimeout(() => setMessage(null), 5000);
      }
    },
  });

  // Refresh HR data
  const refreshHRMutation = useMutation({
    mutationFn: async (workoutId: number) => {
      const res = await fetch(`${API_BASE}/workout/me/${workoutId}/refresh-hr`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { const error = await res.json(); throw new Error(error.detail || '刷新失败'); }
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

  // Reset post analysis when selecting new workout
  useEffect(() => {
    setShowPostAnalysis(false);
    setPostAnalysis(null);
  }, [selectedWorkout]);

  // Auto-load cached analysis when detail loads
  useEffect(() => {
    if (workoutDetail && workoutDetail.id && !loadingDetail) {
      postAnalysisMutation.mutate({ workoutId: workoutDetail.id, forceRegenerate: false, cacheOnly: true });
    }
  }, [workoutDetail?.id, loadingDetail]);

  // Prepare HR zone chart data
  const hrZoneData = workoutDetail ? [
    { name: '热身区', value: workoutDetail.hr_zone_1_seconds || 0, color: HR_ZONE_COLORS[0] },
    { name: '燃脂区', value: workoutDetail.hr_zone_2_seconds || 0, color: HR_ZONE_COLORS[1] },
    { name: '有氧区', value: workoutDetail.hr_zone_3_seconds || 0, color: HR_ZONE_COLORS[2] },
    { name: '阈值区', value: workoutDetail.hr_zone_4_seconds || 0, color: HR_ZONE_COLORS[3] },
    { name: '极限区', value: workoutDetail.hr_zone_5_seconds || 0, color: HR_ZONE_COLORS[4] },
  ].filter(d => d.value > 0) : [];

  // Prepare type distribution data
  const typeDistribution = stats?.workouts_by_type
    ? Object.entries(stats.workouts_by_type).map(([type, data]) => ({
        name: WORKOUT_TYPES[type as keyof typeof WORKOUT_TYPES]?.name || type,
        count: data.count,
        duration: data.duration_minutes,
        color: WORKOUT_TYPES[type as keyof typeof WORKOUT_TYPES]?.color || '#6b7280',
      }))
    : [];

  // Parse heart rate chart data
  const heartRateChartData = workoutDetail?.heart_rate_data
    ? (() => {
        try {
          const data = JSON.parse(workoutDetail.heart_rate_data);
          return data.map((p: { time: number; hr: number }) => ({ time: Math.floor(p.time / 60), hr: p.hr }));
        } catch { return []; }
      })()
    : [];

  // Parse pace chart data
  const paceChartData = workoutDetail?.pace_data
    ? (() => {
        try {
          const data = JSON.parse(workoutDetail.pace_data);
          return data.map((p: { time: number; pace: number }) => ({
            time: Math.floor(p.time / 60),
            pace: p.pace,
            speed: p.pace > 0 ? (3600 / p.pace) : 0,
          }));
        } catch { return []; }
      })()
    : [];

  // Parse GPS route data
  const routeData = workoutDetail?.route_data
    ? (() => {
        try {
          const data = JSON.parse(workoutDetail.route_data);
          return data.map((p: any) => {
            if (Array.isArray(p)) return { lat: p[0], lng: p[1] };
            return {
              lat: p.lat || p.latitude, lng: p.lng || p.longitude,
              elevation: p.elevation || p.elev, time: p.time,
            };
          }).filter((p: any) => p.lat && p.lng);
        } catch { return []; }
      })()
    : [];

  // Parse elevation data
  const elevationChartData = (() => {
    if (routeData.length > 0) {
      const gpsElevationData = routeData
        .filter((p: any) => p.elevation !== undefined && p.elevation !== null && p.time !== undefined)
        .map((p: any, idx: number) => ({ time: Math.floor((p.time || idx * 10) / 60), elevation: p.elevation }));
      if (gpsElevationData.length > 0) return gpsElevationData;
    }
    if (workoutDetail?.elevation_data) {
      try {
        const data = JSON.parse(workoutDetail.elevation_data);
        if (data[0]?.time !== undefined) {
          return data.map((p: { time: number; elevation: number }) => ({ time: Math.floor(p.time / 60), elevation: p.elevation }));
        } else {
          const avgSpeed = workoutDetail.avg_speed_kmh || 5;
          return data.map((p: { distance: number; elevation: number }) => ({
            time: Math.floor((p.distance / 1000 / avgSpeed) * 60), elevation: p.elevation,
          }));
        }
      } catch { return []; }
    }
    return [];
  })();

  return (
    <main className="min-h-screen p-4 md:p-8 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-4 md:pt-4">
      <div className="max-w-7xl mx-auto">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-2">
              <span>🏋️</span> 运动训练
            </h1>
            <p className="text-gray-400 mt-1">记录和分析您的每次训练</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}
              className="px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 text-sm">
              <option value={7}>最近7天</option>
              <option value={30}>最近30天</option>
              <option value={90}>最近90天</option>
              <option value={365}>最近1年</option>
            </select>
            <div className="flex items-center gap-2">
              <select value={syncDays} onChange={(e) => setSyncDays(Number(e.target.value))}
                className="px-3 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 text-sm">
                <option value={3}>同步3天</option>
                <option value={7}>同步7天</option>
                <option value={14}>同步14天</option>
                <option value={30}>同步30天</option>
              </select>
              <button onClick={() => syncMutation.mutate()} disabled={syncMutation.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium">
                {syncMutation.isPending ? '同步中...' : '🔄 同步Garmin'}
              </button>
            </div>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div className={`mb-4 p-4 rounded-xl ${
            message.type === 'success'
              ? 'bg-green-900/50 text-green-300 border border-green-700'
              : 'bg-red-900/50 text-red-300 border border-red-700'
          }`}>
            {message.text}
          </div>
        )}

        {/* Stats Cards */}
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
          {/* Workout List */}
          <WorkoutList
            workouts={workouts}
            loadingWorkouts={loadingWorkouts}
            selectedWorkout={selectedWorkout}
            setSelectedWorkout={setSelectedWorkout}
          />

          {/* Workout Detail Area */}
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
                  onClick={() => queryClient.invalidateQueries({ queryKey: ['workout-detail', selectedWorkout] })}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                >
                  重试
                </button>
              </div>
            ) : selectedWorkout && workoutDetail ? (
              <>
                <WorkoutDetailHeader
                  workoutDetail={workoutDetail}
                  analyzeMutation={analyzeMutation}
                  postAnalysisMutation={postAnalysisMutation}
                  refreshHRMutation={refreshHRMutation}
                  postAnalysis={postAnalysis}
                />

                <WorkoutCharts
                  workoutDetail={workoutDetail}
                  heartRateChartData={heartRateChartData}
                  elevationChartData={elevationChartData}
                  paceChartData={paceChartData}
                  routeData={routeData}
                  refreshHRMutation={refreshHRMutation}
                />

                <WorkoutDetailStats
                  workoutDetail={workoutDetail}
                  activeTab={activeTab}
                  setActiveTab={setActiveTab}
                  hrZoneData={hrZoneData}
                />

                <WorkoutAnalysis
                  workoutDetail={workoutDetail}
                  activeTab={activeTab}
                  hrZoneData={hrZoneData}
                  showPostAnalysis={showPostAnalysis}
                  postAnalysis={postAnalysis}
                />
              </>
            ) : (
              /* Type Distribution or empty state */
              typeDistribution.length > 0 ? (
                <WorkoutTypeDistribution typeDistribution={typeDistribution} />
              ) : (
                <div className="bg-slate-800/60 rounded-xl p-12 border border-slate-700 text-center">
                  <div className="text-6xl mb-4">👈</div>
                  <p className="text-gray-400 text-lg">选择一条训练记录查看详情</p>
                  <p className="text-gray-500 text-sm mt-2">或点击"同步Garmin"获取运动数据</p>
                </div>
              )
            )}

            {/* Show type distribution alongside detail when workout is selected */}
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
