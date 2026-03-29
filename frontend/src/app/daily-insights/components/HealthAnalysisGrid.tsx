'use client';

import Link from 'next/link';
import { DailyRecommendation, statusColors, statusLabels, trendIcons } from '../types';

interface HealthAnalysisGridProps {
  currentData: DailyRecommendation;
}

export function SmartRecommendations({ currentData }: HealthAnalysisGridProps) {
  return (
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
  );
}

export function DailyGoals({ currentData }: HealthAnalysisGridProps) {
  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-800 mb-4">📋 今日目标</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(currentData?.daily_goals || []).map((goal: { category: string; goal: string; icon: string; target_value: number; unit: string }, index: number) => {
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
  );
}

export function HealthAnalysisGrid({ currentData }: HealthAnalysisGridProps) {
  return (
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
  );
}
