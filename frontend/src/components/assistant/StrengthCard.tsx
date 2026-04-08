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
      const r = await api.get('/daily-health/exercise/me?days=14');
      const recs: any[] = Array.isArray(r.data) ? r.data : r.data?.items || [];
      const byDate: Record<string, number> = {};
      for (const e of recs.filter((e: any) => e.exercise_type === exerciseType)) {
        const d = (e.record_date || '').slice(0, 10);
        byDate[d] = (byDate[d] || 0) + (e.reps || 0);
      }
      // 本周一到周日
      const now = new Date();
      const dayOfWeek = (now.getDay() + 6) % 7; // 0=周一, 6=周日
      const monday = new Date(now);
      monday.setDate(now.getDate() - dayOfWeek);
      const days: number[] = [];
      for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        days.push(byDate[d.toISOString().slice(0, 10)] || 0);
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
  const todayIdx = (new Date().getDay() + 6) % 7; // 0=周一, 6=周日

  return (
    <div className="rounded-2xl bg-white p-4" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-sm font-bold" style={{ color: '#1C1C1E' }}>{exerciseType}</span>
        </div>
        <button onClick={() => setShowDetail(!showDetail)} className="text-[10px] hover:opacity-70" style={{ color: '#8E8E93' }}>
          {showDetail ? '收起' : '详情'}
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative shrink-0">
          <svg width={48} height={48} className="-rotate-90">
            <circle cx={24} cy={24} r={20} fill="none" stroke="#E5E5EA" strokeWidth={4} />
            <circle cx={24} cy={24} r={20} fill="none" stroke="#30D158"
              strokeWidth={4} strokeDasharray={`${2 * Math.PI * 20 * Math.min(pct, 100) / 100} ${2 * Math.PI * 20}`}
              strokeLinecap="round" className="transition-all duration-500" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-sm font-extrabold" style={{ color: '#1C1C1E' }}>{todayTotal}</span>
            <span className="text-[7px]" style={{ color: '#AEAEB2' }}>/{dailyTarget}</span>
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-[10px] mb-1.5" style={{ color: '#8E8E93' }}>第{todaySets + 1}组</div>
          <div className="flex flex-wrap gap-1.5">
            {quickAmounts.map(n => (
              <button key={n} onClick={() => recordExercise(n)} disabled={recording}
                className="px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all active:scale-95"
                style={{
                  background: recording ? '#E5E5EA' : '#F2F2F7',
                  color: recording ? '#AEAEB2' : '#1C1C1E',
                }}>+{n}</button>
            ))}
          </div>
          {todayTotal > 0 && (
            <div className="text-[10px] mt-1" style={{ color: '#8E8E93' }}>{todaySets}组 · {pct}%</div>
          )}
        </div>
      </div>

      {weekData.length > 0 && (
        <div className="mt-3 pt-2.5" style={{ borderTop: '1px solid #E5E5EA' }}>
          <div className="flex items-end gap-1 h-7">
            {weekData.map((val, i) => {
              const h = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 28) : 2;
              const isToday = i === todayIdx;
              return (
                <div key={i} className="flex-1 rounded-sm transition-all"
                  style={{ height: `${h}px`, background: isToday ? '#30D158' : val > 0 ? 'rgba(48,209,88,0.3)' : '#E5E5EA' }} />
              );
            })}
          </div>
          <div className="flex gap-1 mt-0.5">
            {weekDays.map((d, i) => (
              <div key={i} className="flex-1 text-center text-[8px] font-medium"
                style={{ color: i === todayIdx ? '#1C1C1E' : '#AEAEB2' }}>
                {d}
              </div>
            ))}
          </div>
        </div>
      )}

      {showDetail && records.length > 0 && (
        <div className="mt-2.5 pt-2.5 space-y-1" style={{ borderTop: '1px solid #E5E5EA' }}>
          {records.map((r, i) => (
            <div key={r.id} className="flex items-center justify-between text-xs">
              <span style={{ color: '#8E8E93' }}>第{i + 1}组</span>
              <span className="font-bold" style={{ color: '#1C1C1E' }}>{r.reps} 个</span>
              <span style={{ color: '#AEAEB2' }}>{new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
