'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

interface EnvironmentReading {
  available: boolean;
  source?: string;
  weather?: string;
  level?: string;
  update_time?: string;
  display?: Record<string, number | null>;
}
const sourceLabels: Record<string, string> = {
  qweather: '和风天气', 'open-meteo': 'Open-Meteo', aqicn: 'AQICN', waqi: 'AQICN',
};
function reading(value: number | null | undefined, unit = '') {
  return value == null ? '—' : `${value}${unit}`;
}

function EnvironmentContent() {
  const { user, isAuthenticated } = useAuth();
  const weather = useQuery({
    queryKey: ['environment', 'weather', user?.id],
    queryFn: async () => (await api.get<{ weather: EnvironmentReading }>('/environment/weather')).data.weather,
    enabled: isAuthenticated && !!user?.id,
    staleTime: 10 * 60 * 1000,
  });
  const air = useQuery({
    queryKey: ['environment', 'air', user?.id],
    queryFn: async () => (await api.get<EnvironmentReading>('/environment/air-quality')).data,
    enabled: isAuthenticated && !!user?.id,
    staleTime: 10 * 60 * 1000,
  });
  const available = (data?: EnvironmentReading) => data?.available && data.source !== 'default';
  const source = (data?: EnvironmentReading) => data?.source ? sourceLabels[data.source] || data.source : '未提供来源';
  return (
    <main className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">环境健康</h1>
        <p className="text-gray-600 mb-6">根据账户的位置设置查询当前天气与空气质量。<Link href="/settings" className="text-indigo-600 underline">检查位置设置</Link></p>
        <div className="grid md:grid-cols-2 gap-6">
          <section className="bg-white rounded-2xl shadow-sm p-6" aria-label="当前天气">
            <h2 className="text-xl font-semibold mb-4">当前天气</h2>
            {weather.isLoading ? <p role="status">正在加载天气…</p> : weather.isError ? (
              <div role="alert"><p>天气加载失败</p><button onClick={() => weather.refetch()} className="text-indigo-600 mt-3">重试天气</button></div>
            ) : !available(weather.data) ? <p className="text-gray-500">暂无天气数据</p> : (
              <>
                <p className="text-4xl font-semibold mb-2">{reading(weather.data?.display?.temperature, '°C')}</p>
                <p className="text-gray-700 mb-4">{weather.data?.weather || '天气描述未提供'}</p>
                <dl className="space-y-2 text-gray-700">
                  <div className="flex justify-between"><dt>体感温度</dt><dd>{reading(weather.data?.display?.feels_like, '°C')}</dd></div>
                  <div className="flex justify-between"><dt>湿度</dt><dd>{reading(weather.data?.display?.humidity, '%')}</dd></div>
                  <div className="flex justify-between"><dt>风速</dt><dd>{reading(weather.data?.display?.wind_speed, ' km/h')}</dd></div>
                </dl>
                <p className="text-xs text-gray-500 mt-5">数据来源：<span>{source(weather.data)}</span></p>
                {weather.data?.update_time && <p className="text-xs text-gray-500 mt-1">更新时间：{weather.data.update_time}</p>}
              </>
            )}
          </section>
          <section className="bg-white rounded-2xl shadow-sm p-6" aria-label="空气质量">
            <h2 className="text-xl font-semibold mb-4">空气质量</h2>
            {air.isLoading ? <p role="status">正在加载空气质量…</p> : air.isError ? (
              <div role="alert"><p>空气质量加载失败</p><button onClick={() => air.refetch()} className="text-indigo-600 mt-3">重试空气质量</button></div>
            ) : !available(air.data) ? <p className="text-gray-500">暂无空气质量数据</p> : (
              <>
                <p className="text-4xl font-semibold mb-2">{reading(air.data?.display?.aqi)}</p>
                <p className="text-gray-700 mb-4">AQI · {air.data?.level || '等级未提供'}</p>
                <dl className="space-y-2 text-gray-700">
                  <div className="flex justify-between"><dt>PM2.5</dt><dd>{reading(air.data?.display?.pm25, ' μg/m³')}</dd></div>
                  <div className="flex justify-between"><dt>PM10</dt><dd>{reading(air.data?.display?.pm10, ' μg/m³')}</dd></div>
                </dl>
                <p className="text-xs text-gray-500 mt-5">数据来源：<span>{source(air.data)}</span></p>
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
export default function EnvironmentPage() {
  return <ProtectedRoute><EnvironmentContent /></ProtectedRoute>;
}
