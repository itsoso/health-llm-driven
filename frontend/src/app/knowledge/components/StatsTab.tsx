'use client';

import { UseMutationResult } from '@tanstack/react-query';

interface KnowledgeStats {
  available: boolean;
  total_documents: number;
  collection_name: string;
  persist_directory: string;
  embedding_model: string;
  error?: string;
}

interface StatsTabProps {
  stats: KnowledgeStats | undefined;
  statsLoading: boolean;
  initBasicsMutation: UseMutationResult<any, any, void, unknown>;
  clearAllMutation: UseMutationResult<any, any, void, unknown>;
  refetchStats: () => void;
}

export function StatsTab({ stats, statsLoading, initBasicsMutation, clearAllMutation, refetchStats }: StatsTabProps) {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow-lg p-6">
        <h2 className="text-xl font-bold text-gray-800 mb-4">知识库状态</h2>

        {statsLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto"></div>
            <p className="text-gray-500 mt-2">加载中...</p>
          </div>
        ) : stats?.available ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 rounded-xl p-4">
              <div className="text-3xl font-bold text-indigo-600">{stats.total_documents}</div>
              <div className="text-sm text-indigo-700">文档总数</div>
            </div>
            <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4">
              <div className="text-lg font-semibold text-purple-600 truncate">{stats.collection_name}</div>
              <div className="text-sm text-purple-700">集合名称</div>
            </div>
            <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4">
              <div className="text-lg font-semibold text-blue-600 truncate">{stats.embedding_model}</div>
              <div className="text-sm text-blue-700">嵌入模型</div>
            </div>
          </div>
        ) : (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
            知识库服务不可用: {stats?.error || '未知错误'}
          </div>
        )}

        <div className="flex flex-wrap gap-3 mt-6">
          <button
            onClick={() => initBasicsMutation.mutate()}
            disabled={initBasicsMutation.isPending}
            className="px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-lg font-medium hover:from-green-600 hover:to-emerald-600 disabled:opacity-50 transition-all"
          >
            {initBasicsMutation.isPending ? '初始化中...' : '🌱 初始化基础健康知识'}
          </button>
          <button
            onClick={() => refetchStats()}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-all"
          >
            🔄 刷新统计
          </button>
          <button
            onClick={() => clearAllMutation.mutate()}
            disabled={clearAllMutation.isPending}
            className="px-4 py-2 bg-red-100 text-red-700 rounded-lg font-medium hover:bg-red-200 disabled:opacity-50 transition-all"
          >
            {clearAllMutation.isPending ? '清空中...' : '🗑️ 清空知识库'}
          </button>
        </div>
      </div>

      {/* 预置知识说明 */}
      <div className="bg-white rounded-2xl shadow-lg p-6">
        <h2 className="text-xl font-bold text-gray-800 mb-4">预置健康知识</h2>
        <p className="text-gray-600 mb-4">点击"初始化基础健康知识"将导入以下内容：</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[
            '😴 睡眠的重要性',
            '🏃 有氧运动指南',
            '❤️ 静息心率与健康',
            '📊 心率变异性(HRV)解读',
            '🧘 压力管理与身体电量',
            '👃 慢性鼻炎的日常管理',
            '💧 健康饮水指南',
            '🚶 步数与健康',
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2 bg-indigo-50 border border-indigo-100 rounded-lg px-4 py-3">
              <span className="text-gray-800 font-medium">{item}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
