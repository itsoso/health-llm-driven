'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { healthTrendApi } from '@/services/api/health';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const DIMENSION_LABELS: Record<string, string> = {
  weight: '体重/体脂',
  sleep: '睡眠质量',
  exercise: '运动表现',
  overall: '综合健康',
};

const DIMENSION_ICONS: Record<string, string> = {
  weight: '⚖️',
  sleep: '😴',
  exercise: '🏃',
  overall: '💚',
};

const TREND_ICONS: Record<string, string> = {
  improving: '📈',
  declining: '📉',
  stable: '➡️',
};

const TREND_LABELS: Record<string, string> = {
  improving: '改善中',
  declining: '下降中',
  stable: '平稳',
};

const TREND_COLORS: Record<string, string> = {
  improving: 'text-green-600 bg-green-50',
  declining: 'text-red-600 bg-red-50',
  stable: 'text-blue-600 bg-blue-50',
};

function HealthTrendsContent() {
  const { user } = useAuth();
  const [selectedDim, setSelectedDim] = useState<string | null>(null);
  const [period, setPeriod] = useState('7d');

  const { data: latestData, isLoading } = useQuery({
    queryKey: ['health-trends-latest', user?.id],
    queryFn: () => healthTrendApi.getLatest(),
    enabled: !!user?.id,
  });

  const { data: detailData, isLoading: isDetailLoading } = useQuery({
    queryKey: ['health-trends-detail', user?.id, selectedDim, period],
    queryFn: () => healthTrendApi.getDimension(selectedDim!, period),
    enabled: !!user?.id && !!selectedDim,
  });

  const latest = latestData?.data;
  const detail = detailData?.data;

  return (
    <div className="min-h-screen bg-gray-50 p-4 pb-20">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">健康趋势</h1>

      {isLoading ? (
        <div className="text-center text-gray-500 py-12">加载中...</div>
      ) : !latest?.dimensions?.length ? (
        <div className="text-center text-gray-500 py-12">
          <p className="text-lg mb-2">暂无趋势数据</p>
          <p className="text-sm">系统每晚自动分析，请保持数据记录</p>
        </div>
      ) : (
        <>
          {/* 趋势概览卡片 */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            {latest.dimensions.map((dim) => (
              <button
                key={dim.dimension}
                onClick={() => setSelectedDim(dim.dimension === selectedDim ? null : dim.dimension)}
                className={`p-4 rounded-xl text-left transition-all ${
                  selectedDim === dim.dimension
                    ? 'ring-2 ring-blue-500 bg-white shadow-lg'
                    : 'bg-white shadow-sm hover:shadow-md'
                }`}
              >
                <div className="text-2xl mb-1">
                  {DIMENSION_ICONS[dim.dimension] || '📊'}
                </div>
                <div className="text-sm font-medium text-gray-700">
                  {DIMENSION_LABELS[dim.dimension] || dim.dimension}
                </div>
                <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs mt-2 ${
                  TREND_COLORS[dim.trend_direction || 'stable']
                }`}>
                  {TREND_ICONS[dim.trend_direction || 'stable']}{' '}
                  {TREND_LABELS[dim.trend_direction || 'stable']}
                </div>
                {dim.insights?.[0] && (
                  <p className="text-xs text-gray-500 mt-2 line-clamp-2">
                    {dim.insights[0]}
                  </p>
                )}
              </button>
            ))}
          </div>

          {/* 详细报告区 */}
          {selectedDim && (
            <div className="bg-white rounded-xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">
                  {DIMENSION_ICONS[selectedDim]} {DIMENSION_LABELS[selectedDim]} 详细报告
                </h2>
                <div className="flex gap-1">
                  {['7d', '14d', '30d'].map((p) => (
                    <button
                      key={p}
                      onClick={() => setPeriod(p)}
                      className={`px-3 py-1 rounded-full text-xs ${
                        period === p
                          ? 'bg-blue-500 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {p.replace('d', '天')}
                    </button>
                  ))}
                </div>
              </div>

              {isDetailLoading ? (
                <div className="text-center text-gray-400 py-8">分析加载中...</div>
              ) : detail?.full_report ? (
                <div className="space-y-4">
                  {/* 洞察 */}
                  {detail.insights?.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 mb-2">关键洞察</h3>
                      <ul className="space-y-1">
                        {detail.insights.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                            <span className="text-blue-500 mt-0.5">•</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* 建议 */}
                  {detail.suggestions?.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 mb-2">行动建议</h3>
                      <ul className="space-y-1">
                        {detail.suggestions.map((item: string, i: number) => (
                          <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                            <span className="text-green-500 mt-0.5">✓</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* 风险 */}
                  {detail.risk_alerts?.length > 0 && (
                    <div className="bg-red-50 rounded-lg p-3">
                      <h3 className="text-sm font-medium text-red-700 mb-1">风险提醒</h3>
                      {detail.risk_alerts.map((item: string, i: number) => (
                        <p key={i} className="text-sm text-red-600">{item}</p>
                      ))}
                    </div>
                  )}

                  <p className="text-xs text-gray-400 pt-2">
                    报告日期: {detail.report_date}
                  </p>
                </div>
              ) : (
                <div className="text-center text-gray-400 py-8">暂无该周期的报告</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function HealthTrendsPage() {
  return (
    <ProtectedRoute>
      <HealthTrendsContent />
    </ProtectedRoute>
  );
}
