'use client';
import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api/family';

interface ExtractedItem {
  name: string;
  value: string | number;
  unit?: string;
  reference_range?: string;
  is_abnormal?: boolean;
  direction?: string;
}

interface AiSuggestion {
  indicator: string;
  status: string;
  risk: string;
  action: string;
  timeline: string;
  specialist: string;
}

interface TrendPoint {
  date: string;
  value: number;
}

interface ReportDetail {
  id: number;
  report_date: string;
  hospital: string | null;
  title: string | null;
  status: string;
  extracted_items: ExtractedItem[];
  abnormal_items: ExtractedItem[];
  ai_summary: string | null;
  ai_suggestions: string | AiSuggestion[] | null;
}

function MiniTrendChart({ data }: { data: TrendPoint[] }) {
  if (!data || data.length < 2) {
    return <p className="text-xs text-gray-400 py-2">数据不足，无法显示趋势</p>;
  }

  const values = data.map(d => d.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;

  const width = 200;
  const height = 60;
  const padding = 4;
  const chartW = width - padding * 2;
  const chartH = height - padding * 2;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1)) * chartW;
    const y = padding + chartH - ((d.value - minVal) / range) * chartH;
    return { x, y, ...d };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');

  return (
    <div className="mt-2 bg-gray-50 rounded-lg p-2">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="w-full max-w-[200px]">
        <path d={linePath} fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="#6366f1" />
        ))}
      </svg>
      <div className="flex justify-between text-[10px] text-gray-400 mt-1 max-w-[200px]">
        <span>{data[0].date}</span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  );
}

function SuggestionCard({ suggestion }: { suggestion: AiSuggestion }) {
  const statusConfig: Record<string, { bg: string; border: string; text: string; dot: string; label: string }> = {
    urgent: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-800', dot: 'bg-red-500', label: '紧急' },
    monitor: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-800', dot: 'bg-amber-500', label: '需关注' },
    improving: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-800', dot: 'bg-green-500', label: '改善中' },
  };
  const config = statusConfig[suggestion.status] || statusConfig.monitor;

  return (
    <div className={`${config.bg} ${config.border} border rounded-xl p-4`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full ${config.dot}`} />
        <span className={`font-semibold text-sm ${config.text}`}>{suggestion.indicator}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${config.bg} ${config.text} border ${config.border}`}>{config.label}</span>
      </div>
      {suggestion.risk && (
        <p className={`text-xs ${config.text} mb-1`}>
          <span className="font-medium">风险：</span>{suggestion.risk}
        </p>
      )}
      {suggestion.action && (
        <p className="text-xs text-gray-700 mb-1">
          <span className="font-medium">建议：</span>{suggestion.action}
        </p>
      )}
      <div className="flex flex-wrap gap-3 mt-2">
        {suggestion.timeline && (
          <span className="text-[11px] text-gray-500">
            <span className="font-medium">时间线：</span>{suggestion.timeline}
          </span>
        )}
        {suggestion.specialist && (
          <span className="text-[11px] text-gray-500">
            <span className="font-medium">推荐科室：</span>{suggestion.specialist}
          </span>
        )}
      </div>
    </div>
  );
}

export default function ReportDetailPage() {
  return <ProtectedRoute><ReportDetailContent /></ProtectedRoute>;
}

function ReportDetailContent() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedTrends, setExpandedTrends] = useState<Record<string, boolean>>({});
  const [trendData, setTrendData] = useState<Record<string, TrendPoint[]>>({});
  const [trendLoading, setTrendLoading] = useState<Record<string, boolean>>({});
  const [hasMultipleReports, setHasMultipleReports] = useState(false);
  const [latestReportIds, setLatestReportIds] = useState<number[]>([]);

  useEffect(() => {
    if (!id) return;
    loadReport();
    loadReportsList();
    const timer = setInterval(() => {
      if (report?.status === 'processing') loadReport();
    }, 5000);
    return () => clearInterval(timer);
  }, [id, report?.status]);

  const loadReport = async () => {
    try {
      const res = await familyApi.getReportDetail(id);
      setReport(res.data);
    } catch (e: any) {
      setError(e.response?.status === 404 ? '报告不存在' : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const loadReportsList = async () => {
    try {
      const res = await familyApi.getReports(10);
      const reports = res.data || [];
      if (reports.length >= 2) {
        setHasMultipleReports(true);
        // Get the current report and the one before it
        const ids = reports.map((r: any) => r.id);
        const currentIdx = ids.indexOf(id);
        if (currentIdx >= 0 && ids.length >= 2) {
          const compareIds = currentIdx === 0 && ids.length > 1
            ? [ids[0], ids[1]]
            : [ids[currentIdx], ids[currentIdx > 0 ? currentIdx - 1 : currentIdx + 1]];
          setLatestReportIds(compareIds);
        } else {
          setLatestReportIds([ids[0], ids[1]]);
        }
      }
    } catch {
      // Silently fail — comparison is optional
    }
  };

  const toggleTrend = async (name: string) => {
    const isExpanded = expandedTrends[name];
    setExpandedTrends(prev => ({ ...prev, [name]: !isExpanded }));
    if (!isExpanded && !trendData[name]) {
      setTrendLoading(prev => ({ ...prev, [name]: true }));
      try {
        const res = await familyApi.getIndicatorTrend(name);
        const points: TrendPoint[] = (res.data?.data_points || res.data || []).map((p: any) => ({
          date: p.date || p.report_date,
          value: typeof p.value === 'number' ? p.value : parseFloat(p.value),
        })).filter((p: TrendPoint) => !isNaN(p.value));
        setTrendData(prev => ({ ...prev, [name]: points }));
      } catch {
        setTrendData(prev => ({ ...prev, [name]: [] }));
      } finally {
        setTrendLoading(prev => ({ ...prev, [name]: false }));
      }
    }
  };

  const parseSuggestions = (): AiSuggestion[] | null => {
    if (!report?.ai_suggestions) return null;
    if (Array.isArray(report.ai_suggestions)) return report.ai_suggestions;
    if (typeof report.ai_suggestions === 'string') {
      try {
        const parsed = JSON.parse(report.ai_suggestions);
        if (Array.isArray(parsed)) return parsed;
      } catch {
        return null;
      }
    }
    return null;
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
        <div className="max-w-2xl mx-auto text-center py-20">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mx-auto" />
          <p className="mt-4 text-gray-500">加载中...</p>
        </div>
      </main>
    );
  }

  if (error || !report) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
        <div className="max-w-2xl mx-auto text-center py-20">
          <div className="text-4xl mb-3">📋</div>
          <p className="text-gray-500">{error || '报告不存在'}</p>
          <button onClick={() => router.back()} className="mt-4 text-indigo-600 text-sm">返回</button>
        </div>
      </main>
    );
  }

  const abnormalCount = report.abnormal_items?.length || 0;
  const suggestions = parseSuggestions();

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
      <div className="max-w-2xl mx-auto">
        {/* 返回按钮 + 标题 */}
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-600 text-xl">
            &larr;
          </button>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-gray-900">
              {report.title || `${report.report_date} 体检报告`}
            </h1>
            <div className="text-xs text-gray-400 mt-1">
              {report.report_date} {report.hospital && `· ${report.hospital}`}
            </div>
          </div>
          {hasMultipleReports && latestReportIds.length === 2 && (
            <button
              onClick={() => router.push(`/family/reports/compare?ids=${latestReportIds.join(',')}`)}
              className="text-xs bg-indigo-100 text-indigo-700 px-3 py-1.5 rounded-lg hover:bg-indigo-200 transition-colors whitespace-nowrap"
            >
              与上次对比
            </button>
          )}
        </div>

        {/* 处理中状态 */}
        {report.status === 'processing' && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-4 flex items-center gap-3">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-amber-500" />
            <span className="text-amber-700 text-sm">AI 正在提取报告内容，请稍候...</span>
          </div>
        )}

        {/* AI 总结 */}
        {report.ai_summary && (
          <div className="bg-white rounded-xl p-5 shadow-sm border mb-4">
            <h2 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
              <span className="text-lg">🤖</span> AI 分析总结
            </h2>
            <p className="text-sm text-gray-700 whitespace-pre-line leading-relaxed">{report.ai_summary}</p>
          </div>
        )}

        {/* AI 建议卡片（结构化） */}
        {suggestions && suggestions.length > 0 && (
          <div className="mb-4">
            <h2 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <span className="text-lg">💡</span> 健康建议
            </h2>
            <div className="space-y-3">
              {suggestions.map((s, i) => (
                <SuggestionCard key={i} suggestion={s} />
              ))}
            </div>
          </div>
        )}

        {/* AI 建议（纯文本 fallback） */}
        {report.ai_suggestions && !suggestions && (
          <div className="bg-indigo-50 rounded-xl p-5 border border-indigo-100 mb-4">
            <h2 className="font-semibold text-indigo-900 mb-2 flex items-center gap-2">
              <span className="text-lg">💡</span> 健康建议
            </h2>
            <p className="text-sm text-indigo-800 whitespace-pre-line leading-relaxed">
              {typeof report.ai_suggestions === 'string' ? report.ai_suggestions : JSON.stringify(report.ai_suggestions)}
            </p>
          </div>
        )}

        {/* 异常指标 */}
        {abnormalCount > 0 && (
          <div className="bg-white rounded-xl p-5 shadow-sm border mb-4">
            <h2 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <span className="text-lg">⚠️</span> 异常指标
              <span className="text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full">{abnormalCount} 项</span>
            </h2>
            <div className="space-y-2">
              {report.abnormal_items.map((item, i) => (
                <div key={i}>
                  <div className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-900">{item.name}</span>
                      {item.direction && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          item.direction === 'high' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
                        }`}>
                          {item.direction === 'high' ? '↑ 偏高' : '↓ 偏低'}
                        </span>
                      )}
                      <button
                        onClick={() => toggleTrend(item.name)}
                        className="text-xs text-indigo-500 hover:text-indigo-700 transition-colors"
                      >
                        {expandedTrends[item.name] ? '收起趋势' : '查看趋势'}
                      </button>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-semibold text-red-600">{item.value}</span>
                      {item.unit && <span className="text-xs text-gray-400 ml-1">{item.unit}</span>}
                      {item.reference_range && (
                        <div className="text-xs text-gray-400">参考: {item.reference_range}</div>
                      )}
                    </div>
                  </div>
                  {expandedTrends[item.name] && (
                    <div className="pl-2 pb-2">
                      {trendLoading[item.name] ? (
                        <div className="flex items-center gap-2 py-2">
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-500" />
                          <span className="text-xs text-gray-400">加载趋势数据...</span>
                        </div>
                      ) : (
                        <MiniTrendChart data={trendData[item.name] || []} />
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 全部指标 */}
        {report.extracted_items?.length > 0 && (
          <div className="bg-white rounded-xl p-5 shadow-sm border mb-4">
            <h2 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <span className="text-lg">📊</span> 全部指标
              <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{report.extracted_items.length} 项</span>
            </h2>
            <div className="space-y-1">
              {report.extracted_items.map((item, i) => (
                <div key={i} className={`flex items-center justify-between py-2 border-b border-gray-50 last:border-0 ${
                  item.is_abnormal ? 'bg-red-50 -mx-2 px-2 rounded' : ''
                }`}>
                  <span className={`text-sm ${item.is_abnormal ? 'text-red-700 font-medium' : 'text-gray-700'}`}>
                    {item.name}
                  </span>
                  <div className="text-right">
                    <span className={`text-sm ${item.is_abnormal ? 'text-red-600 font-semibold' : 'text-gray-900'}`}>
                      {item.value}
                    </span>
                    {item.unit && <span className="text-xs text-gray-400 ml-1">{item.unit}</span>}
                    {item.reference_range && (
                      <span className="text-xs text-gray-400 ml-2">({item.reference_range})</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
