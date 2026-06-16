/**
 * RevaWeatherRow —— 首页天气一行(Reva 重设计第 5 块,降级版)。
 *
 * 不再是整张大卡:一行内联「{城市} {温度}° {天气} · 湿度 X%」+ 右侧空气 Chip。
 * 复用 EnvironmentCard 已有的 env query keys(['env','weather'|'aqi'|'location'])
 * → React Query 自动去重,不新建请求。整行无数据 → 不渲染(不显示噪声)。
 * 点击进 /location(设置当前位置)。
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';

import api from '../../services/api';
import { revaColors as C } from '../../constants/revaTheme';
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

  const left = [
    loc?.city || null,
    w?.temperature != null ? `${Math.round(w.temperature)}°` : null,
    w?.weather || null,
    w?.humidity != null ? `湿度 ${w.humidity}%` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Pressable
      style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}
      onPress={() => router.push('/location' as any)}
      accessibilityRole="button"
      accessibilityLabel="天气与空气质量,点击设置位置"
    >
      <Icon name="sun" size={15} color={C.ink3} />
      <Text style={styles.text} numberOfLines={1}>
        {left || '环境同步中'}
      </Text>
      <Chip status={aqiStatus(a?.aqi)}>{aqiLabel(a?.aqi)}</Chip>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
  text: { flex: 1, minWidth: 0, fontSize: 13, color: C.ink2, fontWeight: '600' },
});
