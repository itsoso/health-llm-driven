/**
 * RevaWeatherRow —— 首页天气一行(2026-06-23 收成单行 pill)。
 *
 * 默认一行:[图标] {城市} · {温度}° {天气}        [空气等级 Chip] [展开 v]
 * 点「展开」→ 露出第二段:湿度 / AQI / PM2.5 + 明日预报(收起回单行)。
 * 点行其余位置 → 进 /location 设置位置。
 * 复用 EnvironmentCard 的 env query keys(['env','weather'|'aqi'|'location'])→ React Query 去重。
 * 整卡无数据 → 不渲染。
 */
import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';

import api from '../../services/api';
import { revaColors as C, revaRadii } from '../../constants/revaTheme';
import { Chip, Icon } from '../reva/RevaKit';
import type { RevaStatus } from '../../constants/revaTheme';

interface WeatherInner {
  temperature?: number;
  weather?: string;
  humidity?: number;
}
interface WeatherResponse {
  weather?: WeatherInner;
}
interface AirQuality {
  aqi?: number;
  pm25?: number;
}
interface ForecastDay {
  date: string;
  weather: string;
  temp_max: number;
  temp_min: number;
  humidity?: number | null;
}
interface ForecastResponse {
  available?: boolean;
  forecasts?: ForecastDay[];
}
interface ProfileLocation {
  use_manual_location?: boolean;
  manual_location?: { city: string | null; region: string | null } | null;
  detected_location?: { city: string | null; region: string | null } | null;
}

function aqiStatus(aqi: number | undefined): RevaStatus {
  if (aqi == null) return 'info';
  if (aqi <= 100) return 'normal';
  if (aqi <= 150) return 'caution';
  return 'risk';
}
function aqiLabel(aqi: number | undefined): string {
  if (aqi == null) return '空气 —';
  if (aqi <= 50) return '空气 优';
  if (aqi <= 100) return '空气 良';
  if (aqi <= 150) return '空气 轻度';
  if (aqi <= 200) return '空气 中度';
  return '空气 重度';
}

export default function RevaWeatherRow() {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);

  const weatherQ = useQuery<WeatherInner | null>({
    queryKey: ['env', 'weather'],
    queryFn: async () => {
      try {
        const { data } = await api.get<WeatherResponse>('/environment/weather');
        return data?.weather ?? null;
      } catch {
        return null;
      }
    },
    staleTime: 30 * 60 * 1000,
  });

  const aqiQ = useQuery<AirQuality | null>({
    queryKey: ['env', 'aqi'],
    queryFn: async () => {
      try {
        const { data } = await api.get<AirQuality>('/environment/air-quality');
        return data;
      } catch {
        return null;
      }
    },
    staleTime: 30 * 60 * 1000,
  });

  // 明日预报 — 复用 EnvironmentCard 的 ['env','forecast'] key,React Query 去重。
  const forecastQ = useQuery<ForecastDay[] | null>({
    queryKey: ['env', 'forecast'],
    queryFn: async () => {
      try {
        const { data } = await api.get<ForecastResponse>('/environment/weather/forecast', {
          params: { days: 3 },
        });
        return data?.forecasts ?? null;
      } catch {
        return null;
      }
    },
    staleTime: 60 * 60 * 1000,
  });

  const locationQ = useQuery<{ city: string | null; region: string | null }>({
    queryKey: ['env', 'location'],
    queryFn: async () => {
      try {
        const { data } = await api.get<ProfileLocation>('/profile/me');
        if (data?.use_manual_location && data?.manual_location?.city) {
          return { city: data.manual_location.city, region: data.manual_location.region };
        }
        return {
          city: data?.detected_location?.city ?? null,
          region: data?.detected_location?.region ?? null,
        };
      } catch {
        return { city: null, region: null };
      }
    },
    staleTime: 60 * 60 * 1000,
  });

  const w = weatherQ.data;
  const a = aqiQ.data;
  const loc = locationQ.data;

  // 明日 = 按日期匹配(今天+1),匹配不到再退回索引 1,避免「源首项不是今天」时错位。
  const tomorrow = (() => {
    const fc = forecastQ.data;
    if (!fc || fc.length === 0) return null;
    const d = new Date();
    d.setDate(d.getDate() + 1);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    return fc.find((f) => f.date === iso) ?? fc[1] ?? null;
  })();

  if (!w && !a && !loc?.city && !tomorrow) return null;

  const top = [
    loc?.city || null,
    w?.temperature != null ? `${Math.round(w.temperature)}°` : null,
    w?.weather || null,
  ]
    .filter(Boolean)
    .join(' · ');

  const metrics: { label: string; value: string }[] = [];
  if (w?.humidity != null) metrics.push({ label: '湿度', value: `${w.humidity}%` });
  if (a?.aqi != null) metrics.push({ label: 'AQI', value: `${a.aqi}` });
  if (a?.pm25 != null) metrics.push({ label: 'PM2.5', value: `${a.pm25}` });

  // 展开里是否有可看的内容(没有 → 不画展开箭头,单纯一行进位置)。
  const hasMore = metrics.length > 0 || tomorrow != null;

  return (
    <View style={styles.card}>
      {/* 默认单行:城市 · 温度 · 天气 + 空气 chip(点空白进位置) + 展开箭头 */}
      <View style={styles.topRow}>
        <Pressable
          style={({ pressed }) => [styles.topMain, pressed && { opacity: 0.7 }]}
          onPress={() => router.push('/location' as any)}
          accessibilityRole="button"
          accessibilityLabel="天气与空气质量,点击设置位置"
        >
          <Icon name="sun" size={17} color={C.ink2} />
          <Text style={styles.topText} numberOfLines={1}>
            {top || '环境同步中'}
          </Text>
          <Chip status={aqiStatus(a?.aqi)}>{aqiLabel(a?.aqi)}</Chip>
        </Pressable>
        {hasMore ? (
          <Pressable
            style={({ pressed }) => [styles.expandBtn, pressed && { opacity: 0.6 }]}
            onPress={() => setExpanded((v) => !v)}
            accessibilityRole="button"
            accessibilityLabel={expanded ? '收起天气详情' : '展开天气详情'}
            hitSlop={8}
          >
            <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={C.ink3} />
          </Pressable>
        ) : null}
      </View>

      {/* 展开:湿度 / AQI / PM2.5 + 明日预报 */}
      {expanded && hasMore ? (
        <View style={styles.detail}>
          {metrics.length > 0 ? (
            <View style={styles.metricsRow}>
              {metrics.map((m, idx) => (
                <View key={m.label} style={styles.metric}>
                  {idx > 0 ? <Text style={styles.dot}>·</Text> : null}
                  <Text style={styles.metricLabel}>{m.label}</Text>
                  <Text style={styles.metricValue}>{m.value}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {tomorrow ? (
            <View style={styles.forecastRow}>
              <Text style={styles.forecastLabel}>明日</Text>
              <Text style={styles.forecastTemp}>
                {Math.round(tomorrow.temp_max)}° / {Math.round(tomorrow.temp_min)}°
              </Text>
              {tomorrow.weather ? (
                <Text style={styles.forecastWeather} numberOfLines={1}>
                  {tomorrow.weather}
                  {tomorrow.humidity != null ? ` · 湿度 ${tomorrow.humidity}%` : ''}
                </Text>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 10,
  },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  topMain: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 8 },
  topText: { flex: 1, minWidth: 0, fontSize: 14.5, color: C.ink1, fontWeight: '600' },
  expandBtn: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  detail: {
    gap: 8,
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  metricsRow: { flexDirection: 'row', alignItems: 'baseline', flexWrap: 'wrap', gap: 7 },
  metric: { flexDirection: 'row', alignItems: 'baseline', gap: 5 },
  dot: { color: C.ink4, fontSize: 12, marginRight: 2 },
  metricLabel: { fontSize: 12, color: C.ink3 },
  metricValue: { fontFamily: 'IBMPlexMono', fontSize: 13, fontWeight: '500', color: C.ink2 },
  forecastRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 7,
  },
  forecastLabel: { fontSize: 12, color: C.ink3 },
  forecastTemp: { fontFamily: 'IBMPlexMono', fontSize: 13, fontWeight: '600', color: C.ink1 },
  forecastWeather: { flex: 1, minWidth: 0, fontSize: 12.5, color: C.ink2 },
});
