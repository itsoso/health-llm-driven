'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { smartPlanApi } from '@/services/api';
import {
  Calendar, ChevronRight, Check, Circle, Star,
  Loader2, Trash2, Dumbbell, Utensils, Moon, Sparkles, MoreHorizontal,
  Target, TrendingUp, ArrowRight, Lightbulb, AlertTriangle,
  X, Plus, CloudRain, Sun, Cloud, Snowflake, Wind, Plane, Activity, Brain
} from 'lucide-react';

interface PlanItem {
  id: number;
  day_of_week: number;
  category: string;
  title: string;
  description: string | null;
  target_value: number | null;
  target_unit: string | null;
  checkin_template_id: number | null;
  is_completed: boolean;
  completed_at: string | null;
  sort_order: number;
}

interface WeeklyPlan {
  id: number;
  user_id: number;
  week_start: string;
  status: string;
  focus_areas: string[];
  ai_insights: string[];
  ai_risks: string[];
  weekly_summary: string | null;
  completion_rate: number;
  ai_model: string | null;
  user_feedback: number | null;
  items: PlanItem[];
  created_at: string;
  updated_at: string | null;
}

interface PlanListItem {
  id: number;
  week_start: string;
  status: string;
  focus_areas: string[];
  completion_rate: number;
  user_feedback: number | null;
  item_count: number;
  completed_count: number;
  created_at: string;
}

interface GoalMetric {
  id: number;
  metric_type: string;
  metric_name: string | null;
  current_value: number | null;
  target_value: number | null;
  unit: string | null;
  milestones: { period: string; target: number; action: string }[] | null;
  strategy: string | null;
}

interface PeriodGoal {
  id: number;
  user_id: number;
  period_type: string;
  period_start: string;
  period_end: string;
  status: string;
  focus_areas: string[];
  summary: string | null;
  ai_model: string | null;
  user_feedback: number | null;
  metrics: GoalMetric[];
  created_at: string;
  updated_at: string | null;
}

interface GoalListItem {
  id: number;
  period_type: string;
  period_start: string;
  period_end: string;
  status: string;
  focus_areas: string[];
  summary: string | null;
  metric_count: number;
  created_at: string;
}

const dayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const categoryConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  exercise: { label: '运动', color: 'bg-blue-100 text-blue-700', icon: <Dumbbell className="w-3.5 h-3.5" /> },
  diet: { label: '饮食', color: 'bg-green-100 text-green-700', icon: <Utensils className="w-3.5 h-3.5" /> },
  rest: { label: '休息', color: 'bg-purple-100 text-purple-700', icon: <Moon className="w-3.5 h-3.5" /> },
  habit: { label: '习惯', color: 'bg-amber-100 text-amber-700', icon: <Sparkles className="w-3.5 h-3.5" /> },
  other: { label: '其他', color: 'bg-gray-100 text-gray-700', icon: <MoreHorizontal className="w-3.5 h-3.5" /> },
};

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

  // 检查是否有下周计划（用于显示切换按钮）
  const { data: nextWeekPlan } = useQuery<WeeklyPlan | null>({
    queryKey: ['smart-plan', 'current', 'next'],
    queryFn: async () => {
      const res = await smartPlanApi.getCurrent('next');
      return res.data;
    },
    enabled: viewingWeek === 'current',
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
              {/* Plan Summary */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-5 mb-6">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-5 h-5 text-blue-600" />
                    <span className="font-semibold text-gray-900">
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
                  <div className="text-right">
                    <span className="text-2xl font-bold text-blue-600">{Math.round(currentPlan.completion_rate)}%</span>
                    <p className="text-xs text-gray-500">完成率</p>
                  </div>
                </div>

                {/* Focus Areas */}
                {currentPlan.focus_areas.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {currentPlan.focus_areas.map((area, idx) => (
                      <span key={idx} className="text-xs bg-white/70 text-blue-700 px-2 py-1 rounded-full">
                        {area}
                      </span>
                    ))}
                  </div>
                )}

                {currentPlan.weekly_summary && (
                  <p className="text-sm text-gray-600 leading-relaxed">{currentPlan.weekly_summary}</p>
                )}

                {/* AI Insights */}
                {currentPlan.ai_insights && currentPlan.ai_insights.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-700">
                      <Lightbulb className="w-3.5 h-3.5" />
                      <span>AI 数据洞察</span>
                    </div>
                    {currentPlan.ai_insights.map((insight, idx) => (
                      <div key={idx} className="text-xs text-gray-600 bg-white/60 rounded-lg px-3 py-2 leading-relaxed">
                        {insight}
                      </div>
                    ))}
                  </div>
                )}

                {/* AI Risks */}
                {currentPlan.ai_risks && currentPlan.ai_risks.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-red-600">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      <span>风险提示</span>
                    </div>
                    {currentPlan.ai_risks.map((risk, idx) => (
                      <div key={idx} className="text-xs text-red-700 bg-red-50/60 rounded-lg px-3 py-2 leading-relaxed">
                        {risk}
                      </div>
                    ))}
                  </div>
                )}

                {/* Feedback & Delete */}
                <div className="flex items-center gap-3 mt-4 pt-3 border-t border-blue-100">
                  {currentPlan.user_feedback ? (
                    <div className="flex items-center gap-1 text-sm text-gray-500">
                      <span>评分:</span>
                      {[1, 2, 3, 4, 5].map(s => (
                        <Star key={s} className={`w-4 h-4 ${s <= currentPlan.user_feedback! ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`} />
                      ))}
                    </div>
                  ) : (
                    <button
                      onClick={() => setShowFeedback(!showFeedback)}
                      className="text-sm text-blue-600 hover:text-blue-700"
                    >
                      评价本周计划
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (confirm('确定删除此计划？')) deleteMutation.mutate(currentPlan.id);
                    }}
                    className="ml-auto text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                {/* Feedback Form */}
                {showFeedback && !currentPlan.user_feedback && (
                  <div className="flex items-center gap-3 mt-3 pt-3 border-t border-blue-100">
                    <span className="text-sm text-gray-600">评分:</span>
                    <div className="flex gap-1">
                      {[1, 2, 3, 4, 5].map(s => (
                        <button key={s} onClick={() => setFeedbackScore(s)}>
                          <Star className={`w-6 h-6 transition-colors ${s <= feedbackScore ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300 hover:text-yellow-300'}`} />
                        </button>
                      ))}
                    </div>
                    {feedbackScore > 0 && (
                      <button
                        onClick={() => feedbackMutation.mutate({ planId: currentPlan.id, score: feedbackScore })}
                        disabled={feedbackMutation.isPending}
                        className="text-sm px-3 py-1 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                      >
                        提交
                      </button>
                    )}
                  </div>
                )}
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
            </>
          )}
        </>
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

// ===== 向导类型定义 =====
interface AnalyzeData {
  week_start: string;
  week_end: string;
  past_performance: {
    weeks_analyzed: number;
    avg_completion_rate: number;
    by_category: Record<string, { done: number; total: number; rate: number; top_items: string[] }>;
    trend: string;
    strong_items: string[];
    weak_items: string[];
  };
  body_metrics: {
    weight?: { current: number; target: number | null; unit: string; date: string };
    bmi?: number;
    body_fat?: number;
    body_battery?: number;
    stress_level?: number;
    sleep_score?: number;
    resting_hr?: number;
  };
  weather_forecast: {
    available: boolean;
    city?: string;
    daily?: { date: string; day_name: string; weather: string; temp_high: number; temp_low: number }[];
    air_quality?: { aqi: number; level: string; primary_pollutant: string };
    exercise_advice?: string;
    reason?: string;
  };
  active_goals: { id: number; period_type: string; focus_areas: string[]; metrics: { metric_name: string; current_value: number | null; target_value: number | null; unit: string | null }[] }[];
  trips: { name: string; destination: string; start_date: string; end_date: string; days: { day_name: string; date: string; title: string; type: string }[] }[];
  suggested_focus: { label: string; reason: string }[];
}

function getWeatherIcon(weather: string) {
  if (weather.includes('雨')) return <CloudRain className="w-4 h-4 text-blue-500" />;
  if (weather.includes('雪')) return <Snowflake className="w-4 h-4 text-cyan-500" />;
  if (weather.includes('晴')) return <Sun className="w-4 h-4 text-amber-500" />;
  if (weather.includes('风')) return <Wind className="w-4 h-4 text-gray-500" />;
  return <Cloud className="w-4 h-4 text-gray-400" />;
}

function PlanWizard({ targetWeek, debugMode, onClose, onSuccess }: {
  targetWeek: string;
  debugMode: boolean;
  onClose: () => void;
  onSuccess: (data: any, targetWeek: string) => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [analyzeData, setAnalyzeData] = useState<AnalyzeData | null>(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(true);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [selectedFocus, setSelectedFocus] = useState<string[]>([]);
  const [customFocus, setCustomFocus] = useState('');
  const [intensity, setIntensity] = useState<'light' | 'moderate' | 'challenge'>('moderate');
  const [userNotes, setUserNotes] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [progressStep, setProgressStep] = useState(0);

  // Step 1: 加载分析数据
  useEffect(() => {
    (async () => {
      try {
        setAnalyzeLoading(true);
        const res = await smartPlanApi.analyze(targetWeek);
        setAnalyzeData(res.data);
        // 预选建议的 focus
        const suggested = res.data.suggested_focus?.slice(0, 2).map((f: any) => f.label) || [];
        setSelectedFocus(suggested);
      } catch (e: any) {
        setAnalyzeError(e?.response?.data?.detail || '数据分析失败');
      } finally {
        setAnalyzeLoading(false);
      }
    })();
  }, [targetWeek]);

  // Step 3: 生成计划
  const handleGenerate = async () => {
    setGenerating(true);
    setGenerateError(null);
    setStep(3);
    setProgressStep(0);

    const timer = setInterval(() => {
      setProgressStep(prev => Math.min(prev + 1, 3));
    }, 2000);

    try {
      const allFocus = [...selectedFocus];
      if (customFocus.trim()) allFocus.push(customFocus.trim());

      const res = await smartPlanApi.generate({
        target_week: targetWeek,
        user_focus: allFocus,
        user_notes: userNotes,
        intensity,
      }, debugMode);

      clearInterval(timer);
      setProgressStep(4);
      setTimeout(() => {
        onSuccess(res.data, targetWeek);
      }, 1500);
    } catch (e: any) {
      clearInterval(timer);
      setGenerateError(e?.response?.data?.detail || 'AI 生成失败，请稍后重试');
      setStep(2);
      setGenerating(false);
    }
  };

  const toggleFocus = (label: string) => {
    setSelectedFocus(prev =>
      prev.includes(label) ? prev.filter(f => f !== label) : [...prev, label]
    );
  };

  const addCustomFocus = () => {
    if (customFocus.trim() && !selectedFocus.includes(customFocus.trim())) {
      setSelectedFocus(prev => [...prev, customFocus.trim()]);
      setCustomFocus('');
    }
  };

  const formatWeekRange = (start: string, end: string) => {
    const s = new Date(start);
    const e = new Date(end);
    return `${s.getMonth() + 1}/${s.getDate()} - ${e.getMonth() + 1}/${e.getDate()}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="text-lg font-bold text-gray-900">
            制定{targetWeek === 'next' ? '下' : '本'}周计划
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center gap-0 px-6 py-3 bg-gray-50">
          {[
            { num: 1, label: '数据回顾' },
            { num: 2, label: '定制偏好' },
            { num: 3, label: '生成计划' },
          ].map((s, idx) => (
            <div key={s.num} className="flex items-center flex-1">
              <div className={`flex items-center gap-1.5 ${step >= s.num ? 'text-blue-600' : 'text-gray-400'}`}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  step > s.num ? 'bg-blue-600 text-white' :
                  step === s.num ? 'bg-blue-600 text-white' :
                  'bg-gray-200 text-gray-500'
                }`}>
                  {step > s.num ? <Check className="w-3.5 h-3.5" /> : s.num}
                </div>
                <span className="text-xs font-medium hidden sm:inline">{s.label}</span>
              </div>
              {idx < 2 && <div className={`flex-1 h-0.5 mx-2 ${step > s.num ? 'bg-blue-600' : 'bg-gray-200'}`} />}
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* Step 1: 数据回顾 */}
          {step === 1 && (
            analyzeLoading ? (
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-3" />
                <p className="text-sm text-gray-500">正在分析你的健康数据...</p>
              </div>
            ) : analyzeError ? (
              <div className="text-center py-12">
                <AlertTriangle className="w-10 h-10 mx-auto text-red-400 mb-3" />
                <p className="text-red-600">{analyzeError}</p>
              </div>
            ) : analyzeData && (
              <>
                {/* 周期信息 */}
                <div className="text-center text-sm text-gray-500">
                  计划周期: {formatWeekRange(analyzeData.week_start, analyzeData.week_end)}
                </div>

                {/* 过去执行情况 */}
                {analyzeData.past_performance.weeks_analyzed > 0 && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                      <Activity className="w-4 h-4" />
                      过去执行情况
                      <span className="text-xs text-gray-400 font-normal">（近{analyzeData.past_performance.weeks_analyzed}周）</span>
                    </h3>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="text-2xl font-bold text-blue-600">{analyzeData.past_performance.avg_completion_rate}%</div>
                      <div className="text-xs text-gray-500">
                        平均完成率
                        <span className={`ml-1 ${analyzeData.past_performance.trend === 'improving' ? 'text-green-600' : analyzeData.past_performance.trend === 'declining' ? 'text-red-600' : 'text-gray-400'}`}>
                          {analyzeData.past_performance.trend === 'improving' ? '↑ 上升' : analyzeData.past_performance.trend === 'declining' ? '↓ 下降' : '→ 稳定'}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(analyzeData.past_performance.by_category).map(([cat, stat]) => {
                        const config = categoryConfig[cat] || categoryConfig.other;
                        return (
                          <div key={cat} className="bg-white rounded-lg p-2 text-xs">
                            <div className="flex items-center gap-1 mb-1">
                              <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full ${config.color}`}>
                                {config.icon}{config.label}
                              </span>
                            </div>
                            <div className="flex items-center gap-1">
                              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${stat.rate}%` }} />
                              </div>
                              <span className="text-gray-500 min-w-[32px] text-right">{stat.rate}%</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 身体指标 */}
                {Object.keys(analyzeData.body_metrics).length > 0 && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                      <TrendingUp className="w-4 h-4" />
                      身体指标
                    </h3>
                    <div className="grid grid-cols-3 gap-2">
                      {analyzeData.body_metrics.weight && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.weight.current}</div>
                          <div className="text-xs text-gray-400">体重 kg</div>
                          {analyzeData.body_metrics.weight.target && (
                            <div className="text-xs text-blue-500">目标 {analyzeData.body_metrics.weight.target}</div>
                          )}
                        </div>
                      )}
                      {analyzeData.body_metrics.sleep_score != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.sleep_score}</div>
                          <div className="text-xs text-gray-400">睡眠评分</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.body_battery != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.body_battery}</div>
                          <div className="text-xs text-gray-400">身体电量</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.stress_level != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.stress_level}</div>
                          <div className="text-xs text-gray-400">压力水平</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.resting_hr != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.resting_hr}</div>
                          <div className="text-xs text-gray-400">静息心率</div>
                        </div>
                      )}
                      {analyzeData.body_metrics.bmi != null && (
                        <div className="bg-white rounded-lg p-2 text-center">
                          <div className="text-lg font-bold text-gray-800">{analyzeData.body_metrics.bmi.toFixed(1)}</div>
                          <div className="text-xs text-gray-400">BMI</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 天气预报 */}
                {analyzeData.weather_forecast.available && analyzeData.weather_forecast.daily && (
                  <div className="bg-gray-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                      <Sun className="w-4 h-4" />
                      {analyzeData.weather_forecast.city}天气预报
                    </h3>
                    <div className="grid grid-cols-7 gap-1">
                      {analyzeData.weather_forecast.daily.map((d, idx) => (
                        <div key={idx} className="text-center bg-white rounded-lg p-1.5">
                          <div className="text-xs text-gray-500">{d.day_name}</div>
                          <div className="my-1">{getWeatherIcon(d.weather)}</div>
                          <div className="text-xs text-gray-400">{d.temp_low}~{d.temp_high}°</div>
                        </div>
                      ))}
                    </div>
                    {analyzeData.weather_forecast.air_quality && (
                      <div className="mt-2 text-xs text-gray-500">
                        空气质量: AQI {analyzeData.weather_forecast.air_quality.aqi} {analyzeData.weather_forecast.air_quality.level}
                      </div>
                    )}
                    {analyzeData.weather_forecast.exercise_advice && (
                      <div className="mt-1 text-xs text-blue-600">{analyzeData.weather_forecast.exercise_advice}</div>
                    )}
                  </div>
                )}

                {/* 行程 */}
                {analyzeData.trips.length > 0 && (
                  <div className="bg-amber-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-1.5">
                      <Plane className="w-4 h-4" />
                      本周行程
                    </h3>
                    {analyzeData.trips.map((trip, idx) => (
                      <div key={idx} className="text-sm">
                        <div className="font-medium text-gray-700">{trip.name} - {trip.destination}</div>
                        {trip.days.map((d, didx) => (
                          <div key={didx} className="text-xs text-gray-500 ml-2">{d.day_name}: {d.title}</div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* 活跃目标 */}
                {analyzeData.active_goals.length > 0 && (
                  <div className="bg-indigo-50 rounded-xl p-4">
                    <h3 className="text-sm font-semibold text-indigo-700 mb-2 flex items-center gap-1.5">
                      <Target className="w-4 h-4" />
                      活跃目标
                    </h3>
                    {analyzeData.active_goals.map((goal, idx) => (
                      <div key={idx} className="text-sm">
                        <div className="font-medium text-gray-700">{goal.period_type === 'monthly' ? '月度' : '年度'}目标</div>
                        {goal.metrics.map((m, midx) => (
                          <div key={midx} className="text-xs text-gray-500 ml-2">
                            {m.metric_name}: {m.current_value}{m.unit} → {m.target_value}{m.unit}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )
          )}

          {/* Step 2: 定制偏好 */}
          {step === 2 && analyzeData && (
            <>
              {generateError && (
                <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  {generateError}
                </div>
              )}

              {/* 重点方向 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">本周重点方向</h3>
                <p className="text-xs text-gray-400 mb-3">基于你的数据建议，点击选择或添加自定义</p>
                <div className="flex flex-wrap gap-2">
                  {analyzeData.suggested_focus.map((f, idx) => (
                    <button
                      key={idx}
                      onClick={() => toggleFocus(f.label)}
                      className={`text-sm px-3 py-1.5 rounded-full border transition-all ${
                        selectedFocus.includes(f.label)
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white text-gray-700 border-gray-200 hover:border-blue-300'
                      }`}
                      title={f.reason}
                    >
                      {selectedFocus.includes(f.label) ? <Check className="w-3 h-3 inline mr-1" /> : null}
                      {f.label}
                    </button>
                  ))}
                  {/* 已选但不在建议中的 */}
                  {selectedFocus.filter(f => !analyzeData.suggested_focus.some(s => s.label === f)).map((f, idx) => (
                    <button
                      key={`custom-${idx}`}
                      onClick={() => toggleFocus(f)}
                      className="text-sm px-3 py-1.5 rounded-full bg-blue-600 text-white border border-blue-600"
                    >
                      <Check className="w-3 h-3 inline mr-1" />{f}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2 mt-2">
                  <input
                    type="text"
                    value={customFocus}
                    onChange={(e) => setCustomFocus(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomFocus(); } }}
                    placeholder="添加自定义重点..."
                    className="flex-1 text-sm px-3 py-1.5 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400"
                  />
                  <button onClick={addCustomFocus} disabled={!customFocus.trim()} className="px-3 py-1.5 text-sm bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 disabled:opacity-50">
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* 运动强度 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">运动强度偏好</h3>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { key: 'light' as const, label: '轻松', desc: '恢复为主', icon: '🌿' },
                    { key: 'moderate' as const, label: '适中', desc: '平衡可持续', icon: '💪' },
                    { key: 'challenge' as const, label: '挑战', desc: '追求突破', icon: '🔥' },
                  ].map(opt => (
                    <button
                      key={opt.key}
                      onClick={() => setIntensity(opt.key)}
                      className={`p-3 rounded-xl border text-center transition-all ${
                        intensity === opt.key
                          ? 'border-blue-600 bg-blue-50 ring-1 ring-blue-600'
                          : 'border-gray-200 hover:border-blue-300'
                      }`}
                    >
                      <div className="text-xl mb-1">{opt.icon}</div>
                      <div className="text-sm font-medium text-gray-800">{opt.label}</div>
                      <div className="text-xs text-gray-400">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 备注 */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">备注（可选）</h3>
                <textarea
                  value={userNotes}
                  onChange={(e) => setUserNotes(e.target.value)}
                  placeholder="如：周三出差不能运动、周末想安排户外跑步、最近膝盖不舒服..."
                  rows={3}
                  className="w-full text-sm px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-blue-400 resize-none"
                />
              </div>
            </>
          )}

          {/* Step 3: 生成中 */}
          {step === 3 && (
            <div className="flex flex-col items-center justify-center py-8">
              <div className="w-16 h-16 mb-6 relative">
                <Brain className="w-16 h-16 text-blue-500 animate-pulse" />
              </div>
              <div className="space-y-3 w-full max-w-xs">
                {[
                  { icon: '🧠', text: '分析健康数据...' },
                  { icon: '🌤', text: '结合天气和行程...' },
                  { icon: '📊', text: '制定个性化方案...' },
                  { icon: '✅', text: '生成完成！' },
                ].map((item, idx) => (
                  <div key={idx} className={`flex items-center gap-3 transition-all duration-500 ${
                    progressStep >= idx ? 'opacity-100' : 'opacity-30'
                  }`}>
                    <span className="text-lg">{item.icon}</span>
                    <span className={`text-sm ${progressStep >= idx ? 'text-gray-700' : 'text-gray-400'}`}>{item.text}</span>
                    {progressStep > idx && <Check className="w-4 h-4 text-green-500 ml-auto" />}
                    {progressStep === idx && idx < 3 && <Loader2 className="w-4 h-4 text-blue-500 animate-spin ml-auto" />}
                  </div>
                ))}
              </div>
              <div className="mt-6 w-full max-w-xs">
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min((progressStep / 4) * 100, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {step !== 3 && (
          <div className="flex items-center justify-between px-5 py-4 border-t bg-gray-50">
            {step === 1 ? (
              <>
                <div />
                <button
                  onClick={() => setStep(2)}
                  disabled={analyzeLoading || !!analyzeError}
                  className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
                >
                  下一步 <ArrowRight className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setStep(1)}
                  className="text-sm text-gray-600 hover:text-gray-800"
                >
                  ← 上一步
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium"
                >
                  <Sparkles className="w-4 h-4" />
                  生成计划
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DebugPanel({ debug }: { debug: any }) {
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());

  const toggleSource = (key: string) => {
    setExpandedSources(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="bg-gradient-to-br from-purple-50 to-indigo-50 rounded-xl p-5 mb-6 border border-purple-200">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-purple-800 flex items-center gap-2">
          <span>🔍</span> AI 决策过程
        </h3>
        {debug.performance?.['总耗时'] && (
          <span className="text-sm font-mono bg-purple-100 text-purple-700 px-3 py-1 rounded-full">
            ⏱ {debug.performance['总耗时']}
          </span>
        )}
      </div>

      {/* Steps with Timing */}
      {debug.steps?.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-purple-700 mb-2">📋 执行步骤</h4>
          <div className="space-y-1.5">
            {debug.steps.map((step: string, index: number) => {
              const stepName = step.replace(/^\d+\.\s*/, '');
              const duration = debug.performance?.[stepName];
              return (
                <div key={index} className="flex items-center gap-2 bg-white/70 rounded-lg px-3 py-2">
                  <span className="text-purple-600 font-bold min-w-[24px] text-center bg-purple-100 rounded px-1.5 py-0.5 text-xs">
                    {index + 1}
                  </span>
                  <span className="flex-1 text-sm text-gray-700">{stepName}</span>
                  {duration && (
                    <span className="text-xs font-mono text-purple-500 bg-purple-50 px-2 py-0.5 rounded">
                      {duration}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {debug.reasoning?.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-purple-700 mb-2">💡 推理过程</h4>
          <div className="space-y-1">
            {debug.reasoning.map((reason: string, index: number) => {
              const isError = reason.includes('❌');
              const isWarning = reason.includes('⚠️');
              const isSuccess = reason.includes('✅');
              const bgColor = isError
                ? 'bg-red-50 border-red-200'
                : isWarning
                ? 'bg-yellow-50 border-yellow-200'
                : isSuccess
                ? 'bg-green-50 border-green-200'
                : 'bg-white/60 border-gray-200';

              return (
                <div key={index} className={`${bgColor} rounded-lg px-3 py-2 border text-sm`}>
                  <span className="text-gray-700 leading-relaxed whitespace-pre-wrap">{reason}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Data Sources */}
      {debug.data_sources && Object.keys(debug.data_sources).length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-purple-700 mb-2">📊 数据来源</h4>
          <div className="space-y-1.5">
            {Object.entries(debug.data_sources).map(([key, value]) => (
              <div key={key} className="bg-white/70 rounded-lg border border-gray-200 overflow-hidden">
                <button
                  onClick={() => toggleSource(key)}
                  className="w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-white/90 transition-colors"
                >
                  <span className="font-medium text-gray-700">{key}</span>
                  <span className="text-gray-400 text-xs">{expandedSources.has(key) ? '收起 ▲' : '展开 ▼'}</span>
                </button>
                {expandedSources.has(key) && (
                  <div className="px-3 pb-2 border-t border-gray-100">
                    <pre className="text-xs text-gray-600 whitespace-pre-wrap break-all max-h-60 overflow-y-auto mt-2 font-mono">
                      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Performance Metrics */}
      {debug.performance && Object.keys(debug.performance).length > 1 && (
        <div>
          <h4 className="text-sm font-semibold text-purple-700 mb-2">⚡ 性能指标</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {Object.entries(debug.performance).map(([key, value]) => (
              <div key={key} className="bg-white/70 rounded-lg p-2 border border-gray-200">
                <div className="text-purple-600 truncate">{key}</div>
                <div className="text-gray-800 font-mono font-medium">{String(value)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function GoalsTab({ debugMode }: { debugMode: boolean }) {
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

function HistoryCard({ plan }: { plan: PlanListItem }) {
  const router = useRouter();

  const formatWeekRange = (weekStart: string) => {
    const start = new Date(weekStart);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return `${start.getMonth() + 1}/${start.getDate()} - ${end.getMonth() + 1}/${end.getDate()}`;
  };

  return (
    <div
      onClick={() => router.push(`/smart-plan/${plan.id}`)}
      className="bg-white border border-gray-200 rounded-xl p-4 hover:border-blue-200 hover:shadow-sm transition-all cursor-pointer"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-gray-400" />
          <span className="font-medium text-gray-800">{formatWeekRange(plan.week_start)}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            plan.status === 'active' ? 'bg-green-100 text-green-700' :
            plan.status === 'completed' ? 'bg-blue-100 text-blue-700' :
            'bg-gray-100 text-gray-500'
          }`}>
            {plan.status === 'active' ? '进行中' :
             plan.status === 'completed' ? '已完成' :
             plan.status === 'archived' ? '已归档' : plan.status}
          </span>
        </div>
        <ChevronRight className="w-4 h-4 text-gray-300" />
      </div>

      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full"
              style={{ width: `${plan.completion_rate}%` }}
            />
          </div>
        </div>
        <span className="text-sm font-medium text-gray-600">
          {plan.completed_count}/{plan.item_count}
        </span>
        <span className="text-sm text-blue-600 font-medium">{Math.round(plan.completion_rate)}%</span>
      </div>

      {plan.focus_areas.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {plan.focus_areas.slice(0, 3).map((area, idx) => (
            <span key={idx} className="text-xs bg-gray-50 text-gray-500 px-2 py-0.5 rounded-full">{area}</span>
          ))}
        </div>
      )}

      {plan.user_feedback && (
        <div className="flex items-center gap-1 mt-2">
          {[1, 2, 3, 4, 5].map(s => (
            <Star key={s} className={`w-3 h-3 ${s <= plan.user_feedback! ? 'fill-yellow-400 text-yellow-400' : 'text-gray-200'}`} />
          ))}
        </div>
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
