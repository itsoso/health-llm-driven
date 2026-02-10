'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = '/api';

interface AIInsight {
  id: number;
  user_id: number;
  review_date: string;
  content: string;
  summary: string | null;
  health_snapshot: any;
  generated_at: string;
}

interface RealtimeRecommendation {
  id: number;
  user_id: number;
  content: string;
  recommendation_type: string;
  priority: string;
  context_data: any;
  location: any;
  weather_data: any;
  air_quality_data: any;
  generated_at: string;
  expires_at: string;
  is_active: number;
}

function AIInsightsContent() {
  const router = useRouter();
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [currentRecommendation, setCurrentRecommendation] = useState<RealtimeRecommendation | null>(null);
  const [activeTab, setActiveTab] = useState<'insights' | 'recommendations'>('insights');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      await Promise.all([
        loadInsights(),
        loadLatestRecommendation(),
      ]);
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  };

  const loadInsights = async () => {
    try {
      if (!token) return;

      const response = await fetch(`${API_BASE}/ai-insights/insights/daily?days=7`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load insights');
      }

      const data = await response.json();
      setInsights(data.items || []);
    } catch (error) {
      console.error('Failed to load insights:', error);
    }
  };

  const loadLatestRecommendation = async () => {
    try {
      if (!token) return;

      const response = await fetch(`${API_BASE}/ai-insights/recommendations/latest`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setCurrentRecommendation(data);
      }
    } catch (error) {
      console.error('Failed to load latest recommendation:', error);
    }
  };

  const handleGenerateInsight = async () => {
    if (!token) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/ai-insights/insights/daily/generate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to generate insight');
      }

      alert('✅ 今日洞察生成成功！');
      await loadInsights();
    } catch (error) {
      console.error('Failed to generate insight:', error);
      alert('❌ 生成失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateRecommendation = async () => {
    if (!token) return;

    setLoading(true);
    try {
      // 获取用户位置（简化版，实际应该使用地理位置API）
      const response = await fetch(`${API_BASE}/ai-insights/recommendations/realtime`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          city: '北京', // 默认城市，可以后续改进
          latitude: 39.9,
          longitude: 116.4,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate recommendation');
      }

      const data = await response.json();
      setCurrentRecommendation(data);
      alert('✅ 实时建议生成成功！');
    } catch (error) {
      console.error('Failed to generate recommendation:', error);
      alert('❌ 生成失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const formatDateTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'text-red-600 bg-red-50';
      case 'medium': return 'text-yellow-600 bg-yellow-50';
      case 'low': return 'text-green-600 bg-green-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const getPriorityLabel = (priority: string) => {
    switch (priority) {
      case 'high': return '🔴 紧急';
      case 'medium': return '🟡 重要';
      case 'low': return '🟢 常规';
      default: return '⚪ 一般';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        {/* 页面标题 */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent mb-3">
            🧠 AI 健康洞察
          </h1>
          <p className="text-gray-600">
            基于你的健康数据，AI 为你生成个性化的健康分析和实时建议
          </p>
        </div>

        {/* Tab切换 */}
        <div className="flex justify-center mb-8">
          <div className="inline-flex rounded-lg bg-white shadow-sm p-1">
            <button
              onClick={() => setActiveTab('insights')}
              className={`px-6 py-2.5 rounded-md font-medium transition-all ${
                activeTab === 'insights'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-gray-600 hover:text-indigo-600'
              }`}
            >
              📊 每日洞察
            </button>
            <button
              onClick={() => setActiveTab('recommendations')}
              className={`px-6 py-2.5 rounded-md font-medium transition-all ${
                activeTab === 'recommendations'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-gray-600 hover:text-indigo-600'
              }`}
            >
              ⚡ 实时建议
            </button>
          </div>
        </div>

        {/* 每日洞察标签页 */}
        {activeTab === 'insights' && (
          <div className="space-y-6">
            {/* 生成按钮 */}
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900 mb-2">生成今日洞察</h2>
                  <p className="text-gray-600">
                    基于今日健康数据生成AI分析报告
                  </p>
                </div>
                <button
                  onClick={handleGenerateInsight}
                  disabled={loading}
                  className={`px-8 py-3 rounded-xl font-semibold text-white transition-all ${
                    loading
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-gradient-to-r from-indigo-600 to-purple-600 hover:shadow-lg hover:scale-105'
                  }`}
                >
                  {loading ? '生成中...' : '🎯 生成洞察'}
                </button>
              </div>
            </div>

            {/* 洞察列表 */}
            {insights.length > 0 ? (
              <div className="space-y-6">
                <h3 className="text-lg font-semibold text-gray-700 px-2">
                  最近洞察（{insights.length}条）
                </h3>
                {insights.map((insight, index) => (
                  <div
                    key={insight.id}
                    className="bg-white rounded-xl shadow-lg p-6"
                  >
                    {/* 标题栏 */}
                    <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-100">
                      <div className="flex items-center space-x-3">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-indigo-600 text-white font-bold text-sm">
                          {insights.length - index}
                        </span>
                        <div>
                          <h3 className="font-bold text-gray-900 text-lg">
                            {formatDate(insight.review_date)}
                          </h3>
                          <p className="text-sm text-gray-500">
                            生成于 {formatDateTime(insight.generated_at)}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* 完整内容 - Markdown渲染 */}
                    <div className="prose prose-slate max-w-none
                      prose-headings:text-gray-900 prose-headings:font-bold
                      prose-p:text-gray-800 prose-p:leading-relaxed
                      prose-strong:text-gray-900 prose-strong:font-semibold
                      prose-ul:list-disc prose-ul:pl-6
                      prose-ol:list-decimal prose-ol:pl-6
                      prose-li:text-gray-800 prose-li:my-1
                      prose-code:bg-gray-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
                      prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg
                    ">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {insight.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-md p-12 text-center">
                <div className="text-6xl mb-4">📊</div>
                <p className="text-gray-500 text-lg">暂无洞察记录</p>
                <p className="text-gray-400 text-sm mt-2">
                  点击上方按钮生成你的第一份AI健康洞察
                </p>
              </div>
            )}
          </div>
        )}

        {/* 实时建议标签页 */}
        {activeTab === 'recommendations' && (
          <div className="space-y-6">
            {/* 生成按钮 */}
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900 mb-2">生成实时建议</h2>
                  <p className="text-gray-600">
                    结合当前时间、位置、天气、身体状态等生成个性化建议
                  </p>
                </div>
                <button
                  onClick={handleGenerateRecommendation}
                  disabled={loading}
                  className={`px-8 py-3 rounded-xl font-semibold text-white transition-all ${
                    loading
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-gradient-to-r from-purple-600 to-pink-600 hover:shadow-lg hover:scale-105'
                  }`}
                >
                  {loading ? '分析中...' : '⚡ 生成建议'}
                </button>
              </div>
            </div>

            {/* 当前建议展示 */}
            {currentRecommendation ? (
              <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
                <div className="bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <span className={`px-3 py-1 rounded-full text-sm font-semibold ${getPriorityColor(currentRecommendation.priority)}`}>
                        {getPriorityLabel(currentRecommendation.priority)}
                      </span>
                    </div>
                    <span className="text-white text-sm">
                      {formatDateTime(currentRecommendation.generated_at)}
                    </span>
                  </div>
                </div>

                <div className="p-6">
                  <div className="prose prose-slate max-w-none mb-6
                    prose-headings:text-gray-900 prose-headings:font-bold
                    prose-p:text-gray-800 prose-p:leading-relaxed
                    prose-strong:text-gray-900 prose-strong:font-semibold
                    prose-ul:list-disc prose-ul:pl-6
                    prose-ol:list-decimal prose-ol:pl-6
                    prose-li:text-gray-800 prose-li:my-1
                    prose-code:bg-gray-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
                  ">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {currentRecommendation.content}
                    </ReactMarkdown>
                  </div>

                  {/* 上下文信息 */}
                  {(currentRecommendation.weather_data || currentRecommendation.air_quality_data) && (
                    <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl p-5">
                      <h4 className="font-semibold text-gray-900 mb-3 flex items-center">
                        <span className="mr-2">📍</span>
                        上下文信息
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                        {currentRecommendation.weather_data && (
                          <div className="flex items-center space-x-2">
                            <span className="text-gray-600">天气:</span>
                            <span className="font-medium text-gray-900">
                              {currentRecommendation.weather_data.weather_condition}{' '}
                              {currentRecommendation.weather_data.temperature}°C
                            </span>
                          </div>
                        )}
                        {currentRecommendation.air_quality_data && (
                          <div className="flex items-center space-x-2">
                            <span className="text-gray-600">空气:</span>
                            <span className="font-medium text-gray-900">
                              AQI {currentRecommendation.air_quality_data.aqi}{' '}
                              {currentRecommendation.air_quality_data.quality_level}
                            </span>
                          </div>
                        )}
                        {currentRecommendation.location?.city && (
                          <div className="flex items-center space-x-2">
                            <span className="text-gray-600">位置:</span>
                            <span className="font-medium text-gray-900">
                              {currentRecommendation.location.city}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 过期时间 */}
                  {currentRecommendation.expires_at && (
                    <div className="mt-4 pt-4 border-t border-gray-100">
                      <p className="text-sm text-gray-500">
                        有效期至: {formatDateTime(currentRecommendation.expires_at)}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-md p-12 text-center">
                <div className="text-6xl mb-4">⚡</div>
                <p className="text-gray-500 text-lg">暂无实时建议</p>
                <p className="text-gray-400 text-sm mt-2">
                  点击上方按钮生成你的第一份实时健康建议
                </p>
              </div>
            )}
          </div>
        )}

        {/* API 文档 */}
        <div className="mt-12 bg-white rounded-2xl shadow-lg p-6">
          <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
            <span className="mr-2">📚</span>
            API 端点
          </h3>
          <div className="space-y-3">
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center space-x-3 mb-2">
                <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-semibold rounded">POST</span>
                <code className="text-sm text-gray-700">/api/ai-insights/insights/daily/generate</code>
              </div>
              <p className="text-sm text-gray-600">生成每日洞察</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center space-x-3 mb-2">
                <span className="px-2 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded">GET</span>
                <code className="text-sm text-gray-700">/api/ai-insights/insights/daily?days=7</code>
              </div>
              <p className="text-sm text-gray-600">获取最近N天洞察</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center space-x-3 mb-2">
                <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-semibold rounded">POST</span>
                <code className="text-sm text-gray-700">/api/ai-insights/recommendations/realtime</code>
              </div>
              <p className="text-sm text-gray-600">生成实时建议</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="flex items-center space-x-3 mb-2">
                <span className="px-2 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded">GET</span>
                <code className="text-sm text-gray-700">/api/ai-insights/recommendations/latest</code>
              </div>
              <p className="text-sm text-gray-600">获取最新有效建议</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AIInsightsPage() {
  return (
    <ProtectedRoute>
      <AIInsightsContent />
    </ProtectedRoute>
  );
}
