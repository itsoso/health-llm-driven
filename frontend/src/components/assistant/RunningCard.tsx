'use client';
import { useMemo } from 'react';
import { useRouter } from 'next/navigation';

interface RunningCardProps {
  todayGarmin: any;
  workoutRecent: any[];
}

export default function RunningCard({ todayGarmin, workoutRecent }: RunningCardProps) {
  const router = useRouter();

  // Filter running workouts from recent 7 days
  const runs = useMemo(() => {
    return workoutRecent
      .filter((w: any) => {
        const type = (w.activity_type || w.sport_type || '').toLowerCase();
        return type.includes('running') || type.includes('跑步') || type.includes('run');
      })
      .sort((a: any, b: any) => (b.record_date || '').localeCompare(a.record_date || ''));
  }, [workoutRecent]);

  const latestRun = runs[0];
  const weekRuns = runs.length;
  const weekDistance = runs.reduce((s: number, w: any) => s + (w.distance_meters || 0), 0) / 1000;
  const weekCalories = runs.reduce((s: number, w: any) => s + (w.calories || 0), 0);

  // Format pace (min/km)
  const formatPace = (distM: number, durS: number) => {
    if (!distM || !durS) return '--';
    const paceS = durS / (distM / 1000);
    const m = Math.floor(paceS / 60);
    const s = Math.round(paceS % 60);
    return `${m}'${s.toString().padStart(2, '0')}"`;
  };

  // Format duration
  const formatDuration = (seconds: number) => {
    if (!seconds) return '--';
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return h > 0 ? `${h}h${m}m` : `${m}min`;
  };

  // Week day labels for sparkline
  const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayDayIndex = (new Date().getDay() + 6) % 7;

  // Build 7-day distance data
  const weekData = useMemo(() => {
    const byDate: Record<string, number> = {};
    for (const r of runs) {
      const d = (r.record_date || '').slice(0, 10);
      byDate[d] = (byDate[d] || 0) + (r.distance_meters || 0) / 1000;
    }
    const days: number[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
      days.push(byDate[d] || 0);
    }
    return days;
  }, [runs]);

  const maxWeek = Math.max(...weekData, 5); // min 5km scale

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => router.push('/workout')}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🏃</span>
          <span className="text-sm font-bold text-gray-800">跑步</span>
        </div>
        <span className="text-[10px] text-gray-400">本周{weekRuns}次</span>
      </div>

      {/* Latest run or weekly summary */}
      {latestRun ? (
        <div>
          <div className="flex items-end gap-3">
            <div>
              <div className="text-2xl font-extrabold text-gray-800">
                {(latestRun.distance_meters / 1000).toFixed(1)}
                <span className="text-[10px] font-normal text-gray-400 ml-0.5">km</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">
                {(latestRun.record_date || '').slice(5, 10)}
              </div>
            </div>
            <div className="flex-1 flex gap-3">
              <div className="text-center">
                <div className="text-xs font-bold text-emerald-600">
                  {formatPace(latestRun.distance_meters, latestRun.duration_seconds)}
                </div>
                <div className="text-[9px] text-gray-400">配速</div>
              </div>
              <div className="text-center">
                <div className="text-xs font-bold text-gray-700">
                  {formatDuration(latestRun.duration_seconds)}
                </div>
                <div className="text-[9px] text-gray-400">时长</div>
              </div>
              {latestRun.calories > 0 && (
                <div className="text-center">
                  <div className="text-xs font-bold text-orange-500">{latestRun.calories}</div>
                  <div className="text-[9px] text-gray-400">kcal</div>
                </div>
              )}
            </div>
          </div>
          {/* Weekly summary line */}
          {weekRuns > 1 && (
            <div className="text-[10px] text-gray-400 mt-1.5">
              本周 {weekDistance.toFixed(1)}km · {weekCalories}kcal
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-2">
          <div className="text-2xl font-extrabold text-gray-300">--</div>
          <div className="text-[10px] text-gray-400 mt-1">本周暂无跑步记录</div>
          {todayGarmin?.steps > 0 && (
            <div className="text-[10px] text-emerald-500 mt-1">
              今日 {todayGarmin.steps.toLocaleString()} 步 · {todayGarmin.active_minutes || 0}min活动
            </div>
          )}
        </div>
      )}

      {/* Week sparkline */}
      {weekData.some(v => v > 0) && (
        <div className="mt-3 pt-2.5 border-t border-gray-50">
          <div className="flex items-end gap-1 h-7">
            {weekData.map((val, i) => {
              const h = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 28) : 2;
              const isToday = i === weekData.length - 1;
              return (
                <div key={i} className={`flex-1 rounded-sm transition-all ${isToday ? 'bg-emerald-500' : val > 0 ? 'bg-emerald-200' : 'bg-gray-100'}`}
                  style={{ height: `${h}px` }} />
              );
            })}
          </div>
          <div className="flex gap-1 mt-0.5">
            {weekData.map((_, i) => (
              <div key={i} className="flex-1 text-center text-[8px] text-gray-300">
                {weekDays[(todayDayIndex - 6 + i + 7) % 7]}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
