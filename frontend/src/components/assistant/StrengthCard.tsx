'use client';
import { useState, useEffect, useCallback } from 'react';
import { api, dailyHealthApi } from '@/services/api';

interface StrengthCardProps {
  exerciseType: string;
  icon: string;
  dailyTarget: number;
  color: string;         // e.g. '#3b82f6'
  colorLight: string;    // e.g. 'bg-blue-50'
  colorText: string;     // e.g. 'text-blue-600'
  colorBorder: string;   // e.g. 'border-blue-200'
  colorBar: string;      // e.g. 'bg-blue-500'
  colorBarLight: string; // e.g. 'bg-blue-200'
  quickAmounts?: number[];
}

interface ExerciseRecord {
  id: number;
  reps: number;
  created_at: string;
}

export default function StrengthCard({
  exerciseType, icon, dailyTarget, color,
  colorLight, colorText, colorBorder, colorBar, colorBarLight,
  quickAmounts = [10, 15, 20, 30, 50],
}: StrengthCardProps) {
  const [todayTotal, setTodayTotal] = useState(0);
  const [todaySets, setTodaySets] = useState(0);
  const [records, setRecords] = useState<ExerciseRecord[]>([]);
  const [showDetail, setShowDetail] = useState(false);
  const [recording, setRecording] = useState(false);
  const [weekData, setWeekData] = useState<number[]>([]);

  const today = new Date().toISOString().slice(0, 10);
  const pct = Math.min(100, Math.round((todayTotal / dailyTarget) * 100));

  const loadData = useCallback(async () => {
    try {
      const res = await dailyHealthApi.getTodayExercises();
      const all: any[] = Array.isArray(res.data) ? res.data : [];
      const filtered = all.filter((e: any) => e.exercise_type === exerciseType);
      setTodayTotal(filtered.reduce((s: number, e: any) => s + (e.reps || 0), 0));
      setTodaySets(filtered.length);
      setRecords(filtered.map((e: any) => ({
        id: e.id, reps: e.reps || 0,
        created_at: e.created_at || e.record_date,
      })));
    } catch {}

    try {
      const r = await api.get('/daily-health/exercise/me?days=7');
      const recs: any[] = Array.isArray(r.data) ? r.data : r.data?.items || [];
      const byDate: Record<string, number> = {};
      for (const e of recs.filter((e: any) => e.exercise_type === exerciseType)) {
        const d = (e.record_date || '').slice(0, 10);
        byDate[d] = (byDate[d] || 0) + (e.reps || 0);
      }
      const days: number[] = [];
      for (let i = 6; i >= 0; i--) {
        days.push(byDate[new Date(Date.now() - i * 86400000).toISOString().slice(0, 10)] || 0);
      }
      setWeekData(days);
    } catch {}
  }, [exerciseType]);

  useEffect(() => { loadData(); }, [loadData]);

  const recordExercise = async (count: number) => {
    if (recording) return;
    setRecording(true);
    try {
      await api.post('/daily-health/exercise', {
        record_date: today, exercise_type: exerciseType,
        reps: count, sets: 1,
        intensity: count >= 30 ? 'high' : count >= 15 ? 'medium' : 'low',
      });
      setTodayTotal(prev => prev + count);
      setTodaySets(prev => prev + 1);
      setRecords(prev => [...prev, { id: Date.now(), reps: count, created_at: new Date().toISOString() }]);
    } catch (e) { console.error('记录失败', e); }
    finally { setRecording(false); }
  };

  const maxWeek = Math.max(...weekData, dailyTarget);
  const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayDayIndex = (new Date().getDay() + 6) % 7;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-sm font-bold text-gray-800">{exerciseType}</span>
        </div>
        <button onClick={() => setShowDetail(!showDetail)} className="text-[10px] text-gray-400 hover:text-gray-600">
          {showDetail ? '收起' : '详情'}
        </button>
      </div>

      <div className="flex items-center gap-4">
        {/* Ring */}
        <div className="relative shrink-0">
          <svg width={72} height={72} className="-rotate-90">
            <circle cx={36} cy={36} r={30} fill="none" stroke="#f3f4f6" strokeWidth={6} />
            <circle cx={36} cy={36} r={30} fill="none" stroke={pct >= 100 ? '#10b981' : color}
              strokeWidth={6} strokeDasharray={`${2 * Math.PI * 30 * pct / 100} ${2 * Math.PI * 30}`}
              strokeLinecap="round" className="transition-all duration-500" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-lg font-extrabold text-gray-800">{todayTotal}</span>
            <span className="text-[8px] text-gray-400">/ {dailyTarget}</span>
          </div>
        </div>

        {/* Buttons */}
        <div className="flex-1 min-w-0">
          <div className="text-[10px] text-gray-400 mb-1.5">第{todaySets + 1}组</div>
          <div className="flex flex-wrap gap-1">
            {quickAmounts.map(n => (
              <button key={n} onClick={() => recordExercise(n)} disabled={recording}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all active:scale-95 ${
                  recording ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : `${colorLight} ${colorText} hover:opacity-80 border ${colorBorder}`
                }`}>+{n}</button>
            ))}
          </div>
          {todayTotal > 0 && (
            <div className="text-[10px] text-gray-400 mt-1">{todaySets}组 · {pct}%</div>
          )}
        </div>
      </div>

      {/* Week bar */}
      {weekData.length > 0 && (
        <div className="mt-3 pt-2.5 border-t border-gray-50">
          <div className="flex items-end gap-1 h-7">
            {weekData.map((val, i) => {
              const h = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 28) : 2;
              const isToday = i === weekData.length - 1;
              return (
                <div key={i} className={`flex-1 rounded-sm transition-all ${isToday ? colorBar : val > 0 ? colorBarLight : 'bg-gray-100'}`}
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

      {/* Detail */}
      {showDetail && records.length > 0 && (
        <div className="mt-2.5 pt-2.5 border-t border-gray-100 space-y-1">
          {records.map((r, i) => (
            <div key={r.id} className="flex items-center justify-between text-xs">
              <span className="text-gray-500">第{i + 1}组</span>
              <span className="font-bold text-gray-700">{r.reps} 个</span>
              <span className="text-gray-400">{new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
