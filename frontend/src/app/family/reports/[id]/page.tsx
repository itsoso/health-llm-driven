'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api';

interface ExtractedItem {
  name: string;
  value: string | number;
  unit?: string;
  reference_range?: string;
  is_abnormal?: boolean;
  direction?: string;
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
  ai_suggestions: string | null;
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

  useEffect(() => {
    if (!id) return;
    loadReport();
    // 如果正在处理中，轮询状态
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

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 pt-4 pb-24 px-4">
      <div className="max-w-2xl mx-auto">
        {/* 返回按钮 + 标题 */}
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-600 text-xl">
            &larr;
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {report.title || `${report.report_date} 体检报告`}
            </h1>
            <div className="text-xs text-gray-400 mt-1">
              {report.report_date} {report.hospital && `· ${report.hospital}`}
            </div>
          </div>
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

        {/* AI 建议 */}
        {report.ai_suggestions && (
          <div className="bg-indigo-50 rounded-xl p-5 border border-indigo-100 mb-4">
            <h2 className="font-semibold text-indigo-900 mb-2 flex items-center gap-2">
              <span className="text-lg">💡</span> 健康建议
            </h2>
            <p className="text-sm text-indigo-800 whitespace-pre-line leading-relaxed">{report.ai_suggestions}</p>
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
                <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                  <div>
                    <span className="text-sm font-medium text-gray-900">{item.name}</span>
                    {item.direction && (
                      <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                        item.direction === 'high' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
                      }`}>
                        {item.direction === 'high' ? '↑ 偏高' : '↓ 偏低'}
                      </span>
                    )}
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-semibold text-red-600">{item.value}</span>
                    {item.unit && <span className="text-xs text-gray-400 ml-1">{item.unit}</span>}
                    {item.reference_range && (
                      <div className="text-xs text-gray-400">参考: {item.reference_range}</div>
                    )}
                  </div>
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
