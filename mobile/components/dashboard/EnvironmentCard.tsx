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

interface Weather {
  temp_c?: number;
  feels_like_c?: number;
  description?: string;
  text?: string;
  humidity?: number;
  city?: string;
}

interface AirQuality {
  aqi?: number;
  level?: string;
  category?: string;
  primary_pollutant?: string;
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

  const weatherQ = useQuery<Weather | null>({
    queryKey: ['env', 'weather'],
    queryFn: async () => {
      try {
        const { data } = await api.get<Weather>('/environment/weather');
        return data;
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

  const w = weatherQ.data;
  const a = aqiQ.data;

  // 整卡都没数据 → 不显示
  if (!w && !a) return null;

  const weatherDesc = w?.description || w?.text || '';
  const aqi = a?.aqi;

  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.row}>
        {/* 左: 天气 */}
        <View style={styles.left}>
          <Text style={[styles.temp, { color: c.labelPrimary }]}>
            {w?.temp_c != null ? `${Math.round(w.temp_c)}°` : '—'}
          </Text>
          <Text style={[styles.weatherText, { color: c.labelSecondary }]} numberOfLines={1}>
            {weatherDesc || '天气数据暂无'}
            {w?.city ? ` · ${w.city}` : ''}
          </Text>
        </View>

        {/* 右: AQI */}
        <View style={styles.right}>
          <View style={[styles.aqiBadge, { backgroundColor: aqiColor(aqi) + '22', borderColor: aqiColor(aqi) }]}>
            <Text style={[styles.aqiNum, { color: aqiColor(aqi) }]}>{aqi != null ? aqi : '—'}</Text>
          </View>
          <Text style={[styles.aqiLabel, { color: c.labelTertiary }]}>
            空气 {aqiLabel(aqi)}
          </Text>
        </View>
      </View>

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
