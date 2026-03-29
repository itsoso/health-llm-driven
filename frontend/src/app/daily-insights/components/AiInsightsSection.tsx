'use client';

import { DailyRecommendation } from '../types';

interface AiInsightsSectionProps {
  currentData: DailyRecommendation;
}

export function AiInsightsSection({ currentData }: AiInsightsSectionProps) {
  return (
    <>
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
              &quot;{currentData.ai_insights.encouragement}&quot;
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
    </>
  );
}
