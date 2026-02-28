'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { smartPlanApi } from '@/services/api';
import {
  Calendar, ChevronLeft, ChevronRight, Check, Circle, Star,
  Loader2, RefreshCw, Trash2, Dumbbell, Utensils, Moon, Sparkles, MoreHorizontal
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

const dayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const categoryConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  exercise: { label: '运动', color: 'bg-blue-100 text-blue-700', icon: <Dumbbell className="w-3.5 h-3.5" /> },
  diet: { label: '饮食', color: 'bg-green-100 text-green-700', icon: <Utensils className="w-3.5 h-3.5" /> },
  rest: { label: '休息', color: 'bg-purple-100 text-purple-700', icon: <Moon className="w-3.5 h-3.5" /> },
  habit: { label: '习惯', color: 'bg-amber-100 text-amber-700', icon: <Sparkles className="w-3.5 h-3.5" /> },
  other: { label: '其他', color: 'bg-gray-100 text-gray-700', icon: <MoreHorizontal className="w-3.5 h-3.5" /> },
};

function SmartPlanContent() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'current' | 'history'>('current');
  const [selectedDay, setSelectedDay] = useState<number>(() => {
    const today = new Date().getDay();
    return today === 0 ? 7 : today; // 周日=7
  });
  const [feedbackScore, setFeedbackScore] = useState<number>(0);
  const [showFeedback, setShowFeedback] = useState(false);

  // 当前计划
  const { data: currentPlan, isLoading: planLoading } = useQuery<WeeklyPlan | null>({
    queryKey: ['smart-plan', 'current'],
    queryFn: async () => {
      const res = await smartPlanApi.getCurrent();
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

  // 生成计划
  const generateMutation = useMutation({
    mutationFn: (targetWeek: string) => smartPlanApi.generate(targetWeek),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan'] });
    },
  });

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
          <p className="text-sm text-gray-500 mt-1">AI 为你量身定制的每周健康计划</p>
        </div>
        <button
          onClick={() => generateMutation.mutate('current')}
          disabled={generateMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {generateMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {generateMutation.isPending ? '生成中...' : '生成本周计划'}
        </button>
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
      </div>

      {/* Current Plan Tab */}
      {activeTab === 'current' && (
        <>
          {planLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : !currentPlan ? (
            <div className="text-center py-20">
              <Calendar className="w-16 h-16 mx-auto text-gray-300 mb-4" />
              <h3 className="text-lg font-medium text-gray-600 mb-2">还没有本周计划</h3>
              <p className="text-gray-400 mb-6">点击"生成本周计划"，AI 将根据你的健康数据定制专属计划</p>
              <button
                onClick={() => generateMutation.mutate('current')}
                disabled={generateMutation.isPending}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {generateMutation.isPending ? '生成中...' : '立即生成'}
              </button>
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
