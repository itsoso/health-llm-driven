import api from './api';
import type { GarminDailyRow } from '../types/garmin';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function twoWeeksAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 14);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export interface DashboardData {
  healthScore: any;
  supplements: any;
  garminDaily: GarminDailyRow[] | null;
  waterRecords: any;
  weather: any;
  airQuality: any;
  profile: any;
  checkin: any;
  dietRecords: any;
  weightStats: any;
  weatherForecast: any;
  bloodPressureStats: any;
  moodRecord: any;
  medicationToday: any;
  goals: any;
  workouts: any;
  exerciseToday: any;
}

function getEndpoints() {
  const t = today();
  const tw = twoWeeksAgo();
  return [
    { key: 'healthScore', url: `/health-score/daily/me?target_date=${t}` },
    { key: 'supplements', url: `/supplements/me/date/${t}` },
    { key: 'garminDaily', url: `/daily-health/garmin/me?start_date=${tw}&end_date=${t}` },
    { key: 'waterRecords', url: `/water/records/me/date/${t}` },
    { key: 'weather', url: '/environment/weather' },
    { key: 'airQuality', url: '/environment/air-quality' },
    { key: 'profile', url: '/profile/me' },
    { key: 'checkin', url: '/checkin/me/today' },
    { key: 'dietRecords', url: `/diet/records/me/date/${t}` },
    { key: 'weightStats', url: '/weight/records/me/stats' },
    { key: 'weatherForecast', url: '/environment/weather/forecast?days=2' },
    { key: 'bloodPressureStats', url: '/blood-pressure/records/me/stats' },
    { key: 'moodRecord', url: '/mood/records/me/today' },
    { key: 'medicationToday', url: '/medication/today/me' },
    { key: 'goals', url: '/goals/me?status=active' },
    { key: 'workouts', url: '/workout/me?days=7' },
    { key: 'exerciseToday', url: '/daily-health/exercise/me/today' },
  ] as const;
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const endpoints = getEndpoints();

  // Batch 1: critical above-fold data (8 requests)
  const criticalKeys = new Set([
    'healthScore', 'garminDaily', 'supplements', 'checkin',
    'waterRecords', 'medicationToday', 'exerciseToday', 'profile',
  ]);
  const batch1 = endpoints.filter(ep => criticalKeys.has(ep.key));
  const batch2 = endpoints.filter(ep => !criticalKeys.has(ep.key));

  const data: Record<string, any> = {};

  const results1 = await Promise.allSettled(batch1.map(({ url }) => api.get(url).then(r => r.data)));
  batch1.forEach((ep, i) => { data[ep.key] = results1[i].status === 'fulfilled' ? (results1[i] as PromiseFulfilledResult<any>).value : null; });

  const results2 = await Promise.allSettled(batch2.map(({ url }) => api.get(url).then(r => r.data)));
  batch2.forEach((ep, i) => { data[ep.key] = results2[i].status === 'fulfilled' ? (results2[i] as PromiseFulfilledResult<any>).value : null; });

  return data as DashboardData;
}
