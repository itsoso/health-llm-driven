'use client';

import { formatDuration, HR_ZONE_COLORS } from './workoutUtils';
import { WorkoutDetail } from './workoutTypes';

interface WorkoutAnalysisProps {
  workoutDetail: WorkoutDetail;
  activeTab: 'stats' | 'laps' | 'intervals';
  hrZoneData: { name: string; value: number; color: string }[];
  showPostAnalysis: boolean;
  postAnalysis: any;
}

export default function WorkoutAnalysis({
  workoutDetail,
  activeTab,
  hrZoneData,
  showPostAnalysis,
  postAnalysis,
}: WorkoutAnalysisProps) {
  return (
    <>
      {/* HR Zone Chart (stats tab only) */}
      {activeTab === 'stats' && hrZoneData.length > 0 && (() => {
        const total = hrZoneData.reduce((sum, z) => sum + z.value, 0);
        const maxHR = workoutDetail?.max_heart_rate || 220;
        const hrZones = [
          {
            zone: 1, name: '热身', desc: '热身',
            range: `${Math.round(maxHR * 0.5)} - ${Math.round(maxHR * 0.6)} bpm`,
            color: HR_ZONE_COLORS[0], value: workoutDetail?.hr_zone_1_seconds || 0
          },
          {
            zone: 2, name: '脂肪燃烧', desc: '脂肪燃烧',
            range: `${Math.round(maxHR * 0.6)} - ${Math.round(maxHR * 0.7)} bpm`,
            color: HR_ZONE_COLORS[1], value: workoutDetail?.hr_zone_2_seconds || 0
          },
          {
            zone: 3, name: '有氧', desc: '有氧',
            range: `${Math.round(maxHR * 0.7)} - ${Math.round(maxHR * 0.8)} bpm`,
            color: HR_ZONE_COLORS[2], value: workoutDetail?.hr_zone_3_seconds || 0
          },
          {
            zone: 4, name: '临界心率', desc: '临界心率',
            range: `${Math.round(maxHR * 0.8)} - ${Math.round(maxHR * 0.9)} bpm`,
            color: HR_ZONE_COLORS[3], value: workoutDetail?.hr_zone_4_seconds || 0
          },
          {
            zone: 5, name: '无氧耐力', desc: '无氧耐力',
            range: `> ${Math.round(maxHR * 0.9)} bpm`,
            color: HR_ZONE_COLORS[4], value: workoutDetail?.hr_zone_5_seconds || 0
          },
        ];

        return (
          <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
            <h3 className="text-lg font-bold text-white mb-4">❤️ 心率区间用时</h3>
            <div className="space-y-4">
              {hrZones.map((zone) => {
                const percent = total > 0 ? ((zone.value / total) * 100).toFixed(0) : 0;
                return (
                  <div key={zone.zone} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-400">区间 {zone.zone}</span>
                        <span className="text-white font-medium">{zone.range}</span>
                        <span className="text-gray-500">({zone.desc})</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-white font-mono">{formatDuration(zone.value)}</span>
                        <span className="text-gray-500 text-xs w-10 text-right">{percent}%</span>
                      </div>
                    </div>
                    <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${percent}%`,
                          backgroundColor: zone.color,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* AI Analysis */}
      {workoutDetail.ai_analysis && (
        <div className="bg-gradient-to-br from-purple-900/40 to-slate-800/60 rounded-xl p-6 border border-purple-700/50">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            ✨ AI训练分析
          </h3>
          <div className="text-gray-300 whitespace-pre-wrap leading-relaxed">
            {(() => {
              try {
                const analysis = JSON.parse(workoutDetail.ai_analysis);
                return (
                  <div className="space-y-4">
                    {analysis.ai_enhanced_insights && (
                      <div className="text-gray-300 whitespace-pre-wrap">
                        {analysis.ai_enhanced_insights}
                      </div>
                    )}
                    {analysis.key_insights && (
                      <div>
                        <div className="text-sm font-medium text-purple-400 mb-2">💡 关键洞察</div>
                        <ul className="list-disc list-inside space-y-1 text-sm">
                          {analysis.key_insights.map((insight: string, idx: number) => (
                            <li key={idx}>{insight}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {analysis.improvement_tips && (
                      <div>
                        <div className="text-sm font-medium text-green-400 mb-2">📈 改进建议</div>
                        <ul className="list-disc list-inside space-y-1 text-sm">
                          {analysis.improvement_tips.map((tip: string, idx: number) => (
                            <li key={idx}>{tip}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {analysis.recovery_recommendation && (
                      <div className="bg-slate-700/50 rounded-lg p-3">
                        <div className="text-sm font-medium text-blue-400 mb-1">🛌 恢复建议</div>
                        <div className="text-sm">{analysis.recovery_recommendation}</div>
                      </div>
                    )}
                  </div>
                );
              } catch {
                return workoutDetail.ai_analysis;
              }
            })()}
          </div>
        </div>
      )}

      {/* Post Workout Scientific Analysis */}
      {console.log('🔍 showPostAnalysis:', showPostAnalysis, 'postAnalysis:', postAnalysis)}
      {showPostAnalysis && postAnalysis && postAnalysis.success && (
        <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/20 rounded-xl p-6 border border-blue-700/50 mt-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-2xl font-bold text-white flex items-center gap-2">
              <span>🔬</span> 运动后科学分析
            </h3>
            <div className="flex items-center gap-2">
              {postAnalysis.from_cache ? (
                <span className="px-3 py-1 bg-green-500/20 text-green-300 rounded-full text-sm flex items-center gap-1">
                  <span>✓</span> 已保存
                </span>
              ) : (
                <span className="px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full text-sm flex items-center gap-1">
                  <span>✨</span> 新生成
                </span>
              )}
              {postAnalysis.generated_at && (
                <span className="text-xs text-gray-400">
                  {new Date(postAnalysis.generated_at).toLocaleString('zh-CN', {
                    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
                  })}
                </span>
              )}
            </div>
          </div>

          {/* Overall Rating */}
          {postAnalysis.overall_rating && (
            <div className="bg-slate-800/60 rounded-xl p-6 mb-6 text-center">
              <div className="text-6xl mb-2">{postAnalysis.overall_rating.emoji}</div>
              <div className="text-3xl font-bold text-white mb-2">{postAnalysis.overall_rating.rating}</div>
              <div className="text-lg text-gray-300">{postAnalysis.overall_rating.message}</div>
              <div className="text-sm text-gray-400 mt-2">评分: {postAnalysis.overall_rating.score}/10</div>
            </div>
          )}

          {/* Intensity Assessment */}
          {postAnalysis.intensity_assessment && (
            <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
              <h4 className="text-xl font-bold text-white mb-4">💪 训练强度评估</h4>
              <div className="flex items-center gap-4 mb-4">
                <span className="text-4xl">{postAnalysis.intensity_assessment.emoji}</span>
                <div>
                  <div className="text-2xl font-bold text-white">{postAnalysis.intensity_assessment.level}</div>
                  <div className="text-sm text-gray-400">评分: {postAnalysis.intensity_assessment.score}/10</div>
                </div>
              </div>
              {postAnalysis.intensity_assessment.factors && (
                <ul className="space-y-2">
                  {postAnalysis.intensity_assessment.factors.map((factor: string, idx: number) => (
                    <li key={idx} className="text-gray-300 flex items-start gap-2">
                      <span className="text-blue-400">•</span>
                      <span>{factor}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* HR Zone Analysis */}
          {postAnalysis.hr_analysis && postAnalysis.hr_analysis.has_hr_data && (
            <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
              <h4 className="text-xl font-bold text-white mb-4">❤️ 心率区间分析</h4>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 mb-4">
                {Object.entries(postAnalysis.hr_analysis.zones).map(([key, zone]: [string, any]) => (
                  <div key={key} className="bg-slate-700/50 rounded-lg p-3">
                    <div className="text-xs text-gray-400 mb-1">{zone.name}</div>
                    <div className="text-2xl font-bold text-white">{zone.percentage}%</div>
                    <div className="text-xs text-gray-400 mt-1">{Math.floor(zone.seconds / 60)}分钟</div>
                  </div>
                ))}
              </div>
              {postAnalysis.hr_analysis.recommendations && postAnalysis.hr_analysis.recommendations.length > 0 && (
                <div className="space-y-2">
                  {postAnalysis.hr_analysis.recommendations.map((rec: string, idx: number) => (
                    <div key={idx} className="text-gray-300 flex items-start gap-2">
                      <span>{rec.split(' ')[0]}</span>
                      <span>{rec.substring(rec.indexOf(' ') + 1)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Recovery Tips */}
          {postAnalysis.recovery_tips && postAnalysis.recovery_tips.length > 0 && (
            <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
              <h4 className="text-xl font-bold text-white mb-4">🛀 恢复建议</h4>
              <div className="space-y-3">
                {postAnalysis.recovery_tips.map((tip: string, idx: number) => (
                  <div key={idx} className="flex items-start gap-3 bg-slate-700/50 rounded-lg p-3">
                    <span className="text-xl">{tip.split(' ')[0]}</span>
                    <span className="text-gray-200 flex-1">{tip.substring(tip.indexOf(' ') + 1)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Improvement Tips */}
          {postAnalysis.improvement_tips && postAnalysis.improvement_tips.length > 0 && (
            <div className="bg-slate-800/60 rounded-xl p-6 mb-6">
              <h4 className="text-xl font-bold text-white mb-4">📈 改进建议</h4>
              <ul className="space-y-2">
                {postAnalysis.improvement_tips.map((tip: string, idx: number) => (
                  <li key={idx} className="text-gray-300 flex items-start gap-2">
                    <span className="text-blue-400">→</span>
                    <span>{tip}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </>
  );
}
