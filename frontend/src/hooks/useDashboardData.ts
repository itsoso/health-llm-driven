'use client';
import { useState, useCallback, useRef } from 'react';
import { api } from '@/services/api/client';
import { dailyHealthApi, healthScoreApi } from '@/services/api/health';
import { supplementApi } from '@/services/api/records';

/**
 * Dashboard data 聚合 hook
 *
 * 设计要点（替代之前 batch1 串行 batch2 的实现）:
 *  1. 所有请求在一个 Promise.allSettled 里并发 (17 个)
 *  2. /profile/me 从嵌套里剥出来当独立项
 *  3. 10 秒节流：避免 AI 对话 done 后连打多次 reload
 *  4. refreshAfterAction(): 只刷新真正会变的 3 项（水、补剂、打卡、饮食），
 *     不再每次对话 done 都重打 16 个请求
 *  5. 去掉和 batch 里 Garmin 重复的独立 loadTodayGarmin
 */

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

// 全量刷新节流：10 秒内第二次触发直接跳过
const LOAD_THROTTLE_MS = 10_000;

// ── 小工具：把 allSettled 的结果按索引取 data，失败返回 null ──
const pick = (results: PromiseSettledResult<any>[], i: number): any =>
  results[i]?.status === 'fulfilled' ? (results[i] as any).value?.data : null;

export function useDashboardData() {
  const [data, setData] = useState<DashboardData>(INITIAL);
  const [loading, setLoading] = useState(true);
  const lastLoadedAt = useRef<number>(0);
  const inFlight = useRef<Promise<void> | null>(null);

  const update = useCallback(
    (partial: Partial<DashboardData>) =>
      setData((prev) => ({ ...prev, ...partial })),
    []
  );

  /**
   * 全量刷新：17 个请求并发一次打完。
   *
   * force=true 可绕过节流（用户主动点刷新按钮时用）
   */
  const loadDashboardData = useCallback(
    async (force = false) => {
      // 节流：10s 内非强制刷新直接返回
      const now = Date.now();
      if (!force && now - lastLoadedAt.current < LOAD_THROTTLE_MS) {
        return;
      }
      // 合并并发：同一时刻多个调用共用一次真实请求
      if (inFlight.current) {
        return inFlight.current;
      }

      const today = new Date().toISOString().slice(0, 10);
      const twoWeeksAgo = new Date(Date.now() - 13 * 86400000)
        .toISOString()
        .slice(0, 10);

      setLoading(true);

      const job = (async () => {
        // 17 个请求全部并发，允许任意子请求失败
        const results = await Promise.allSettled([
          /*  0 */ healthScoreApi.getDailyScore(today),
          /*  1 */ supplementApi.getMyRecordsWithStatus(today),
          /*  2 */ dailyHealthApi.getMyGarminData(twoWeeksAgo, today),
          /*  3 */ api.get(`/water/records/me/date/${today}`),
          /*  4 */ api.get('/environment/weather'),
          /*  5 */ api.get('/environment/air-quality'),
          /*  6 */ api.get('/profile/me'),
          /*  7 */ api.get('/checkin/me/today'),
          /*  8 */ api.get(`/diet/records/me/date/${today}`),
          /*  9 */ api.get('/weight/records/me/stats'),
          /* 10 */ api.get('/environment/weather/forecast?days=2'),
          /* 11 */ api.get('/blood-pressure/records/me/stats'),
          /* 12 */ api.get('/mood/records/me/today'),
          /* 13 */ api.get('/medication/today/me'),
          /* 14 */ api.get('/goals/me?status=active'),
          /* 15 */ api.get('/workout/me?days=7'),
          /* 16 */ dailyHealthApi.getTodayExercises(),
        ]);

        const partial: Partial<DashboardData> = {};

        // 0 — Daily health score
        const healthScore = pick(results, 0);
        if (healthScore) partial.healthScore = healthScore;

        // 1 — Supplements
        const supRaw = pick(results, 1);
        if (supRaw) {
          partial.supplementStatus = Array.isArray(supRaw)
            ? supRaw
            : supRaw?.records || [];
        }

        // 2 — Garmin 14 天（同时顶掉之前独立的 loadTodayGarmin）
        const garminRaw = pick(results, 2);
        if (garminRaw) {
          const records = garminRaw as any[];
          partial.garminHistory = [...records].sort((a, b) =>
            (a.record_date || '').localeCompare(b.record_date || '')
          );
          // 从同一份数据里抽"今日/最新"字段，省掉一次单独请求
          const latest = [...records]
            .sort((a, b) =>
              (b.record_date || '').localeCompare(a.record_date || '')
            )
            .find((r) => r.sleep_score || r.hrv || r.steps > 0);
          if (latest) partial.todayGarmin = latest;
          else if (records.length > 0)
            partial.todayGarmin = records[records.length - 1];
        }

        // 3 — Water today
        const water = pick(results, 3);
        if (water) {
          partial.waterToday = {
            total_ml: water?.total_amount || water?.total_ml || 0,
            goal_ml: water?.target_amount || water?.goal_ml || 2000,
            count: water?.records_count || water?.count || 0,
          };
        }

        // 4 + 6 + 10 — Weather 组合（当前 + profile city + 预报）
        const weatherRaw = pick(results, 4);
        const profile = pick(results, 6);
        const forecastRaw = pick(results, 10);
        if (weatherRaw) {
          const wd = weatherRaw?.weather || weatherRaw || {};
          wd.city = (profile?.use_manual_location && profile?.manual_location?.city)
            ? profile.manual_location.city
            : profile?.detected_location?.city || profile?.city || '';
          // 合并今日 min/max + 明日预报
          const forecasts =
            forecastRaw?.forecasts ||
            (Array.isArray(forecastRaw) ? forecastRaw : []);
          const todayFc = forecasts?.[0];
          const tomorrowFc = forecasts?.[1];
          if (todayFc) {
            wd.temp_min = todayFc.temp_min;
            wd.temp_max = todayFc.temp_max;
          }
          if (tomorrowFc) wd.tomorrow = tomorrowFc;
          partial.weatherData = wd;
        }

        // 5 — Air quality
        const air = pick(results, 5);
        if (air) partial.airData = air;

        // 7 — Checkin / rhinitis
        const rhin = pick(results, 7);
        if (rhin) partial.rhinitisToday = rhin;

        // 8 — Diet today
        const diet = pick(results, 8);
        if (diet) partial.dietToday = diet;

        // 9 — Weight stats
        const weight = pick(results, 9);
        if (weight) partial.weightStats = weight;

        // 11 — Blood pressure
        const bp = pick(results, 11);
        if (bp) partial.bpLatest = bp;

        // 12 — Mood
        const mood = pick(results, 12);
        if (mood) partial.moodToday = mood;

        // 13 — Medication today
        const med = pick(results, 13);
        if (med) partial.medToday = Array.isArray(med) ? med : [];

        // 14 — Goals
        const goals = pick(results, 14);
        if (goals) partial.goalsData = Array.isArray(goals) ? goals : goals?.items || [];

        // 15 — Workout recent
        const wk = pick(results, 15);
        if (wk)
          partial.workoutRecent = Array.isArray(wk) ? wk : wk?.items || [];

        // 16 — Exercise today
        const ex = pick(results, 16);
        if (ex) partial.exerciseToday = Array.isArray(ex) ? ex : [];

        update(partial);
        setLoading(false);
        lastLoadedAt.current = Date.now();
      })();

      inFlight.current = job;
      try {
        await job;
      } finally {
        inFlight.current = null;
      }
    },
    [update]
  );

  /**
   * 主动刷新今日 Garmin（例如点了顶部刷新按钮之后）
   * 现在实现为调用一次 loadDashboardData(force=true)，避免维护两套逻辑
   */
  const loadTodayGarmin = useCallback(async () => {
    await loadDashboardData(true);
  }, [loadDashboardData]);

  /**
   * AI 对话 done 事件 / 用户快捷记录后的"轻量刷新"
   * 只重打真正会变的 4 项（水、补剂、打卡、饮食），而不是整张表
   */
  const refreshAfterAction = useCallback(async () => {
    const today = new Date().toISOString().slice(0, 10);
    const results = await Promise.allSettled([
      api.get(`/water/records/me/date/${today}`),
      supplementApi.getMyRecordsWithStatus(today),
      api.get('/checkin/me/today'),
      api.get(`/diet/records/me/date/${today}`),
    ]);

    const partial: Partial<DashboardData> = {};
    const water = pick(results, 0);
    if (water) {
      partial.waterToday = {
        total_ml: water?.total_amount || water?.total_ml || 0,
        goal_ml: water?.target_amount || water?.goal_ml || 2000,
        count: water?.records_count || water?.count || 0,
      };
    }
    const supRaw = pick(results, 1);
    if (supRaw) {
      partial.supplementStatus = Array.isArray(supRaw)
        ? supRaw
        : supRaw?.records || [];
    }
    const rhin = pick(results, 2);
    if (rhin) partial.rhinitisToday = rhin;
    const diet = pick(results, 3);
    if (diet) partial.dietToday = diet;

    update(partial);
  }, [update]);

  return {
    ...data,
    loading,
    loadDashboardData,
    loadTodayGarmin,
    refreshAfterAction,
    setSupplementStatus: (fn: (prev: any[]) => any[]) =>
      setData((prev) => ({ ...prev, supplementStatus: fn(prev.supplementStatus) })),
    setWaterToday: (
      fn: (prev: DashboardData['waterToday']) => DashboardData['waterToday']
    ) => setData((prev) => ({ ...prev, waterToday: fn(prev.waterToday) })),
    setRhinitisToday: (fn: (prev: any) => any) =>
      setData((prev) => ({ ...prev, rhinitisToday: fn(prev.rhinitisToday) })),
  };
}
