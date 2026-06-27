import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { revaColors as C, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 环境类目 accent (青) + 卡底 tint = 装饰色, 保留字面量 (= legacy teal/tintTeal).
const ENV_ACCENT = '#2F9E8F';
const ENV_TINT = '#E0EFEC';

interface WeatherData {
  temperature?: number;
  weather?: string;
  city?: string;
  aqi?: number;
  pm25?: number;
  advice?: string;
}

// AQI 颜色按国标固定 (优良/轻中重度), 不随主题切换 — 红色就是红色, 不能因暗色变绿.
function aqiLabel(aqi?: number, fallback?: string): { label: string; color: string } {
  if (aqi == null) return { label: '—', color: fallback ?? '#8E8E93' };
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
  const q = aqiLabel(aqi, C.ink3);
  return (
    <CardShell icon="partly-sunny" iconColor={ENV_ACCENT} title={city ? `${city}环境` : '环境'} bg={ENV_TINT}>
      <View style={styles.row}>
        <View style={styles.tempBlock}>
          <Text maxFontSizeMultiplier={1.3} style={styles.temp}>
            {temperature != null ? `${Math.round(temperature)}°` : '--'}
          </Text>
          {weather && (
            <Text maxFontSizeMultiplier={1.3} style={styles.weatherLabel}>
              {weather}
            </Text>
          )}
        </View>
        <View style={styles.aqiBlock}>
          <View style={styles.aqiRow}>
            <View style={[styles.aqiDot, { backgroundColor: q.color }]} />
            <Text maxFontSizeMultiplier={1.3} style={[styles.aqiVal, { color: q.color }]}>{aqi ?? '--'}</Text>
            <Text maxFontSizeMultiplier={1.3} style={[styles.aqiLabel, { color: q.color }]}>{q.label}</Text>
          </View>
          {pm25 != null && (
            <Text maxFontSizeMultiplier={1.3} style={styles.pm}>
              PM2.5 {pm25}
            </Text>
          )}
        </View>
      </View>
      {(advice || aqi != null || temperature != null) && (
        <View style={styles.adviceRow}>
          <Ionicons name="fitness" size={12} color={C.green500} />
          <Text maxFontSizeMultiplier={1.3} style={styles.advice}>
            {advice || exerciseAdvice(aqi, temperature)}
          </Text>
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
  temp: { fontFamily: revaFonts.mono, fontSize: 26, fontWeight: '800', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  weatherLabel: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2 } as TextStyle,
  aqiVal: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  aqiLabel: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '600' } as TextStyle,
  pm: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3, fontVariant: ['tabular-nums'] as const } as TextStyle,
  advice: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink2 } as TextStyle,
});
