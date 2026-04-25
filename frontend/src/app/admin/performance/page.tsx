'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  Activity,
  TrendingUp,
  AlertTriangle,
  Clock,
  Zap,
  Smartphone,
  Monitor,
  RefreshCw
} from 'lucide-react';

interface PerformanceOverview {
  platform: string;
  total_metrics: number;
  avg_page_load: number;
  avg_api_call: number;
  error_rate: number;
  slow_pages: Array<{
    name: string;
    avg_duration: number;
    count: number;
  }>;
  slow_apis: Array<{
    name: string;
    avg_duration: number;
    count: number;
  }>;
}

interface PagePerformance {
  page_name: string;
  platform: string;
  total_visits: number;
  avg_duration: number;
  p50_duration: number;
  p90_duration: number;
  p95_duration: number;
  p99_duration: number;
  error_rate: number;
}

interface APIPerformance {
  api_name: string;
  total_calls: number;
  avg_duration: number;
  p50_duration: number;
  p90_duration: number;
  p95_duration: number;
  p99_duration: number;
  success_rate: number;
  error_rate: number;
}

export default function PerformanceMonitorPage() {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(24); // 小时
  const [selectedPlatform, setSelectedPlatform] = useState<'all' | 'mini_program' | 'web'>('all');

  const [overview, setOverview] = useState<PerformanceOverview[]>([]);
  const [pagePerformance, setPagePerformance] = useState<PagePerformance[]>([]);
  const [apiPerformance, setAPIPerformance] = useState<APIPerformance[]>([]);

  const [activeTab, setActiveTab] = useState<'overview' | 'pages' | 'apis'>('overview');

  // 页面加载时滚动到顶部
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    // 等待 token 加载完成后再请求数据
    if (token) {
      loadData();
    }
  }, [timeRange, selectedPlatform, token]);

  const loadData = async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadOverview(),
        loadPagePerformance(),
        loadAPIPerformance()
      ]);
    } finally {
      setLoading(false);
    }
  };

  const loadOverview = async () => {
    if (!token) {
      console.warn('Token 未加载，跳过请求');
      return;
    }

    try {
      const params = new URLSearchParams({ hours: timeRange.toString() });
      if (selectedPlatform !== 'all') {
        params.append('platform', selectedPlatform);
      }

      const response = await fetch(
        `/api/v1/performance/overview?${params}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setOverview(data);
      } else if (response.status === 401) {
        console.error('未授权，请重新登录');
      }
    } catch (error) {
      console.error('加载性能概览失败:', error);
    }
  };

  const loadPagePerformance = async () => {
    if (selectedPlatform === 'all') return;
    if (!token) {
      console.warn('Token 未加载，跳过请求');
      return;
    }

    try {
      const params = new URLSearchParams({
        platform: selectedPlatform,
        hours: timeRange.toString()
      });

      const response = await fetch(
        `/api/v1/performance/pages?${params}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setPagePerformance(data);
      } else if (response.status === 401) {
        console.error('未授权，请重新登录');
      }
    } catch (error) {
      console.error('加载页面性能失败:', error);
    }
  };

  const loadAPIPerformance = async () => {
    if (!token) {
      console.warn('Token 未加载，跳过请求');
      return;
    }

    try {
      const params = new URLSearchParams({ hours: timeRange.toString() });

      const response = await fetch(
        `/api/v1/performance/apis?${params}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setAPIPerformance(data);
      } else if (response.status === 401) {
        console.error('未授权，请重新登录');
      }
    } catch (error) {
      console.error('加载 API 性能失败:', error);
    }
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const getDurationColor = (ms: number, type: 'page' | 'api') => {
    const threshold = type === 'page' ? 3000 : 1000;
    if (ms > threshold) return 'text-red-800';
    if (ms > threshold * 0.7) return 'text-orange-700';
    return 'text-green-800';
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gray-50 pt-8 pb-6 px-6 antialiased">
        <div className="max-w-7xl mx-auto">
          {/* 头部 */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
                  <Activity className="w-8 h-8 text-purple-600" />
                  性能监控中心
                </h1>
                <p className="text-gray-600 mt-1">实时监控小程序和 Web 端的性能指标</p>
              </div>

              <button
                onClick={loadData}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                刷新数据
              </button>
            </div>

            {/* 筛选器 */}
            <div className="flex gap-4">
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedPlatform('all')}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                    selectedPlatform === 'all'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  全部平台
                </button>
                <button
                  onClick={() => setSelectedPlatform('mini_program')}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                    selectedPlatform === 'mini_program'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <Smartphone className="w-4 h-4" />
                  小程序
                </button>
                <button
                  onClick={() => setSelectedPlatform('web')}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                    selectedPlatform === 'web'
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <Monitor className="w-4 h-4" />
                  Web
                </button>
              </div>

              <select
                value={timeRange}
                onChange={(e) => setTimeRange(Number(e.target.value))}
                className="px-4 py-2 bg-white border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              >
                <option value={1}>最近 1 小时</option>
                <option value={6}>最近 6 小时</option>
                <option value={24}>最近 24 小时</option>
                <option value={72}>最近 3 天</option>
                <option value={168}>最近 7 天</option>
              </select>
            </div>
          </div>

          {/* 标签页 */}
          <div className="flex gap-2 mb-6">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                activeTab === 'overview'
                  ? 'bg-white text-purple-600 shadow-md'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              概览
            </button>
            <button
              onClick={() => setActiveTab('pages')}
              className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                activeTab === 'pages'
                  ? 'bg-white text-purple-600 shadow-md'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              页面性能
            </button>
            <button
              onClick={() => setActiveTab('apis')}
              className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                activeTab === 'apis'
                  ? 'bg-white text-purple-600 shadow-md'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              API 性能
            </button>
          </div>

          {/* 概览标签页 */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {overview.map((platform) => (
                <div key={platform.platform} className="bg-white rounded-xl shadow-md p-6">
                  <div className="flex items-center gap-2 mb-6">
                    {platform.platform === 'mini_program' ? (
                      <Smartphone className="w-6 h-6 text-purple-600" />
                    ) : (
                      <Monitor className="w-6 h-6 text-blue-600" />
                    )}
                    <h2 className="text-xl font-bold">
                      {platform.platform === 'mini_program' ? '小程序' : 'Web 端'}
                    </h2>
                  </div>

                  {/* 关键指标 */}
                  <div className="grid grid-cols-4 gap-4 mb-6">
                    <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-purple-600 mb-2">
                        <Activity className="w-5 h-5" />
                        <span className="text-sm font-semibold">总指标数</span>
                      </div>
                      <div className="text-3xl font-extrabold text-purple-900 tabular-nums tracking-tight">
                        {platform.total_metrics.toLocaleString()}
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-blue-600 mb-2">
                        <Clock className="w-5 h-5" />
                        <span className="text-sm font-semibold">平均页面加载</span>
                      </div>
                      <div className={`text-3xl font-extrabold tabular-nums tracking-tight ${getDurationColor(platform.avg_page_load, 'page')}`}>
                        {formatDuration(platform.avg_page_load)}
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-green-600 mb-2">
                        <Zap className="w-5 h-5" />
                        <span className="text-sm font-semibold">平均 API 响应</span>
                      </div>
                      <div className={`text-3xl font-extrabold tabular-nums tracking-tight ${getDurationColor(platform.avg_api_call, 'api')}`}>
                        {formatDuration(platform.avg_api_call)}
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-red-50 to-red-100 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-red-600 mb-2">
                        <AlertTriangle className="w-5 h-5" />
                        <span className="text-sm font-semibold">错误率</span>
                      </div>
                      <div className="text-3xl font-extrabold text-red-900 tabular-nums tracking-tight">
                        {platform.error_rate.toFixed(2)}%
                      </div>
                    </div>
                  </div>

                  {/* 慢页面和慢 API */}
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                        <TrendingUp className="w-5 h-5 text-orange-600" />
                        慢页面 (P95 &gt; 3s)
                      </h3>
                      {platform.slow_pages.length === 0 ? (
                        <p className="text-gray-500 text-sm">暂无慢页面 ✅</p>
                      ) : (
                        <div className="space-y-2">
                          {platform.slow_pages.map((page, idx) => (
                            <div key={idx} className="flex justify-between items-center p-3 bg-orange-50 rounded-lg">
                              <div>
                                <div className="font-semibold text-sm text-gray-900">{page.name}</div>
                                <div className="text-xs text-gray-600 font-medium">访问 {page.count} 次</div>
                              </div>
                              <div className="text-orange-600 font-bold text-lg tabular-nums">
                                {formatDuration(page.avg_duration)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div>
                      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                        <TrendingUp className="w-5 h-5 text-red-600" />
                        慢 API (P95 &gt; 1s)
                      </h3>
                      {platform.slow_apis.length === 0 ? (
                        <p className="text-gray-500 text-sm">暂无慢 API ✅</p>
                      ) : (
                        <div className="space-y-2">
                          {platform.slow_apis.map((api, idx) => (
                            <div key={idx} className="flex justify-between items-center p-3 bg-red-50 rounded-lg">
                              <div>
                                <div className="font-semibold text-sm text-gray-900">{api.name}</div>
                                <div className="text-xs text-gray-600 font-medium">调用 {api.count} 次</div>
                              </div>
                              <div className="text-red-600 font-bold text-lg tabular-nums">
                                {formatDuration(api.avg_duration)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 页面性能标签页 */}
          {activeTab === 'pages' && selectedPlatform !== 'all' && (
            <div className="bg-white rounded-xl shadow-md overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        页面名称
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        访问次数
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        平均耗时
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P50
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P90
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P95
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P99
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        错误率
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {pagePerformance.map((page, idx) => (
                      <tr key={idx} className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900">
                          {page.page_name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {page.total_visits.toLocaleString()}
                        </td>
                        <td className={`px-6 py-4 whitespace-nowrap text-sm font-bold tabular-nums ${getDurationColor(page.avg_duration, 'page')}`}>
                          {formatDuration(page.avg_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {formatDuration(page.p50_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {formatDuration(page.p90_duration)}
                        </td>
                        <td className={`px-6 py-4 whitespace-nowrap text-sm font-bold tabular-nums ${getDurationColor(page.p95_duration, 'page')}`}>
                          {formatDuration(page.p95_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {formatDuration(page.p99_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <span className={`px-2 py-1 rounded-full text-xs font-semibold tabular-nums ${
                            page.error_rate > 5 ? 'bg-red-100 text-red-800' :
                            page.error_rate > 1 ? 'bg-yellow-100 text-yellow-800' :
                            'bg-green-100 text-green-800'
                          }`}>
                            {page.error_rate.toFixed(2)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* API 性能标签页 */}
          {activeTab === 'apis' && (
            <div className="bg-white rounded-xl shadow-md overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        API 端点
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        调用次数
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        平均耗时
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P50
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P90
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P95
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        P99
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                        成功率
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {apiPerformance.map((api, idx) => (
                      <tr key={idx} className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4 text-sm font-semibold text-gray-900">
                          {api.api_name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {api.total_calls.toLocaleString()}
                        </td>
                        <td className={`px-6 py-4 whitespace-nowrap text-sm font-bold tabular-nums ${getDurationColor(api.avg_duration, 'api')}`}>
                          {formatDuration(api.avg_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {formatDuration(api.p50_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {formatDuration(api.p90_duration)}
                        </td>
                        <td className={`px-6 py-4 whitespace-nowrap text-sm font-bold tabular-nums ${getDurationColor(api.p95_duration, 'api')}`}>
                          {formatDuration(api.p95_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-700 tabular-nums">
                          {formatDuration(api.p99_duration)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <span className={`px-2 py-1 rounded-full text-xs font-semibold tabular-nums ${
                            api.success_rate < 95 ? 'bg-red-100 text-red-800' :
                            api.success_rate < 99 ? 'bg-yellow-100 text-yellow-800' :
                            'bg-green-100 text-green-800'
                          }`}>
                            {api.success_rate.toFixed(2)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
            </div>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}
