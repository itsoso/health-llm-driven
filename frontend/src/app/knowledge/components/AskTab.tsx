'use client';

import { UseMutationResult } from '@tanstack/react-query';

interface RAGResponse {
  success: boolean;
  answer?: string;
  key_points?: string[];
  action_items?: string[];
  knowledge_used?: boolean;
  confidence?: string;
  disclaimer?: string;
  sources?: Array<{
    title: string;
    category: string;
    relevance: number;
  }>;
  error?: string;
}

interface AskTabProps {
  askQuestion: string;
  setAskQuestion: (v: string) => void;
  askResponse: RAGResponse | null;
  askMutation: UseMutationResult<any, any, void, unknown>;
}

export function AskTab({ askQuestion, setAskQuestion, askResponse, askMutation }: AskTabProps) {
  return (
    <div className="bg-white rounded-2xl shadow-lg p-6">
      <h2 className="text-xl font-bold text-gray-800 mb-4">💬 RAG 问答</h2>
      <p className="text-gray-600 mb-4">基于知识库和您的个人画像，获取专业健康建议</p>

      <div className="flex gap-3 mb-6">
        <input
          type="text"
          value={askQuestion}
          onChange={(e) => setAskQuestion(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && askMutation.mutate()}
          placeholder="输入您的健康问题，如：我最近睡眠不好怎么办？"
          className="flex-1 px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
        <button
          onClick={() => askMutation.mutate()}
          disabled={!askQuestion.trim() || askMutation.isPending}
          className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg font-medium hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 transition-all"
        >
          {askMutation.isPending ? '思考中...' : '提问'}
        </button>
      </div>

      {askMutation.isPending && (
        <div className="text-center py-8">
          <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto mb-2"></div>
          <p className="text-indigo-600">AI 正在结合知识库生成回答...</p>
        </div>
      )}

      {askResponse && (
        <div className="space-y-4">
          {askResponse.success ? (
            <>
              {/* 主要回答 */}
              <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl p-5">
                <div className="flex items-start gap-3">
                  <span className="text-2xl">✨</span>
                  <div className="flex-1">
                    <p className="text-gray-800 whitespace-pre-wrap">{askResponse.answer}</p>
                  </div>
                </div>
              </div>

              {/* 要点 */}
              {askResponse.key_points && askResponse.key_points.length > 0 && (
                <div className="bg-blue-50 rounded-xl p-4">
                  <h3 className="font-medium text-blue-800 mb-2">📌 关键要点</h3>
                  <ul className="space-y-1">
                    {askResponse.key_points.map((point, i) => (
                      <li key={i} className="text-blue-700 text-sm flex items-start gap-2">
                        <span className="text-blue-400">•</span>
                        {point}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 行动建议 */}
              {askResponse.action_items && askResponse.action_items.length > 0 && (
                <div className="bg-green-50 rounded-xl p-4">
                  <h3 className="font-medium text-green-800 mb-2">✅ 行动建议</h3>
                  <ul className="space-y-1">
                    {askResponse.action_items.map((item, i) => (
                      <li key={i} className="text-green-700 text-sm flex items-start gap-2">
                        <span className="text-green-400">{i + 1}.</span>
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 来源和元信息 */}
              <div className="flex flex-wrap items-center gap-3 text-sm">
                {askResponse.knowledge_used && (
                  <span className="px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                    ✓ 使用了知识库
                  </span>
                )}
                {askResponse.confidence && (
                  <span className={`px-2 py-1 rounded-full ${
                    askResponse.confidence === 'high'
                      ? 'bg-green-100 text-green-700'
                      : askResponse.confidence === 'medium'
                      ? 'bg-yellow-100 text-yellow-700'
                      : 'bg-gray-100 text-gray-700'
                  }`}>
                    置信度: {askResponse.confidence === 'high' ? '高' : askResponse.confidence === 'medium' ? '中' : '低'}
                  </span>
                )}
              </div>

              {/* 免责声明 */}
              {askResponse.disclaimer && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-3">
                  <p className="text-yellow-800 text-sm">⚠️ {askResponse.disclaimer}</p>
                </div>
              )}

              {/* 知识来源 */}
              {askResponse.sources && askResponse.sources.length > 0 && (
                <div className="border-t border-gray-200 pt-4">
                  <h4 className="text-sm font-medium text-gray-600 mb-2">📚 参考来源</h4>
                  <div className="flex flex-wrap gap-2">
                    {askResponse.sources.map((source, i) => (
                      <span key={i} className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded">
                        {source.title || '未知来源'}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
              回答生成失败: {askResponse.error}
            </div>
          )}
        </div>
      )}

      {!askMutation.isPending && !askResponse && (
        <div className="text-center py-8 text-gray-400">
          <span className="text-4xl block mb-2">💬</span>
          输入健康问题，AI 将结合知识库为您解答
        </div>
      )}
    </div>
  );
}
