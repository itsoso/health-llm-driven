'use client';

import { ExternalRecommendation } from '@/services/api';
import { MarkdownContent } from './MarkdownContent';

type DateRange = 'today' | 'week' | 'month' | 'all';

interface PaginatedExternalResponse {
  items: ExternalRecommendation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const CATEGORY_CONFIG: Record<string, { icon: string; label: string; color: string; bgColor: string }> = {
  exercise: { icon: '🏃', label: '运动', color: 'text-emerald-600', bgColor: 'bg-emerald-100' },
  diet: { icon: '🥗', label: '饮食', color: 'text-orange-600', bgColor: 'bg-orange-100' },
  sleep: { icon: '😴', label: '睡眠', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  supplement: { icon: '💊', label: '补剂', color: 'text-purple-600', bgColor: 'bg-purple-100' },
  general: { icon: '✨', label: '综合', color: 'text-pink-600', bgColor: 'bg-pink-100' },
};

const CATEGORY_ORDER = ['exercise', 'diet', 'sleep', 'supplement', 'general'];

const dateRangeLabels: Record<DateRange, string> = {
  today: '今日',
  week: '近7天',
  month: '近30天',
  all: '全部',
};

interface ExternalRecommendationsTabProps {
  externalLoading: boolean;
  paginatedExternalData: PaginatedExternalResponse | undefined;
  externalPage: number;
  setExternalPage: (page: number | ((prev: number) => number)) => void;
  externalCategory: string | null;
  externalDateRange: DateRange;
  expandedId: number | null;
  handleCategoryChange: (cat: string | null) => void;
  handleDateRangeChange: (range: DateRange) => void;
  toggleExpand: (id: number) => void;
  shouldExpand: (id: number) => boolean;
  handleDelete: (id: number, e: React.MouseEvent) => void;
  deleteExternalMutation: { isPending: boolean };
  formatDateTime: (dateStr: string) => string;
}

export function ExternalRecommendationsFilter({
  externalCategory,
  externalDateRange,
  handleCategoryChange,
  handleDateRangeChange,
}: Pick<ExternalRecommendationsTabProps, 'externalCategory' | 'externalDateRange' | 'handleCategoryChange' | 'handleDateRangeChange'>) {
  return (
    <div>
      <p className="text-gray-500 mb-4">来自 AI 助手和外部健康服务的个性化建议</p>

      {/* 日期范围筛选 */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-sm text-gray-600 font-medium">时间：</span>
        {(['today', 'week', 'month', 'all'] as DateRange[]).map((range) => (
          <button
            key={range}
            onClick={() => handleDateRangeChange(range)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              externalDateRange === range
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {dateRangeLabels[range]}
          </button>
        ))}
      </div>

      {/* 分类筛选 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-600 font-medium">分类：</span>
        <button
          onClick={() => handleCategoryChange(null)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
            externalCategory === null
              ? 'bg-violet-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          全部
        </button>
        {CATEGORY_ORDER.map((cat) => (
          <button
            key={cat}
            onClick={() => handleCategoryChange(cat)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              externalCategory === cat
                ? 'bg-violet-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {CATEGORY_CONFIG[cat].icon} {CATEGORY_CONFIG[cat].label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ExternalRecommendationsContent({
  externalLoading,
  paginatedExternalData,
  externalPage,
  setExternalPage,
  externalDateRange,
  shouldExpand,
  handleDelete,
  deleteExternalMutation,
  toggleExpand,
  formatDateTime,
}: Omit<ExternalRecommendationsTabProps, 'externalCategory' | 'handleCategoryChange' | 'handleDateRangeChange' | 'expandedId'>) {
  if (externalLoading) {
    return (
      <div className="bg-white rounded-2xl shadow-lg p-8">
        <div className="flex flex-col items-center justify-center py-10">
          <div className="w-10 h-10 border-4 border-violet-500/30 border-t-violet-500 rounded-full animate-spin"></div>
          <p className="mt-4 text-gray-500 text-sm">加载中...</p>
        </div>
      </div>
    );
  }

  if (!paginatedExternalData?.items?.length) {
    return (
      <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
        <div className="text-5xl mb-4">📭</div>
        <h3 className="text-xl font-bold text-gray-800 mb-2">暂无外部建议</h3>
        <p className="text-gray-500 text-sm max-w-md mx-auto">
          外部 AI 健康助手分析您的健康数据后，会在这里展示个性化建议。
        </p>
      </div>
    );
  }

  return (
    <>
      {/* 统计信息 */}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm text-gray-500">
          共 <span className="text-gray-800 font-semibold">{paginatedExternalData.total}</span> 条建议
        </span>
      </div>

      {/* 建议列表 */}
      <div className="space-y-3 mb-6">
        {paginatedExternalData.items.map((rec) => {
          const config = CATEGORY_CONFIG[rec.category] || { icon: '📋', label: rec.category, color: 'text-gray-600', bgColor: 'bg-gray-100' };
          const isExpanded = shouldExpand(rec.id);

          return (
            <div
              key={rec.id}
              className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:border-gray-300 transition-colors"
            >
              {/* 列表项头部 */}
              <div
                className={`px-4 py-3 flex items-center gap-3 ${externalDateRange !== 'today' ? 'cursor-pointer' : ''}`}
                onClick={() => externalDateRange !== 'today' && toggleExpand(rec.id)}
              >
                {/* 分类标签 */}
                <span className={`px-2 py-1 rounded-md text-xs font-medium ${config.bgColor} ${config.color} whitespace-nowrap`}>
                  {config.icon} {config.label}
                </span>

                {/* 标题 */}
                <h4 className="flex-1 text-gray-800 font-medium truncate">{rec.title}</h4>

                {/* 来源 */}
                <span className="text-xs text-gray-400 hidden sm:block max-w-[80px] truncate">
                  {rec.source_name}
                </span>

                {/* 日期 */}
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  {formatDateTime(rec.created_at)}
                </span>

                {/* 删除按钮 */}
                <button
                  onClick={(e) => handleDelete(rec.id, e)}
                  disabled={deleteExternalMutation.isPending}
                  className="text-gray-400 hover:text-red-500 transition-colors p-1 rounded hover:bg-red-50"
                  title="删除此建议"
                >
                  🗑️
                </button>

                {/* 展开图标 - 仅在非今日筛选时显示 */}
                {externalDateRange !== 'today' && (
                  <span className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                    ▼
                  </span>
                )}
              </div>

              {/* 展开内容 */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-gray-100">
                  <div className="pt-3">
                    <MarkdownContent content={rec.content} />
                    <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
                      <span>来源: {rec.source_name}</span>
                      <span>{formatDateTime(rec.created_at)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 分页控件 */}
      {paginatedExternalData.total_pages > 1 && (
        <div className="bg-white rounded-xl shadow-sm p-4 flex items-center justify-between">
          <div className="text-sm text-gray-500">
            第 <span className="text-gray-800 font-medium">{paginatedExternalData.page}</span> / {paginatedExternalData.total_pages} 页
          </div>

          <div className="flex items-center gap-2">
            {/* 首页 */}
            <button
              onClick={() => setExternalPage(1)}
              disabled={externalPage === 1}
              className="px-3 py-1.5 text-sm font-medium border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
            >
              首页
            </button>

            {/* 上一页 */}
            <button
              onClick={() => setExternalPage(prev => Math.max(1, prev - 1))}
              disabled={externalPage === 1}
              className="px-3 py-1.5 text-sm font-medium border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
            >
              上一页
            </button>

            {/* 页码 */}
            <div className="flex items-center gap-1">
              {(() => {
                const pages: (number | string)[] = [];
                const totalPages = paginatedExternalData.total_pages;

                if (totalPages <= 7) {
                  for (let i = 1; i <= totalPages; i++) pages.push(i);
                } else {
                  pages.push(1);
                  if (externalPage > 3) pages.push('...');

                  const start = Math.max(2, externalPage - 1);
                  const end = Math.min(totalPages - 1, externalPage + 1);

                  for (let i = start; i <= end; i++) pages.push(i);

                  if (externalPage < totalPages - 2) pages.push('...');
                  pages.push(totalPages);
                }

                return pages.map((page, idx) => (
                  typeof page === 'number' ? (
                    <button
                      key={idx}
                      onClick={() => setExternalPage(page)}
                      className={`px-3 py-1.5 text-sm font-medium border rounded-lg transition-colors ${
                        externalPage === page
                          ? 'bg-violet-600 text-white border-violet-600'
                          : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {page}
                    </button>
                  ) : (
                    <span key={idx} className="px-2 text-gray-400">...</span>
                  )
                ));
              })()}
            </div>

            {/* 下一页 */}
            <button
              onClick={() => setExternalPage(prev => Math.min(paginatedExternalData.total_pages, prev + 1))}
              disabled={externalPage >= paginatedExternalData.total_pages}
              className="px-3 py-1.5 text-sm font-medium border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
            >
              下一页
            </button>

            {/* 末页 */}
            <button
              onClick={() => setExternalPage(paginatedExternalData.total_pages)}
              disabled={externalPage >= paginatedExternalData.total_pages}
              className="px-3 py-1.5 text-sm font-medium border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed text-gray-700 transition-colors"
            >
              末页
            </button>
          </div>
        </div>
      )}
    </>
  );
}
