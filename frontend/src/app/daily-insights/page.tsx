'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dailyRecommendationApi, externalRecommendationApi, ExternalRecommendation } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

// 日期范围类型
type DateRange = 'today' | 'week' | 'month' | 'all';

interface ExerciseRecommendation {
  type: string;
  location: string;
  duration: string;
  intensity: string;
  best_time: string;
  reason: string;
}

interface DailyRecommendation {
  status: string;
  date: string;
  analysis_date: string;
  user: string;
  sleep_analysis: {
    status: string;
    score: number | null;
    duration_hours: number | null;
    quality_assessment: string;
    trend: string;
    issues: string[];
    recommendations: string[];
  };
  activity_analysis: {
    status: string;
    steps: number | null;
    steps_goal_met: boolean;
    active_minutes: number | null;
    calories_burned: number | null;
    trend: string;
    issues: string[];
    recommendations: string[];
  };
  heart_rate_analysis: {
    status: string;
    resting_hr: number | null;
    avg_hr: number | null;
    hrv: number | null;
    trend: string;
    issues: string[];
    recommendations: string[];
  };
  stress_analysis: {
    stress_level: number | null;
    body_battery_highest: number | null;
    recovery_status: string;
    issues: string[];
    recommendations: string[];
  };
  overall_status: string;
  priority_recommendations: string[];
  enhanced_recommendations?: string[];
  daily_goals: Array<{
    category: string;
    goal: string;
    icon: string;
    target_value: number;
    unit: string;
  }>;
  raw_data: {
    sleep_score: number | null;
    sleep_duration_minutes: number | null;
    steps: number | null;
    resting_heart_rate: number | null;
    stress_level: number | null;
    body_battery_highest: number | null;
    body_battery_current: number | null;
    body_battery_lowest: number | null;
    body_battery_drained: number | null;
  };
  // 环境数据
  environment?: {
    weather: {
      available: boolean;
      temperature: number | null;
      feels_like: number | null;
      humidity: number | null;
      weather: string;
      wind_speed: number | null;
      summary: string;
    };
    air_quality: {
      available: boolean;
      aqi: number | null;
      level: string;
      description: string;
      pm25: number | null;
      health_implications: string;
    };
    exercise: {
      outdoor_suitable: boolean;
      score: number;
      status: string;
      recommended_activities: string[];
    };
    advices: string[];
    warnings: string[];
  };
  // LLM分析结果
  ai_insights?: {
    health_summary: string;
    key_insights: string[];
    today_focus: string;
    encouragement: string;
    warnings: string[];
  };
  ai_advice?: {
    sleep: string;
    activity: string;
    heart_health: string;
    recovery: string;
    environment?: string;
  };
  // 运动推荐
  exercise_recommendations?: ExerciseRecommendation[];
  llm_analysis?: {
    available: boolean;
    error?: string;
    environment_advice?: string;
    exercise_recommendations?: ExerciseRecommendation[];
  };
}

const statusColors: Record<string, string> = {
  excellent: 'bg-green-500',
  good: 'bg-green-400',
  fair: 'bg-yellow-400',
  poor: 'bg-red-400',
  concerning: 'bg-red-500',
  needs_attention: 'bg-orange-400',
  unknown: 'bg-gray-400',
};

const statusLabels: Record<string, string> = {
  excellent: '优秀',
  good: '良好',
  fair: '一般',
  poor: '较差',
  concerning: '需关注',
  needs_attention: '需要注意',
  unknown: '未知',
};

const trendIcons: Record<string, string> = {
  improving: '📈',
  stable: '➡️',
  declining: '📉',
  concerning: '⚠️',
};

// 类别配置
const CATEGORY_CONFIG: Record<string, { icon: string; label: string; color: string; bgColor: string }> = {
  exercise: { icon: '🏃', label: '运动', color: 'text-emerald-600', bgColor: 'bg-emerald-100' },
  diet: { icon: '🥗', label: '饮食', color: 'text-orange-600', bgColor: 'bg-orange-100' },
  sleep: { icon: '😴', label: '睡眠', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  supplement: { icon: '💊', label: '补剂', color: 'text-purple-600', bgColor: 'bg-purple-100' },
  general: { icon: '✨', label: '综合', color: 'text-pink-600', bgColor: 'bg-pink-100' },
};

const CATEGORY_ORDER = ['exercise', 'diet', 'sleep', 'supplement', 'general'];

// Markdown渲染组件 - 使用 react-markdown（针对移动端优化字号）
function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-p:leading-relaxed prose-strong:text-gray-900 prose-ul:text-gray-700 prose-ol:text-gray-700 prose-li:text-gray-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="text-base font-bold text-gray-800 mt-4 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold text-gray-800 mt-3 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold text-gray-800 mt-3 mb-1.5">{children}</h3>,
          h4: ({ children }) => <h4 className="text-xs font-semibold text-gray-800 mt-2 mb-1">{children}</h4>,
          h5: ({ children }) => <h5 className="text-xs font-semibold text-gray-800 mt-2 mb-1">{children}</h5>,
          h6: ({ children }) => <h6 className="text-xs font-medium text-gray-700 mt-1.5 mb-1">{children}</h6>,
          p: ({ children }) => <p className="text-xs text-gray-700 leading-relaxed my-1.5">{children}</p>,
          ul: ({ children }) => <ul className="list-disc list-inside space-y-0.5 text-xs text-gray-700 my-1.5 ml-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-inside space-y-0.5 text-xs text-gray-700 my-1.5 ml-1">{children}</ol>,
          li: ({ children }) => <li className="text-xs text-gray-700">{children}</li>,
          strong: ({ children }) => <strong className="text-gray-900 font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-indigo-400 pl-2 my-2 text-xs text-gray-600 italic">{children}</blockquote>
          ),
          code: ({ className, children }) => {
            const isInline = !className;
            return isInline ? (
              <code className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
            ) : (
              <code className="block bg-gray-100 p-2 rounded-lg text-xs font-mono overflow-x-auto">{children}</code>
            );
          },
          pre: ({ children }) => <pre className="bg-gray-100 p-2 rounded-lg overflow-x-auto my-2 text-xs">{children}</pre>,
          hr: () => <hr className="my-3 border-gray-300" />,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="min-w-full text-xs border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr className="border-b border-gray-200">{children}</tr>,
          th: ({ children }) => <th className="px-2 py-1.5 text-left text-xs text-gray-700 font-semibold border-b border-gray-300">{children}</th>,
          td: ({ children }) => <td className="px-2 py-1.5 text-xs text-gray-600">{children}</td>,
          a: ({ href, children }) => (
            <a href={href} className="text-xs text-indigo-600 hover:text-indigo-800 underline" target="_blank" rel="noopener noreferrer">{children}</a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

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
      // 处理两种可能的响应格式
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

  // 判断是否应该展开（今日筛选时自动展开全部）
  const shouldExpand = (id: number) => {
    return externalDateRange === 'today' || expandedId === id;
  };

  // 日期范围标签
  const dateRangeLabels: Record<DateRange, string> = {
    today: '今日',
    week: '近7天',
    month: '近30天',
    all: '全部',
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
              href="/garmin"
              className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
            >
              前往Garmin数据页面
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // 外部建议tab不需要检查recommendationsData
  if (!recommendationsData?.data && activeTab !== 'external') return null;

  const currentData = activeTab === 'one-day' ? oneDayData : sevenDayData;

  // 只在非外部建议tab时检查数据
  if (activeTab !== 'external' && (!currentData || currentData.status === 'no_data')) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="text-6xl mb-4">📈</div>
            <h2 className="text-2xl font-bold text-gray-800 mb-4">暂无数据</h2>
            <p className="text-gray-600 mb-6">请先同步Garmin数据后再查看每日分析</p>
            <Link
              href="/garmin"
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
          )}
        </div>

        {/* 外部建议tab内容 */}
        {activeTab === 'external' && (
          <>
            {externalLoading ? (
              <div className="bg-white rounded-2xl shadow-lg p-8">
                <div className="flex flex-col items-center justify-center py-10">
                  <div className="w-10 h-10 border-4 border-violet-500/30 border-t-violet-500 rounded-full animate-spin"></div>
                  <p className="mt-4 text-gray-500 text-sm">加载中...</p>
                </div>
              </div>
            ) : !paginatedExternalData?.items?.length ? (
              <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
                <div className="text-5xl mb-4">📭</div>
                <h3 className="text-xl font-bold text-gray-800 mb-2">暂无外部建议</h3>
                <p className="text-gray-500 text-sm max-w-md mx-auto">
                  外部 AI 健康助手分析您的健康数据后，会在这里展示个性化建议。
                </p>
              </div>
            ) : (
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
            )}
          </>
        )}

        {/* 以下内容仅在非外部建议tab显示 */}
        {activeTab !== 'external' && (
          <>
        {/* 关键指标卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl shadow p-4">
            <div className="text-3xl mb-2">😴</div>
            <div className="text-sm text-gray-700 font-medium">睡眠分数</div>
            <div className="text-2xl font-bold text-indigo-600">
              {activeTab === 'seven-day' && sevenDayData?.averages?.sleep_score 
                ? sevenDayData.averages.sleep_score 
                : currentData?.raw_data?.sleep_score || '-'}
            </div>
            <div className="text-xs text-gray-600">
              {activeTab === 'seven-day' && sevenDayData?.averages?.sleep_duration_minutes
                ? `${(sevenDayData.averages.sleep_duration_minutes / 60).toFixed(1)}小时`
                : currentData?.raw_data?.sleep_duration_minutes 
                  ? `${(currentData.raw_data.sleep_duration_minutes / 60).toFixed(1)}小时` 
                  : '-'}
            </div>
          </div>
          
          <div className="bg-white rounded-xl shadow p-4">
            <div className="text-3xl mb-2">🚶</div>
            <div className="text-sm text-gray-700 font-medium">步数</div>
            <div className="text-2xl font-bold text-green-600">
              {activeTab === 'seven-day' && sevenDayData?.averages?.steps 
                ? sevenDayData.averages.steps.toLocaleString() 
                : currentData?.raw_data?.steps?.toLocaleString() || '-'}
            </div>
            <div className="text-xs text-gray-600">
              {currentData?.activity_analysis?.steps_goal_met ? '✅ 达标' : '🎯 继续加油'}
            </div>
          </div>
          
          <div className="bg-white rounded-xl shadow p-4">
            <div className="text-3xl mb-2">❤️</div>
            <div className="text-sm text-gray-700 font-medium">静息心率</div>
            <div className="text-2xl font-bold text-red-500">
              {activeTab === 'seven-day' && sevenDayData?.averages?.resting_heart_rate 
                ? sevenDayData.averages.resting_heart_rate 
                : currentData?.raw_data?.resting_heart_rate || '-'}
            </div>
            <div className="text-xs text-gray-600">bpm</div>
          </div>
          
          <div className="bg-white rounded-xl shadow p-4">
            <div className="text-3xl mb-2">🔋</div>
            <div className="text-sm text-gray-700 font-medium">身体电量</div>
            {(() => {
              const currentBattery = currentData?.raw_data?.body_battery_current;
              const peakBattery = activeTab === 'seven-day' && sevenDayData?.averages?.body_battery 
                ? sevenDayData.averages.body_battery 
                : currentData?.raw_data?.body_battery_highest;
              const lowestBattery = currentData?.raw_data?.body_battery_lowest;
              const displayBattery = currentBattery ?? peakBattery;
              const hasCurrent = currentBattery !== null && currentBattery !== undefined;
              
              const getBatteryColor = (value: number | null | undefined) => {
                if (value === null || value === undefined) return 'text-gray-400';
                if (value >= 80) return 'text-green-600';
                if (value >= 50) return 'text-yellow-600';
                return 'text-red-500';
              };
              
              const getBatteryStatus = (value: number | null | undefined) => {
                if (value === null || value === undefined) return '';
                if (value >= 80) return '充足';
                if (value >= 50) return '中等';
                return '偏低';
              };
              
              return (
                <>
                  <div className={`text-2xl font-bold ${getBatteryColor(displayBattery)}`}>
                    {displayBattery ?? '-'}
                  </div>
                  <div className="text-xs text-gray-600">
                    {hasCurrent ? (
                      <span>当前 · {getBatteryStatus(currentBattery)}</span>
                    ) : (
                      <span>{activeTab === 'seven-day' ? '7天平均' : '峰值'}</span>
                    )}
                  </div>
                  {(peakBattery || lowestBattery) && activeTab === 'one-day' && (
                    <div className="mt-1 text-xs space-y-0.5">
                      {hasCurrent && peakBattery && (
                        <div className="text-gray-500">📈 峰值 <span className="text-green-600 font-medium">{peakBattery}</span></div>
                      )}
                      {lowestBattery && (
                        <div className="text-gray-500">📉 最低 <span className="text-gray-700 font-medium">{lowestBattery}</span></div>
                      )}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        </div>

        {/* AI 健康摘要 */}
        {currentData?.ai_insights && (
          <div className="bg-gradient-to-r from-emerald-500 to-teal-600 rounded-2xl shadow-lg p-6 mb-6 text-white">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">✨ AI 智能助理</h2>
              <span className="text-xs bg-white/20 px-2 py-1 rounded">由大模型生成</span>
            </div>
            
            {/* 健康摘要 */}
            <p className="text-lg mb-4 leading-relaxed">{currentData.ai_insights.health_summary}</p>
            
            {/* 核心洞察 */}
            {currentData.ai_insights.key_insights && currentData.ai_insights.key_insights.length > 0 && (
              <div className="mb-4">
                <div className="text-sm font-semibold mb-2 text-emerald-100">💡 关键洞察</div>
                <ul className="space-y-2">
                  {currentData.ai_insights.key_insights.map((insight: string, index: number) => (
                    <li key={index} className="flex items-start">
                      <span className="mr-2">•</span>
                      <span>{insight}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {/* 今日焦点 */}
            {currentData.ai_insights.today_focus && (
              <div className="bg-white/10 rounded-xl p-4 mb-4">
                <div className="text-sm text-emerald-100 mb-1">🎯 今日焦点</div>
                <div className="text-lg font-semibold">{currentData.ai_insights.today_focus}</div>
              </div>
            )}
            
            {/* 警告 */}
            {currentData.ai_insights.warnings && currentData.ai_insights.warnings.length > 0 && (
              <div className="bg-orange-500/30 rounded-xl p-3 mb-4">
                <div className="text-sm font-semibold mb-1">⚠️ 注意事项</div>
                {currentData.ai_insights.warnings.map((warning: string, index: number) => (
                  <div key={index} className="text-sm">{warning}</div>
                ))}
              </div>
            )}
            
            {/* 鼓励 */}
            {currentData.ai_insights.encouragement && (
              <div className="text-center italic text-emerald-100 mt-4 text-lg">
                "{currentData.ai_insights.encouragement}"
              </div>
            )}
          </div>
        )}

        {/* AI 详细建议 */}
        {currentData?.ai_advice && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">🧠 AI 个性化建议</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {currentData.ai_advice.sleep && (
                <div className="p-4 bg-indigo-50 rounded-xl">
                  <div className="font-semibold text-indigo-700 mb-2">😴 睡眠建议</div>
                  <p className="text-gray-700 text-sm">{currentData.ai_advice.sleep}</p>
                </div>
              )}
              {currentData.ai_advice.activity && (
                <div className="p-4 bg-green-50 rounded-xl">
                  <div className="font-semibold text-green-700 mb-2">🏃 运动建议</div>
                  <p className="text-gray-700 text-sm">{currentData.ai_advice.activity}</p>
                </div>
              )}
              {currentData.ai_advice.heart_health && (
                <div className="p-4 bg-red-50 rounded-xl">
                  <div className="font-semibold text-red-700 mb-2">❤️ 心血管建议</div>
                  <p className="text-gray-700 text-sm">{currentData.ai_advice.heart_health}</p>
                </div>
              )}
              {currentData.ai_advice.recovery && (
                <div className="p-4 bg-amber-50 rounded-xl">
                  <div className="font-semibold text-amber-700 mb-2">🧘 恢复建议</div>
                  <p className="text-gray-700 text-sm">{currentData.ai_advice.recovery}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 环境信息与运动推荐 */}
        {currentData?.environment && (
          <div className="bg-gradient-to-r from-sky-500 to-cyan-600 rounded-2xl shadow-lg p-6 mb-6 text-white">
            <h2 className="text-xl font-bold mb-4">🌤️ 今日环境与运动推荐</h2>
            
            {/* 天气和空气质量摘要 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              {currentData.environment.weather?.available && (
                <>
                  <div className="bg-white/10 rounded-xl p-3 text-center">
                    <div className="text-3xl mb-1">🌡️</div>
                    <div className="text-sm opacity-80">温度</div>
                    <div className="text-xl font-bold">
                      {currentData.environment.weather.temperature ?? '-'}°C
                    </div>
                    <div className="text-xs opacity-70">
                      体感 {currentData.environment.weather.feels_like ?? '-'}°C
                    </div>
                  </div>
                  <div className="bg-white/10 rounded-xl p-3 text-center">
                    <div className="text-3xl mb-1">☁️</div>
                    <div className="text-sm opacity-80">天气</div>
                    <div className="text-lg font-bold">
                      {currentData.environment.weather.weather || '-'}
                    </div>
                    <div className="text-xs opacity-70">
                      湿度 {currentData.environment.weather.humidity ?? '-'}%
                    </div>
                  </div>
                </>
              )}
              {currentData.environment.air_quality?.available && (
                <>
                  <div className="bg-white/10 rounded-xl p-3 text-center">
                    <div className="text-3xl mb-1">💨</div>
                    <div className="text-sm opacity-80">空气质量</div>
                    <div className="text-xl font-bold">
                      {currentData.environment.air_quality.aqi ?? '-'}
                    </div>
                    <div className="text-xs opacity-70">
                      {currentData.environment.air_quality.level || '-'}
                    </div>
                  </div>
                  <div className="bg-white/10 rounded-xl p-3 text-center">
                    <div className="text-3xl mb-1">🏃</div>
                    <div className="text-sm opacity-80">户外运动</div>
                    <div className="text-xl font-bold">
                      {currentData.environment.exercise?.outdoor_suitable ? '✅ 适宜' : '⚠️ 不宜'}
                    </div>
                    <div className="text-xs opacity-70">
                      评分 {currentData.environment.exercise?.score ?? '-'}/100
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* 环境建议 */}
            {currentData.environment.advices && currentData.environment.advices.length > 0 && (
              <div className="bg-white/10 rounded-xl p-4 mb-4">
                <div className="text-sm font-semibold mb-2 text-cyan-100">💡 环境健康建议</div>
                <ul className="space-y-1">
                  {currentData.environment.advices.slice(0, 3).map((advice: string, i: number) => (
                    <li key={i} className="text-sm flex items-start">
                      <span className="mr-2">•</span>
                      <span>{advice}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 环境警告 */}
            {currentData.environment.warnings && currentData.environment.warnings.length > 0 && (
              <div className="bg-orange-500/30 rounded-xl p-3 mb-4">
                <div className="text-sm font-semibold mb-1">⚠️ 环境注意事项</div>
                {currentData.environment.warnings.map((warning: string, i: number) => (
                  <div key={i} className="text-sm">{warning}</div>
                ))}
              </div>
            )}

            {/* 推荐活动 */}
            {currentData.environment.exercise?.recommended_activities && 
             currentData.environment.exercise.recommended_activities.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <span className="text-sm opacity-80">推荐活动:</span>
                {currentData.environment.exercise.recommended_activities.map((activity: string, i: number) => (
                  <span key={i} className="px-3 py-1 bg-white/20 rounded-full text-sm">
                    {activity}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* AI 运动推荐 */}
        {(currentData?.llm_analysis?.exercise_recommendations || currentData?.exercise_recommendations) && (
          <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">🏋️ AI 运动推荐</h2>
            
            {/* 环境建议 */}
            {(currentData?.llm_analysis?.environment_advice || currentData?.ai_advice?.environment) && (
              <div className="mb-4 p-4 bg-sky-50 rounded-xl">
                <div className="font-semibold text-sky-700 mb-2">🌤️ 基于今日环境的运动建议</div>
                <p className="text-gray-700 text-sm">
                  {currentData?.llm_analysis?.environment_advice || currentData?.ai_advice?.environment}
                </p>
              </div>
            )}
            
            {/* 具体运动推荐 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(currentData?.llm_analysis?.exercise_recommendations || currentData?.exercise_recommendations || [])
                .slice(0, 3)
                .map((rec: ExerciseRecommendation, index: number) => (
                <div key={index} className={`p-4 rounded-xl border-2 ${
                  rec.location === '室内' ? 'bg-purple-50 border-purple-200' : 'bg-green-50 border-green-200'
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className={`text-lg font-bold ${
                      rec.location === '室内' ? 'text-purple-700' : 'text-green-700'
                    }`}>
                      {rec.type}
                    </span>
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      rec.location === '室内' ? 'bg-purple-100 text-purple-600' : 'bg-green-100 text-green-600'
                    }`}>
                      {rec.location}
                    </span>
                  </div>
                  <div className="space-y-1 text-sm text-gray-600">
                    <div className="flex items-center">
                      <span className="w-16 text-gray-500">时长:</span>
                      <span className="font-medium">{rec.duration}</span>
                    </div>
                    <div className="flex items-center">
                      <span className="w-16 text-gray-500">强度:</span>
                      <span className={`font-medium ${
                        rec.intensity === '高' ? 'text-red-600' : 
                        rec.intensity === '中' ? 'text-orange-600' : 'text-green-600'
                      }`}>{rec.intensity}</span>
                    </div>
                    <div className="flex items-center">
                      <span className="w-16 text-gray-500">时间:</span>
                      <span className="font-medium">{rec.best_time}</span>
                    </div>
                  </div>
                  {rec.reason && (
                    <div className="mt-2 pt-2 border-t border-gray-200">
                      <p className="text-xs text-gray-500">{rec.reason}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 智能建议 */}
        <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl shadow-lg p-6 mb-6 text-white">
          <h2 className="text-xl font-bold mb-4">📋 智能建议</h2>
          <ul className="space-y-3">
            {(currentData?.enhanced_recommendations || currentData?.priority_recommendations || []).map((rec: string, index: number) => (
              <li key={index} className="flex items-start">
                <span className="mr-3 text-xl">{index === 0 ? '⭐' : '•'}</span>
                <span className={index === 0 ? 'font-semibold text-lg' : ''}>{rec}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* 今日目标 */}
        <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
          <h2 className="text-xl font-bold text-gray-800 mb-4">📋 今日目标</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(currentData?.daily_goals || []).map((goal: { category: string; goal: string; icon: string; target_value: number; unit: string }, index: number) => {
              // 根据目标类别确定跳转链接
              const getGoalLink = (category: string) => {
                switch (category) {
                  case 'activity':
                    return '/checkin';
                  case 'sleep':
                    return '/garmin';
                  case 'exercise':
                    return '/checkin';
                  case 'hydration':
                    return '/water';
                  default:
                    return '/checkin';
                }
              };
              
              return (
                <Link
                  key={index}
                  href={getGoalLink(goal.category)}
                  className="flex items-center p-4 bg-gray-50 rounded-xl hover:bg-indigo-50 hover:shadow-md transition-all duration-200 cursor-pointer group"
                >
                  <span className="text-3xl mr-4 group-hover:scale-110 transition-transform">{goal.icon}</span>
                  <div className="flex-1">
                    <div className="font-semibold text-gray-800 group-hover:text-indigo-700">{goal.goal}</div>
                    <div className="text-sm text-gray-500">
                      目标: {goal.target_value.toLocaleString()} {goal.unit}
                    </div>
                  </div>
                  <span className="text-gray-400 group-hover:text-indigo-500 transition-colors">→</span>
                </Link>
              );
            })}
          </div>
        </div>

        {/* 详细分析 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 睡眠分析 */}
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-800">😴 睡眠分析</h3>
              <div className="flex items-center">
                <span className={`w-3 h-3 rounded-full mr-2 ${statusColors[currentData?.sleep_analysis?.status || 'unknown']}`}></span>
                <span className="text-sm text-gray-600">{statusLabels[currentData?.sleep_analysis?.status || 'unknown']}</span>
                <span className="ml-2">{trendIcons[currentData?.sleep_analysis?.trend || 'stable']}</span>
              </div>
            </div>
            
            <div className="text-gray-600 mb-4">
              {currentData?.sleep_analysis?.quality_assessment || '暂无评估'}
            </div>
            
            {(currentData?.sleep_analysis?.issues || []).length > 0 && (
              <div className="mb-4">
                <div className="text-sm font-semibold text-red-600 mb-1">问题:</div>
                <ul className="text-sm text-gray-600">
                  {currentData.sleep_analysis.issues.map((issue: string, i: number) => (
                    <li key={i}>• {issue}</li>
                  ))}
                </ul>
              </div>
            )}
            
            {(currentData?.sleep_analysis?.recommendations || []).length > 0 && (
              <div>
                <div className="text-sm font-semibold text-green-600 mb-1">建议:</div>
                <ul className="text-sm text-gray-600">
                  {currentData.sleep_analysis.recommendations.slice(0, 2).map((rec: string, i: number) => (
                    <li key={i}>• {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* 活动分析 */}
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-800">🏃 活动分析</h3>
              <div className="flex items-center">
                <span className={`w-3 h-3 rounded-full mr-2 ${statusColors[currentData?.activity_analysis?.status || 'unknown']}`}></span>
                <span className="text-sm text-gray-600">{statusLabels[currentData?.activity_analysis?.status || 'unknown']}</span>
                <span className="ml-2">{trendIcons[currentData?.activity_analysis?.trend || 'stable']}</span>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-2 mb-4">
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{currentData?.activity_analysis?.steps?.toLocaleString() || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">步数</div>
              </div>
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{currentData?.activity_analysis?.active_minutes || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">活动分钟</div>
              </div>
            </div>
            
            {(currentData?.activity_analysis?.recommendations || []).length > 0 && (
              <div>
                <div className="text-sm font-semibold text-green-600 mb-1">建议:</div>
                <ul className="text-sm text-gray-600">
                  {currentData.activity_analysis.recommendations.slice(0, 2).map((rec: string, i: number) => (
                    <li key={i}>• {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* 心率分析 */}
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-800">❤️ 心率分析</h3>
              <div className="flex items-center">
                <span className={`w-3 h-3 rounded-full mr-2 ${statusColors[currentData?.heart_rate_analysis?.status || 'unknown']}`}></span>
                <span className="text-sm text-gray-600">{statusLabels[currentData?.heart_rate_analysis?.status || 'unknown']}</span>
                <span className="ml-2">{trendIcons[currentData?.heart_rate_analysis?.trend || 'stable']}</span>
              </div>
            </div>
            
            <div className="grid grid-cols-3 gap-2 mb-4">
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{currentData?.heart_rate_analysis?.resting_hr || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">静息心率</div>
              </div>
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{currentData?.heart_rate_analysis?.avg_hr || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">平均心率</div>
              </div>
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{currentData?.heart_rate_analysis?.hrv || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">HRV</div>
              </div>
            </div>
            
            {(currentData?.heart_rate_analysis?.recommendations || []).length > 0 && (
              <div>
                <div className="text-sm font-semibold text-green-600 mb-1">建议:</div>
                <ul className="text-sm text-gray-600">
                  {currentData.heart_rate_analysis.recommendations.slice(0, 2).map((rec: string, i: number) => (
                    <li key={i}>• {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* 压力与恢复 */}
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-800">🧘 压力与恢复</h3>
              <span className={`text-sm px-2 py-1 rounded font-semibold ${
                currentData?.stress_analysis?.recovery_status === 'well_recovered' 
                  ? 'bg-green-100 text-green-800' 
                  : currentData?.stress_analysis?.recovery_status === 'needs_rest' 
                  ? 'bg-orange-100 text-orange-800' 
                  : 'bg-gray-200 text-gray-800'
              }`}>
                {currentData?.stress_analysis?.recovery_status === 'well_recovered' ? '✅ 恢复良好' :
                 currentData?.stress_analysis?.recovery_status === 'needs_rest' ? '⚠️ 需要休息' :
                 '➡️ 部分恢复'}
              </span>
            </div>
            
            <div className="grid grid-cols-2 gap-2 mb-4">
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-lg font-bold text-gray-900">{currentData?.stress_analysis?.stress_level || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">压力水平</div>
              </div>
              <div className="text-center p-2 bg-gray-50 rounded">
                {(() => {
                  const currentBattery = currentData?.raw_data?.body_battery_current;
                  const peakBattery = currentData?.stress_analysis?.body_battery_highest;
                  const displayValue = currentBattery ?? peakBattery;
                  const hasCurrent = currentBattery !== null && currentBattery !== undefined;
                  return (
                    <>
                      <div className={`text-lg font-bold ${
                        displayValue !== null && displayValue !== undefined
                          ? (displayValue >= 80 ? 'text-green-600' : displayValue >= 50 ? 'text-yellow-600' : 'text-red-500')
                          : 'text-gray-900'
                      }`}>
                        {displayValue ?? '-'}
                      </div>
                      <div className="text-xs text-gray-600 font-medium">
                        {hasCurrent ? '当前电量' : '电量峰值'}
                      </div>
                      {hasCurrent && peakBattery && (
                        <div className="text-xs text-gray-500">峰值 {peakBattery}</div>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
            
            {(currentData?.stress_analysis?.recommendations || []).length > 0 && (
              <div>
                <div className="text-sm font-semibold text-green-600 mb-1">建议:</div>
                <ul className="text-sm text-gray-600">
                  {currentData.stress_analysis.recommendations.slice(0, 2).map((rec: string, i: number) => (
                    <li key={i}>• {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
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

