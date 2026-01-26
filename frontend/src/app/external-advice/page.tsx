'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = '/api';

// 类别配置
const CATEGORY_CONFIG: Record<string, { icon: string; label: string; color: string; bgColor: string }> = {
  exercise: { icon: '🏃', label: '运动', color: 'text-emerald-400', bgColor: 'bg-emerald-500/20' },
  diet: { icon: '🥗', label: '饮食', color: 'text-orange-400', bgColor: 'bg-orange-500/20' },
  sleep: { icon: '😴', label: '睡眠', color: 'text-blue-400', bgColor: 'bg-blue-500/20' },
  supplement: { icon: '💊', label: '补剂', color: 'text-purple-400', bgColor: 'bg-purple-500/20' },
  general: { icon: '✨', label: '综合', color: 'text-pink-400', bgColor: 'bg-pink-500/20' },
};

const CATEGORY_ORDER = ['exercise', 'diet', 'sleep', 'supplement', 'general'];

// 简单的Markdown渲染组件
function MarkdownContent({ content }: { content: string }) {
  const paragraphs = content.split(/\n\n+/);

  return (
    <div className="prose prose-invert prose-sm max-w-none">
      {paragraphs.map((paragraph, index) => {
        const trimmed = paragraph.trim();

        if (trimmed.startsWith('#### ')) {
          return (
            <h4 key={index} className="text-base font-semibold text-white mt-4 mb-2">
              {trimmed.replace(/^#### /, '')}
            </h4>
          );
        }
        if (trimmed.startsWith('### ')) {
          return (
            <h3 key={index} className="text-lg font-semibold text-white mt-5 mb-2">
              {trimmed.replace(/^### /, '')}
            </h3>
          );
        }
        if (trimmed.startsWith('## ')) {
          return (
            <h2 key={index} className="text-xl font-bold text-white mt-6 mb-3">
              {trimmed.replace(/^## /, '')}
            </h2>
          );
        }

        if (trimmed.includes('|') && trimmed.split('\n').length > 1) {
          const lines = trimmed.split('\n').filter(line => line.trim() && !line.match(/^\|[\s-|]+\|$/));
          if (lines.length > 0) {
            const headers = lines[0].split('|').filter(cell => cell.trim());
            const rows = lines.slice(1).map(line => line.split('|').filter(cell => cell.trim()));

            return (
              <div key={index} className="my-4 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-600">
                      {headers.map((header, i) => (
                        <th key={i} className="px-3 py-2 text-left text-gray-300 font-medium">
                          {header.trim()}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="border-b border-gray-700/50">
                        {row.map((cell, cellIndex) => (
                          <td key={cellIndex} className="px-3 py-2 text-gray-400">
                            {cell.trim()}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }
        }

        if (trimmed.match(/^[-*]\s/m)) {
          const items = trimmed.split(/\n/).filter(line => line.trim());
          return (
            <ul key={index} className="list-disc list-inside space-y-1 text-gray-300 my-3 ml-2">
              {items.map((item, i) => (
                <li key={i}>{renderInlineMarkdown(item.replace(/^[-*]\s+/, ''))}</li>
              ))}
            </ul>
          );
        }

        if (trimmed.match(/^\d+\.\s/m)) {
          const items = trimmed.split(/\n/).filter(line => line.trim());
          return (
            <ol key={index} className="list-decimal list-inside space-y-1 text-gray-300 my-3 ml-2">
              {items.map((item, i) => (
                <li key={i}>{renderInlineMarkdown(item.replace(/^\d+\.\s+/, ''))}</li>
              ))}
            </ol>
          );
        }

        if (trimmed.match(/^[-*_]{3,}$/)) {
          return <hr key={index} className="my-4 border-gray-600" />;
        }

        return (
          <p key={index} className="text-gray-300 leading-relaxed my-3">
            {renderInlineMarkdown(trimmed)}
          </p>
        );
      })}
    </div>
  );
}

function renderInlineMarkdown(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

interface ExternalRecommendation {
  id: number;
  category: string;
  title: string;
  content: string;
  source_name: string;
  recommendation_date: string;
  created_at: string;
}

interface PaginatedResponse {
  items: ExternalRecommendation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export default function ExternalAdvicePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [data, setData] = useState<ExternalRecommendation[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const pageSize = 10;

  const getToken = () => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('auth_token');
    }
    return null;
  };

  useEffect(() => {
    loadData();
  }, [currentPage, selectedCategory]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    const token = getToken();

    if (!token) {
      router.push('/login');
      return;
    }

    try {
      let url = `${API_BASE}/external-recommendations?page=${currentPage}&page_size=${pageSize}`;
      if (selectedCategory) {
        url += `&category=${selectedCategory}`;
      }

      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.ok) {
        const result = await res.json();
        // 处理两种可能的响应格式
        if (Array.isArray(result)) {
          setData(result);
          setTotalItems(result.length);
          setTotalPages(1);
        } else if (result.items) {
          setData(result.items);
          setTotalItems(result.total || result.items.length);
          setTotalPages(result.total_pages || Math.ceil((result.total || result.items.length) / pageSize));
        } else {
          setData([]);
          setTotalItems(0);
          setTotalPages(0);
        }
      } else if (res.status === 401) {
        router.push('/login');
        return;
      } else {
        throw new Error('加载失败');
      }
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const formatDateTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch {
      return '';
    }
  };

  const handleCategoryChange = (cat: string | null) => {
    setSelectedCategory(cat);
    setCurrentPage(1);
    setExpandedId(null);
  };

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <div className="flex justify-between items-center mb-2">
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              📡 外部健康建议
            </h1>
            <button
              onClick={() => { setCurrentPage(1); loadData(); }}
              className="px-4 py-2 bg-purple-600/30 hover:bg-purple-600/50 rounded-lg text-purple-300 text-sm transition-colors"
            >
              ↻ 刷新
            </button>
          </div>
          <p className="text-gray-400 text-sm">来自 AI 助手和外部健康服务的个性化建议</p>

          {/* Category Filter */}
          <div className="flex flex-wrap gap-2 mt-4">
            <button
              onClick={() => handleCategoryChange(null)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                selectedCategory === null
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-700/50 text-gray-300 hover:bg-gray-700'
              }`}
            >
              全部
            </button>
            {CATEGORY_ORDER.map((cat) => (
              <button
                key={cat}
                onClick={() => handleCategoryChange(cat)}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  selectedCategory === cat
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-700/50 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {CATEGORY_CONFIG[cat].icon} {CATEGORY_CONFIG[cat].label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-10 h-10 border-4 border-purple-500/30 border-t-purple-500 rounded-full animate-spin"></div>
            <p className="mt-4 text-gray-400 text-sm">加载中...</p>
          </div>
        ) : error ? (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">😔</div>
            <p className="text-gray-400 mb-4">{error}</p>
            <button
              onClick={loadData}
              className="px-5 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-white text-sm transition-colors"
            >
              点击重试
            </button>
          </div>
        ) : data.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">📭</div>
            <h3 className="text-xl font-bold text-white mb-2">暂无外部建议</h3>
            <p className="text-gray-400 text-sm max-w-md mx-auto">
              外部 AI 健康助手分析您的健康数据后，会在这里展示个性化建议。
            </p>
          </div>
        ) : (
          <>
            {/* Stats */}
            <div className="mb-4 flex items-center justify-between">
              <span className="text-sm text-gray-400">
                共 <span className="text-white font-semibold">{totalItems}</span> 条建议
              </span>
            </div>

            {/* List */}
            <div className="space-y-3">
              {data.map((rec) => {
                const config = CATEGORY_CONFIG[rec.category] || { icon: '📋', label: rec.category, color: 'text-gray-400', bgColor: 'bg-gray-500/20' };
                const isExpanded = expandedId === rec.id;

                return (
                  <div
                    key={rec.id}
                    className="bg-gray-800/60 rounded-xl border border-gray-700/50 overflow-hidden hover:border-gray-600/50 transition-colors"
                  >
                    {/* List Item Header - Always Visible */}
                    <div
                      className="px-4 py-3 cursor-pointer flex items-center gap-3"
                      onClick={() => toggleExpand(rec.id)}
                    >
                      {/* Category Badge */}
                      <span className={`px-2 py-1 rounded-md text-xs font-medium ${config.bgColor} ${config.color} whitespace-nowrap`}>
                        {config.icon} {config.label}
                      </span>

                      {/* Title */}
                      <h4 className="flex-1 text-white font-medium truncate">{rec.title}</h4>

                      {/* Source */}
                      <span className="text-xs text-gray-500 hidden sm:block max-w-[80px] truncate">
                        {rec.source_name}
                      </span>

                      {/* Date */}
                      <span className="text-xs text-gray-500 whitespace-nowrap">
                        {formatDateTime(rec.created_at)}
                      </span>

                      {/* Expand Icon */}
                      <span className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                        ▼
                      </span>
                    </div>

                    {/* Expanded Content */}
                    {isExpanded && (
                      <div className="px-4 pb-4 border-t border-gray-700/50">
                        <div className="pt-3">
                          <MarkdownContent content={rec.content} />
                          <div className="mt-3 pt-3 border-t border-gray-700/30 flex items-center justify-between text-xs text-gray-500">
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

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-between border-t border-gray-700/50 pt-4">
                <div className="text-sm text-gray-400">
                  第 <span className="text-white font-medium">{currentPage}</span> / {totalPages} 页
                </div>

                <div className="flex items-center gap-2">
                  {/* First Page */}
                  <button
                    onClick={() => setCurrentPage(1)}
                    disabled={currentPage === 1}
                    className="px-3 py-1.5 text-sm font-medium border border-gray-600 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 transition-colors"
                  >
                    首页
                  </button>

                  {/* Prev */}
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1.5 text-sm font-medium border border-gray-600 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 transition-colors"
                  >
                    上一页
                  </button>

                  {/* Page Numbers */}
                  <div className="flex items-center gap-1">
                    {(() => {
                      const pages: (number | string)[] = [];

                      if (totalPages <= 7) {
                        for (let i = 1; i <= totalPages; i++) pages.push(i);
                      } else {
                        pages.push(1);
                        if (currentPage > 3) pages.push('...');

                        const start = Math.max(2, currentPage - 1);
                        const end = Math.min(totalPages - 1, currentPage + 1);

                        for (let i = start; i <= end; i++) pages.push(i);

                        if (currentPage < totalPages - 2) pages.push('...');
                        pages.push(totalPages);
                      }

                      return pages.map((page, idx) => (
                        typeof page === 'number' ? (
                          <button
                            key={idx}
                            onClick={() => setCurrentPage(page)}
                            className={`px-3 py-1.5 text-sm font-medium border rounded-lg transition-colors ${
                              currentPage === page
                                ? 'bg-purple-600 text-white border-purple-600'
                                : 'border-gray-600 text-gray-300 hover:bg-gray-700'
                            }`}
                          >
                            {page}
                          </button>
                        ) : (
                          <span key={idx} className="px-2 text-gray-500">...</span>
                        )
                      ));
                    })()}
                  </div>

                  {/* Next */}
                  <button
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-1.5 text-sm font-medium border border-gray-600 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 transition-colors"
                  >
                    下一页
                  </button>

                  {/* Last Page */}
                  <button
                    onClick={() => setCurrentPage(totalPages)}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-1.5 text-sm font-medium border border-gray-600 rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 transition-colors"
                  >
                    末页
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
