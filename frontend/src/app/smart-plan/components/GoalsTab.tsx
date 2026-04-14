'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Target, TrendingUp, Trash2 } from 'lucide-react';
import { smartPlanApi } from '@/services/api/content';
import { GoalListItem, PeriodGoal, GoalMetric } from './types';
import { DebugPanel } from './DebugPanel';

/* eslint-disable @typescript-eslint/no-explicit-any */

export function GoalsTab({ debugMode }: { debugMode: boolean }) {
  const queryClient = useQueryClient();
  const [debugData, setDebugData] = useState<any>(null);

  const { data: goals, isLoading } = useQuery<GoalListItem[]>({
    queryKey: ['smart-plan', 'goals'],
    queryFn: async () => {
      const res = await smartPlanApi.getActiveGoals();
      return res.data;
    },
  });

  const { data: goalDetails } = useQuery<PeriodGoal[]>({
    queryKey: ['smart-plan', 'goal-details'],
    queryFn: async () => {
      if (!goals || goals.length === 0) return [];
      const details = await Promise.all(
        goals.map(async (g) => {
          const res = await smartPlanApi.getGoalDetail(g.id);
          return res.data;
        })
      );
      return details;
    },
    enabled: !!goals && goals.length > 0,
  });

  const generateGoalMutation = useMutation({
    mutationFn: (periodType: string) => smartPlanApi.generateGoal(periodType, undefined, debugMode),
    onSuccess: (res) => {
      if (res.data?.debug) setDebugData(res.data.debug);
      queryClient.invalidateQueries({ queryKey: ['smart-plan', 'goals'] });
      queryClient.invalidateQueries({ queryKey: ['smart-plan', 'goal-details'] });
    },
  });

  const deleteGoalMutation = useMutation({
    mutationFn: (goalId: number) => smartPlanApi.deleteGoal(goalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan', 'goals'] });
      queryClient.invalidateQueries({ queryKey: ['smart-plan', 'goal-details'] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  const monthlyGoal = goalDetails?.find(g => g.period_type === 'monthly');
  const yearlyGoal = goalDetails?.find(g => g.period_type === 'yearly');

  const getMetricProgress = (metric: GoalMetric) => {
    if (metric.current_value == null || metric.target_value == null) return null;
    const start = metric.milestones?.[0]?.target ?? metric.current_value;
    const diff = metric.target_value - start;
    if (diff === 0) return 100;
    const progress = ((metric.current_value - start) / diff) * 100;
    return Math.max(0, Math.min(100, Math.round(progress)));
  };

  const renderGoalCard = (goal: PeriodGoal) => {
    const periodLabel = goal.period_type === 'monthly' ? '月度目标' : '年度目标';
    const startDate = new Date(goal.period_start);
    const periodStr = goal.period_type === 'monthly'
      ? `${startDate.getFullYear()}年${startDate.getMonth() + 1}月`
      : `${startDate.getFullYear()}年`;

    return (
      <div key={goal.id} className="bg-white border border-gray-200 rounded-xl p-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-indigo-600" />
            <span className="font-semibold text-gray-900">{periodLabel}</span>
            <span className="text-sm text-gray-500">{periodStr}</span>
          </div>
          <button
            onClick={() => { if (confirm('确定删除此目标？')) deleteGoalMutation.mutate(goal.id); }}
            className="text-gray-400 hover:text-red-500"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {goal.focus_areas.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {goal.focus_areas.map((area, idx) => (
              <span key={idx} className="text-xs bg-indigo-50 text-indigo-700 px-2 py-1 rounded-full">{area}</span>
            ))}
          </div>
        )}

        {goal.summary && (
          <p className="text-sm text-gray-600 mb-4 leading-relaxed">{goal.summary}</p>
        )}

        {/* Metrics */}
        <div className="space-y-4">
          {goal.metrics.map(metric => {
            const progress = getMetricProgress(metric);
            return (
              <div key={metric.id} className="bg-gray-50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-indigo-500" />
                    <span className="font-medium text-gray-800">{metric.metric_name || metric.metric_type}</span>
                  </div>
                  <span className="text-sm text-gray-500">
                    {metric.current_value ?? '?'} {metric.unit} → {metric.target_value ?? '?'} {metric.unit}
                  </span>
                </div>

                {progress !== null && (
                  <div className="mb-2">
                    <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <div className="text-xs text-gray-400 mt-1 text-right">{progress}%</div>
                  </div>
                )}

                {metric.strategy && (
                  <p className="text-xs text-gray-500 mt-1">{metric.strategy}</p>
                )}

                {metric.milestones && metric.milestones.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {metric.milestones.slice(0, 4).map((ms, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-xs text-gray-500">
                        <span className="w-16 text-gray-400">{ms.period}</span>
                        <span className="font-medium">{ms.target}{metric.unit}</span>
                        <span className="text-gray-400 truncate">{ms.action}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div>
      {/* Generate Buttons */}
      <div className="flex gap-3 mb-6">
        <button
          onClick={() => generateGoalMutation.mutate('monthly')}
          disabled={generateGoalMutation.isPending}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-indigo-50 text-indigo-700 rounded-xl hover:bg-indigo-100 disabled:opacity-50 transition-colors"
        >
          {generateGoalMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Target className="w-4 h-4" />}
          生成月度目标
        </button>
        <button
          onClick={() => generateGoalMutation.mutate('yearly')}
          disabled={generateGoalMutation.isPending}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-purple-50 text-purple-700 rounded-xl hover:bg-purple-100 disabled:opacity-50 transition-colors"
        >
          {generateGoalMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Target className="w-4 h-4" />}
          生成年度目标
        </button>
      </div>

      {debugData && <DebugPanel debug={debugData} />}

      {/* Goal Cards */}
      {monthlyGoal && renderGoalCard(monthlyGoal)}
      {yearlyGoal && renderGoalCard(yearlyGoal)}

      {!monthlyGoal && !yearlyGoal && !generateGoalMutation.isPending && (
        <div className="text-center py-16">
          <Target className="w-16 h-16 mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-600 mb-2">还没有健康目标</h3>
          <p className="text-gray-400">生成月度或年度目标，追踪体重、BMI 等关键指标</p>
        </div>
      )}
    </div>
  );
}
