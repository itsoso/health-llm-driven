'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { healthAnalysisApi } from '@/services/api';
import Link from 'next/link';

export default function AnalysisPage() {
  const [userId] = useState(1); // 临时使用固定用户ID

  const { data: response, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['health-analysis', userId],
    queryFn: () => healthAnalysisApi.analyzeIssues(userId),
  });

  // 实际数据在 response.data 中
  const analysis = response?.data;

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

  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-blue-50 via-white to-purple-50">
      <div className="max-w-4xl mx-auto">
        <Link href="/" className="text-blue-700 hover:text-blue-800 hover:underline mb-4 inline-block font-medium">← 返回首页</Link>
        
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-gray-900">🏥 健康问题分析</h1>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-md"
          >
            {isFetching && (
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
            <div className="text-6xl mb-4">🎉</div>
            <h2 className="text-2xl font-bold text-gray-900 mb-3">暂无健康问题</h2>
            <p className="text-gray-800 text-lg leading-7">根据当前数据，未发现明显的健康问题。请继续保持良好的生活习惯！</p>
          </div>
        )}
      </div>
    </main>
  );
}

