'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
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

export default function DashboardPage() {
  const [userId] = useState(1);
  const [days] = useState(30);

  const endDate = format(new Date(), 'yyyy-MM-dd');
  const startDate = format(subDays(new Date(), days), 'yyyy-MM-dd');

  // 获取Garmin数据
  const { data: garminData } = useQuery({
    queryKey: ['garmin-data', userId, startDate, endDate],
    queryFn: () => dailyHealthApi.getUserGarminData(userId, startDate, endDate),
  });

  // 获取基础健康数据
  const { data: basicHealth } = useQuery({
    queryKey: ['basic-health', userId],
    queryFn: () => basicHealthApi.getLatest(userId),
  });

  // 获取综合分析
  const { data: comprehensive } = useQuery({
    queryKey: ['garmin-comprehensive', userId, 7],
    queryFn: () => garminAnalysisApi.getComprehensive(userId, 7),
  });

  // 准备图表数据
  const chartData = garminData?.data?.slice(-14).map((item: any) => ({
    date: format(new Date(item.record_date), 'MM-dd'),
    sleep: item.sleep_score,
    steps: item.steps,
    heartRate: item.avg_heart_rate,
  })) || [];

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="max-w-7xl mx-auto">
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
              {comprehensive?.data?.body_battery?.average_charged?.toFixed(0) || '-'}
            </p>
            <p className="text-xs font-medium text-gray-600">/100</p>
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

        {/* 快速链接 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Link
            href="/garmin"
            className="group p-6 bg-white rounded-xl shadow-lg border-2 border-blue-200 hover:shadow-xl hover:border-blue-400 transition-all"
          >
            <div className="flex items-center mb-3">
              <span className="text-3xl mr-3">📊</span>
              <h3 className="text-lg font-bold text-gray-900 group-hover:text-blue-700 transition-colors">查看详细Garmin数据</h3>
            </div>
            <p className="text-sm font-medium text-gray-700">查看完整的Garmin数据和分析</p>
          </Link>

          <Link
            href="/analysis"
            className="group p-6 bg-white rounded-xl shadow-lg border-2 border-green-200 hover:shadow-xl hover:border-green-400 transition-all"
          >
            <div className="flex items-center mb-3">
              <span className="text-3xl mr-3">🏥</span>
              <h3 className="text-lg font-bold text-gray-900 group-hover:text-green-700 transition-colors">健康问题分析</h3>
            </div>
            <p className="text-sm font-medium text-gray-700">AI驱动的健康分析</p>
          </Link>

          <Link
            href="/checkin"
            className="group p-6 bg-white rounded-xl shadow-lg border-2 border-purple-200 hover:shadow-xl hover:border-purple-400 transition-all"
          >
            <div className="flex items-center mb-3">
              <span className="text-3xl mr-3">✅</span>
              <h3 className="text-lg font-bold text-gray-900 group-hover:text-purple-700 transition-colors">每日打卡</h3>
            </div>
            <p className="text-sm font-medium text-gray-700">记录今日健康活动</p>
          </Link>
        </div>
      </div>
    </main>
  );
}

