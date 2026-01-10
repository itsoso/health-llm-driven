'use client';

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dailyHealthApi, garminAnalysisApi, basicHealthApi } from '@/services/api';
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
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function DashboardContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [days] = useState(30);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  const endDate = format(new Date(), 'yyyy-MM-dd');
  const startDate = format(subDays(new Date(), days), 'yyyy-MM-dd');
  const today = format(new Date(), 'yyyy-MM-dd');

  // 获取今天的实时数据
  const { data: todayData, refetch: refetchToday } = useQuery({
    queryKey: ['garmin-today', userId, today],
    queryFn: () => dailyHealthApi.getMyGarminData(today, today),
    refetchInterval: 5 * 60 * 1000, // 每5分钟自动刷新
    enabled: !!userId,
  });

  // 获取Garmin数据
  const { data: garminData } = useQuery({
    queryKey: ['garmin-data', userId, startDate, endDate],
    queryFn: () => dailyHealthApi.getMyGarminData(startDate, endDate),
    enabled: !!userId,
  });

  // 获取基础健康数据
  const { data: basicHealth } = useQuery({
    queryKey: ['basic-health', userId],
    queryFn: () => basicHealthApi.getMyLatest(),
    enabled: !!userId,
  });

  // 获取综合分析
  const { data: comprehensive } = useQuery({
    queryKey: ['garmin-comprehensive', userId, 7],
    queryFn: () => garminAnalysisApi.getMyComprehensive(7),
    enabled: !!userId,
  });

  // 监听数据更新
  useEffect(() => {
    if (todayData) {
      setLastUpdate(new Date());
    }
  }, [todayData]);

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
    <main className="min-h-screen p-8 bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24">
      <div className="max-w-7xl mx-auto">
        {/* 今日实时数据 */}
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl shadow-2xl p-6 mb-8 text-white">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-3xl font-bold mb-1">📊 今日实时数据</h2>
              <p className="text-indigo-100 text-sm">
                最后更新: {format(lastUpdate, 'HH:mm:ss')} | 自动刷新中...
              </p>
            </div>
            <button
              onClick={() => {
                refetchToday();
                setLastUpdate(new Date());
              }}
              className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg font-semibold transition-all backdrop-blur-sm border border-white/30"
            >
              🔄 手动刷新
            </button>
          </div>

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
                <p className="text-3xl font-bold">
                  {todayRecord.body_battery_most_charged || todayRecord.body_battery_charged || '-'}
                </p>
                {todayRecord.body_battery_most_charged && (
                  <p className="text-xs text-indigo-200 mt-1">
                    {todayRecord.body_battery_drained ? `消耗: ${todayRecord.body_battery_drained}` : ''}
                    {todayRecord.body_battery_lowest ? ` | 最低: ${todayRecord.body_battery_lowest}` : ''}
                  </p>
                )}
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
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
              <p className="text-indigo-100">正在加载今日数据...</p>
            </div>
          )}
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
            <p className="text-4xl font-bold text-yellow-700 mb-1">
              {todayRecord?.body_battery_most_charged || 
               comprehensive?.data?.body_battery?.average_most_charged?.toFixed(0) || 
               comprehensive?.data?.body_battery?.average_charged?.toFixed(0) || '-'}
            </p>
            <p className="text-xs font-medium text-gray-600">
              {todayRecord?.body_battery_most_charged ? '今日最高' : '最近7天平均'}
            </p>
          </div>
        </div>

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

