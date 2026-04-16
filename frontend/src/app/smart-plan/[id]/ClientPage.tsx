'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter, useParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { smartPlanApi } from '@/services/api/content';
import {
  Calendar, ChevronLeft, Check, Circle, Star,
  Loader2, Trash2, Dumbbell, Utensils, Moon, Sparkles, MoreHorizontal
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

const dayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

const categoryConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  exercise: { label: '运动', color: 'bg-blue-100 text-blue-700', icon: <Dumbbell className="w-3.5 h-3.5" /> },
  diet: { label: '饮食', color: 'bg-green-100 text-green-700', icon: <Utensils className="w-3.5 h-3.5" /> },
  rest: { label: '休息', color: 'bg-purple-100 text-purple-700', icon: <Moon className="w-3.5 h-3.5" /> },
  habit: { label: '习惯', color: 'bg-amber-100 text-amber-700', icon: <Sparkles className="w-3.5 h-3.5" /> },
  other: { label: '其他', color: 'bg-gray-100 text-gray-700', icon: <MoreHorizontal className="w-3.5 h-3.5" /> },
};

export default function PlanDetailPage() {
  const router = useRouter();
  const params = useParams();
  const planId = Number(params.id);
  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [selectedDay, setSelectedDay] = useState<number>(1);
  const [feedbackScore, setFeedbackScore] = useState<number>(0);
  const [showFeedback, setShowFeedback] = useState(false);

  const { data: plan, isLoading } = useQuery<WeeklyPlan>({
    queryKey: ['smart-plan', planId],
    queryFn: async () => {
      const res = await smartPlanApi.getDetail(planId);
      return res.data;
    },
    enabled: !!planId && isAuthenticated,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ itemId, isCompleted }: { itemId: number; isCompleted: boolean }) =>
      smartPlanApi.updateItem(planId, itemId, isCompleted),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan', planId] });
    },
  });

  const feedbackMutation = useMutation({
    mutationFn: (score: number) => smartPlanApi.submitFeedback(planId, score),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['smart-plan'] });
      setShowFeedback(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => smartPlanApi.deletePlan(planId),
    onSuccess: () => {
      router.push('/smart-plan');
    },
  });

  if (authLoading || isLoading) {
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

  if (!plan) {
    return (
      <div className="max-w-4xl mx-auto p-4 text-center py-20">
        <p className="text-gray-500">计划不存在</p>
        <button onClick={() => router.push('/smart-plan')} className="mt-4 text-blue-600 hover:underline">
          返回计划列表
        </button>
      </div>
    );
  }

  const todayItems = plan.items.filter(i => i.day_of_week === selectedDay);

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

  return (
    <div className="max-w-4xl mx-auto p-4 pb-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.push('/smart-plan')} className="text-gray-400 hover:text-gray-600">
          <ChevronLeft className="w-6 h-6" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-900">{formatWeekRange(plan.week_start)}</h1>
          <p className="text-sm text-gray-500">
            {plan.status === 'active' ? '进行中' :
             plan.status === 'completed' ? '已完成' :
             plan.status === 'archived' ? '已归档' : plan.status}
            {' · '}完成率 {Math.round(plan.completion_rate)}%
          </p>
        </div>
        <button
          onClick={() => {
            if (confirm('确定删除此计划？')) deleteMutation.mutate();
          }}
          className="text-gray-400 hover:text-red-500"
        >
          <Trash2 className="w-5 h-5" />
        </button>
      </div>

      {/* Summary */}
      {plan.weekly_summary && (
        <div className="bg-blue-50 rounded-xl p-4 mb-4">
          <p className="text-sm text-gray-700 leading-relaxed">{plan.weekly_summary}</p>
          {plan.focus_areas.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {plan.focus_areas.map((area, idx) => (
                <span key={idx} className="text-xs bg-white/70 text-blue-700 px-2 py-1 rounded-full">{area}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Feedback */}
      <div className="flex items-center gap-3 mb-4">
        {plan.user_feedback ? (
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <span>评分:</span>
            {[1, 2, 3, 4, 5].map(s => (
              <Star key={s} className={`w-4 h-4 ${s <= plan.user_feedback! ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`} />
            ))}
          </div>
        ) : (
          <>
            <button onClick={() => setShowFeedback(!showFeedback)} className="text-sm text-blue-600 hover:text-blue-700">
              评价此计划
            </button>
            {showFeedback && (
              <div className="flex items-center gap-2">
                {[1, 2, 3, 4, 5].map(s => (
                  <button key={s} onClick={() => setFeedbackScore(s)}>
                    <Star className={`w-5 h-5 ${s <= feedbackScore ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`} />
                  </button>
                ))}
                {feedbackScore > 0 && (
                  <button
                    onClick={() => feedbackMutation.mutate(feedbackScore)}
                    className="text-sm px-3 py-1 bg-blue-600 text-white rounded-md"
                  >
                    提交
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Day Selector */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        {[1, 2, 3, 4, 5, 6, 7].map(day => {
          const dayItems = plan.items.filter(i => i.day_of_week === day);
          const dayCompleted = dayItems.filter(i => i.is_completed).length;
          const dayTotal = dayItems.length;

          return (
            <button
              key={day}
              onClick={() => setSelectedDay(day)}
              className={`flex-1 min-w-[52px] py-2 px-1 rounded-lg text-center transition-colors ${
                selectedDay === day
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
              }`}
            >
              <div className="text-xs font-medium">{dayNames[day - 1]}</div>
              <div className="text-xs opacity-70">{getWeekDayDate(plan.week_start, day)}</div>
              {dayTotal > 0 && (
                <div className={`text-xs mt-0.5 ${selectedDay === day ? 'text-blue-100' : 'text-gray-400'}`}>
                  {dayCompleted}/{dayTotal}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Items */}
      <div className="space-y-3">
        {todayItems.length === 0 ? (
          <div className="text-center py-8 text-gray-400">这一天没有计划项</div>
        ) : (
          todayItems.map(item => {
            const cat = categoryConfig[item.category] || categoryConfig.other;
            return (
              <div
                key={item.id}
                className={`flex items-start gap-3 p-4 rounded-xl border transition-all ${
                  item.is_completed
                    ? 'bg-gray-50 border-gray-100'
                    : 'bg-white border-gray-200 hover:border-blue-200'
                }`}
              >
                <button
                  onClick={() => toggleMutation.mutate({ itemId: item.id, isCompleted: !item.is_completed })}
                  disabled={toggleMutation.isPending}
                  className="mt-0.5 flex-shrink-0"
                >
                  {item.is_completed ? (
                    <Check className="w-5 h-5 text-green-500" />
                  ) : (
                    <Circle className="w-5 h-5 text-gray-300 hover:text-blue-400" />
                  )}
                </button>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${cat.color}`}>
                      {cat.icon}
                      {cat.label}
                    </span>
                    {item.target_value && item.target_unit && (
                      <span className="text-xs text-gray-400">目标: {item.target_value}{item.target_unit}</span>
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
    </div>
  );
}
