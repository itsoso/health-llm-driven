'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { requireAiConsent } from '@/services/aiConsent';
import { healthAnalysisApi } from '@/services/api/health';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

function AnalysisContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const { data: response, isLoading, refetch, isFetching, isError } = useQuery({
    queryKey: ['health-analysis', userId],
    queryFn: () => healthAnalysisApi.analyzeMyIssues(false, userId),
    enabled: isAuthenticated && !!userId,
  });
  const analysis = response?.data;
  const refresh = useMutation({
    mutationFn: async (subjectId: number) => {
      await requireAiConsent(String(subjectId));
      return healthAnalysisApi.analyzeMyIssues(true, subjectId);
    },
    onSuccess: (result, subjectId) => {
      if (userId === subjectId) queryClient.setQueryData(['health-analysis', subjectId], result);
    },
  });
  const handleRefresh = () => { if (userId) refresh.mutate(userId); };

  if (isLoading) {
    return (
      <main className="min-h-screen p-8 bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-800 text-lg font-medium">正在使用 AI 分析您的健康数据...</p>
            <p className="text-sm text-gray-600 mt-2">这可能需要几秒钟</p>
          </div>
        </div>
      </main>
    );
  }

  if (isError) {
    return <main className="min-h-screen bg-gray-50 p-8">
      <h1 className="text-2xl font-bold mb-4">健康分析</h1>
      <div role="alert" className="rounded-xl bg-red-50 p-5 text-red-800">
        健康分析加载失败，请重试。<button onClick={() => refetch()} className="ml-3 underline">重新加载</button>
      </div>
    </main>;
  }

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-blue-50 via-white to-purple-50">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">健康分析</h1>
        {refresh.isError && <div role="alert" className="mb-4 bg-red-50 text-red-800 p-4 rounded-xl">重新分析失败，当前显示上次结果，请稍后重试。</div>}
        <div className="flex justify-between items-center mb-6">
          <div>
            {analysis?.cached && (
              <span className="text-xs px-3 py-1 bg-green-100 text-green-700 rounded-full font-medium">
                ✓ 缓存数据 ({analysis.analysis_date})
              </span>
            )}
          </div>
          <button
            onClick={handleRefresh}
            disabled={isFetching || refresh.isPending}
            className="px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-md"
          >
            {(isFetching || refresh.isPending) && (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            )}
            重新分析
          </button>
        </div>

        {analysis?.error && (
          <div className="mb-6 p-4 bg-yellow-100 rounded-lg text-yellow-900 border-2 border-yellow-300">
            <strong className="font-bold">提示：</strong> <span className="font-medium">{analysis.error}</span>
          </div>
        )}

        {analysis?.issues && analysis.issues.length > 0 && (
          <div className="mb-6 bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-4 text-red-700">⚠️ 识别的健康问题</h2>
            <ul className="space-y-3">
              {analysis.issues.map((issue: string, index: number) => (
                <li key={index} className="p-4 bg-red-50 rounded-lg border-l-4 border-red-500">
                  <p className="text-gray-900 text-base leading-7 font-medium">{issue}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {analysis?.recommendations && analysis.recommendations.length > 0 && (
          <div className="mb-6 bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-4 text-green-700">💡 健康建议</h2>
            <ul className="space-y-3">
              {analysis.recommendations.map((rec: string, index: number) => (
                <li key={index} className="p-4 bg-green-50 rounded-lg border-l-4 border-green-500">
                  <p className="text-gray-900 text-base leading-7 font-medium">{rec}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {analysis?.summary && (
          <div className="bg-white p-6 rounded-xl shadow-lg border border-gray-200">
            <h2 className="text-2xl font-bold mb-4 text-blue-700">📋 详细分析报告</h2>
            <div className="prose max-w-none whitespace-pre-wrap text-gray-900 leading-8 text-base">
              {analysis.summary}
            </div>
          </div>
        )}

        {!analysis?.issues?.length && !analysis?.recommendations?.length && !analysis?.summary && !analysis?.error && (
          <div className="bg-white p-8 rounded-xl shadow-lg text-center border border-gray-200">
            <div className="text-6xl mb-4">📋</div>
            <h2 className="text-2xl font-bold text-gray-900 mb-3">暂无可用分析</h2>
            <p className="text-gray-800 text-lg leading-7">请确认已有健康记录，或点击重新分析获取结果。</p>
          </div>
        )}
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function AnalysisPage() {
  return (
    <ProtectedRoute>
      <AnalysisContent />
    </ProtectedRoute>
  );
}
