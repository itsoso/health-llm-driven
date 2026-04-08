'use client';
import { useState, useCallback } from 'react';
import { api, dailyHealthApi, healthScoreApi, supplementApi } from '@/services/api';

export interface DashboardData {
  todayGarmin: any;
  healthScore: any;
  supplementStatus: any[];
  garminHistory: any[];
  waterToday: { total_ml: number; goal_ml: number; count: number };
  weatherData: any;
  airData: any;
  rhinitisToday: any;
  dietToday: any;
  weightStats: any;
  bpLatest: any;
  moodToday: any;
  medToday: any[];
  goalsData: any[];
  workoutRecent: any[];
  exerciseToday: any[];
}

const INITIAL: DashboardData = {
  todayGarmin: null,
  healthScore: null,
  supplementStatus: [],
  garminHistory: [],
  waterToday: { total_ml: 0, goal_ml: 2000, count: 0 },
  weatherData: null,
  airData: null,
  rhinitisToday: null,
  dietToday: null,
  weightStats: null,
  bpLatest: null,
  moodToday: null,
  medToday: [],
  goalsData: [],
  workoutRecent: [],
  exerciseToday: [],
};

export function useDashboardData() {
  const [data, setData] = useState<DashboardData>(INITIAL);
  const [loading, setLoading] = useState(true);

  const update = (partial: Partial<DashboardData>) =>
    setData(prev => ({ ...prev, ...partial }));

  const loadTodayGarmin = useCallback(async () => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const res = await dailyHealthApi.getMyGarminData(yesterday, today);
      const records: any[] = res.data || [];
      const latest = records
        .sort((a: any, b: any) => (b.record_date || '').localeCompare(a.record_date || ''))
        .find((r: any) => r.sleep_score || r.hrv || r.steps > 0);
      if (latest) update({ todayGarmin: latest });
      else if (records.length > 0) update({ todayGarmin: records[records.length - 1] });
    } catch {}
  }, []);

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    const today = new Date().toISOString().slice(0, 10);

    // Batch 1: Critical data for first paint
    const batch1 = await Promise.allSettled([
      healthScoreApi.getDailyScore(today),            // 0
      supplementApi.getMyRecordsWithStatus(today),     // 1
      dailyHealthApi.getMyGarminData(                  // 2
        new Date(Date.now() - 13 * 86400000).toISOString().slice(0, 10),
        today
      ),
      api.get(`/water/records/me/date/${today}`),      // 3
      api.get('/environment/weather'),                  // 4
      api.get('/environment/air-quality'),              // 5
    ]);

    const ok1 = (i: number) => batch1[i].status === 'fulfilled' ? (batch1[i] as any).value.data : null;

    const partial: Partial<DashboardData> = {};

    if (ok1(0)) partial.healthScore = ok1(0);
    if (ok1(1)) {
      const raw = ok1(1);
      partial.supplementStatus = Array.isArray(raw) ? raw : raw?.records || [];
    }
    if (ok1(2)) {
      const records = ok1(2) || [];
      partial.garminHistory = [...records].sort((a: any, b: any) =>
        (a.record_date || '').localeCompare(b.record_date || '')
      );
    }
    if (ok1(3)) {
      const w = ok1(3);
      partial.waterToday = {
        total_ml: w?.total_amount || w?.total_ml || 0,
        goal_ml: w?.target_amount || w?.goal_ml || 2000,
        count: w?.records_count || w?.count || 0,
      };
    }
    if (ok1(4)) {
      const raw = ok1(4);
      const wd = raw?.weather || raw || {};
      // Get city
      try {
        const profileRes = await api.get('/profile/me');
        wd.city = profileRes.data?.city || '';
      } catch { wd.city = ''; }
      partial.weatherData = wd;
    }
    if (ok1(5)) partial.airData = ok1(5);

    update(partial);
    setLoading(false);

    // Batch 2: Secondary data (non-blocking)
    const batch2 = await Promise.allSettled([
      api.get('/checkin/me/today'),                     // 0
      api.get(`/diet/records/me/date/${today}`),        // 1
      api.get('/weight/records/me/stats'),              // 2
      api.get('/environment/weather/forecast?days=2'),  // 3
      api.get('/blood-pressure/records/me/stats'),      // 4
      api.get('/mood/records/me/today'),                // 5
      api.get('/medication/today/me'),                  // 6
      api.get('/goals/me?status=active'),               // 7
      api.get('/workout/me?days=7'),                    // 8
      dailyHealthApi.getTodayExercises(),               // 9
    ]);

    const ok2 = (i: number) => batch2[i].status === 'fulfilled' ? (batch2[i] as any).value.data : null;

    const partial2: Partial<DashboardData> = {};
    if (ok2(0)) partial2.rhinitisToday = ok2(0);
    if (ok2(1)) partial2.dietToday = ok2(1);
    if (ok2(2)) partial2.weightStats = ok2(2);
    // merge forecast into weather (today + tomorrow)
    const fc = ok2(3);
    if (fc) {
      const forecasts = fc?.forecasts || (Array.isArray(fc) ? fc : []);
      const todayFc = forecasts[0] || null;
      const tomorrowFc = forecasts[1] || null;
      if (todayFc || tomorrowFc) {
        setData(prev => {
          const wd = { ...(prev.weatherData || {}) };
          if (todayFc) {
            wd.temp_min = todayFc.temp_min;
            wd.temp_max = todayFc.temp_max;
          }
          if (tomorrowFc) {
            wd.tomorrow = tomorrowFc;
          }
          return { ...prev, weatherData: wd };
        });
      }
    }
    if (ok2(4)) partial2.bpLatest = ok2(4);
    if (ok2(5)) partial2.moodToday = ok2(5);
    if (ok2(6)) partial2.medToday = Array.isArray(ok2(6)) ? ok2(6) : [];
    if (ok2(7)) partial2.goalsData = Array.isArray(ok2(7)) ? ok2(7) : ok2(7)?.items || [];
    if (ok2(8)) partial2.workoutRecent = Array.isArray(ok2(8)) ? ok2(8) : ok2(8)?.items || [];
    if (ok2(9)) partial2.exerciseToday = Array.isArray(ok2(9)) ? ok2(9) : [];

    update(partial2);
  }, []);

  return {
    ...data,
    loading,
    loadTodayGarmin,
    loadDashboardData,
    setSupplementStatus: (fn: (prev: any[]) => any[]) => setData(prev => ({ ...prev, supplementStatus: fn(prev.supplementStatus) })),
    setWaterToday: (fn: (prev: DashboardData['waterToday']) => DashboardData['waterToday']) =>
      setData(prev => ({ ...prev, waterToday: fn(prev.waterToday) })),
    setRhinitisToday: (fn: (prev: any) => any) => setData(prev => ({ ...prev, rhinitisToday: fn(prev.rhinitisToday) })),
  };
}
