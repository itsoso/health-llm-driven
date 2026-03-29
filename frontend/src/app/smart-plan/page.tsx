'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { smartPlanApi } from '@/services/api';
import {
  Calendar, Check, Circle,
  Loader2, Sparkles, Activity
} from 'lucide-react';

import { WeeklyPlan, PlanListItem, dayNames, categoryConfig } from './components/types';
import { WeekExecutionCard } from './components/WeekExecutionCard';
import { DebugPanel } from './components/DebugPanel';
import { PlanWizard } from './components/PlanWizard';
import { GoalsTab } from './components/GoalsTab';
import { HistoryCard } from './components/HistoryCard';
import { PlanSummary } from './components/PlanSummary';

/* eslint-disable @typescript-eslint/no-explicit-any */
function SmartPlanContent() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'current' | 'history' | 'goals'>('current');
  const [selectedDay, setSelectedDay] = useState<number>(() => {
    const today = new Date().getDay();
    return today === 0 ? 7 : today; // 周日=7
  });
  const [feedbackScore, setFeedbackScore] = useState<number>(0);
  const [showFeedback, setShowFeedback] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [debugData, setDebugData] = useState<any>(null);
  const [viewingWeek, setViewingWeek] = useState<'current' | 'next'>('current');
  const [showWizard, setShowWizard] = useState(false);

  // 当前周计划
  const { data: currentPlan, isLoading: planLoading } = useQuery<WeeklyPlan | null>({
    queryKey: ['smart-plan', 'current', viewingWeek],
    queryFn: async () => {
      const res = await smartPlanApi.getCurrent(viewingWeek);
      return res.data;
    },
  });

  // 本周计划（固定，不受 viewingWeek 影响，用于底部执行情况）
  const { data: thisWeekPlan } = useQuery<WeeklyPlan | null>({
    queryKey: ['smart-plan', 'this-week'],
    queryFn: async () => {
      const res = await smartPlanApi.getCurrent('current');
      return res.data;
    },
  });

  // 下周计划（始终获取，用于切换按钮和底部执行情况）
  const { data: nextWeekPlan } = useQuery<WeeklyPlan | null>({
    queryKey: ['smart-plan', 'current', 'next'],
    queryFn: async () => {
      const res = await smartPlanApi.getCurrent('next');
      return res.data;
    },
  });

  // 历史计划
  const { data: history, isLoading: historyLoading } = useQuery<PlanListItem[]>({
    queryKey: ['smart-plan', 'history'],
    queryFn: async () => {
      const res = await smartPlanApi.getHistory(1, 20);
      return res.data;
    },
    enabled: activeTab === 'history',
  });

  // 向导生成成功回调
  const handleWizardSuccess = (data: any, targetWeek: string) => {
    if (data?.debug) {
      setDebugData(data.debug);
    }
    setViewingWeek(targetWeek === 'next' ? 'next' : 'current');
    setShowWizard(false);
    queryClient.invalidateQueries({ queryKey: ['smart-plan'] });
  };

  // 切换完成
  const toggleMutation = useMutation({
    mutationFn: ({ planId, itemId, isCompleted }: { planId: number; itemId: number; isCompleted: boolean }) =>
      smartPlanApi.updateItem(planId, itemId, isCompleted),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan', 'current'] });
    },
  });

  // 提交反馈
  const feedbackMutation = useMutation({
    mutationFn: ({ planId, score }: { planId: number; score: number }) =>
      smartPlanApi.submitFeedback(planId, score),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan'] });
      setShowFeedback(false);
    },
  });

  // 删除计划
  const deleteMutation = useMutation({
    mutationFn: (planId: number) => smartPlanApi.deletePlan(planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan'] });
    },
    onError: (error: any) => {
      alert(error?.response?.data?.detail || '删除失败');
    },
  });

  const todayItems = currentPlan?.items.filter(i => i.day_of_week === selectedDay) || [];
  const completedToday = todayItems.filter(i => i.is_completed).length;
  const totalToday = todayItems.length;

  const formatWeekRange = (weekStart: string) => {
    const start = new Date(weekStart);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return `${start.getMonth() + 1}/${start.getDate()} - ${end.getMonth() + 1}/${end.getDate()}`;
  };

  const getWeekDayDate = (weekStart: string, dayOfWeek: number) => {
    const start = new Date(weekStart);
    start.setDate(start.getDate() + dayOfWeek - 1);
    return `${start.getMonth() + 1}/${start.getDate()}`;
  };

  const isToday = (weekStart: string, dayOfWeek: number) => {
    const start = new Date(weekStart);
    start.setDate(start.getDate() + dayOfWeek - 1);
    const today = new Date();
    return start.toDateString() === today.toDateString();
  };

  return (
    <div className="max-w-4xl mx-auto p-4 pb-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">智能计划</h1>
          <p className="text-sm text-gray-500 mt-1">AI 为你量身定制的健康计划与目标</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
          >
            <Sparkles className="w-4 h-4" />
            {currentPlan ? '重新制定' : '制定计划'}
          </button>
        </div>
      </div>

      {/* Debug Toggle */}
      <div className="mb-4 flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
        <input
          type="checkbox"
          id="debugMode"
          checked={debugMode}
          onChange={(e) => { setDebugMode(e.target.checked); if (!e.target.checked) setDebugData(null); }}
          className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
        />
        <label htmlFor="debugMode" className="text-gray-600 cursor-pointer select-none flex items-center gap-2 text-sm">
          <span>🔍</span>
          <span className="font-medium">Debug 模式</span>
          <span className="text-gray-400">（展示 AI 决策过程和耗时）</span>
        </label>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6">
        <button
          onClick={() => setActiveTab('current')}
          className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'current' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          当前计划
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'history' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          历史记录
        </button>
        <button
          onClick={() => setActiveTab('goals')}
          className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'goals' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          目标
        </button>
      </div>

      {/* Current Plan Tab */}
      {activeTab === 'current' && (
        <>
          {/* Week Switcher */}
          <div className="flex items-center gap-2 mb-4">
            <button
              onClick={() => setViewingWeek('current')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                viewingWeek === 'current'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              本周
            </button>
            <button
              onClick={() => setViewingWeek('next')}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1 ${
                viewingWeek === 'next'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              下周
              {viewingWeek === 'current' && nextWeekPlan && (
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              )}
            </button>
          </div>

          {planLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : !currentPlan ? (
            <div className="text-center py-20">
              <Calendar className="w-16 h-16 mx-auto text-gray-300 mb-4" />
              <h3 className="text-lg font-medium text-gray-600 mb-2">
                {viewingWeek === 'next' ? '还没有下周计划' : '还没有本周计划'}
              </h3>
              <p className="text-gray-400 mb-6">
                点击下方按钮，AI 将根据你的健康数据定制专属计划
              </p>
              <button
                onClick={() => setShowWizard(true)}
                className="flex items-center gap-2 mx-auto px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                <Sparkles className="w-4 h-4" />
                {viewingWeek === 'next' ? '制定下周计划' : '制定本周计划'}
              </button>
              {debugData && <div className="mt-6 text-left"><DebugPanel debug={debugData} /></div>}
            </div>
          ) : (
            <>
              {/* Compact Plan Header */}
              <div className="flex items-center justify-between mb-4 px-1">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-blue-600" />
                  <span className="font-semibold text-gray-900 text-sm">
                    {formatWeekRange(currentPlan.week_start)}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    currentPlan.status === 'active' ? 'bg-green-100 text-green-700' :
                    currentPlan.status === 'completed' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {currentPlan.status === 'active' ? '进行中' :
                     currentPlan.status === 'completed' ? '已完成' : currentPlan.status}
                  </span>
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="text-xl font-bold text-blue-600">{Math.round(currentPlan.completion_rate)}%</span>
                  <span className="text-xs text-gray-500">完成率</span>
                </div>
              </div>

              {/* Debug Panel */}
              {debugData && (
                <DebugPanel debug={debugData} />
              )}

              {/* Day Selector */}
              <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
                {[1, 2, 3, 4, 5, 6, 7].map(day => {
                  const dayItems = currentPlan.items.filter(i => i.day_of_week === day);
                  const dayCompleted = dayItems.filter(i => i.is_completed).length;
                  const dayTotal = dayItems.length;
                  const today = isToday(currentPlan.week_start, day);

                  return (
                    <button
                      key={day}
                      onClick={() => setSelectedDay(day)}
                      className={`flex-1 min-w-[52px] py-2 px-1 rounded-lg text-center transition-colors ${
                        selectedDay === day
                          ? 'bg-blue-600 text-white'
                          : today
                            ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
                            : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <div className="text-xs font-medium">{dayNames[day - 1]}</div>
                      <div className="text-xs opacity-70">{getWeekDayDate(currentPlan.week_start, day)}</div>
                      {dayTotal > 0 && (
                        <div className={`text-xs mt-0.5 ${selectedDay === day ? 'text-blue-100' : 'text-gray-400'}`}>
                          {dayCompleted}/{dayTotal}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Day Progress */}
              {totalToday > 0 && (
                <div className="mb-4">
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-gray-500">{dayNames[selectedDay - 1]}进度</span>
                    <span className="font-medium text-gray-700">{completedToday}/{totalToday}</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all duration-300"
                      style={{ width: `${totalToday > 0 ? (completedToday / totalToday) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Plan Items */}
              <div className="space-y-3">
                {todayItems.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">
                    <p>这一天没有计划项</p>
                  </div>
                ) : (
                  todayItems.map(item => {
                    const cat = categoryConfig[item.category] || categoryConfig.other;
                    return (
                      <div
                        key={item.id}
                        className={`flex items-start gap-3 p-4 rounded-xl border transition-all ${
                          item.is_completed
                            ? 'bg-gray-50 border-gray-100'
                            : 'bg-white border-gray-200 hover:border-blue-200 hover:shadow-sm'
                        }`}
                      >
                        <button
                          onClick={() => toggleMutation.mutate({
                            planId: currentPlan.id,
                            itemId: item.id,
                            isCompleted: !item.is_completed,
                          })}
                          disabled={toggleMutation.isPending}
                          className="mt-0.5 flex-shrink-0"
                        >
                          {item.is_completed ? (
                            <Check className="w-5 h-5 text-green-500" />
                          ) : (
                            <Circle className="w-5 h-5 text-gray-300 hover:text-blue-400 transition-colors" />
                          )}
                        </button>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${cat.color}`}>
                              {cat.icon}
                              {cat.label}
                            </span>
                            {item.target_value && item.target_unit && (
                              <span className="text-xs text-gray-400">
                                目标: {item.target_value}{item.target_unit}
                              </span>
                            )}
                            {item.checkin_template_id && (
                              <span className="text-xs text-blue-400">可打卡</span>
                            )}
                          </div>
                          <h4 className={`font-medium ${item.is_completed ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
                            {item.title}
                          </h4>
                          {item.description && (
                            <p className={`text-sm mt-1 ${item.is_completed ? 'text-gray-300' : 'text-gray-500'}`}>
                              {item.description}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Plan Summary */}
              <PlanSummary
                plan={currentPlan}
                showFeedback={showFeedback}
                feedbackScore={feedbackScore}
                feedbackPending={feedbackMutation.isPending}
                deletePending={deleteMutation.isPending}
                onToggleFeedback={() => setShowFeedback(!showFeedback)}
                onSetFeedbackScore={setFeedbackScore}
                onSubmitFeedback={() => feedbackMutation.mutate({ planId: currentPlan.id, score: feedbackScore })}
                onDelete={() => { if (confirm('确定删除此计划？')) deleteMutation.mutate(currentPlan.id); }}
              />
            </>
          )}
        </>
      )}

      {/* 执行情况总览（始终在当前计划 tab 最下方展示） */}
      {activeTab === 'current' && (
        <div className="mt-8 border-t border-gray-100 pt-6">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4 text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-700">计划执行情况</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <WeekExecutionCard
              plan={thisWeekPlan}
              weekLabel="本周"
              isCurrent
              onCreatePlan={() => { setViewingWeek('current'); setShowWizard(true); }}
            />
            <WeekExecutionCard
              plan={nextWeekPlan}
              weekLabel="下周"
              isCurrent={false}
              onCreatePlan={() => { setViewingWeek('next'); setShowWizard(true); }}
            />
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <>
          {historyLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : !history || history.length === 0 ? (
            <div className="text-center py-20 text-gray-400">
              <p>暂无历史计划</p>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map(plan => (
                <HistoryCard key={plan.id} plan={plan} />
              ))}
            </div>
          )}
        </>
      )}

      {/* Goals Tab */}
      {activeTab === 'goals' && (
        <GoalsTab debugMode={debugMode} />
      )}

      {/* Planning Wizard */}
      {showWizard && (
        <PlanWizard
          targetWeek={viewingWeek}
          debugMode={debugMode}
          onClose={() => setShowWizard(false)}
          onSuccess={handleWizardSuccess}
        />
      )}
    </div>
  );
}

export default function SmartPlanPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!isAuthenticated) {
    router.push('/login');
    return null;
  }

  return <SmartPlanContent />;
}
