'use client';

import { useRouter } from 'next/navigation';
import { Calendar, ChevronRight, Star } from 'lucide-react';
import { PlanListItem } from './types';

export function HistoryCard({ plan }: { plan: PlanListItem }) {
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
