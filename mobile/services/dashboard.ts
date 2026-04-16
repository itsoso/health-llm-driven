import api from './api';

function today(): string {
  return new Date().toISOString().split('T')[0];
}

function twoWeeksAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 14);
  return d.toISOString().split('T')[0];
}

export interface DashboardData {
  healthScore: any;
  supplements: any;
  garminDaily: any;
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

const endpoints = [
  { key: 'healthScore', url: `/health-score/daily/me?target_date=${today()}` },
  { key: 'supplements', url: `/supplements/me/date/${today()}` },
  {
    key: 'garminDaily',
    url: `/daily-health/garmin/me?start_date=${twoWeeksAgo()}&end_date=${today()}`,
  },
  { key: 'waterRecords', url: `/water/records/me/date/${today()}` },
  { key: 'weather', url: '/environment/weather' },
  { key: 'airQuality', url: '/environment/air-quality' },
  { key: 'profile', url: '/profile/me' },
  { key: 'checkin', url: '/checkin/me/today' },
  { key: 'dietRecords', url: `/diet/records/me/date/${today()}` },
  { key: 'weightStats', url: '/weight/records/me/stats' },
  { key: 'weatherForecast', url: '/environment/weather/forecast?days=2' },
  { key: 'bloodPressureStats', url: '/blood-pressure/records/me/stats' },
  { key: 'moodRecord', url: '/mood/records/me/today' },
  { key: 'medicationToday', url: '/medication/today/me' },
  { key: 'goals', url: '/goals/me?status=active' },
  { key: 'workouts', url: '/workout/me?days=7' },
  { key: 'exerciseToday', url: '/daily-health/exercise/me/today' },
] as const;

export async function fetchDashboardData(): Promise<DashboardData> {
  const promises = endpoints.map(({ url }) =>
    api.get(url).then((r) => r.data),
  );
  const results = await Promise.allSettled(promises);

  const data: Record<string, any> = {};
  endpoints.forEach((ep, i) => {
    const r = results[i];
    data[ep.key] = r.status === 'fulfilled' ? r.value : null;
  });

  return data as DashboardData;
}
