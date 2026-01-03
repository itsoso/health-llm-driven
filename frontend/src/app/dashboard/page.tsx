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
    <main className="min-h-screen p-8 bg-gray-50">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">健康仪表盘</h1>

        {/* 关键指标卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-6 rounded-lg shadow-md">
            <p className="text-sm text-gray-600 mb-1">平均睡眠分数</p>
            <p className="text-3xl font-bold text-blue-600">
              {comprehensive?.data?.sleep?.average_sleep_score?.toFixed(0) || '-'}
            </p>
            <p className="text-xs text-gray-500 mt-1">最近7天</p>
          </div>

          <div className="bg-white p-6 rounded-lg shadow-md">
            <p className="text-sm text-gray-600 mb-1">平均步数</p>
            <p className="text-3xl font-bold text-green-600">
              {comprehensive?.data?.activity?.average_steps_per_day?.toLocaleString() || '-'}
            </p>
            <p className="text-xs text-gray-500 mt-1">最近7天</p>
          </div>

          <div className="bg-white p-6 rounded-lg shadow-md">
            <p className="text-sm text-gray-600 mb-1">静息心率</p>
            <p className="text-3xl font-bold text-red-600">
              {comprehensive?.data?.heart_rate?.average_resting_heart_rate?.toFixed(0) || '-'}
            </p>
            <p className="text-xs text-gray-500 mt-1">bpm</p>
          </div>

          <div className="bg-white p-6 rounded-lg shadow-md">
            <p className="text-sm text-gray-600 mb-1">身体电量</p>
            <p className="text-3xl font-bold text-yellow-600">
              {comprehensive?.data?.body_battery?.average_charged?.toFixed(0) || '-'}
            </p>
            <p className="text-xs text-gray-500 mt-1">/100</p>
          </div>
        </div>

        {/* 基础健康数据 */}
        {basicHealth?.data && (
          <div className="bg-white p-6 rounded-lg shadow-md mb-6">
            <h2 className="text-xl font-semibold mb-4">基础健康指标</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-600">身高</p>
                <p className="text-lg font-semibold">{basicHealth.data.height} cm</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">体重</p>
                <p className="text-lg font-semibold">{basicHealth.data.weight} kg</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">BMI</p>
                <p className="text-lg font-semibold">{basicHealth.data.bmi?.toFixed(1)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">血压</p>
                <p className="text-lg font-semibold">
                  {basicHealth.data.systolic_bp}/{basicHealth.data.diastolic_bp} mmHg
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 趋势图表 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold mb-4">睡眠分数趋势</h2>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="sleep" stroke="#8884d8" name="睡眠分数" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold mb-4">步数趋势</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="steps" fill="#82ca9d" name="步数" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 快速链接 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            href="/garmin"
            className="p-4 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h3 className="font-semibold mb-2">查看详细Garmin数据</h3>
            <p className="text-sm text-gray-600">查看完整的Garmin数据和分析</p>
          </Link>

          <Link
            href="/analysis"
            className="p-4 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h3 className="font-semibold mb-2">健康问题分析</h3>
            <p className="text-sm text-gray-600">AI驱动的健康分析</p>
          </Link>

          <Link
            href="/checkin"
            className="p-4 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h3 className="font-semibold mb-2">每日打卡</h3>
            <p className="text-sm text-gray-600">记录今日健康活动</p>
          </Link>
        </div>
      </div>
    </main>
  );
}

