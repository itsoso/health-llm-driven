'use client';

import { Plus } from 'lucide-react';
import { WeeklyPlan, categoryConfig } from './types';

export function WeekExecutionCard({ plan, weekLabel, isCurrent, onCreatePlan }: {
  plan: WeeklyPlan | null | undefined;
  weekLabel: string;
  isCurrent: boolean;
  onCreatePlan: () => void;
}) {
  const today = new Date();
  const todayDow = today.getDay() === 0 ? 7 : today.getDay();
  const shortDayNames = ['一', '二', '三', '四', '五', '六', '日'];

  const formatRange = (weekStart: string) => {
    const s = new Date(weekStart);
    const e = new Date(s);
    e.setDate(e.getDate() + 6);
    return `${s.getMonth() + 1}/${s.getDate()} - ${e.getMonth() + 1}/${e.getDate()}`;
  };

  if (!plan) {
    return (
      <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-dashed border-gray-200">
        <div>
          <span className="font-medium text-gray-700">{weekLabel}</span>
          <p className="text-xs text-gray-400 mt-1">尚未制定计划</p>
        </div>
        <button
          onClick={onCreatePlan}
          className="flex items-center gap-1 text-sm px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          制定
        </button>
      </div>
    );
  }

  const dayStats = [1, 2, 3, 4, 5, 6, 7].map(day => {
    const dayItems = plan.items.filter(i => i.day_of_week === day);
    const done = dayItems.filter(i => i.is_completed).length;
    const total = dayItems.length;
    return { day, done, total };
  });

  const catStats = ['exercise', 'diet', 'rest', 'habit'].map(cat => {
    const items = plan.items.filter(i => i.category === cat);
    return { cat, done: items.filter(i => i.is_completed).length, total: items.length };
  }).filter(c => c.total > 0);

  const rate = Math.round(plan.completion_rate);
  const rateColor = rate >= 80 ? 'text-green-600' : rate >= 50 ? 'text-blue-600' : 'text-amber-600';
  const barColor = rate >= 80 ? 'bg-green-500' : rate >= 50 ? 'bg-blue-500' : 'bg-amber-500';

  return (
    <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-gray-800 flex-shrink-0">{weekLabel}</span>
          <span className="text-xs text-gray-400 truncate">{formatRange(plan.week_start)}</span>
        </div>
        <div className="flex items-baseline gap-1 flex-shrink-0">
          <span className={`text-xl font-bold ${rateColor}`}>{rate}%</span>
          <span className="text-xs text-gray-400">完成</span>
        </div>
      </div>

      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-3">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${rate}%` }} />
      </div>

      <div className="flex gap-1 mb-2.5">
        {dayStats.map(({ day, done, total }) => {
          const isActiveDay = isCurrent && day === todayDow;
          const isEmpty = total === 0;
          const isDone = !isEmpty && done === total;
          const isPartial = !isEmpty && done > 0 && done < total;
          return (
            <div key={day} className="flex-1 flex flex-col items-center gap-0.5">
              <div className={`w-full h-2 rounded-full ${
                isEmpty ? 'bg-gray-100' :
                isDone ? 'bg-green-400' :
                isPartial ? 'bg-amber-400' : 'bg-red-200'
              } ${isActiveDay ? 'ring-1 ring-offset-1 ring-blue-400' : ''}`} />
              <span className={`text-[9px] leading-none ${isActiveDay ? 'text-blue-500 font-bold' : 'text-gray-400'}`}>
                {shortDayNames[day - 1]}
              </span>
            </div>
          );
        })}
      </div>

      {catStats.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {catStats.map(({ cat, done, total }) => {
            const cfg = categoryConfig[cat] || categoryConfig.other;
            return (
              <span key={cat} className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${cfg.color}`}>
                {cfg.icon}
                {done}/{total}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
