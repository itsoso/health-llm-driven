'use client';

import { UseMutationResult } from '@tanstack/react-query';

interface SearchResult {
  content: string;
  metadata: {
    title?: string;
    category?: string;
    source?: string;
  };
  relevance_score: number;
}

interface Category {
  value: string;
  label: string;
}

interface SearchTabProps {
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  searchResults: SearchResult[];
  searchMutation: UseMutationResult<any, any, void, unknown>;
  categories: Category[];
}

export function SearchTab({ searchQuery, setSearchQuery, searchResults, searchMutation, categories }: SearchTabProps) {
  return (
    <div className="bg-white rounded-2xl shadow-lg p-6">
      <h2 className="text-xl font-bold text-gray-800 mb-4">🔍 知识搜索</h2>

      <div className="flex gap-3 mb-6">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && searchMutation.mutate()}
          placeholder="输入搜索内容，如：如何改善睡眠"
          className="flex-1 px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
        <button
          onClick={() => searchMutation.mutate()}
          disabled={!searchQuery.trim() || searchMutation.isPending}
          className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg font-medium hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 transition-all"
        >
          {searchMutation.isPending ? '搜索中...' : '搜索'}
        </button>
      </div>

      {searchResults.length > 0 ? (
        <div className="space-y-4">
          <p className="text-sm text-gray-500">找到 {searchResults.length} 条相关内容</p>
          {searchResults.map((result, index) => (
            <div key={index} className="border border-gray-200 rounded-xl p-4 hover:border-indigo-300 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-gray-800">{result.metadata.title || '无标题'}</span>
                <span className="text-sm px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                  相关度: {(result.relevance_score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="flex gap-2 mb-2">
                {result.metadata.category && (
                  <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                    {categories.find(c => c.value === result.metadata.category)?.label || result.metadata.category}
                  </span>
                )}
                {result.metadata.source && (
                  <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-600 rounded">
                    {result.metadata.source}
                  </span>
                )}
              </div>
              <p className="text-gray-600 text-sm line-clamp-3">{result.content}</p>
            </div>
          ))}
        </div>
      ) : searchMutation.isSuccess ? (
        <div className="text-center py-8 text-gray-500">
          <span className="text-4xl block mb-2">🔍</span>
          未找到相关内容
        </div>
      ) : (
        <div className="text-center py-8 text-gray-400">
          <span className="text-4xl block mb-2">💡</span>
          输入关键词搜索知识库内容
        </div>
      )}
    </div>
  );
}
