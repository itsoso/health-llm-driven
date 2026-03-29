'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { dailyHealthApi, garminAnalysisApi, basicHealthApi, dataCollectionApi, healthTrendApi, api } from '@/services/api';
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

function DashboardContent() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.id;
  const [days] = useState(30);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState('');

  // 下拉刷新相关状态
  const [pullStartY, setPullStartY] = useState(0);
  const [pullDistance, setPullDistance] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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
      {(isPulling || pullDistance > 0) && (
        <div 
          className="fixed top-0 left-0 right-0 flex items-center justify-center bg-gradient-to-r from-indigo-600 to-purple-600 text-white z-50"
          style={{
            height: `${pullDistance}px`,
            opacity: Math.min(pullDistance / 60, 1),
          }}
        >
          <div className="flex items-center gap-2">
            {pullDistance > 60 ? (
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

