'use client';

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api';

interface ComparisonIndicator {
  name: string;
  unit?: string;
  reference_range?: string;
  values: (string | number | null)[];
  trend: 'worsened' | 'improved' | 'stable' | 'new_abnormal';
  is_abnormal?: boolean[];
}

interface ComparisonReport {
  id: number;
  report_date: string;
  hospital: string | null;
  title: string | null;
}

interface ComparisonData {
  reports: ComparisonReport[];
  indicators: ComparisonIndicator[];
  summary?: {
    improved: number;
    worsened: number;
    stable: number;
    new_abnormal: number;
  };
}

const trendConfig = {
  worsened: { label: '恶化', bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', badge: 'bg-red-100 text-red-600', arrow: '↑' },
  improved: { label: '改善', bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', badge: 'bg-green-100 text-green-600', arrow: '↓' },
  stable: { label: '稳定', bg: 'bg-gray-50', border: 'border-gray-200', text: 'text-gray-600', badge: 'bg-gray-100 text-gray-500', arrow: '→' },
  new_abnormal: { label: '新增异常', bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', badge: 'bg-amber-100 text-amber-600', arrow: '!' },
};

function TrendArrowSvg({ trend }: { trend: string }) {
  if (trend === 'worsened') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" className="inline-block">
        <path d="M8 2 L13 8 L10 8 L10 14 L6 14 L6 8 L3 8 Z" fill="#dc2626" />
      </svg>
    );
  }
  if (trend === 'improved') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" className="inline-block">
        <path d="M8 14 L13 8 L10 8 L10 2 L6 2 L6 8 L3 8 Z" fill="#16a34a" />
      </svg>
    );
  }
  if (trend === 'new_abnormal') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" className="inline-block">
        <circle cx="8" cy="8" r="6" fill="none" stroke="#d97706" strokeWidth="2" />
        <text x="8" y="12" textAnchor="middle" fontSize="10" fill="#d97706" fontWeight="bold">!</text>
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className="inline-block">
      <path d="M2 8 L14 8" stroke="#6b7280" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function ReportComparePage() {
  return <ProtectedRoute><ReportCompareContent /></ProtectedRoute>;
}

function ReportCompareContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const idsParam = searchParams.get('ids');
  const [data, setData] = useState<ComparisonData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!idsParam) {
      setError('缺少报告 ID 参数');
      setLoading(false);
      return;
    }
    const ids = idsParam.split(',').map(Number).filter(n => !isNaN(n) && n > 0);
    if (ids.length < 2) {
      setError('至少需要两份报告才能对比');
      setLoading(false);
      return;
    }
    loadComparison(ids);
  }, [idsParam]);

  const loadComparison = async (ids: number[]) => {
    try {
      const res = await familyApi.compareReports(ids);
      setData(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || '加载对比数据失败');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
        <div className="max-w-2xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto" />
          <p className="mt-4 text-gray-500">加载对比数据...</p>
        </div>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
        <div className="max-w-2xl mx-auto text-center py-20">
          <div className="text-4xl mb-3">📊</div>
          <p className="text-gray-500">{error || '无法加载对比数据'}</p>
          <button onClick={() => router.back()} className="mt-4 text-indigo-600 text-sm">返回</button>
        </div>
      </main>
    );
  }

  const groupedByTrend = {
    worsened: data.indicators.filter(ind => ind.trend === 'worsened'),
    new_abnormal: data.indicators.filter(ind => ind.trend === 'new_abnormal'),
    improved: data.indicators.filter(ind => ind.trend === 'improved'),
    stable: data.indicators.filter(ind => ind.trend === 'stable'),
  };

  const summary = data.summary || {
    improved: groupedByTrend.improved.length,
    worsened: groupedByTrend.worsened.length,
    stable: groupedByTrend.stable.length,
    new_abnormal: groupedByTrend.new_abnormal.length,
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-600 text-xl">
            &larr;
          </button>
          <h1 className="text-xl font-bold text-gray-900">报告对比</h1>
        </div>

        {/* Report metadata */}
        <div className="bg-white rounded-xl p-4 shadow-sm border mb-4">
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${data.reports.length}, 1fr)` }}>
            {data.reports.map((r, i) => (
              <div key={r.id} className={`text-center ${i > 0 ? 'border-l border-gray-100 pl-3' : ''}`}>
                <div className="text-xs text-gray-400 mb-1">报告 {i + 1}</div>
                <div className="text-sm font-semibold text-gray-900">{r.report_date}</div>
                {r.hospital && <div className="text-xs text-gray-500 mt-0.5">{r.hospital}</div>}
                <button
                  onClick={() => router.push(`/family/reports/${r.id}`)}
                  className="text-xs text-indigo-500 hover:text-indigo-700 mt-1"
                >
                  查看详情
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Trend groups */}
        {(Object.keys(groupedByTrend) as Array<keyof typeof groupedByTrend>).map(trendKey => {
          const items = groupedByTrend[trendKey];
          if (items.length === 0) return null;
          const config = trendConfig[trendKey];

          return (
            <div key={trendKey} className={`${config.bg} ${config.border} border rounded-xl p-4 mb-4`}>
              <h2 className={`font-semibold ${config.text} mb-3 flex items-center gap-2`}>
                <TrendArrowSvg trend={trendKey} />
                {config.label}
                <span className={`text-xs px-2 py-0.5 rounded-full ${config.badge}`}>{items.length} 项</span>
              </h2>
              <div className="space-y-2">
                {items.map((ind, i) => (
                  <div key={i} className="bg-white/70 rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">{ind.name}</span>
                        {ind.unit && <span className="text-xs text-gray-400">{ind.unit}</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        {ind.values.map((val, vi) => (
                          <span key={vi} className={`text-sm ${
                            ind.is_abnormal?.[vi] ? 'text-red-600 font-semibold' : 'text-gray-700'
                          }`}>
                            {val ?? '-'}
                            {vi < ind.values.length - 1 && (
                              <span className="text-gray-300 mx-1">
                                <TrendArrowSvg trend={ind.trend} />
                              </span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                    {ind.reference_range && (
                      <div className="text-xs text-gray-400 mt-0.5">参考范围: {ind.reference_range}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {/* Overall summary */}
        <div className="bg-white rounded-xl p-5 shadow-sm border mb-4">
          <h2 className="font-semibold text-gray-900 mb-3">总体变化</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <div className="text-2xl font-bold text-green-600">{summary.improved}</div>
              <div className="text-xs text-green-700 mt-1">改善</div>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg">
              <div className="text-2xl font-bold text-red-600">{summary.worsened}</div>
              <div className="text-xs text-red-700 mt-1">恶化</div>
            </div>
            <div className="text-center p-3 bg-amber-50 rounded-lg">
              <div className="text-2xl font-bold text-amber-600">{summary.new_abnormal}</div>
              <div className="text-xs text-amber-700 mt-1">新增异常</div>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <div className="text-2xl font-bold text-gray-600">{summary.stable}</div>
              <div className="text-xs text-gray-600 mt-1">稳定</div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
