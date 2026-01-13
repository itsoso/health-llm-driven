'use client';

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';
import Navigation from '@/components/Navigation';

interface WeatherData {
  available: boolean;
  temperature: number;
  feels_like: number;
  humidity: number;
  weather: string;
  wind_direction: string;
  wind_speed: number;
  summary?: string;
}

interface AirQualityData {
  available: boolean;
  aqi: number;
  level: string;
  description: string;
  pm25: number;
  pm10?: number;
  health_implications: string;
}

interface ExerciseAdvice {
  outdoor_suitable: boolean;
  score: number;
  status: string;
  recommended_activities: string[];
}

interface EnvironmentAdvice {
  timestamp: string;
  location: string;
  weather: WeatherData;
  air_quality: AirQualityData;
  exercise: ExerciseAdvice;
  advices: string[];
  warnings: string[];
  condition_specific: Record<string, any>;
}

interface MorningBriefing {
  briefing: string;
  outdoor_score: number;
  key_advice: string;
  full_data: EnvironmentAdvice;
}

interface Forecast {
  date: string;
  weather: string;
  temp_max: number;
  temp_min: number;
  precipitation_probability: number;
  uv_index: number;
}

const statusColors: Record<string, string> = {
  excellent: 'from-green-500 to-emerald-600',
  good: 'from-blue-500 to-cyan-600',
  moderate: 'from-yellow-500 to-amber-600',
  poor: 'from-orange-500 to-red-500',
  not_recommended: 'from-red-600 to-rose-700',
};

const statusLabels: Record<string, string> = {
  excellent: '非常适宜',
  good: '适宜',
  moderate: '一般',
  poor: '较差',
  not_recommended: '不建议',
};

const aqiColors: Record<string, string> = {
  excellent: 'text-green-400',
  good: 'text-blue-400',
  moderate: 'text-yellow-400',
  unhealthy: 'text-orange-400',
  very_unhealthy: 'text-red-400',
  hazardous: 'text-purple-400',
};

export default function EnvironmentPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const [city, setCity] = useState<string>('');

  // 获取综合环境建议
  const { data: advice, isLoading: adviceLoading, refetch: refetchAdvice } = useQuery<EnvironmentAdvice>({
    queryKey: ['environmentAdvice', city],
    queryFn: async () => {
      const params = city ? { city } : {};
      const response = await api.get('/environment/advice', { params });
      return response.data;
    },
    enabled: !!user,
    refetchInterval: 30 * 60 * 1000, // 30分钟自动刷新
  });

  // 获取早间简报
  const { data: briefing } = useQuery<MorningBriefing>({
    queryKey: ['morningBriefing', city],
    queryFn: async () => {
      const params = city ? { city } : {};
      const response = await api.get('/environment/morning-briefing', { params });
      return response.data;
    },
    enabled: !!user,
  });

  // 获取天气预报
  const { data: forecast } = useQuery<{ forecasts: Forecast[] }>({
    queryKey: ['weatherForecast', city],
    queryFn: async () => {
      const params = city ? { city, days: 5 } : { days: 5 };
      const response = await api.get('/environment/weather/forecast', { params });
      return response.data;
    },
    enabled: !!user,
  });

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-400"></div>
      </div>
    );
  }

  if (!user) {
    router.push('/login');
    return null;
  }

  const weather = advice?.weather;
  const airQuality = advice?.air_quality;
  const exercise = advice?.exercise;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      <Navigation />
      
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* 页面标题 */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">🌤️ 环境健康</h1>
            <p className="text-white/60">实时环境数据与健康建议</p>
          </div>
          <div className="flex items-center gap-4">
            <input
              type="text"
              placeholder="输入城市名..."
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => refetchAdvice()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            >
              刷新
            </button>
          </div>
        </div>

        {adviceLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-400"></div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 户外运动评分 */}
            {exercise && (
              <div className={`rounded-2xl p-6 bg-gradient-to-r ${statusColors[exercise.status] || 'from-gray-600 to-gray-700'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-white/80 text-sm mb-1">户外运动适宜度</h2>
                    <div className="flex items-baseline gap-3">
                      <span className="text-5xl font-bold text-white">{exercise.score}</span>
                      <span className="text-white/70 text-lg">/ 100</span>
                    </div>
                    <span className="text-white/90 text-lg mt-2 block">
                      {exercise.outdoor_suitable ? '✅ 适合户外运动' : '❌ 建议室内运动'}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-6xl">{
                      exercise.score >= 80 ? '🏃' :
                      exercise.score >= 60 ? '🚶' :
                      exercise.score >= 40 ? '🏠' : '⚠️'
                    }</span>
                    <p className="text-white/80 mt-2">{statusLabels[exercise.status]}</p>
                  </div>
                </div>
              </div>
            )}

            {/* 天气和空气质量 */}
            <div className="grid md:grid-cols-2 gap-6">
              {/* 天气卡片 */}
              {weather?.available && (
                <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
                  <h3 className="text-white/70 text-sm mb-4 flex items-center gap-2">
                    <span>🌡️</span> 实时天气
                  </h3>
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <div className="text-4xl font-bold text-white">{Math.round(weather.temperature)}°C</div>
                      <div className="text-white/50 text-sm">体感 {Math.round(weather.feels_like)}°C</div>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl text-white">{weather.weather}</div>
                      <div className="text-white/50 text-sm">{weather.wind_direction} {weather.wind_speed}km/h</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-white/60">
                    <span>💧 湿度 {weather.humidity}%</span>
                  </div>
                </div>
              )}

              {/* 空气质量卡片 */}
              {airQuality?.available && (
                <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
                  <h3 className="text-white/70 text-sm mb-4 flex items-center gap-2">
                    <span>🌬️</span> 空气质量
                  </h3>
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <div className={`text-4xl font-bold ${aqiColors[airQuality.level] || 'text-white'}`}>
                        {airQuality.aqi}
                      </div>
                      <div className="text-white/50 text-sm">AQI 指数</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-2xl ${aqiColors[airQuality.level] || 'text-white'}`}>
                        {airQuality.description}
                      </div>
                    </div>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between text-white/60">
                      <span>PM2.5</span>
                      <span>{airQuality.pm25} μg/m³</span>
                    </div>
                    {airQuality.pm10 && (
                      <div className="flex justify-between text-white/60">
                        <span>PM10</span>
                        <span>{airQuality.pm10} μg/m³</span>
                      </div>
                    )}
                  </div>
                  <p className="text-white/50 text-xs mt-3">{airQuality.health_implications}</p>
                </div>
              )}
            </div>

            {/* 健康建议 */}
            {advice?.advices && advice.advices.length > 0 && (
              <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
                <h3 className="text-white font-medium mb-4 flex items-center gap-2">
                  <span>💡</span> 健康建议
                </h3>
                <div className="space-y-3">
                  {advice.advices.map((item, index) => (
                    <div key={index} className="flex items-start gap-3 text-white/80">
                      <span className="text-blue-400">•</span>
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 警告信息 */}
            {advice?.warnings && advice.warnings.length > 0 && (
              <div className="bg-red-500/10 backdrop-blur rounded-xl p-6 border border-red-500/30">
                <h3 className="text-red-400 font-medium mb-4 flex items-center gap-2">
                  <span>⚠️</span> 注意事项
                </h3>
                <div className="space-y-3">
                  {advice.warnings.map((item, index) => (
                    <div key={index} className="flex items-start gap-3 text-red-300">
                      <span>!</span>
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 推荐活动 */}
            {exercise?.recommended_activities && exercise.recommended_activities.length > 0 && (
              <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
                <h3 className="text-white font-medium mb-4 flex items-center gap-2">
                  <span>🏋️</span> 推荐活动
                </h3>
                <div className="flex flex-wrap gap-3">
                  {exercise.recommended_activities.map((activity, index) => (
                    <span
                      key={index}
                      className="px-4 py-2 bg-blue-500/20 text-blue-300 rounded-full text-sm"
                    >
                      {activity}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 天气预报 */}
            {forecast?.forecasts && forecast.forecasts.length > 0 && (
              <div className="bg-white/5 backdrop-blur rounded-xl p-6 border border-white/10">
                <h3 className="text-white font-medium mb-4 flex items-center gap-2">
                  <span>📅</span> 未来天气
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  {forecast.forecasts.map((day, index) => (
                    <div key={index} className="bg-white/5 rounded-lg p-4 text-center">
                      <div className="text-white/60 text-sm mb-2">
                        {new Date(day.date).toLocaleDateString('zh-CN', { weekday: 'short', month: 'numeric', day: 'numeric' })}
                      </div>
                      <div className="text-white text-lg mb-1">{day.weather}</div>
                      <div className="text-white/80">
                        <span className="text-red-400">{Math.round(day.temp_max)}°</span>
                        <span className="text-white/40 mx-1">/</span>
                        <span className="text-blue-400">{Math.round(day.temp_min)}°</span>
                      </div>
                      {day.precipitation_probability > 0 && (
                        <div className="text-blue-300 text-xs mt-1">
                          🌧️ {day.precipitation_probability}%
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 早间简报 */}
            {briefing && (
              <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 backdrop-blur rounded-xl p-6 border border-purple-500/30">
                <h3 className="text-white font-medium mb-4 flex items-center gap-2">
                  <span>🌅</span> 早间健康简报
                </h3>
                <div className="text-white/80 whitespace-pre-line leading-relaxed">
                  {briefing.briefing}
                </div>
                <div className="mt-4 p-4 bg-white/5 rounded-lg">
                  <p className="text-purple-300 font-medium">💡 {briefing.key_advice}</p>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
