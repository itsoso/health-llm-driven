'use client';
import { useRouter } from 'next/navigation';

interface ActivityCardProps {
  todayGarmin: any;
  workoutRecent: any[];
  medToday: any[];
  supplementStatus: any[];
}

export default function ActivityCard({ todayGarmin, workoutRecent, medToday, supplementStatus }: ActivityCardProps) {
  const router = useRouter();

  // Supplement summary
  const seen = new Set<string>();
  const deduped = supplementStatus.filter((s: any) => {
    const name = s.supplement?.name || s.supplement_name || s.name;
    const timing = s.supplement?.timing || s.timing || 'morning';
    const key = `${name}_${timing}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const suppChecked = deduped.filter((s: any) => s.record?.taken || s.is_taken || s.checked).length;
  const suppTotal = deduped.length;

  return (
    <div className="grid grid-cols-2 gap-2.5">
      {/* Activity */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-3 cursor-pointer" onClick={() => router.push('/garmin')}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-600">🏃 活动</span>
          {todayGarmin?.active_calories > 0 && <span className="text-[10px] font-bold text-orange-500">{todayGarmin.active_calories}kcal</span>}
        </div>
        <div className="text-2xl font-bold text-gray-800 leading-tight">
          {todayGarmin?.active_minutes || 0}<span className="text-xs font-normal text-gray-400 ml-0.5">min</span>
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

      {/* Supplements summary */}
      {suppTotal > 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-gray-600">💊 补剂</span>
            <span className="text-[11px] text-gray-400">{suppChecked}/{suppTotal}</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-gray-100 mb-2">
            <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${suppTotal > 0 ? (suppChecked / suppTotal * 100) : 0}%` }} />
          </div>
          <div className="flex flex-col gap-0.5 max-h-[120px] overflow-y-auto">
            {deduped.slice(0, 5).map((s: any, i: number) => {
              const taken = s.taken || s.is_taken || s.record?.taken || s.checked;
              const name = s.product_name || s.supplement_name || s.supplement?.name || s.name || '';
              return (
                <div key={i} className="flex items-center gap-1.5">
                  <div className={`w-3 h-3 rounded-sm flex items-center justify-center shrink-0 ${taken ? 'bg-emerald-500' : 'border border-gray-300'}`}>
                    {taken && <svg className="w-2 h-2 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                  </div>
                  <span className={`text-[10px] truncate ${taken ? 'text-gray-400' : 'text-gray-700'}`}>{name}</span>
                </div>
              );
            })}
            {deduped.length > 5 && <span className="text-[9px] text-emerald-600 mt-0.5">+{deduped.length - 5} 项</span>}
          </div>
        </div>
      )}
    </div>
  );
}
