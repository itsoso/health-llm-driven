'use client';
import { requireAiConsent } from '@/services/aiConsent';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dailyRecommendationApi } from '@/services/api/health';
import { externalRecommendationApi, ExternalRecommendation } from '@/services/api/content';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { DailyRecommendation, statusColors, statusLabels } from './types';
import { ExternalRecommendationsFilter, ExternalRecommendationsContent } from './components/ExternalRecommendationsTab';
import { MetricCards } from './components/MetricCards';
import { AiInsightsSection } from './components/AiInsightsSection';
import { EnvironmentSection } from './components/EnvironmentSection';
import { SmartRecommendations, DailyGoals, HealthAnalysisGrid } from './components/HealthAnalysisGrid';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

type DateRange = 'today' | 'week' | 'month' | 'all';

interface PaginatedExternalResponse {
  items: ExternalRecommendation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

function DailyInsightsContent() {
  const { user, isAuthenticated, token } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'one-day' | 'seven-day' | 'external'>('one-day');
  const [refreshMessage, setRefreshMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 外部建议分页状态
  const [externalPage, setExternalPage] = useState(1);
  const [externalCategory, setExternalCategory] = useState<string | null>(null);
  const [externalDateRange, setExternalDateRange] = useState<DateRange>('today');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const pageSize = 10;

  // 计算日期范围
  const getDateRangeParams = () => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    switch (externalDateRange) {
      case 'today':
        return { start_date: today.toISOString().split('T')[0] };
      case 'week': {
        const weekAgo = new Date(today);
        weekAgo.setDate(weekAgo.getDate() - 7);
        return { start_date: weekAgo.toISOString().split('T')[0] };
      }
      case 'month': {
        const monthAgo = new Date(today);
        monthAgo.setDate(monthAgo.getDate() - 30);
        return { start_date: monthAgo.toISOString().split('T')[0] };
      }
      case 'all':
      default:
        return {};
    }
  };

  // 获取建议数据（1天和7天）
  const { data: recommendationsData, isLoading, error, refetch } = useQuery({
    queryKey: ['daily-recommendations'],
    queryFn: () => dailyRecommendationApi.getMyRecommendations(true),
    enabled: isAuthenticated,
  });

  // 获取外部建议（今日预览）
  const { data: externalRecsData } = useQuery({
    queryKey: ['external-recommendations-today'],
    queryFn: () => externalRecommendationApi.getToday(),
    enabled: isAuthenticated && activeTab !== 'external',
  });

  // 获取外部建议（分页列表）
  const { data: paginatedExternalData, isLoading: externalLoading } = useQuery({
    queryKey: ['external-recommendations-paginated', externalPage, externalCategory, externalDateRange],
    queryFn: async () => {
      const dateParams = getDateRangeParams();
      let url = `${API_BASE}/external-recommendations?page=${externalPage}&page_size=${pageSize}`;
      if (externalCategory) {
        url += `&category=${externalCategory}`;
      }
      if (dateParams.start_date) {
        url += `&start_date=${dateParams.start_date}`;
      }
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('加载失败');
      const result = await res.json();
      if (Array.isArray(result)) {
        return { items: result, total: result.length, page: 1, page_size: pageSize, total_pages: 1 };
      }
      return result as PaginatedExternalResponse;
    },
    enabled: isAuthenticated && activeTab === 'external',
  });

  // 刷新建议（清除缓存并重新生成）
  const refreshMutation = useMutation({
    mutationFn: async () => {
      await requireAiConsent();
      const res = await fetch(`${API_BASE}/daily-recommendation/me/refresh?use_llm=true`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail?.message || errorData.detail || '刷新失败');
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['daily-recommendations'] });
      setRefreshMessage({ type: 'success', text: '✓ 建议已刷新' });
      setTimeout(() => setRefreshMessage(null), 3000);
    },
    onError: (error: Error) => {
      setRefreshMessage({ type: 'error', text: `✗ ${error.message}` });
      setTimeout(() => setRefreshMessage(null), 5000);
    },
  });

  const oneDayData = recommendationsData?.data?.one_day;
  const sevenDayData = recommendationsData?.data?.seven_day;
  const isCached = recommendationsData?.data?.cached;

  // 外部建议辅助函数
  const formatDateTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch {
      return '';
    }
  };

  const handleCategoryChange = (cat: string | null) => {
    setExternalCategory(cat);
    setExternalPage(1);
    setExpandedId(null);
  };

  const handleDateRangeChange = (range: DateRange) => {
    setExternalDateRange(range);
    setExternalPage(1);
    setExpandedId(null);
  };

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  // 删除外部建议
  const deleteExternalMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(`${API_BASE}/external-recommendations/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('删除失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-recommendations-paginated'] });
      queryClient.invalidateQueries({ queryKey: ['external-recommendations-today'] });
    },
  });

  const handleDelete = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('确定要删除这条建议吗？')) {
      deleteExternalMutation.mutate(id);
    }
  };

  const shouldExpand = (id: number) => {
    return externalDateRange === 'today' || expandedId === id;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
        <div className="max-w-7xl mx-auto">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-1/3 mb-8"></div>
            <div className="h-64 bg-gray-200 rounded mb-4"></div>
            <div className="h-48 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    const errorMessage = (error as any)?.response?.data?.detail?.message ||
                        (error as any)?.message ||
                        '获取数据失败';
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="text-6xl mb-4">📈</div>
            <h2 className="text-2xl font-bold text-gray-800 mb-4">{errorMessage}</h2>
            <p className="text-gray-600 mb-6">请先同步Garmin数据后再查看每日分析</p>
            <Link
              href="/settings"
              className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
            >
              前往Garmin数据页面
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!recommendationsData?.data && activeTab !== 'external') return null;

  const currentData = activeTab === 'one-day' ? oneDayData : sevenDayData;

  if (activeTab !== 'external' && (!currentData || currentData.status === 'no_data')) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="text-6xl mb-4">📈</div>
            <h2 className="text-2xl font-bold text-gray-800 mb-4">暂无数据</h2>
            <p className="text-gray-600 mb-6">请先同步Garmin数据后再查看每日分析</p>
            <Link
              href="/settings"
              className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
            >
              前往Garmin数据页面
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
      <div className="max-w-7xl mx-auto">
        {/* 标签页切换 */}
        <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex gap-2">
              <button
                onClick={() => setActiveTab('one-day')}
                className={`px-6 py-3 rounded-lg font-semibold transition-all duration-200 ${
                  activeTab === 'one-day'
                    ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                最近1天建议
              </button>
              <button
                onClick={() => setActiveTab('seven-day')}
                className={`px-6 py-3 rounded-lg font-semibold transition-all duration-200 ${
                  activeTab === 'seven-day'
                    ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                本周建议
              </button>
              <button
                onClick={() => { setActiveTab('external'); setExternalPage(1); setExpandedId(null); }}
                className={`px-6 py-3 rounded-lg font-semibold transition-all duration-200 ${
                  activeTab === 'external'
                    ? 'bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white shadow-md'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                📡 外部建议
              </button>
            </div>
            <div className="flex items-center gap-2">
              {isCached && (
                <span className="text-xs px-3 py-1 bg-green-100 text-green-700 rounded-full font-medium">
                  ✓ 缓存数据
                </span>
              )}
              <button
                onClick={() => refreshMutation.mutate()}
                disabled={refreshMutation.isPending}
                className="px-4 py-2 bg-indigo-100 text-indigo-700 rounded-lg hover:bg-indigo-200 disabled:opacity-50 transition-colors text-sm font-medium flex items-center gap-1"
                title="清除缓存并重新生成建议"
              >
                {refreshMutation.isPending ? (
                  <>
                    <span className="animate-spin">⏳</span>
                    刷新中...
                  </>
                ) : (
                  <>
                    🔄 刷新建议
                  </>
                )}
              </button>
            </div>
          </div>

          {/* 刷新消息 */}
          {refreshMessage && (
            <div className={`mb-4 p-3 rounded-lg text-sm font-medium ${
              refreshMessage.type === 'success'
                ? 'bg-green-100 text-green-800'
                : 'bg-red-100 text-red-800'
            }`}>
              {refreshMessage.text}
            </div>
          )}

          {/* 头部信息 - 仅非外部建议tab显示 */}
          {activeTab !== 'external' && (
            <div className="flex justify-between items-start">
              <div>
                <p className="text-gray-500">
                  {activeTab === 'one-day'
                    ? `基于 ${currentData?.date || recommendationsData?.data?.analysis_date} 的数据分析`
                    : `基于 ${sevenDayData?.analysis_period || '最近7天'} 的数据分析`}
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">智能分析</span>
                  {currentData?.ai_insights ? (
                    <span className="text-xs px-2 py-1 bg-emerald-100 text-emerald-700 rounded">✓ AI增强</span>
                  ) : currentData?.llm_analysis?.available === false ? (
                    <span className="text-xs px-2 py-1 bg-gray-100 text-gray-500 rounded">AI未启用</span>
                  ) : null}
                </div>
              </div>
              <div className={`px-4 py-2 rounded-full text-white font-semibold ${statusColors[currentData?.overall_status || 'unknown']}`}>
                整体状态: {statusLabels[currentData?.overall_status || 'unknown']}
              </div>
            </div>
          )}

          {/* 外部建议tab的筛选器 */}
          {activeTab === 'external' && (
            <ExternalRecommendationsFilter
              externalCategory={externalCategory}
              externalDateRange={externalDateRange}
              handleCategoryChange={handleCategoryChange}
              handleDateRangeChange={handleDateRangeChange}
            />
          )}
        </div>

        {/* 外部建议tab内容 */}
        {activeTab === 'external' && (
          <ExternalRecommendationsContent
            externalLoading={externalLoading}
            paginatedExternalData={paginatedExternalData}
            externalPage={externalPage}
            setExternalPage={setExternalPage}
            externalDateRange={externalDateRange}
            shouldExpand={shouldExpand}
            handleDelete={handleDelete}
            deleteExternalMutation={deleteExternalMutation}
            toggleExpand={toggleExpand}
            formatDateTime={formatDateTime}
          />
        )}

        {/* 以下内容仅在非外部建议tab显示 */}
        {activeTab !== 'external' && (
          <>
            <MetricCards currentData={currentData} activeTab={activeTab} sevenDayData={sevenDayData} />
            <AiInsightsSection currentData={currentData} />
            <EnvironmentSection currentData={currentData} />
            <SmartRecommendations currentData={currentData} />
            <DailyGoals currentData={currentData} />
            <HealthAnalysisGrid currentData={currentData} />
          </>
        )}

        {/* 底部提示 */}
        <div className="mt-8">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 px-6 py-4 text-center">
            <p className="text-gray-900 text-sm font-semibold">
              数据来源: <span className="text-indigo-700 font-bold">Garmin</span> | 分析时间: <span className="text-gray-800">{new Date().toLocaleString('zh-CN')}</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// 导出受保护的页面
export default function DailyInsightsPage() {
  return (
    <ProtectedRoute>
      <DailyInsightsContent />
    </ProtectedRoute>
  );
}
