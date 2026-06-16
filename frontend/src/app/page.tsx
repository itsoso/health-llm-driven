'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api/client';

export default function Home() {
  const { data: healthStatus } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get('/health'),
  });

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {/* 主入口: Web 端深度阅读, 日常对话用 mobile "会诊" */}
          <Link
            href="/dashboard"
            className="p-6 bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105 md:col-span-2 lg:col-span-1"
          >
            <h2 className="text-xl font-bold mb-2">✨ 健康仪表盘</h2>
            <p className="text-purple-100 text-sm">数据全景, 多维分析, 趋势洞察</p>
          </Link>

          {/* 数字孪生 - 个性化健康模型 */}
          <Link
            href="/digital-twin"
            className="p-6 bg-gradient-to-r from-cyan-600 to-blue-600 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2">🧬 数字孪生</h2>
            <p className="text-cyan-100 text-sm">个性化健康模型、生理指标、趋势分析</p>
          </Link>

          {/* 今日建议 */}
          <Link
            href="/agenda"
            className="p-6 bg-gradient-to-r from-slate-700 to-sky-700 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2">今日议程</h2>
            <p className="text-sky-100 text-sm">训练灯 / 复查 / 协议待办</p>
          </Link>

          <Link
            href="/daily-insights"
            className="p-6 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2">💪 今日健康建议</h2>
            <p className="text-indigo-100 text-sm">基于昨日数据的个性化建议</p>
          </Link>

          <Link
            href="/supplements"
            className="p-6 bg-gradient-to-r from-green-500 to-teal-600 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2">💊 补剂管理</h2>
            <p className="text-green-100 text-sm">管理和追踪每日补剂摄入</p>
          </Link>

          <Link
            href="/dashboard"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">📈 健康仪表盘</h2>
            <p className="text-gray-600 text-sm">查看您的整体健康状况</p>
          </Link>

          <Link
            href="/checkin"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">🏃 运动打卡</h2>
            <p className="text-gray-600 text-sm">记录今日的运动活动</p>
          </Link>

          <Link
            href="/goals"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">🎯 目标管理</h2>
            <p className="text-gray-600 text-sm">设置和追踪健康目标</p>
          </Link>

          <Link
            href="/health-trends"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">📈 健康趋势</h2>
            <p className="text-gray-600 text-sm">长期指标变化与预测</p>
          </Link>

          <Link
            href="/analysis"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">🔍 健康分析</h2>
            <p className="text-gray-600 text-sm">AI驱动的健康问题分析</p>
          </Link>

          <Link
            href="/profile"
            className="p-6 bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-300 border border-gray-100 hover:border-indigo-200 transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2 text-gray-800">👤 个人画像</h2>
            <p className="text-gray-600 text-sm">设置健康目标和个人信息</p>
          </Link>

          <Link
            href="/smart-plan"
            className="p-6 bg-gradient-to-r from-blue-500 to-cyan-600 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 text-white transform hover:scale-105"
          >
            <h2 className="text-xl font-bold mb-2">📅 智能周计划</h2>
            <p className="text-blue-100 text-sm">本周训练 / 营养 / 复查节奏</p>
          </Link>
        </div>

      </div>
    </main>
  );
}
