'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { dailyRecommendationApi } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

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
  };
  llm_analysis?: {
    available: boolean;
    error?: string;
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

function DailyInsightsContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [activeTab, setActiveTab] = useState<'one-day' | 'seven-day'>('one-day');

  // 获取建议数据（1天和7天）
  const { data: recommendationsData, isLoading, error, refetch } = useQuery({
    queryKey: ['daily-recommendations'],
    queryFn: () => dailyRecommendationApi.getMyRecommendations(true),
    enabled: isAuthenticated,
  });

  const oneDayData = recommendationsData?.data?.one_day;
  const sevenDayData = recommendationsData?.data?.seven_day;
  const isCached = recommendationsData?.data?.cached;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
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
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="text-6xl mb-4">📊</div>
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

  if (!recommendationsData?.data) return null;

  const currentData = activeTab === 'one-day' ? oneDayData : sevenDayData;
  
  if (!currentData || currentData.status === 'no_data') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="text-6xl mb-4">📊</div>
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
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
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
                最近7天建议
              </button>
            </div>
            {isCached && (
              <span className="text-xs px-3 py-1 bg-green-100 text-green-700 rounded-full font-medium">
                ✓ 缓存数据
              </span>
            )}
          </div>
          
          {/* 头部信息 */}
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
        </div>

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
            <div className="text-2xl font-bold text-yellow-600">
              {activeTab === 'seven-day' && sevenDayData?.averages?.body_battery 
                ? sevenDayData.averages.body_battery 
                : currentData?.raw_data?.body_battery_highest || '-'}
            </div>
            <div className="text-xs text-gray-600">最高值</div>
          </div>
        </div>

        {/* AI 健康摘要 */}
        {currentData?.ai_insights && (
          <div className="bg-gradient-to-r from-emerald-500 to-teal-600 rounded-2xl shadow-lg p-6 mb-6 text-white">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">🤖 AI 健康顾问</h2>
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
                <div className="text-lg font-bold text-gray-900">{currentData?.stress_analysis?.body_battery_highest || '-'}</div>
                <div className="text-xs text-gray-600 font-medium">身体电量峰值</div>
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

