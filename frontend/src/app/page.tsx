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
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {/* 今日建议 - 放在最显眼的位置 */}
          <Link
            href="/daily-insights"
            className="p-6 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2">💪 今日健康建议</h2>
            <p className="text-indigo-100 text-sm">基于昨日数据的个性化建议</p>
          </Link>

          <Link
            href="/dashboard"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">📊 健康仪表盘</h2>
            <p className="text-gray-600 text-sm">查看您的整体健康状况</p>
          </Link>

          <Link
            href="/checkin"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">✅ 每日打卡</h2>
            <p className="text-gray-600 text-sm">记录今日的健康活动</p>
          </Link>

          <Link
            href="/goals"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">🎯 目标管理</h2>
            <p className="text-gray-600 text-sm">设置和追踪健康目标</p>
          </Link>

          <Link
            href="/medical-exams"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">🏥 体检记录</h2>
            <p className="text-gray-600 text-sm">管理体检数据</p>
          </Link>

          <Link
            href="/analysis"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">🔍 健康分析</h2>
            <p className="text-gray-600 text-sm">AI驱动的健康问题分析</p>
          </Link>

          <Link
            href="/data-collection"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">📥 数据收集</h2>
            <p className="text-gray-600 text-sm">同步Garmin等设备数据</p>
          </Link>

          <Link
            href="/garmin"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">⌚ Garmin数据</h2>
            <p className="text-gray-600 text-sm">查看和分析Garmin健康数据</p>
          </Link>
        </div>

        {healthStatus && (
          <div className="mt-8 p-4 bg-green-50 rounded-xl border border-green-200 shadow-sm">
            <p className="text-green-700 font-medium">
              ✅ 后端服务状态: {healthStatus.status}
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

