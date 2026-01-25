'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = '/api';

// 类别配置
const CATEGORY_CONFIG: Record<string, { icon: string; label: string; color: string }> = {
  exercise: { icon: '\u{1F3C3}', label: '运动建议', color: 'emerald' },
  diet: { icon: '\u{1F957}', label: '饮食建议', color: 'orange' },
  sleep: { icon: '\u{1F634}', label: '睡眠建议', color: 'blue' },
  supplement: { icon: '\u{1F48A}', label: '补剂建议', color: 'purple' },
  general: { icon: '\u{2728}', label: '综合建议', color: 'pink' },
};

const CATEGORY_ORDER = ['exercise', 'diet', 'sleep', 'supplement', 'general'];

interface ExternalRecommendation {
  id: number;
  category: string;
  title: string;
  content: string;
  source_name: string;
  recommendation_date: string;
  created_at: string;
}

interface TodayRecommendations {
  date: string;
  has_recommendations: boolean;
  categories: Record<string, ExternalRecommendation[]>;
}

export default function ExternalAdvicePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'today' | 'history'>('today');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [todayData, setTodayData] = useState<TodayRecommendations | null>(null);
  const [historyData, setHistoryData] = useState<ExternalRecommendation[]>([]);

  const getToken = () => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('auth_token');
    }
    return null;
  };

  useEffect(() => {
    loadData();
  }, [viewMode, selectedDate, selectedCategory]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    const token = getToken();

    if (!token) {
      router.push('/login');
      return;
    }

    try {
      if (viewMode === 'today') {
        const res = await fetch(`${API_BASE}/external-recommendations/today`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          setTodayData(await res.json());
        } else if (res.status === 401) {
          router.push('/login');
          return;
        } else {
          throw new Error('加载失败');
        }
      } else {
        let url = `${API_BASE}/external-recommendations?limit=50&date=${selectedDate}`;
        if (selectedCategory) {
          url += `&category=${selectedCategory}`;
        }
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.ok) {
          setHistoryData(await res.json());
        } else if (res.status === 401) {
          router.push('/login');
          return;
        } else {
          throw new Error('加载失败');
        }
      }
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch {
      return '';
    }
  };

  const renderRecommendation = (rec: ExternalRecommendation) => {
    const config = CATEGORY_CONFIG[rec.category] || { icon: '\u{1F4CB}', label: rec.category, color: 'gray' };

    return (
      <div
        key={rec.id}
        className={`bg-gray-800/50 rounded-xl p-5 border-l-4 border-${config.color}-500`}
      >
        <div className="flex justify-between items-start mb-3">
          <h4 className="text-lg font-semibold text-white flex-1">{rec.title}</h4>
          <span className="ml-3 px-3 py-1 bg-blue-500/20 rounded-full text-xs text-blue-400 flex items-center gap-1">
            <span>{'\u{1F517}'}</span>
            <span className="max-w-[100px] truncate">{rec.source_name}</span>
          </span>
        </div>
        <p className="text-gray-300 whitespace-pre-wrap leading-relaxed">{rec.content}</p>
        <div className="mt-3 text-right text-xs text-gray-500">
          {formatTime(rec.created_at)}
        </div>
      </div>
    );
  };

  const renderCategorySection = (category: string, recommendations: ExternalRecommendation[]) => {
    const config = CATEGORY_CONFIG[category] || { icon: '\u{1F4CB}', label: category, color: 'gray' };

    return (
      <div key={category} className="mb-8">
        <h3 className={`text-xl font-bold text-${config.color}-400 mb-4 flex items-center gap-2`}>
          <span className="text-2xl">{config.icon}</span>
          {config.label}
          <span className="text-sm text-gray-500 font-normal">({recommendations.length})</span>
        </h3>
        <div className="space-y-4">
          {recommendations.map(renderRecommendation)}
        </div>
      </div>
    );
  };

  const isEmpty = viewMode === 'today'
    ? !todayData?.has_recommendations
    : historyData.length === 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <span>{'\u{1F4E1}'}</span> 外部健康建议
            </h1>
            <button
              onClick={loadData}
              className="px-4 py-2 bg-purple-600/30 hover:bg-purple-600/50 rounded-lg text-purple-300 text-sm transition-colors"
            >
              {'\u{21BB}'} 刷新
            </button>
          </div>
          <p className="text-gray-400">来自 AI 助手和外部健康服务的个性化建议</p>

          {/* View Mode Tabs */}
          <div className="flex gap-2 mt-6">
            <button
              onClick={() => setViewMode('today')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                viewMode === 'today'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-700/50 text-gray-300 hover:bg-gray-700'
              }`}
            >
              今日
            </button>
            <button
              onClick={() => setViewMode('history')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                viewMode === 'history'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-700/50 text-gray-300 hover:bg-gray-700'
              }`}
            >
              历史
            </button>
          </div>

          {/* History Filters */}
          {viewMode === 'history' && (
            <div className="mt-4 space-y-4">
              <div className="flex items-center gap-4">
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="px-4 py-2 bg-gray-700/50 border border-gray-600 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setSelectedCategory(null)}
                  className={`px-3 py-1 rounded-full text-sm transition-colors ${
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
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3 py-1 rounded-full text-sm transition-colors ${
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
          )}
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-12 h-12 border-4 border-purple-500/30 border-t-purple-500 rounded-full animate-spin"></div>
            <p className="mt-4 text-gray-400">加载中...</p>
          </div>
        ) : error ? (
          <div className="text-center py-20">
            <div className="text-6xl mb-4">{'\u{1F614}'}</div>
            <p className="text-gray-400 mb-6">{error}</p>
            <button
              onClick={loadData}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg text-white transition-colors"
            >
              点击重试
            </button>
          </div>
        ) : isEmpty ? (
          <div className="text-center py-20">
            <div className="text-6xl mb-4">{'\u{1F4ED}'}</div>
            <h3 className="text-2xl font-bold text-white mb-3">暂无外部建议</h3>
            <p className="text-gray-400 max-w-md mx-auto">
              外部 AI 健康助手（如 Browser-LLM-Driven、GPT Health 等）分析您的健康数据后，会在这里展示个性化建议。
            </p>
            <p className="text-gray-500 text-sm mt-4">
              您可以在「设置」中创建 API Key 以允许外部系统访问您的数据。
            </p>
          </div>
        ) : (
          <>
            {/* Today View */}
            {viewMode === 'today' && todayData && (
              <>
                {CATEGORY_ORDER.map((category) => {
                  const recs = todayData.categories[category];
                  if (!recs || recs.length === 0) return null;
                  return renderCategorySection(category, recs);
                })}
              </>
            )}

            {/* History View */}
            {viewMode === 'history' && historyData.length > 0 && (
              <>
                {(() => {
                  const grouped: Record<string, ExternalRecommendation[]> = {};
                  historyData.forEach((rec) => {
                    if (!grouped[rec.category]) {
                      grouped[rec.category] = [];
                    }
                    grouped[rec.category].push(rec);
                  });

                  return CATEGORY_ORDER.map((category) => {
                    const recs = grouped[category];
                    if (!recs || recs.length === 0) return null;
                    return renderCategorySection(category, recs);
                  });
                })()}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
