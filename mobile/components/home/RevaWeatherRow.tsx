/**
 * RevaWeatherCard —— 首页天气卡(前置到 hero 下方,环境是重要日常信息)。
 *
 * 第 1 行:[图标] {城市} · {温度}° {天气}        [空气等级 Chip]
 * 第 2 行:湿度 X% · AQI N · PM2.5 N μg/m³(PM2.5 用 mono 数字,空气质量关键指标)
 * 复用 EnvironmentCard 的 env query keys(['env','weather'|'aqi'|'location'])→ React Query 去重。
 * 整卡无数据 → 不渲染。点击进 /location。
 */
import React from 'react';
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

  if (!w && !a && !loc?.city) return null;

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

  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
      onPress={() => router.push('/location' as any)}
      accessibilityRole="button"
      accessibilityLabel="天气与空气质量,点击设置位置"
    >
      <View style={styles.topRow}>
        <Icon name="sun" size={17} color={C.ink2} />
        <Text style={styles.topText} numberOfLines={1}>
          {top || '环境同步中'}
        </Text>
        <Chip status={aqiStatus(a?.aqi)}>{aqiLabel(a?.aqi)}</Chip>
      </View>
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
    </Pressable>
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
    gap: 8,
  },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  topText: { flex: 1, minWidth: 0, fontSize: 14.5, color: C.ink1, fontWeight: '600' },
  metricsRow: { flexDirection: 'row', alignItems: 'baseline', flexWrap: 'wrap', gap: 7 },
  metric: { flexDirection: 'row', alignItems: 'baseline', gap: 5 },
  dot: { color: C.ink4, fontSize: 12, marginRight: 2 },
  metricLabel: { fontSize: 12, color: C.ink3 },
  metricValue: { fontFamily: 'IBMPlexMono', fontSize: 13, fontWeight: '500', color: C.ink2 },
});
