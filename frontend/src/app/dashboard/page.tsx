'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api/client';
import { dailyHealthApi, garminAnalysisApi, basicHealthApi, healthTrendApi, healthScoreApi } from '@/services/api/health';
import { dataCollectionApi } from '@/services/api/devices';
import { useMutation } from '@tanstack/react-query';
import { format, subDays } from 'date-fns';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { bloodPressureSaveFeedback } from '../blood-pressure/saveFeedback';

function DashboardContent() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.id;
  const [days] = useState(30);

  useEffect(() => { document.title = '首页 | 健康管理'; }, []);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState('');

  // 下拉刷新相关状态
  const [pullStartY, setPullStartY] = useState(0);
  const [pullDistance, setPullDistance] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 数据健康度
  const [dataHealth, setDataHealth] = useState<Record<string, { status: string; message: string }> | null>(null);
  useEffect(() => {
    api.get('/data-health/status').then(r => setDataHealth(r.data)).catch(() => {});
  }, []);

  // 快速记录
  const [quickInput, setQuickInput] = useState('');
  const [quickToast, setQuickToast] = useState('');
  const [quickToastType, setQuickToastType] = useState<'success' | 'warning' | 'error'>('success');
  const quickRecordMutation = useMutation({
    mutationFn: (text: string) => api.post('/quick-record', { text }),
    onSuccess: (res) => {
      const feedback = res.data?.type === 'bp'
        ? bloodPressureSaveFeedback(res.data)
        : { message: res.data?.message || '记录成功', type: 'success' as const };
      setQuickToast(feedback.message);
      setQuickToastType(feedback.type);
      setQuickInput('');
      setTimeout(() => setQuickToast(''), feedback.type === 'warning' ? 9000 : 3000);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || '记录失败，请检查格式';
      setQuickToast(detail);
      setQuickToastType('error');
      setTimeout(() => setQuickToast(''), 4000);
    },
  });

  const handleQuickRecord = () => {
    const text = quickInput.trim();
    if (!text) return;
    quickRecordMutation.mutate(text);
  };

  const endDate = format(new Date(), 'yyyy-MM-dd');
  const startDate = format(subDays(new Date(), days), 'yyyy-MM-dd');
  const today = format(new Date(), 'yyyy-MM-dd');

  // 获取今天的实时数据
  const { data: todayData, refetch: refetchToday, isFetching: isFetchingToday } = useQuery({
    queryKey: ['garmin-today', userId, today],
    queryFn: () => dailyHealthApi.getMyGarminData(today, today),
    refetchInterval: 15 * 60 * 1000, // 每15分钟自动刷新
    enabled: !!userId,
  });

  // 获取Garmin数据
  const { data: garminData, refetch: refetchGarminData } = useQuery({
    queryKey: ['garmin-data', userId, startDate, endDate],
    queryFn: () => dailyHealthApi.getMyGarminData(startDate, endDate),
    enabled: !!userId,
  });

  // 获取基础健康数据
  const { data: basicHealth, refetch: refetchBasicHealth } = useQuery({
    queryKey: ['basic-health', userId],
    queryFn: () => basicHealthApi.getMyLatest(),
    enabled: !!userId,
  });

  // 获取综合分析
  const { data: comprehensive, refetch: refetchComprehensive } = useQuery({
    queryKey: ['garmin-comprehensive', userId, 7],
    queryFn: () => garminAnalysisApi.getMyComprehensive(7),
    enabled: !!userId,
  });

  // 获取健康趋势数据
  const { data: trendData } = useQuery({
    queryKey: ['health-trends-latest', userId],
    queryFn: () => healthTrendApi.getLatest(),
    enabled: !!userId,
  });

  // 每日健康评分
  const { data: healthScore } = useQuery({
    queryKey: ['health-score-daily', userId, today],
    queryFn: () => healthScoreApi.getDailyScore(today),
    enabled: !!userId,
    staleTime: 10 * 60 * 1000,
  });
  const scoreData = healthScore?.data;
  const scoreGradeColor = (s: number) =>
    s >= 90 ? 'text-emerald-400' : s >= 75 ? 'text-green-400' : s >= 60 ? 'text-yellow-400' : 'text-red-400';
  const scoreBg = (s: number) =>
    s >= 90 ? 'from-emerald-600 to-teal-600' : s >= 75 ? 'from-green-600 to-emerald-600' : s >= 60 ? 'from-yellow-600 to-amber-600' : 'from-red-600 to-rose-600';

  // 非 Garmin 用户数据：饮水/饮食/体重（当 Garmin 数据为空时展示）
  const { data: waterToday } = useQuery({
    queryKey: ['water-today', userId, today],
    queryFn: () => api.get(`/water/records/me/daily-summary?date=${today}`),
    enabled: !!userId,
  });
  const { data: dietToday } = useQuery({
    queryKey: ['diet-today', userId, today],
    queryFn: () => api.get(`/diet/records/me/date/${today}`),
    enabled: !!userId,
  });
  const { data: weightLatest } = useQuery({
    queryKey: ['weight-latest', userId],
    queryFn: () => api.get('/weight/records/me?limit=1'),
    enabled: !!userId,
  });

  // 手动刷新所有数据（包含 Garmin 同步）
  const handleManualRefresh = async () => {
    if (isRefreshing) return; // 防止重复点击

    setIsRefreshing(true);
    setRefreshError('');
    try {
      // 1. 先触发 Garmin 同步
      if (userId) {
        try {
          await dataCollectionApi.syncGarmin(userId, today);
          console.log('Garmin 同步已触发');
        } catch (syncError) {
          console.warn('Garmin 同步失败:', syncError);
          // 同步失败不影响数据刷新
        }
      }

      // 2. 等待 2 秒让同步有时间完成
      await new Promise(resolve => setTimeout(resolve, 2000));

      // 3. 使所有相关查询失效并重新获取
      await Promise.all([
        refetchToday(),
        refetchGarminData(),
        refetchBasicHealth(),
        refetchComprehensive(),
      ]);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('刷新数据失败:', error);
      setRefreshError('刷新数据失败，请稍后重试');
      setTimeout(() => setRefreshError(''), 5000);
    } finally {
      setIsRefreshing(false);
    }
  };

  // 监听数据更新
  useEffect(() => {
    if (todayData) {
      setLastUpdate(new Date());
    }
  }, [todayData]);

  // 下拉刷新触摸事件处理
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let startY = 0;
    let currentY = 0;

    const handleTouchStart = (e: TouchEvent) => {
      // 只在页面顶部时启用下拉刷新
      if (window.scrollY === 0 && !isRefreshing) {
        startY = e.touches[0].clientY;
        setIsPulling(true);
        setPullStartY(startY);
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!isPulling || isRefreshing) return;

      currentY = e.touches[0].clientY;
      const distance = currentY - startY;

      // 只允许向下拉
      if (distance > 0 && window.scrollY === 0) {
        // 限制最大拉动距离为 100px
        const maxDistance = 100;
        const dampedDistance = Math.min(distance * 0.5, maxDistance);
        setPullDistance(dampedDistance);

        // 阻止默认滚动行为
        if (distance > 10) {
          e.preventDefault();
        }
      }
    };

    const handleTouchEnd = async () => {
      if (!isPulling) return;

      setIsPulling(false);

      // 如果拉动距离超过 60px，触发刷新
      if (pullDistance > 60 && !isRefreshing) {
        await handleManualRefresh();
      }

      // 重置拉动距离
      setPullDistance(0);
      setPullStartY(0);
    };

    container.addEventListener('touchstart', handleTouchStart, { passive: true });
    container.addEventListener('touchmove', handleTouchMove, { passive: false });
    container.addEventListener('touchend', handleTouchEnd);

    return () => {
      container.removeEventListener('touchstart', handleTouchStart);
      container.removeEventListener('touchmove', handleTouchMove);
      container.removeEventListener('touchend', handleTouchEnd);
    };
  }, [isPulling, pullDistance, isRefreshing, handleManualRefresh]);

  // 今天的数据
  const todayRecord = todayData?.data?.[0];

  // 准备图表数据 - 按日期排序后取最近14天
  const chartData = (() => {
    if (!garminData?.data || garminData.data.length === 0) return [];

    // 按日期排序（升序）
    const sorted = [...garminData.data].sort((a: any, b: any) =>
      new Date(a.record_date).getTime() - new Date(b.record_date).getTime()
    );

    // 取最近14天的数据
    const recent14 = sorted.slice(-14);

    return recent14.map((item: any) => ({
      date: format(new Date(item.record_date), 'MM-dd'),
      sleep: item.sleep_score,
      steps: item.steps,
      heartRate: item.avg_heart_rate,
    }));
  })();

  return (
    <main
      ref={containerRef}
      className="min-h-screen p-8 bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 relative"
      style={{
        transform: `translateY(${pullDistance}px)`,
        transition: isPulling ? 'none' : 'transform 0.3s ease-out',
      }}
    >
      {/* 下拉刷新指示器 */}
      {(isPulling || pullDistance > 0 || isRefreshing) && (
        <div
          className="fixed top-0 left-0 right-0 flex items-center justify-center bg-gradient-to-r from-indigo-600 to-purple-600 text-white z-50"
          style={{
            height: isRefreshing ? '48px' : `${pullDistance}px`,
            opacity: isRefreshing ? 1 : Math.min(pullDistance / 60, 1),
          }}
        >
          <div className="flex items-center gap-2">
            {isRefreshing ? (
              <>
                <span className="text-xl animate-spin">🔄</span>
                <span className="font-semibold">正在同步 Garmin 数据...</span>
              </>
            ) : pullDistance > 60 ? (
              <>
                <span className="text-xl">🔄</span>
                <span className="font-semibold">释放刷新</span>
              </>
            ) : (
              <>
                <span className="text-xl">⬇️</span>
                <span className="font-semibold">下拉刷新</span>
              </>
            )}
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto">
        {/* 健康评分卡 */}
        {scoreData?.status === 'ok' && (
          <div className={`bg-gradient-to-r ${scoreBg(scoreData.total_score)} rounded-2xl shadow-xl p-5 mb-6 text-white flex items-center gap-6`}>
            {/* 分数圆圈 */}
            <div className="flex-shrink-0 flex flex-col items-center">
              <div className="w-20 h-20 rounded-full bg-white/20 border-4 border-white/40 flex items-center justify-center">
                <span className="text-3xl font-black">{scoreData.total_score}</span>
              </div>
              <span className="mt-1 text-sm font-semibold text-white/90">{scoreData.grade}</span>
            </div>
            {/* 维度 + 建议 */}
            <div className="flex-1 min-w-0">
              <div className="text-xs uppercase tracking-widest text-white/70 mb-2">今日健康评分</div>
              <div className="flex flex-wrap gap-2 mb-3">
                {(scoreData.dimensions || []).map((d: any) => (
                  <span key={d.name} className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-medium">
                    {d.name} <span className={`font-bold ${scoreGradeColor(d.score)}`}>{d.score}</span>
                  </span>
                ))}
              </div>
              {scoreData.suggestions?.[0] && (
                <p className="text-sm text-white/80 truncate">💡 {scoreData.suggestions[0]}</p>
              )}
            </div>
          </div>
        )}

        {/* 今日实时数据 */}
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl shadow-2xl p-6 mb-8 text-white">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-3xl font-bold mb-1">⚡ 今日实时数据</h2>
              <p className="text-indigo-100 text-sm">
                最后更新: {format(lastUpdate, 'HH:mm:ss')} | 自动刷新中...
              </p>
            </div>
            <button
              onClick={handleManualRefresh}
              disabled={isRefreshing || isFetchingToday}
              className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg font-semibold transition-all backdrop-blur-sm border border-white/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isRefreshing || isFetchingToday ? (
                <>
                  <span className="animate-spin">🔄</span>
                  <span>刷新中...</span>
                </>
              ) : (
                <>
                  <span>🔄</span>
                  <span>手动刷新</span>
                </>
              )}
            </button>
          </div>

          {refreshError && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-400/30 rounded-lg text-red-100 text-sm">
              {refreshError}
            </div>
          )}

          {todayRecord ? (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">😴</span>
                  <p className="text-sm font-medium text-indigo-100">睡眠分数</p>
                </div>
                <p className="text-3xl font-bold">
                  {todayRecord.sleep_score || '-'}
                </p>
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">🚶</span>
                  <p className="text-sm font-medium text-indigo-100">步数</p>
                </div>
                <p className="text-3xl font-bold">
                  {todayRecord.steps?.toLocaleString() || '-'}
                </p>
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">❤️</span>
                  <p className="text-sm font-medium text-indigo-100">静息心率</p>
                </div>
                <p className="text-3xl font-bold">
                  {todayRecord.resting_heart_rate || '-'}
                  {todayRecord.resting_heart_rate && <span className="text-lg ml-1">bpm</span>}
                </p>
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">🔋</span>
                  <p className="text-sm font-medium text-indigo-100">身体电量</p>
                </div>
                {(() => {
                  const currentBattery = todayRecord.body_battery_current;
                  const peakBattery = todayRecord.body_battery_most_charged ?? todayRecord.body_battery_charged;
                  const lowestBattery = todayRecord.body_battery_lowest;
                  const drainedBattery = todayRecord.body_battery_drained;
                  const displayBattery = currentBattery ?? peakBattery;
                  const hasCurrent = currentBattery !== null && currentBattery !== undefined;

                  const getBatteryStatus = (value: number | null | undefined) => {
                    if (value === null || value === undefined) return '';
                    if (value >= 80) return '充足';
                    if (value >= 50) return '中等';
                    return '偏低';
                  };

                  return (
                    <>
                      <p className={`text-3xl font-bold ${
                        displayBattery !== null && displayBattery !== undefined
                          ? (displayBattery >= 80 ? 'text-green-400' : displayBattery >= 50 ? 'text-yellow-400' : 'text-red-400')
                          : ''
                      }`}>
                        {displayBattery ?? '-'}
                        {displayBattery !== null && displayBattery !== undefined && (
                          <span className="text-sm ml-2 font-normal opacity-80">
                            {hasCurrent ? `当前 · ${getBatteryStatus(currentBattery)}` : '峰值'}
                          </span>
                        )}
                      </p>
                      <div className="text-xs text-indigo-200 mt-1 space-y-0.5">
                        {hasCurrent && peakBattery !== null && peakBattery !== undefined && (
                          <p>📈 峰值 {peakBattery}</p>
                        )}
                        {lowestBattery !== null && lowestBattery !== undefined && (
                          <p>📉 最低 {lowestBattery}</p>
                        )}
                        {drainedBattery !== null && drainedBattery !== undefined && (
                          <p>⚡ 消耗 -{drainedBattery}</p>
                        )}
                      </div>
                    </>
                  );
                })()}
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">💪</span>
                  <p className="text-sm font-medium text-indigo-100">HRV</p>
                </div>
                <p className="text-3xl font-bold">
                  {todayRecord.hrv || '-'}
                  {todayRecord.hrv && <span className="text-lg ml-1">ms</span>}
                </p>
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">😌</span>
                  <p className="text-sm font-medium text-indigo-100">压力水平</p>
                </div>
                <p className="text-3xl font-bold">
                  {todayRecord.stress_level || '-'}
                </p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* 没有 Garmin 数据时展示手动记录的数据 */}
              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">💧</span>
                  <p className="text-sm font-medium text-indigo-100">今日饮水</p>
                </div>
                <p className="text-3xl font-bold">
                  {waterToday?.data?.total_amount || 0}
                  <span className="text-lg ml-1">ml</span>
                </p>
                <p className="text-xs text-indigo-200 mt-1">目标 {waterToday?.data?.target_amount || 2000}ml</p>
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">🍽️</span>
                  <p className="text-sm font-medium text-indigo-100">今日饮食</p>
                </div>
                <p className="text-3xl font-bold">
                  {Array.isArray(dietToday?.data) ? dietToday.data.length : 0}
                  <span className="text-lg ml-1">餐</span>
                </p>
                <p className="text-xs text-indigo-200 mt-1">
                  {Array.isArray(dietToday?.data) && dietToday.data.length > 0
                    ? `${dietToday.data.reduce((s: number, d: any) => s + (d.calories || 0), 0).toFixed(0)} kcal`
                    : '暂无记录'}
                </p>
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">⚖️</span>
                  <p className="text-sm font-medium text-indigo-100">最近体重</p>
                </div>
                {(() => {
                  const records = weightLatest?.data;
                  const latest = Array.isArray(records) && records.length > 0 ? records[0] : null;
                  return (
                    <>
                      <p className="text-3xl font-bold">
                        {latest?.weight || '-'}
                        {latest?.weight && <span className="text-lg ml-1">kg</span>}
                      </p>
                      <p className="text-xs text-indigo-200 mt-1">{latest?.record_date || '暂无记录'}</p>
                    </>
                  );
                })()}
              </div>

              <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/20 flex flex-col items-center justify-center cursor-pointer hover:bg-white/20 transition"
                onClick={() => router.push('/settings#garmin')}>
                <span className="text-3xl mb-2">⌚</span>
                <p className="text-sm font-medium text-indigo-100">连接智能手表</p>
                <p className="text-xs text-indigo-200 mt-1">解锁更多健康数据</p>
              </div>
            </div>
          )}
        </div>

        {/* 数据健康度状态条 */}
        {dataHealth && (
          <div className="mb-4 flex flex-wrap gap-2 items-center">
            <span className="text-xs text-gray-400 font-medium mr-1">数据状态</span>
            {[
              { key: 'garmin', label: 'Garmin', icon: '⌚' },
              { key: 'hrv', label: 'HRV', icon: '💓' },
              { key: 'diet', label: '饮食', icon: '🍽️' },
              { key: 'water', label: '饮水', icon: '💧' },
              { key: 'notifications', label: '推送', icon: '🔔' },
              { key: 'genetic', label: '基因', icon: '🧬' },
            ].map(({ key, label, icon }) => {
              const item = dataHealth[key];
              if (!item) return null;
              const color = item.status === 'ok'
                ? 'bg-green-50 border-green-200 text-green-700'
                : item.status === 'warning'
                  ? 'bg-yellow-50 border-yellow-200 text-yellow-700'
                  : 'bg-red-50 border-red-200 text-red-700';
              const dot = item.status === 'ok' ? 'bg-green-500' : item.status === 'warning' ? 'bg-yellow-500' : 'bg-red-500';
              return (
                <div key={key} title={item.message} className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium cursor-default ${color}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
                  <span>{icon} {label}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* 快速记录输入栏 */}
        <div className="mb-6 relative">
          <form
            onSubmit={(e) => { e.preventDefault(); handleQuickRecord(); }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={quickInput}
              onChange={(e) => setQuickInput(e.target.value)}
              placeholder="午餐牛肉面 / 血压120/80 / 喝水500 / 体重71.5 / 吃了维生素D"
              className="flex-1 px-4 py-3 rounded-xl border border-gray-200 bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent text-sm text-gray-700 placeholder-gray-400"
              disabled={quickRecordMutation.isPending}
            />
            <button
              type="submit"
              disabled={quickRecordMutation.isPending || !quickInput.trim()}
              className="px-5 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium text-sm shadow-sm transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {quickRecordMutation.isPending ? (
                <span className="animate-spin">...</span>
              ) : (
                <>
                  <span>📝</span>
                  <span>记录</span>
                </>
              )}
            </button>
          </form>
          {quickToast && (
            <div className="absolute top-full left-0 right-0 mt-2 z-10">
              <div className={`inline-block max-w-full px-4 py-2 rounded-lg text-sm font-medium shadow-md ${
                quickToastType === 'error'
                  ? 'bg-red-50 text-red-700 border border-red-200'
                  : quickToastType === 'warning'
                    ? 'bg-amber-50 text-amber-900 border border-amber-300 whitespace-pre-line'
                    : 'bg-green-50 text-green-700 border border-green-200'
              }`}>
                {quickToast}
              </div>
            </div>
          )}
        </div>

        {/* 快捷操作 */}
        <div className="grid grid-cols-4 md:grid-cols-8 gap-3 mb-8">
          {[
            { icon: '💧', label: '喝水', path: '/water' },
            { icon: '🍽️', label: '饮食', path: '/diet' },
            { icon: '⚖️', label: '体重', path: '/weight' },
            { icon: '🩺', label: '血压', path: '/blood-pressure' },
            { icon: '🤖', label: 'AI助理', path: '/ai-assistant' },
            { icon: '📋', label: '体检报告', path: '/family/reports' },
            { icon: '🏃', label: '运动', path: '/workout' },
            { icon: '🧬', label: '基因', path: '/genetic' },
            { icon: '📊', label: '总览', path: '/overview' },
          ].map(item => (
            <button
              key={item.path}
              onClick={() => router.push(item.path)}
              className="flex flex-col items-center gap-1.5 py-3 px-2 bg-white rounded-xl shadow-sm border border-gray-100 hover:shadow-md hover:border-indigo-200 transition"
            >
              <span className="text-2xl">{item.icon}</span>
              <span className="text-xs font-medium text-gray-600">{item.label}</span>
            </button>
          ))}
        </div>

        {/* 关键指标卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white p-6 rounded-xl shadow-lg border-2 border-blue-200 hover:shadow-xl transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-gray-700">平均睡眠分数</p>
              <span className="text-2xl">😴</span>
            </div>
            <p className="text-4xl font-bold text-blue-700 mb-1">
              {comprehensive?.data?.sleep?.average_sleep_score?.toFixed(0) || '-'}
            </p>
            <p className="text-xs font-medium text-gray-600">最近7天</p>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-lg border-2 border-green-200 hover:shadow-xl transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-gray-700">平均步数</p>
              <span className="text-2xl">🚶</span>
            </div>
            <p className="text-4xl font-bold text-green-700 mb-1">
              {comprehensive?.data?.activity?.average_steps_per_day?.toLocaleString() || '-'}
            </p>
            <p className="text-xs font-medium text-gray-600">最近7天</p>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-lg border-2 border-red-200 hover:shadow-xl transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-gray-700">静息心率</p>
              <span className="text-2xl">❤️</span>
            </div>
            <p className="text-4xl font-bold text-red-700 mb-1">
              {comprehensive?.data?.heart_rate?.average_resting_heart_rate?.toFixed(0) || '-'}
            </p>
            <p className="text-xs font-medium text-gray-600">bpm</p>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-lg border-2 border-yellow-200 hover:shadow-xl transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-gray-700">身体电量</p>
              <span className="text-2xl">🔋</span>
            </div>
            {(() => {
              const currentBattery = todayRecord?.body_battery_current;
              const peakBattery = todayRecord?.body_battery_most_charged ?? todayRecord?.body_battery_charged;
              const lowestBattery = todayRecord?.body_battery_lowest;
              const avgBattery = comprehensive?.data?.body_battery?.average_most_charged ?? comprehensive?.data?.body_battery?.average_charged;
              const displayBattery = currentBattery ?? peakBattery ?? avgBattery;
              const hasCurrent = currentBattery !== null && currentBattery !== undefined;
              const hasPeak = peakBattery !== null && peakBattery !== undefined;

              const getBatteryColor = (value: number | null | undefined) => {
                if (value === null || value === undefined) return 'text-gray-400';
                if (value >= 80) return 'text-green-600';
                if (value >= 50) return 'text-yellow-600';
                return 'text-red-500';
              };

              const getBatteryStatus = (value: number | null | undefined) => {
                if (value === null || value === undefined) return '';
                if (value >= 80) return '充足';
                if (value >= 50) return '中等';
                return '偏低';
              };

              return (
                <>
                  <p className={`text-4xl font-bold mb-1 ${getBatteryColor(displayBattery)}`}>
                    {displayBattery?.toFixed ? displayBattery.toFixed(0) : displayBattery ?? '-'}
                  </p>
                  <p className="text-xs font-medium text-gray-600 mb-2">
                    {hasCurrent ? `当前 · ${getBatteryStatus(currentBattery)}` : hasPeak ? '今日峰值' : '最近7天平均'}
                  </p>
                  {(hasCurrent || lowestBattery !== null) && (
                    <div className="text-xs text-gray-500 space-y-0.5 border-t pt-2 mt-1">
                      {hasCurrent && hasPeak && (
                        <p className="flex justify-between">
                          <span>📈 峰值</span>
                          <span className="text-green-600 font-medium">{peakBattery}</span>
                        </p>
                      )}
                      {lowestBattery !== null && lowestBattery !== undefined && (
                        <p className="flex justify-between">
                          <span>📉 最低</span>
                          <span className="font-medium">{lowestBattery}</span>
                        </p>
                      )}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        </div>

        {/* 健康趋势卡片 */}
        {(trendData?.data?.dimensions?.length ?? 0) > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-gray-800">健康趋势</h3>
              <a href="/health-trends" className="text-sm text-blue-500">查看详情 →</a>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {trendData?.data?.dimensions?.map((dim: any) => {
                const icons: Record<string, string> = { weight: '⚖️', sleep: '😴', exercise: '🏃', overall: '💚' };
                const labels: Record<string, string> = { weight: '体重', sleep: '睡眠', exercise: '运动', overall: '综合' };
                const trendIcons: Record<string, string> = { improving: '↑', declining: '↓', stable: '→' };
                const trendColors: Record<string, string> = { improving: 'text-green-600', declining: 'text-red-600', stable: 'text-blue-600' };
                return (
                  <div key={dim.dimension} className="flex items-center gap-2 p-2 rounded-lg bg-gray-50">
                    <span>{icons[dim.dimension] || '📊'}</span>
                    <span className="text-sm text-gray-700">{labels[dim.dimension] || dim.dimension}</span>
                    <span className={`ml-auto font-medium ${trendColors[dim.trend_direction || 'stable']}`}>
                      {trendIcons[dim.trend_direction || 'stable']}
                    </span>
                  </div>
                );
              })}
            </div>
            {trendData?.data?.dimensions?.[0]?.insights?.[0] && (
              <p className="text-xs text-gray-500 mt-2">{trendData?.data?.dimensions?.[0]?.insights?.[0]}</p>
            )}
          </div>
        )}

        {/* 基础健康数据 */}
        {basicHealth?.data && (
          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200 mb-8">
            <h2 className="text-2xl font-bold mb-6 text-gray-900">基础健康指标</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">身高</p>
                <p className="text-2xl font-bold text-gray-900">{basicHealth.data.height} cm</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">体重</p>
                <p className="text-2xl font-bold text-gray-900">{basicHealth.data.weight} kg</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">BMI</p>
                <p className="text-2xl font-bold text-gray-900">{basicHealth.data.bmi?.toFixed(1)}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
                <p className="text-sm font-semibold text-gray-700 mb-2">血压</p>
                <p className="text-2xl font-bold text-gray-900">
                  {basicHealth.data.systolic_bp}/{basicHealth.data.diastolic_bp} <span className="text-lg">mmHg</span>
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 趋势图表 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-6 text-gray-900">睡眠分数趋势</h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="date"
                  stroke="#6b7280"
                  style={{ fontSize: '12px', fontWeight: 500 }}
                />
                <YAxis
                  domain={[0, 100]}
                  stroke="#6b7280"
                  style={{ fontSize: '12px', fontWeight: 500 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'white',
                    border: '2px solid #e5e7eb',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: 500
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                />
                <Line
                  type="monotone"
                  dataKey="sleep"
                  stroke="#6366f1"
                  strokeWidth={3}
                  dot={{ fill: '#6366f1', r: 4 }}
                  name="睡眠分数"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-6 text-gray-900">步数趋势</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="date"
                  stroke="#6b7280"
                  style={{ fontSize: '12px', fontWeight: 500 }}
                />
                <YAxis
                  stroke="#6b7280"
                  style={{ fontSize: '12px', fontWeight: 500 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'white',
                    border: '2px solid #e5e7eb',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: 500
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: '14px', fontWeight: 600 }}
                />
                <Bar
                  dataKey="steps"
                  fill="#10b981"
                  name="步数"
                  radius={[8, 8, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}
