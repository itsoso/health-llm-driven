'use client';
import { useMemo } from 'react';
import { useRouter } from 'next/navigation';

interface WorkoutCardProps {
  todayGarmin: any;
  workoutRecent: any[];
}

// 运动类型 → 中文 + emoji
const ACTIVITY_LABELS: Record<string, { label: string; emoji: string }> = {
  running: { label: '跑步', emoji: '🏃' },
  trail_running: { label: '越野跑', emoji: '⛰️' },
  treadmill_running: { label: '跑步机', emoji: '🏃' },
  walking: { label: '步行', emoji: '🚶' },
  hiking: { label: '徒步', emoji: '🥾' },
  cycling: { label: '骑行', emoji: '🚴' },
  swimming: { label: '游泳', emoji: '🏊' },
  stair_climbing: { label: '爬楼', emoji: '🪜' },
  floor_climbing: { label: '爬楼', emoji: '🪜' },
  elliptical: { label: '椭圆机', emoji: '🏋️' },
  strength_training: { label: '力量', emoji: '💪' },
  yoga: { label: '瑜伽', emoji: '🧘' },
  cardio: { label: '有氧', emoji: '❤️‍🔥' },
  other: { label: '运动', emoji: '🏅' },
};

function getActivityInfo(type: string): { label: string; emoji: string } {
  const t = (type || '').toLowerCase().replace(/\s+/g, '_');
  // Direct match
  if (ACTIVITY_LABELS[t]) return ACTIVITY_LABELS[t];
  // Partial match
  for (const [key, val] of Object.entries(ACTIVITY_LABELS)) {
    if (t.includes(key) || key.includes(t)) return val;
  }
  // Chinese match
  if (t.includes('跑步') || t.includes('run')) return ACTIVITY_LABELS.running;
  if (t.includes('爬楼') || t.includes('stair') || t.includes('floor') || t.includes('climb')) return ACTIVITY_LABELS.stair_climbing;
  if (t.includes('骑') || t.includes('cycl')) return ACTIVITY_LABELS.cycling;
  if (t.includes('游泳') || t.includes('swim')) return ACTIVITY_LABELS.swimming;
  if (t.includes('步行') || t.includes('walk')) return ACTIVITY_LABELS.walking;
  if (t.includes('徒步') || t.includes('hik')) return ACTIVITY_LABELS.hiking;
  return { label: type || '运动', emoji: '🏅' };
}

function formatDuration(seconds: number) {
  if (!seconds) return '--';
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h${m}m` : `${m}min`;
}

function formatPace(distM: number, durS: number) {
  if (!distM || !durS) return null;
  const paceS = durS / (distM / 1000);
  const m = Math.floor(paceS / 60);
  const s = Math.round(paceS % 60);
  return `${m}'${s.toString().padStart(2, '0')}"`;
}

export default function WorkoutCard({ todayGarmin, workoutRecent }: WorkoutCardProps) {
  const router = useRouter();

  // All workouts sorted by date desc
  const workouts = useMemo(() => {
    return [...workoutRecent]
      .sort((a: any, b: any) => (b.workout_date || '').localeCompare(a.workout_date || ''));
  }, [workoutRecent]);

  const weekCount = workouts.length;
  const weekCalories = workouts.reduce((s: number, w: any) => s + (w.calories || 0), 0);
  const weekDuration = workouts.reduce((s: number, w: any) => s + (w.duration_seconds || 0), 0);

  // Latest workout
  const latest = workouts[0];
  const latestInfo = latest ? getActivityInfo(latest.workout_type || latest.activity_type || '') : null;

  // Today's Garmin summary
  const steps = todayGarmin?.steps || 0;
  const activeMin = todayGarmin?.active_minutes || 0;
  const activeCal = todayGarmin?.active_calories || 0;

  // Week sparkline by day (calories or duration)
  const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayIdx = (new Date().getDay() + 6) % 7;

  const weekData = useMemo(() => {
    const now = new Date();
    const dayOfWeek = (now.getDay() + 6) % 7;
    const monday = new Date(now);
    monday.setDate(now.getDate() - dayOfWeek);

    const byDate: Record<string, number> = {};
    for (const w of workouts) {
      const d = (w.workout_date || '').slice(0, 10);
      byDate[d] = (byDate[d] || 0) + (w.duration_seconds || 0) / 60; // minutes
    }
    const days: number[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      days.push(byDate[d.toISOString().slice(0, 10)] || 0);
    }
    return days;
  }, [workouts]);

  const maxWeek = Math.max(...weekData, 30); // min 30min scale

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => router.push('/workout')}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🏅</span>
          <span className="text-sm font-bold text-gray-800">运动</span>
        </div>
        <span className="text-[10px] text-gray-400">本周{weekCount}次</span>
      </div>

      {/* Today's Garmin Activity */}
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 flex items-baseline gap-1">
          <span className="text-2xl font-extrabold text-gray-800">{steps.toLocaleString()}</span>
          <span className="text-[10px] text-gray-400">步</span>
        </div>
        <div className="text-right">
          <div className="text-xs font-bold text-orange-500">{activeCal > 0 ? `${activeCal}kcal` : '--'}</div>
          <div className="text-[10px] text-gray-400">{activeMin}min活动</div>
        </div>
      </div>

      {/* Recent workouts (up to 2) */}
      {workouts.length > 0 && (
        <div className="space-y-1 mb-1">
          {workouts.slice(0, 2).map((w: any, i: number) => {
            const info = getActivityInfo(w.workout_type || w.activity_type || '');
            const dist = w.distance_meters ? (w.distance_meters / 1000).toFixed(1) : null;
            const dur = formatDuration(w.duration_seconds);
            const pace = w.distance_meters ? formatPace(w.distance_meters, w.duration_seconds) : null;
            const dateStr = (w.workout_date || '').slice(5, 10);
            return (
              <div key={i} className="flex items-center gap-2 text-[10px] bg-emerald-50 rounded-lg px-2.5 py-1.5">
                <span>{info.emoji}</span>
                <span className="font-semibold text-emerald-700">{info.label}</span>
                {dist && <span className="text-emerald-600">{dist}km</span>}
                {pace && <span className="text-emerald-500">{pace}</span>}
                <span className="text-gray-500">{dur}</span>
                {w.calories > 0 && <span className="text-orange-500">{w.calories}kcal</span>}
                <span className="ml-auto text-gray-400">{dateStr}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Week summary */}
      {weekCount > 0 && (
        <div className="text-[10px] text-gray-400 mb-1">
          本周 {formatDuration(weekDuration)} · {weekCalories}kcal
        </div>
      )}

      {/* Week sparkline */}
      {weekData.some(v => v > 0) && (
        <div className="mt-2 pt-2 border-t border-gray-50">
          <div className="flex items-end gap-1 h-7">
            {weekData.map((val, i) => {
              const h = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 28) : 2;
              const isToday = i === todayIdx;
              return (
                <div key={i} className={`flex-1 rounded-sm transition-all ${isToday ? 'bg-emerald-500' : val > 0 ? 'bg-emerald-200' : 'bg-gray-100'}`}
                  style={{ height: `${h}px` }} />
              );
            })}
          </div>
          <div className="flex gap-1 mt-0.5">
            {weekDays.map((d, i) => (
              <div key={i} className={`flex-1 text-center text-[8px] ${i === todayIdx ? 'text-gray-500 font-bold' : 'text-gray-300'}`}>
                {d}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
