/**
 * EnvironmentCard —— 首页天气 + AQI 卡 (2026-05-11 P2 重做漏了, 用户报缺).
 *
 * 简洁 4 元素: 温度 / 天气描述 / AQI 数值 + 等级 / 户外活动建议.
 * 数据 API 失败时整卡隐藏 (不显示噪声).
 */

import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../services/api';
import { useTheme } from '../../hooks/useTheme';
import { spacing, radii } from '../../constants/theme';
import AgentFeedbackLink from '../agent/AgentFeedbackLink';
import { createEnvironmentAgentContext } from '../../utils/agentContext';

interface WeatherInner {
  available?: boolean;
  temperature?: number;
  feels_like?: number;
  weather?: string;
  humidity?: number;
}
interface WeatherResponse {
  weather?: WeatherInner;
}

interface AirQuality {
  aqi?: number;
  aqi_level?: string;
  aqi_description?: string;
  primary_pollutant?: string;
  pm25?: number;
  pm10?: number;
}

interface ForecastDay {
  date: string;
  weather: string;
  temp_max: number;
  temp_min: number;
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

function aqiColor(aqi: number | undefined): string {
  if (aqi == null) return '#999';
  if (aqi <= 50) return '#30D158';
  if (aqi <= 100) return '#FFCC00';
  if (aqi <= 150) return '#FF9F0A';
  if (aqi <= 200) return '#FF453A';
  return '#BF5AF2';
}

function aqiLabel(aqi: number | undefined): string {
  if (aqi == null) return '—';
  if (aqi <= 50) return '优';
  if (aqi <= 100) return '良';
  if (aqi <= 150) return '轻度';
  if (aqi <= 200) return '中度';
  return '重度';
}

export default function EnvironmentCard() {
  const router = useRouter();
  const { c } = useTheme();

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
    staleTime: 60 * 60 * 1000,  // 预报变得慢, 1h
  });

  // 用户当前生效的地区显示 — manual > detected
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
  const tomorrow = forecastQ.data?.[1] ?? null;  // 索引 1 = 明日 (0 = 今日)
  const loc = locationQ.data;

  // 整卡都没数据 → 不显示
  if (!w && !a && !tomorrow && !loc?.city) return null;

  const weatherDesc = w?.weather || '';
  const aqi = a?.aqi;

  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      {/* 顶部: 地区 + 设置齿轮 (从原首页 header 搬过来, 2026-05-12) */}
      <View style={styles.topRow}>
        {loc?.city ? (
          <TouchableOpacity style={styles.locTouch} onPress={() => router.push('/location' as any)}>
            <Ionicons name="location-outline" size={14} color={c.labelTertiary} />
            <Text style={[styles.locText, { color: c.labelSecondary }]} numberOfLines={1}>
              {loc.region && !loc.region.includes(loc.city) ? `${loc.region} · ${loc.city}` : loc.city}
            </Text>
            <Ionicons name="chevron-forward" size={12} color={c.labelTertiary} />
          </TouchableOpacity>
        ) : (
          <View style={{ flex: 1 }} />
        )}
        <TouchableOpacity
          onPress={() => router.push('/settings' as any)}
          accessibilityLabel="设置"
          style={styles.settingsBtn}
          hitSlop={8}
        >
          <Ionicons name="settings-outline" size={20} color={c.labelTertiary} />
        </TouchableOpacity>
      </View>

      <View style={styles.row}>
        {/* 左: 天气 */}
        <View style={styles.left}>
          <Text style={[styles.temp, { color: c.labelPrimary }]}>
            {w?.temperature != null ? `${Math.round(w.temperature)}°` : '—'}
          </Text>
          <Text style={[styles.weatherText, { color: c.labelSecondary }]} numberOfLines={1}>
            {weatherDesc || '天气数据暂无'}
            {w?.humidity != null ? ` · 湿度 ${w.humidity}%` : ''}
          </Text>
        </View>

        {/* 右: AQI + PM2.5 */}
        <View style={styles.right}>
          <View style={[styles.aqiBadge, { backgroundColor: aqiColor(aqi) + '22', borderColor: aqiColor(aqi) }]}>
            <Text style={[styles.aqiNum, { color: aqiColor(aqi) }]}>{aqi != null ? aqi : '—'}</Text>
          </View>
          <Text style={[styles.aqiLabel, { color: c.labelTertiary }]}>
            空气 {aqiLabel(aqi)}
          </Text>
          {a?.pm25 != null && (
            <Text style={[styles.pm25Label, { color: c.labelTertiary }]}>
              PM2.5 {Math.round(a.pm25)}
            </Text>
          )}
        </View>
      </View>

      {/* 明日预报 — 让用户提前知道是不是要带伞/穿厚一点 */}
      {tomorrow && (
        <View style={[styles.forecastRow, { borderTopColor: c.separator }]}>
          <Text style={[styles.forecastLabel, { color: c.labelTertiary }]}>明日</Text>
          <Text style={[styles.forecastTemp, { color: c.labelPrimary }]}>
            {Math.round(tomorrow.temp_max)}° / {Math.round(tomorrow.temp_min)}°
          </Text>
          <Text style={[styles.forecastWeather, { color: c.labelSecondary }]} numberOfLines={1}>
            {tomorrow.weather}
          </Text>
        </View>
      )}

      <AgentFeedbackLink
        label="跟 Agent 调整今天户外安排"
        accessibilityLabel="跟 Agent 调整今天户外安排"
        prompt="请基于我当前城市的天气、空气质量和明日预报，给出今天户外运动、通勤防护、鼻炎/睡眠/补水方面的调整建议。"
        context={createEnvironmentAgentContext({
          weather: w ?? null,
          airQuality: a ?? null,
          forecast: forecastQ.data ?? null,
          location: loc ?? null,
        })}
        badge={loc?.city ? `${loc.city}环境` : '当前环境'}
      />

      {/* 跑步入口 — 用户报缺, 2026-05-11 加 */}
      <TouchableOpacity
        style={[styles.runBtn, { backgroundColor: c.brandLight, borderColor: c.brand }]}
        onPress={() => router.push('/live-run' as any)}
        accessibilityLabel="开始跑步"
      >
        <Ionicons name="play-circle" size={18} color={c.brand} />
        <Text style={[styles.runBtnText, { color: c.brand }]}>开始跑步</Text>
        {aqi != null && aqi > 150 && (
          <Text style={[styles.runHint, { color: c.amber }]}>· 空气差,建议室内</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.md,
  },
  locRow: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    marginBottom: -spacing.xs,  // 紧贴下面温度
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: -spacing.xs,
  },
  locTouch: {
    flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1,
  },
  settingsBtn: { paddingLeft: 8, paddingVertical: 2 },
  locText: { fontSize: 12, fontWeight: '500', flex: 1 },
  pm25Label: { fontSize: 10, fontWeight: '500', marginTop: 2 },
  row: { flexDirection: 'row', alignItems: 'center' },
  left: { flex: 1, gap: 2 },
  right: { alignItems: 'center', gap: 4 },
  temp: { fontSize: 28, fontWeight: '700' },
  weatherText: { fontSize: 13 },
  aqiBadge: {
    minWidth: 56,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
    borderWidth: 1.5,
    alignItems: 'center',
  },
  aqiNum: { fontSize: 20, fontWeight: '700' },
  aqiLabel: { fontSize: 11, fontWeight: '500' },
  forecastRow: {
    flexDirection: 'row', alignItems: 'baseline', gap: 8,
    paddingTop: spacing.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  forecastLabel: { fontSize: 12, fontWeight: '600' },
  forecastTemp: { fontSize: 14, fontWeight: '600' },
  forecastWeather: { fontSize: 12, flex: 1 },
  runBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  runBtnText: { fontSize: 14, fontWeight: '600' },
  runHint: { fontSize: 11, marginLeft: 'auto' },
});
