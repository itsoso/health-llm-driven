'use client';
import { useState, useEffect, useCallback } from 'react';
import { api } from '@/services/api/client';
import { dailyHealthApi } from '@/services/api/health';
import { getLocalDateStr } from '@/utils/timezone';

const DAILY_TARGET = 100;
const QUICK_AMOUNTS = [10, 15, 20, 30, 50];

interface PushupRecord {
  id: number;
  reps: number;
  sets: number;
  created_at: string;
  notes?: string;
}

export default function PushupCard() {
  const [todayTotal, setTodayTotal] = useState(0);
  const [todaySets, setTodaySets] = useState(0);
  const [records, setRecords] = useState<PushupRecord[]>([]);
  const [showDetail, setShowDetail] = useState(false);
  const [recording, setRecording] = useState(false);
  const [weekData, setWeekData] = useState<number[]>([]);

  const today = getLocalDateStr();
  const pct = Math.min(100, Math.round((todayTotal / DAILY_TARGET) * 100));

  const loadData = useCallback(async () => {
    try {
      // Load today's exercises
      const res = await dailyHealthApi.getTodayExercises();
      const all: any[] = Array.isArray(res.data) ? res.data : [];
      const pushups = all.filter((e: any) => e.exercise_type === '俯卧撑');
      const total = pushups.reduce((s: number, e: any) => s + (e.reps || 0), 0);
      setTodayTotal(total);
      setTodaySets(pushups.length);
      setRecords(pushups.map((e: any) => ({
        id: e.id,
        reps: e.reps || 0,
        sets: e.sets || 1,
        created_at: e.created_at || e.record_date,
        notes: e.notes,
      })));
    } catch {}

    // Load 7-day history (single API call)
    try {
      const r = await api.get('/daily-health/exercise/me?days=7');
      const recs: any[] = Array.isArray(r.data) ? r.data : r.data?.items || [];
      const pushupRecs = recs.filter((e: any) => e.exercise_type === '俯卧撑');
      // Group by date
      const byDate: Record<string, number> = {};
      for (const e of pushupRecs) {
        const d = (e.record_date || '').slice(0, 10);
        byDate[d] = (byDate[d] || 0) + (e.reps || 0);
      }
      const days: number[] = [];
      for (let i = 6; i >= 0; i--) {
        const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
        days.push(byDate[d] || 0);
      }
      setWeekData(days);
    } catch {}
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const recordPushups = async (count: number) => {
    if (recording) return;
    setRecording(true);
    try {
      await api.post('/daily-health/exercise', {
        record_date: today,
        exercise_type: '俯卧撑',
        reps: count,
        sets: 1,
        intensity: count >= 30 ? 'high' : count >= 15 ? 'medium' : 'low',
        notes: `${count}个俯卧撑`,
      });
      setTodayTotal(prev => prev + count);
      setTodaySets(prev => prev + 1);
      setRecords(prev => [...prev, { id: Date.now(), reps: count, sets: 1, created_at: new Date().toISOString() }]);
    } catch (e) {
      console.error('记录失败', e);
    } finally {
      setRecording(false);
    }
  };

  const maxWeek = Math.max(...weekData, DAILY_TARGET);
  const weekDays = ['一', '二', '三', '四', '五', '六', '日'];
  const todayDayIndex = (new Date().getDay() + 6) % 7; // Monday=0

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">💪</span>
          <span className="text-sm font-bold text-gray-800">俯卧撑</span>
        </div>
        <button onClick={() => setShowDetail(!showDetail)}
          className="text-[10px] text-gray-400 hover:text-gray-600">
          {showDetail ? '收起' : '详情'}
        </button>
      </div>

      {/* Main: Progress Ring + Quick Record */}
      <div className="flex items-center gap-5">
        {/* Circle Progress */}
        <div className="relative shrink-0">
          <svg width={80} height={80} className="-rotate-90">
            <circle cx={40} cy={40} r={34} fill="none" stroke="#f3f4f6" strokeWidth={7} />
            <circle cx={40} cy={40} r={34} fill="none" stroke={pct >= 100 ? '#10b981' : pct >= 50 ? '#3b82f6' : '#6366f1'}
              strokeWidth={7} strokeDasharray={`${2 * Math.PI * 34 * pct / 100} ${2 * Math.PI * 34}`}
              strokeLinecap="round" className="transition-all duration-500" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-extrabold text-gray-800">{todayTotal}</span>
            <span className="text-[9px] text-gray-400">/ {DAILY_TARGET}</span>
          </div>
        </div>

        {/* Quick record buttons */}
        <div className="flex-1">
          <div className="text-[10px] text-gray-400 mb-1.5">快速记录 · 第{todaySets + 1}组</div>
          <div className="flex flex-wrap gap-1.5">
            {QUICK_AMOUNTS.map(n => (
              <button key={n} onClick={() => recordPushups(n)} disabled={recording}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all active:scale-95 ${
                  recording ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-blue-50 text-blue-600 hover:bg-blue-100 border border-blue-200'
                }`}>
                +{n}
              </button>
            ))}
          </div>
          {todayTotal > 0 && (
            <div className="text-[10px] text-gray-400 mt-1.5">
              今日 {todaySets} 组 · 共 {todayTotal} 个 · {pct}%
            </div>
          )}
        </div>
      </div>

      {/* Week sparkline */}
      {weekData.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-50">
          <div className="flex items-end gap-1 h-8">
            {weekData.map((val, i) => {
              const h = maxWeek > 0 ? Math.max(2, (val / maxWeek) * 32) : 2;
              const isToday = i === weekData.length - 1;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                  <div className={`w-full rounded-sm transition-all ${isToday ? 'bg-blue-500' : val > 0 ? 'bg-blue-200' : 'bg-gray-100'}`}
                    style={{ height: `${h}px` }} />
                </div>
              );
            })}
          </div>
          <div className="flex gap-1 mt-0.5">
            {weekData.map((val, i) => {
              const dayIdx = (todayDayIndex - 6 + i + 7) % 7;
              return (
                <div key={i} className="flex-1 text-center text-[8px] text-gray-300">{weekDays[dayIdx]}</div>
              );
            })}
          </div>
        </div>
      )}

      {/* Detail view */}
      {showDetail && records.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100 space-y-1">
          {records.map((r, i) => (
            <div key={r.id} className="flex items-center justify-between text-xs">
              <span className="text-gray-500">第{i + 1}组</span>
              <span className="font-bold text-gray-700">{r.reps} 个</span>
              <span className="text-gray-400">
                {new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
