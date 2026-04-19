import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { colors } from '@/constants/theme';
import type { CardSpec } from './types';

interface WeatherData {
  temperature?: number;
  weather?: string;
  city?: string;
  aqi?: number;
  pm25?: number;
  advice?: string;
}

function aqiLabel(aqi?: number): { label: string; color: string } {
  if (aqi == null) return { label: '—', color: '#8E8E93' };
  if (aqi <= 50) return { label: '优', color: '#30D158' };
  if (aqi <= 100) return { label: '良', color: '#FFCC00' };
  if (aqi <= 150) return { label: '轻度', color: '#FF9F0A' };
  if (aqi <= 200) return { label: '中度', color: '#FF6723' };
  if (aqi <= 300) return { label: '重度', color: '#FF453A' };
  return { label: '严重', color: '#AF52DE' };
}

function exerciseAdvice(aqi?: number, temp?: number): string {
  if (aqi != null && aqi > 150) return '不建议户外运动';
  if (temp != null && temp > 32) return '避开正午，傍晚运动';
  if (temp != null && temp < 5) return '注意保暖，可室内';
  if (aqi != null && aqi <= 50) return '适合户外运动';
  return '适中，注意量力';
}

export function WeatherCardView({ temperature, weather, city, aqi, pm25, advice }: WeatherData) {
  const q = aqiLabel(aqi);
  return (
    <CardShell icon="partly-sunny" iconColor="#5AC8FA" title={city ? `${city}环境` : '环境'} bg="#F0F9FF">
      <View style={styles.row}>
        <View style={styles.tempBlock}>
          <Text style={txt.temp}>{temperature != null ? `${Math.round(temperature)}°` : '--'}</Text>
          {weather && <Text style={txt.weatherLabel}>{weather}</Text>}
        </View>
        <View style={styles.aqiBlock}>
          <View style={styles.aqiRow}>
            <View style={[styles.aqiDot, { backgroundColor: q.color }]} />
            <Text style={[txt.aqiVal, { color: q.color }]}>{aqi ?? '--'}</Text>
            <Text style={[txt.aqiLabel, { color: q.color }]}>{q.label}</Text>
          </View>
          {pm25 != null && <Text style={txt.pm}>PM2.5 {pm25}</Text>}
        </View>
      </View>
      {(advice || aqi != null || temperature != null) && (
        <View style={styles.adviceRow}>
          <Ionicons name="fitness" size={12} color="#30D158" />
          <Text style={txt.advice}>{advice || exerciseAdvice(aqi, temperature)}</Text>
        </View>
      )}
    </CardShell>
  );
}

export const WeatherCardSpec: CardSpec<WeatherData> = {
  type: 'weather',
  label: '环境',
  match({ query_lower }) {
    if (/天气|气温|温度|aqi|空气|pm2|户外|适合跑|适合运动/.test(query_lower)) return 15;
    return null;
  },
  build({ data }) {
    const w = data.weather?.weather ?? data.weather;
    const aqi = data.aqi;
    const city = data.profile?.manual_location?.city || data.profile?.detected_location?.city || data.profile?.city;
    const cardData: WeatherData = {};
    if (w?.temperature != null) cardData.temperature = w.temperature;
    if (w?.weather) cardData.weather = w.weather;
    if (city) cardData.city = city;
    if (aqi?.aqi != null) cardData.aqi = aqi.aqi;
    if (aqi?.pm25 != null) cardData.pm25 = aqi.pm25;
    return Object.keys(cardData).length > 0 ? cardData : null;
  },
  render: (d) => <WeatherCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  tempBlock: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  aqiBlock: { alignItems: 'flex-end' },
  aqiRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  aqiDot: { width: 8, height: 8, borderRadius: 4 },
  adviceRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 8 },
});

const txt = {
  temp: { fontSize: 26, fontWeight: '800', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  weatherLabel: { fontSize: 12, color: colors.labelSecondary } as TextStyle,
  aqiVal: { fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  aqiLabel: { fontSize: 11, fontWeight: '600' } as TextStyle,
  pm: { fontSize: 10, color: colors.labelTertiary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  advice: { fontSize: 11, color: colors.labelSecondary } as TextStyle,
};
