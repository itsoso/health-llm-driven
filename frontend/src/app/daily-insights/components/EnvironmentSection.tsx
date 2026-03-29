'use client';

import { DailyRecommendation, ExerciseRecommendation } from '../types';

interface EnvironmentSectionProps {
  currentData: DailyRecommendation;
}

export function EnvironmentSection({ currentData }: EnvironmentSectionProps) {
  return (
    <>
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
    </>
  );
}
