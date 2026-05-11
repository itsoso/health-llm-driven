'use client';
import { useRouter } from 'next/navigation';

interface ActivityCardProps {
  todayGarmin: any;
  workoutRecent: any[];
  medToday: any[];
}

export default function ActivityCard({ todayGarmin, workoutRecent, medToday }: ActivityCardProps) {
  const router = useRouter();

  // active_minutes 可能偏低，取 active_minutes 和 (moderate + vigorous) 的较大值
  const intensityMinutes = (todayGarmin?.moderate_intensity_minutes || 0) + (todayGarmin?.vigorous_intensity_minutes || 0);
  const displayMinutes = Math.max(todayGarmin?.active_minutes || 0, intensityMinutes);

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-3 cursor-pointer" onClick={() => router.push('/settings')}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-gray-600">🏃 活动</span>
        {todayGarmin?.active_calories > 0 && <span className="text-[10px] font-bold text-orange-500">{todayGarmin.active_calories}kcal</span>}
      </div>
      <div className="text-2xl font-bold text-gray-800 leading-tight">
        {displayMinutes}<span className="text-xs font-normal text-gray-400 ml-0.5">min</span>
      </div>
      <div className="text-[10px] text-gray-500 mt-1">
        {todayGarmin?.steps ? `${todayGarmin.steps.toLocaleString()} 步` : '0 步'}
      </div>
      {workoutRecent.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          {workoutRecent.slice(0, 2).map((w: any, i: number) => {
            const dist = w.distance_meters ? (w.distance_meters / 1000).toFixed(1) : null;
            const dur = w.duration_seconds ? Math.round(w.duration_seconds / 60) : null;
            return (
              <div key={i} className="text-[10px] bg-emerald-50 rounded-md px-2 py-1 text-emerald-700 font-medium">
                {dist && `${dist}km`} {dur && `${dur}min`} {w.calories && <span className="text-orange-500">{w.calories}kcal</span>}
              </div>
            );
          })}
        </div>
      )}
      {medToday.length > 0 && (
        <div className="flex items-center gap-1 mt-2 flex-wrap">
          {medToday.map((m: any) => (
            <span key={m.medication_id} className={`text-[9px] px-1.5 py-0.5 rounded-full ${m.taken_count > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>{m.name}</span>
          ))}
        </div>
      )}
    </div>
  );
}
