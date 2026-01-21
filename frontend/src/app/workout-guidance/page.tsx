'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { workoutGuidanceApi, goalApi } from '@/services/api';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

// 心率区间颜色
const HR_ZONE_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#dc2626'];

export default function WorkoutGuidancePage() {
  const { user, isAuthenticated } = useAuth();
  const [selectedGoalId, setSelectedGoalId] = useState<number | undefined>();
  const [workoutType, setWorkoutType] = useState('');
  const [showPreGuidance, setShowPreGuidance] = useState(false);
  const [preGuidance, setPreGuidance] = useState<any>(null);
  const [debugMode, setDebugMode] = useState(false);

  // 获取用户目标列表
  const { data: goalsData } = useQuery({
    queryKey: ['goals', user?.id],
    queryFn: () => goalApi.getMyGoals('active'),
    enabled: isAuthenticated && !!user,
  });

  // 获取运动前指导
  const preGuidanceMutation = useMutation({
    mutationFn: () => workoutGuidanceApi.getPreWorkoutGuidance(selectedGoalId, workoutType || undefined, debugMode),
    onSuccess: (response) => {
      setPreGuidance(response.data);
      setShowPreGuidance(true);
    },
  });

  const goals = goalsData?.data || [];

  return (
    <ProtectedRoute>
      <main className="min-h-screen p-4 md:p-8 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <div className="max-w-5xl mx-auto">
          {/* 页面标题 */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white flex items-center gap-3 mb-2">
              <span>🎯</span> 智能运动指导
            </h1>
            <p className="text-gray-400">基于科学训练理论，为您提供个性化的运动指导</p>
          </div>

          {/* 运动前指导卡片 */}
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl shadow-2xl p-6 mb-6 border border-slate-700">
            <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
              <span>🏃</span> 运动前指导
            </h2>
            <p className="text-gray-300 mb-6">
              根据您的目标和当前状态，获取个性化的训练建议
            </p>

            {/* 选择表单 */}
            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  选择目标（可选）
                </label>
                <select
                  value={selectedGoalId || ''}
                  onChange={(e) => setSelectedGoalId(e.target.value ? Number(e.target.value) : undefined)}
                  className="w-full px-4 py-3 bg-slate-700 text-white rounded-lg border border-slate-600 focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">不选择特定目标</option>
                  {goals.map((goal: any) => (
                    <option key={goal.id} value={goal.id}>
                      {goal.title}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  运动类型（可选）
                </label>
                <select
                  value={workoutType}
                  onChange={(e) => setWorkoutType(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-700 text-white rounded-lg border border-slate-600 focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">自动推断</option>
                  <option value="RUNNING">跑步</option>
                  <option value="CARDIO">心肺训练</option>
                  <option value="WEIGHT_LOSS">减肥训练</option>
                  <option value="MUSCLE_GAIN">力量增肌</option>
                  <option value="EXERCISE">一般运动</option>
                </select>
              </div>
            </div>

            {/* Debug 模式开关 */}
            <div className="mb-4 flex items-center gap-3 p-4 bg-slate-700/50 rounded-lg border border-slate-600">
              <input
                type="checkbox"
                id="debugMode"
                checked={debugMode}
                onChange={(e) => setDebugMode(e.target.checked)}
                className="w-5 h-5 text-blue-600 bg-slate-600 border-slate-500 rounded focus:ring-blue-500"
              />
              <label htmlFor="debugMode" className="text-gray-300 cursor-pointer select-none flex items-center gap-2">
                <span>🔍</span>
                <span className="font-medium">Debug 模式</span>
                <span className="text-sm text-gray-400">（展示 AI 决策过程）</span>
              </label>
            </div>

            <button
              onClick={() => preGuidanceMutation.mutate()}
              disabled={preGuidanceMutation.isPending}
              className="w-full px-6 py-4 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl hover:from-blue-700 hover:to-blue-800 disabled:opacity-50 transition-all font-semibold text-lg shadow-lg"
            >
              {preGuidanceMutation.isPending ? '生成中...' : '🎯 获取运动前指导'}
            </button>
          </div>

          {/* 运动前指导结果 */}
          {showPreGuidance && preGuidance && preGuidance.success && (
            <div className="space-y-6">
              {/* Debug 信息面板 */}
              {preGuidance.debug && (
                <div className="bg-gradient-to-br from-purple-900/50 to-purple-800/30 rounded-xl p-6 border border-purple-700/50">
                  <h3 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>🔍</span> AI 决策过程
                  </h3>
                  <p className="text-purple-200 mb-6 text-sm">
                    以下展示了 AI 如何分析您的数据并生成个性化建议
                  </p>

                  {/* 决策步骤 */}
                  <div className="mb-6">
                    <h4 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                      <span>📋</span> 决策步骤
                    </h4>
                    <div className="space-y-2">
                      {preGuidance.debug.steps.map((step: string, index: number) => (
                        <div key={index} className="flex items-start gap-3 bg-slate-800/50 rounded-lg p-3">
                          <span className="text-purple-400 font-bold min-w-[24px]">{index + 1}</span>
                          <span className="text-gray-200">{step}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 推理过程 */}
                  <div className="mb-6">
                    <h4 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                      <span>🧠</span> 推理过程
                    </h4>
                    <div className="space-y-2">
                      {preGuidance.debug.reasoning.map((reason: string, index: number) => (
                        <div key={index} className="bg-slate-800/50 rounded-lg p-3">
                          <span className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">{reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 数据来源 */}
                  <div>
                    <h4 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                      <span>📊</span> 数据来源
                    </h4>
                    <details className="bg-slate-800/50 rounded-lg">
                      <summary className="cursor-pointer p-4 text-purple-300 hover:text-purple-200 font-medium">
                        点击查看详细数据来源 →
                      </summary>
                      <div className="p-4 pt-0">
                        <pre className="text-xs text-gray-300 overflow-x-auto bg-slate-900/50 rounded p-4 border border-slate-700">
                          {JSON.stringify(preGuidance.debug.data_sources, null, 2)}
                        </pre>
                      </div>
                    </details>
                  </div>
                </div>
              )}

              {/* 当前状态 */}
              {preGuidance.current_status && Object.keys(preGuidance.current_status).length > 0 && (
                <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
                  <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>📊</span> 当前状态
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {preGuidance.current_status.sleep && (
                      <div className="bg-slate-700/50 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">睡眠</div>
                        <div className="text-2xl font-bold text-white">
                          {preGuidance.current_status.sleep.score}
                        </div>
                        <div className="text-sm text-gray-300 mt-1">
                          {preGuidance.current_status.sleep.hours?.toFixed(1)} 小时 · {preGuidance.current_status.sleep.status}
                        </div>
                      </div>
                    )}
                    {preGuidance.current_status.stress && (
                      <div className="bg-slate-700/50 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">压力</div>
                        <div className="text-2xl font-bold text-white">
                          {preGuidance.current_status.stress.level}
                        </div>
                        <div className="text-sm text-gray-300 mt-1">
                          {preGuidance.current_status.stress.status}
                        </div>
                      </div>
                    )}
                    {preGuidance.current_status.resting_hr && (
                      <div className="bg-slate-700/50 rounded-lg p-4">
                        <div className="text-sm text-gray-400 mb-1">静息心率</div>
                        <div className="text-2xl font-bold text-white">
                          {preGuidance.current_status.resting_hr}
                        </div>
                        <div className="text-sm text-gray-300 mt-1">bpm</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 今日训练目标 */}
              {preGuidance.today_target && (
                <div className="bg-gradient-to-br from-blue-900/50 to-blue-800/30 rounded-xl p-6 border border-blue-700/50">
                  <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>🎯</span> 今日训练目标
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <div className="text-sm text-blue-300 mb-1">训练时长</div>
                      <div className="text-lg font-semibold text-white">
                        {preGuidance.today_target.duration}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-blue-300 mb-1">训练强度</div>
                      <div className="text-lg font-semibold text-white">
                        {preGuidance.today_target.intensity}
                      </div>
                    </div>
                    {preGuidance.today_target.recommended_hr_range && (
                      <div className="md:col-span-2">
                        <div className="text-sm text-blue-300 mb-1">推荐心率区间</div>
                        <div className="text-xl font-bold text-white">
                          {preGuidance.today_target.recommended_hr_range}
                        </div>
                        <div className="text-sm text-blue-200 mt-1">
                          {preGuidance.today_target.hr_zone_name}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 热身建议 */}
              {preGuidance.warm_up_tips && preGuidance.warm_up_tips.length > 0 && (
                <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
                  <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>🔥</span> 热身建议
                  </h3>
                  <ul className="space-y-2">
                    {preGuidance.warm_up_tips.map((tip: string, index: number) => (
                      <li key={index} className="flex items-start gap-3 text-gray-300">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 关键提醒 */}
              {preGuidance.key_reminders && preGuidance.key_reminders.length > 0 && (
                <div className="bg-gradient-to-br from-orange-900/50 to-orange-800/30 rounded-xl p-6 border border-orange-700/50">
                  <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>⚠️</span> 关键提醒
                  </h3>
                  <div className="space-y-3">
                    {preGuidance.key_reminders.map((reminder: string, index: number) => (
                      <div key={index} className="flex items-start gap-3 bg-slate-800/50 rounded-lg p-3">
                        <span className="text-xl">{reminder.split(' ')[0]}</span>
                        <span className="text-gray-200 flex-1">{reminder.substring(reminder.indexOf(' ') + 1)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 科学知识要点 */}
              {preGuidance.knowledge_points && preGuidance.knowledge_points.length > 0 && (
                <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
                  <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>📚</span> 科学知识要点
                  </h3>
                  <div className="space-y-3">
                    {preGuidance.knowledge_points.map((point: string, index: number) => (
                      <div key={index} className="bg-slate-700/50 rounded-lg p-4">
                        <p className="text-gray-300 leading-relaxed">{point}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 错误提示 */}
          {preGuidanceMutation.isError && (
            <div className="bg-red-900/50 border border-red-700 rounded-xl p-4 text-red-200">
              ❌ 获取运动前指导失败，请稍后重试
            </div>
          )}
        </div>
      </main>
    </ProtectedRoute>
  );
}
