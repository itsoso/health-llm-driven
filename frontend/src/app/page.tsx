'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';

export default function Home() {
  const { data: healthStatus } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get('/health'),
  });

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">健康管理系统</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {/* 今日建议 - 放在最显眼的位置 */}
          <Link
            href="/daily-insights"
            className="p-6 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg shadow-md hover:shadow-lg transition-shadow text-white"
          >
            <h2 className="text-xl font-semibold mb-2">💪 今日健康建议</h2>
            <p className="text-indigo-100">基于昨日数据的个性化建议</p>
          </Link>

          <Link
            href="/dashboard"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">健康仪表盘</h2>
            <p className="text-gray-600">查看您的整体健康状况</p>
          </Link>

          <Link
            href="/checkin"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">每日打卡</h2>
            <p className="text-gray-600">记录今日的健康活动</p>
          </Link>

          <Link
            href="/goals"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">目标管理</h2>
            <p className="text-gray-600">设置和追踪健康目标</p>
          </Link>

          <Link
            href="/medical-exams"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">体检记录</h2>
            <p className="text-gray-600">管理体检数据</p>
          </Link>

          <Link
            href="/analysis"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">健康分析</h2>
            <p className="text-gray-600">AI驱动的健康问题分析</p>
          </Link>

          <Link
            href="/data-collection"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">数据收集</h2>
            <p className="text-gray-600">同步Garmin等设备数据</p>
          </Link>

          <Link
            href="/garmin"
            className="p-6 bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">Garmin数据</h2>
            <p className="text-gray-600">查看和分析Garmin健康数据</p>
          </Link>
        </div>

        {healthStatus && (
          <div className="mt-8 p-4 bg-green-100 rounded-lg">
            <p className="text-green-800">
              后端服务状态: {healthStatus.status}
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

