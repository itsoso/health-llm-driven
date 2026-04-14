'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, RadarChart, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';
import ProtectedRoute from '@/components/ProtectedRoute';
import { bodyCompositionApi, BodyAnalysisItem } from '@/services/api/health';

type Tab = 'trend' | 'analysis';

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    '正常': 'bg-green-100 text-green-700',
    '充足': 'bg-green-100 text-green-700',
    '偏低': 'bg-yellow-100 text-yellow-700',
    '偏高': 'bg-orange-100 text-orange-700',
    '过高': 'bg-red-100 text-red-700',
    '肥胖': 'bg-red-100 text-red-700',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  );
}

function BodyCompositionContent() {
  const [tab, setTab] = useState<Tab>('trend');
  const [days, setDays] = useState(30);

  const { data: trendData, isLoading: trendLoading } = useQuery({
    queryKey: ['body-composition-trend', days],
    queryFn: async () => {
      const res = await bodyCompositionApi.getTrend(days);
      return res.data;
    },
  });

  const { data: analysisData, isLoading: analysisLoading } = useQuery({
    queryKey: ['body-composition-analysis'],
    queryFn: async () => {
      const res = await bodyCompositionApi.getAnalysis();
      return res.data;
    },
  });

  const isLoading = trendLoading || analysisLoading;

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-cyan-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600 mx-auto mb-4" />
          <p className="text-gray-800 text-lg">加载中...</p>
        </div>
      </main>
    );
  }

  const summary = trendData?.summary;
  const dataPoints = trendData?.data_points || [];

  // 图表数据
  const chartData = dataPoints.map((p) => ({
    date: format(new Date(p.date), 'MM-dd'),
    weight: p.weight,
    bodyFat: p.body_fat_percentage,
    muscleMass: p.muscle_mass_kg,
    waterPct: p.water_percentage,
    bmi: p.bmi,
  }));

  // 雷达图数据（基于最新记录的分析结果）
  const radarData = analysisData?.analysis?.map((a: BodyAnalysisItem) => {
    const scoreMap: Record<string, number> = { '正常': 90, '充足': 95, '偏低': 50, '偏高': 40, '过高': 20, '肥胖': 15 };
    return { metric: a.metric, score: scoreMap[a.status] || 60 };
  }) || [];

  return (
    <main className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-cyan-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">身体成分分析</h1>
            <p className="text-gray-500 mt-1">全面了解你的身体组成变化</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setTab('trend')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === 'trend' ? 'bg-emerald-600 text-white' : 'bg-white text-gray-600 border hover:bg-gray-50'
              }`}
            >
              趋势
            </button>
            <button
              onClick={() => setTab('analysis')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === 'analysis' ? 'bg-emerald-600 text-white' : 'bg-white text-gray-600 border hover:bg-gray-50'
              }`}
            >
              分析
            </button>
          </div>
        </div>

        {/* 摘要卡片 */}
        {summary && summary.current_weight && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">当前体重</p>
              <p className="text-2xl font-bold text-emerald-600">{summary.current_weight} <span className="text-sm">kg</span></p>
              {summary.weight_change !== null && (
                <p className={`text-xs mt-1 ${summary.weight_change > 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {summary.weight_change > 0 ? '+' : ''}{summary.weight_change} kg
                </p>
              )}
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">体脂率</p>
              <p className="text-2xl font-bold text-blue-600">{summary.current_body_fat ?? '—'}<span className="text-sm">%</span></p>
              {summary.body_fat_change !== undefined && (
                <p className={`text-xs mt-1 ${summary.body_fat_change > 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {summary.body_fat_change > 0 ? '+' : ''}{summary.body_fat_change}%
                </p>
              )}
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">肌肉量</p>
              <p className="text-2xl font-bold text-purple-600">{summary.current_muscle_mass ?? '—'} <span className="text-sm">kg</span></p>
              {summary.muscle_mass_change !== undefined && (
                <p className={`text-xs mt-1 ${summary.muscle_mass_change > 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {summary.muscle_mass_change > 0 ? '+' : ''}{summary.muscle_mass_change} kg
                </p>
              )}
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">BMI</p>
              <p className="text-2xl font-bold text-orange-600">{summary.current_bmi ?? '—'}</p>
            </div>
            <div className="bg-white p-4 rounded-xl shadow-sm border">
              <p className="text-sm text-gray-500 mb-1">记录数</p>
              <p className="text-2xl font-bold text-gray-700">{summary.record_count} <span className="text-sm">条</span></p>
            </div>
          </div>
        )}

        {tab === 'trend' && (
          <>
            {/* 时间范围选择 */}
            <div className="flex gap-2 mb-4">
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-3 py-1 rounded text-sm ${
                    days === d ? 'bg-emerald-600 text-white' : 'bg-white border text-gray-600'
                  }`}
                >
                  {d}天
                </button>
              ))}
            </div>

            {chartData.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm border p-12 text-center">
                <p className="text-gray-400 text-lg mb-2">暂无身体成分数据</p>
                <p className="text-gray-400">在体重记录页面添加数据后，这里将显示趋势分析</p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* 体重趋势 */}
                <div className="bg-white rounded-xl shadow-sm border p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">体重趋势</h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                      <YAxis domain={['dataMin - 2', 'dataMax + 2']} stroke="#6b7280" style={{ fontSize: '12px' }} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="weight" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} name="体重(kg)" />
                      {chartData.some(d => d.bmi) && (
                        <Line type="monotone" dataKey="bmi" stroke="#f97316" strokeWidth={2} dot={{ r: 2 }} name="BMI" />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* 身体成分趋势 */}
                {chartData.some(d => d.bodyFat || d.muscleMass) && (
                  <div className="bg-white rounded-xl shadow-sm border p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">身体成分趋势</h3>
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                        <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                        <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
                        <Tooltip />
                        <Legend />
                        {chartData.some(d => d.bodyFat) && (
                          <Line type="monotone" dataKey="bodyFat" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} name="体脂率(%)" />
                        )}
                        {chartData.some(d => d.muscleMass) && (
                          <Line type="monotone" dataKey="muscleMass" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3 }} name="肌肉量(kg)" />
                        )}
                        {chartData.some(d => d.waterPct) && (
                          <Line type="monotone" dataKey="waterPct" stroke="#06b6d4" strokeWidth={2} dot={{ r: 2 }} name="水分率(%)" />
                        )}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {tab === 'analysis' && (
          <div className="space-y-6">
            {analysisData?.status === 'no_data' ? (
              <div className="bg-white rounded-2xl shadow-sm border p-12 text-center">
                <p className="text-gray-400 text-lg mb-2">暂无分析数据</p>
                <p className="text-gray-400">记录体重和身体成分后即可查看健康分析</p>
              </div>
            ) : (
              <>
                {/* 雷达图 */}
                {radarData.length >= 3 && (
                  <div className="bg-white rounded-xl shadow-sm border p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">综合评估</h3>
                    <ResponsiveContainer width="100%" height={300}>
                      <RadarChart data={radarData}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="metric" />
                        <PolarRadiusAxis domain={[0, 100]} tick={false} />
                        <Radar name="评分" dataKey="score" stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* 分析详情 */}
                <div className="bg-white rounded-xl shadow-sm border p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">
                    详细分析
                    {analysisData?.record_date && (
                      <span className="text-sm font-normal text-gray-400 ml-2">
                        数据日期: {analysisData.record_date}
                      </span>
                    )}
                  </h3>
                  <div className="space-y-4">
                    {analysisData?.analysis?.map((item: BodyAnalysisItem, i: number) => (
                      <div key={i} className="flex items-start gap-4 p-4 bg-gray-50 rounded-lg">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-gray-900">{item.metric}</span>
                            <StatusBadge status={item.status} />
                          </div>
                          <p className="text-sm text-gray-500">当前值: {item.value}</p>
                        </div>
                        <p className="text-sm text-gray-600 max-w-xs">{item.advice}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

export default function BodyCompositionPage() {
  return <ProtectedRoute><BodyCompositionContent /></ProtectedRoute>;
}
