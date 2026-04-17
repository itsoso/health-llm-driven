import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii, shadows } from '@/constants/theme';

interface Forecast {
  date: string;
  weather: string;
  temp_max: number;
  temp_min: number;
}

interface Props {
  userName?: string;
  weather?: { temperature?: number; weather?: string; humidity?: number };
  aqi?: { aqi?: number; pm25?: number; aqi_description?: string };
  forecast?: Forecast[];
  city?: string;
}

const weatherIcons: Record<string, keyof typeof Ionicons.glyphMap> = {
  '晴': 'sunny',
  '多云': 'partly-sunny',
  '阴': 'cloudy',
  '雾': 'cloud',
  '霾': 'cloud',
  '雨': 'rainy',
  '小雨': 'rainy',
  '中雨': 'rainy',
  '大雨': 'thunderstorm',
  '雪': 'snow',
};

function getWeatherIcon(w?: string): keyof typeof Ionicons.glyphMap {
  if (!w) return 'partly-sunny';
  for (const [key, icon] of Object.entries(weatherIcons)) {
    if (w.includes(key)) return icon;
  }
  return 'partly-sunny';
}

function getAqiColor(aqi?: number | null): string {
  if (!aqi) return colors.labelTertiary;
  if (aqi <= 50) return '#30D158';
  if (aqi <= 100) return '#FF9F0A';
  return '#FF453A';
}

function getAqiLevel(aqi?: number | null): string {
  if (!aqi) return '--';
  if (aqi <= 50) return '优';
  if (aqi <= 100) return '良';
  if (aqi <= 150) return '轻度';
  return '重度';
}

export default function GreetingHeader({ userName, weather, aqi, forecast, city }: Props) {
  const hour = new Date().getHours();
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
  const dateStr = new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' });

  const todayForecast = forecast?.[0];
  const tomorrowForecast = forecast?.[1];
  const weatherDesc = weather?.weather || todayForecast?.weather || '';

  return (
    <View style={styles.container}>
      {/* Greeting */}
      <Text style={txt.greeting}>{greeting}</Text>
      <Text style={txt.date}>{dateStr}</Text>

      {/* Weather Card */}
      {(weather || todayForecast) && (
        <View style={styles.weatherCard}>
          {/* Today row */}
          <View style={styles.todaySection}>
            <View style={styles.weatherIconWrap}>
              <Ionicons name={getWeatherIcon(weatherDesc)} size={36} color="#FF9F0A" />
            </View>
            <View style={styles.todayMain}>
              <View style={styles.cityRow}>
                <Ionicons name="location-outline" size={12} color={colors.brand} />
                <Text style={txt.city}>{city || '--'}</Text>
                <Text style={txt.weatherDesc}>{weatherDesc}</Text>
              </View>
              <Text style={txt.temp}>
                {weather?.temperature != null ? `${Math.round(weather.temperature)}°` : '--'}
              </Text>
              {todayForecast && (
                <Text style={txt.tempRange}>{todayForecast.temp_min}° / {todayForecast.temp_max}°</Text>
              )}
            </View>
            {/* AQI */}
            {aqi?.aqi != null && (
              <View style={styles.aqiSection}>
                <View style={[styles.aqiDot, { backgroundColor: getAqiColor(aqi.aqi) }]} />
                <Text style={txt.aqiLabel}>AQI</Text>
                <Text style={[txt.aqiValue, { color: getAqiColor(aqi.aqi) }]}>{aqi.aqi}</Text>
                <Text style={txt.aqiLevel}>{getAqiLevel(aqi.aqi)}</Text>
                <Text style={txt.pm25}>PM2.5 {aqi.pm25 != null ? Math.round(aqi.pm25) : '--'}</Text>
              </View>
            )}
          </View>

          {/* Tomorrow */}
          {tomorrowForecast && (
            <View style={styles.tomorrowRow}>
              <Ionicons name={getWeatherIcon(tomorrowForecast.weather)} size={16} color={colors.labelTertiary} />
              <Text style={txt.tomorrow}>明天</Text>
              <Text style={txt.tomorrowWeather}>{tomorrowForecast.weather}</Text>
              <Text style={txt.tomorrowTemp}>{tomorrowForecast.temp_min}° / {tomorrowForecast.temp_max}°</Text>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginBottom: spacing.md },
  weatherCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    padding: spacing.lg,
    marginTop: spacing.md,
    ...shadows.medium,
  },
  todaySection: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  weatherIconWrap: {
    width: 52, height: 52, borderRadius: 16,
    backgroundColor: '#FFF8EC',
    alignItems: 'center', justifyContent: 'center',
    marginRight: spacing.md,
  },
  todayMain: { flex: 1 },
  cityRow: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  aqiSection: {
    alignItems: 'center',
    backgroundColor: colors.bgPrimary,
    borderRadius: radii.md,
    paddingHorizontal: 10, paddingVertical: 8,
    minWidth: 64,
  },
  aqiDot: { width: 6, height: 6, borderRadius: 3, marginBottom: 3 },
  tomorrowRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginTop: spacing.md, paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator,
  },
});

const txt = {
  greeting: { fontSize: 30, fontWeight: '800', color: colors.labelPrimary, letterSpacing: -0.5 } as TextStyle,
  date: { fontSize: 14, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  city: { fontSize: 12, fontWeight: '600', color: colors.brand } as TextStyle,
  weatherDesc: { fontSize: 12, color: colors.labelSecondary, marginLeft: 4 } as TextStyle,
  temp: { fontSize: 32, fontWeight: '800', color: colors.labelPrimary, marginTop: -2, letterSpacing: -1 } as TextStyle,
  tempRange: { fontSize: 12, color: colors.labelTertiary } as TextStyle,
  aqiLabel: { fontSize: 9, fontWeight: '600', color: colors.labelTertiary } as TextStyle,
  aqiValue: { fontSize: 20, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  aqiLevel: { fontSize: 10, fontWeight: '500', color: colors.labelSecondary } as TextStyle,
  pm25: { fontSize: 9, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  tomorrow: { fontSize: 13, color: colors.labelSecondary } as TextStyle,
  tomorrowWeather: { fontSize: 13, fontWeight: '500', color: colors.labelPrimary, flex: 1 } as TextStyle,
  tomorrowTemp: { fontSize: 13, color: colors.labelSecondary, fontVariant: ['tabular-nums'] as const } as TextStyle,
};
