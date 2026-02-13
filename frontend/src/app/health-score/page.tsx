'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import ProtectedRoute from '@/components/ProtectedRoute';
import { healthScoreApi, HealthScoreDimension } from '@/services/api';

function ScoreGauge({ score, grade, size = 160 }: { score: number; grade?: string; size?: number }) {
  const r = (size - 12) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#eab308' : score >= 40 ? '#f97316' : '#ef4444';

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={10} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={10}
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-bold" style={{ color }}>{score}</span>
        {grade && <span className="text-sm text-gray-500 mt-1">{grade}</span>}
      </div>
    </div>
  );
}

function DimensionBar({ dim }: { dim: HealthScoreDimension }) {
  const color = dim.score >= 80 ? '#22c55e' : dim.score >= 60 ? '#eab308' : dim.score >= 40 ? '#f97316' : '#ef4444';

  return (
    <div className="py-3 border-b border-gray-100 last:border-0">
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm font-medium text-gray-700">{dim.name}</span>
        <span className="text-sm font-bold" style={{ color }}>{dim.score}</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2 mb-1">
        <div className="h-2 rounded-full transition-all" style={{ width: `${dim.score}%`, backgroundColor: color }} />
      </div>
      <p className="text-xs text-gray-500">{dim.description}</p>
    </div>
  );
}

function HealthScoreContent() {
  const [trendDays, setTrendDays] = useState(7);

  const { data: scoreData, isLoading: scoreLoading } = useQuery({
    queryKey: ['health-score-daily'],
    queryFn: async () => {
      const res = await healthScoreApi.getDailyScore();
      return res.data;
    },
  });

  const { data: trendData, isLoading: trendLoading } = useQuery({
    queryKey: ['health-score-trend', trendDays],
    queryFn: async () => {
      const res = await healthScoreApi.getScoreTrend(trendDays);
      return res.data;
    },
  });

  const isLoading = scoreLoading || trendLoading;

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-amber-50 pt-4 pb-8 px-8">
        <div className="max-w-6xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-violet-600 mx-auto mb-4" />
          <p className="text-gray-800 text-lg">计算评分中...</p>
        </div>
      </main>
    );
  }

  const radarData = scoreData?.dimensions?.map((d: HealthScoreDimension) => ({
    name: d.name,
    score: d.score,
    fullMark: 100,
  })) || [];

  const trendChartData = trendData?.scores?.map((s) => ({
    date: s.date.slice(5), // MM-DD
    score: s.score,
  })) || [];

  return (
    <main className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-amber-50 pt-4 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">健康评分</h1>
          <p className="text-gray-500 mt-1">多维度综合评估你的健康状态</p>
        </div>

        {scoreData?.status === 'no_data' ? (
          <div className="bg-white rounded-2xl shadow-sm border p-12 text-center">
            <p className="text-gray-400 text-lg mb-2">暂无健康数据</p>
            <p className="text-gray-400">记录运动、睡眠、饮食等数据后即可查看健康评分</p>
          </div>
        ) : (
          <>
            {/* 总分 + 雷达图 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div className="bg-white rounded-2xl shadow-sm border p-6 flex flex-col items-center">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">今日评分</h3>
                <ScoreGauge score={scoreData?.total_score || 0} grade={scoreData?.grade} />
                <p className="text-sm text-gray-500 mt-3">{scoreData?.date}</p>
              </div>

              {radarData.length >= 3 && (
                <div className="bg-white rounded-2xl shadow-sm border p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">维度雷达</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <RadarChart data={radarData}>
                      <PolarGrid />
                      <PolarAngleAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <PolarRadiusAxis domain={[0, 100]} tick={false} />
                      <Radar name="评分" dataKey="score" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* 各维度得分 */}
            <div className="bg-white rounded-2xl shadow-sm border p-6 mb-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">各维度评分</h3>
              {scoreData?.dimensions?.map((d: HealthScoreDimension, i: number) => (
                <DimensionBar key={i} dim={d} />
              ))}
            </div>

            {/* 建议 */}
            {scoreData?.suggestions && scoreData.suggestions.length > 0 && (
              <div className="bg-white rounded-2xl shadow-sm border p-6 mb-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">改善建议</h3>
                <ul className="space-y-3">
                  {scoreData.suggestions.map((s: string, i: number) => (
                    <li key={i} className="flex gap-3">
                      <span className="text-violet-500 mt-0.5 flex-shrink-0">&#x2022;</span>
                      <span className="text-gray-700 text-sm leading-relaxed">{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 趋势 */}
            <div className="bg-white rounded-2xl shadow-sm border p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-gray-900">评分趋势</h3>
                <div className="flex gap-2">
                  {[7, 14, 30].map((d) => (
                    <button
                      key={d}
                      onClick={() => setTrendDays(d)}
                      className={`px-3 py-1 rounded text-sm ${
                        trendDays === d ? 'bg-violet-600 text-white' : 'bg-white border text-gray-600'
                      }`}
                    >
                      {d}天
                    </button>
                  ))}
                </div>
              </div>

              {trendChartData.length === 0 ? (
                <p className="text-gray-400 text-center py-8">暂无趋势数据</p>
              ) : (
                <>
                  <div className="flex gap-6 mb-4 text-sm">
                    {trendData?.avg_score && (
                      <span className="text-gray-600">平均: <strong className="text-violet-600">{trendData.avg_score}</strong></span>
                    )}
                    {trendData?.trend && (
                      <span className="text-gray-600">
                        趋势: <strong className={trendData.trend === 'up' ? 'text-green-600' : trendData.trend === 'down' ? 'text-red-600' : 'text-gray-600'}>
                          {trendData.trend === 'up' ? '上升' : trendData.trend === 'down' ? '下降' : '稳定'}
                        </strong>
                      </span>
                    )}
                  </div>
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={trendChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                      <YAxis domain={[0, 100]} stroke="#6b7280" style={{ fontSize: '12px' }} />
                      <Tooltip />
                      <Area type="monotone" dataKey="score" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.2} strokeWidth={2} name="评分" />
                    </AreaChart>
                  </ResponsiveContainer>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

export default function HealthScorePage() {
  return <ProtectedRoute><HealthScoreContent /></ProtectedRoute>;
}
