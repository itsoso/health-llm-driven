'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { healthAnalysisApi } from '@/services/api';

export default function AnalysisPage() {
  const [userId] = useState(1); // 临时使用固定用户ID

  const { data: analysis, isLoading, refetch } = useQuery({
    queryKey: ['health-analysis', userId],
    queryFn: () => healthAnalysisApi.analyzeIssues(userId),
  });

  if (isLoading) {
    return (
      <main className="min-h-screen p-8">
        <div className="max-w-4xl mx-auto">
          <div className="text-center">分析中...</div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">健康问题分析</h1>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
          >
            重新分析
          </button>
        </div>

        {analysis?.error && (
          <div className="mb-6 p-4 bg-yellow-100 rounded-lg text-yellow-800">
            {analysis.error}
          </div>
        )}

        {analysis?.issues && analysis.issues.length > 0 && (
          <div className="mb-6 bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold mb-4">识别的健康问题</h2>
            <ul className="space-y-2">
              {analysis.issues.map((issue: string, index: number) => (
                <li key={index} className="p-3 bg-red-50 rounded-md">
                  {issue}
                </li>
              ))}
            </ul>
          </div>
        )}

        {analysis?.recommendations && analysis.recommendations.length > 0 && (
          <div className="mb-6 bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold mb-4">健康建议</h2>
            <ul className="space-y-2">
              {analysis.recommendations.map((rec: string, index: number) => (
                <li key={index} className="p-3 bg-blue-50 rounded-md">
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        )}

        {analysis?.summary && (
          <div className="bg-white p-6 rounded-lg shadow-md">
            <h2 className="text-xl font-semibold mb-4">详细分析</h2>
            <div className="prose max-w-none whitespace-pre-wrap">
              {analysis.summary}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

