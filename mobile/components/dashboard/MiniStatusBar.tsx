import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii } from '@/constants/theme';

interface Props {
  score: number;
  weatherText?: string;
  aqiValue?: number | null;
  pm25?: number | null;
  tomorrowText?: string;
}

function getAqiColor(v?: number | null): string {
  if (!v) return colors.labelTertiary;
  if (v <= 50) return '#30D158';
  if (v <= 100) return '#FF9F0A';
  return '#FF453A';
}

export default function MiniStatusBar({ score, weatherText, aqiValue, pm25, tomorrowText }: Props) {
  const size = 32;
  const sw = 3;
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));

  return (
    <View style={styles.container}>
      {/* Top row: score + weather + AQI */}
      <View style={styles.row}>
        <View style={styles.scoreWrap}>
          <Svg width={size} height={size}>
            <Defs>
              <LinearGradient id="miniG" x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor="#0A8F8F" />
                <Stop offset="1" stopColor="#30D158" />
              </LinearGradient>
            </Defs>
            <Circle cx={size / 2} cy={size / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
            <Circle cx={size / 2} cy={size / 2} r={r} stroke="url(#miniG)" strokeWidth={sw} fill="none"
              strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} />
          </Svg>
          <Text style={txt.score}>{score}</Text>
        </View>

        {weatherText && (
          <View style={styles.weatherChip}>
            <Ionicons name="partly-sunny" size={12} color="#FF9F0A" />
            <Text style={txt.weather} numberOfLines={1}>{weatherText}</Text>
          </View>
        )}

        {aqiValue != null && (
          <View style={styles.aqiChip}>
            <View style={[styles.aqiDot, { backgroundColor: getAqiColor(aqiValue) }]} />
            <Text style={[txt.aqiVal, { color: getAqiColor(aqiValue) }]}>{aqiValue}</Text>
            {pm25 != null && <Text style={txt.pm25}>PM2.5 {Math.round(pm25)}</Text>}
          </View>
        )}
      </View>

      {/* Tomorrow row */}
      {tomorrowText && (
        <View style={styles.tomorrowRow}>
          <Ionicons name="calendar-outline" size={11} color={colors.labelTertiary} />
          <Text style={txt.tomorrow}>{tomorrowText}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.lg,
    paddingVertical: 6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  scoreWrap: {
    width: 32, height: 32,
    alignItems: 'center', justifyContent: 'center',
  },
  weatherChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: '#FFF8EC', paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: radii.full, flex: 1,
  },
  aqiChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
  },
  aqiDot: { width: 6, height: 6, borderRadius: 3 },
  tomorrowRow: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    marginTop: 4, paddingLeft: 40,
  },
});

const txt = {
  score: { position: 'absolute', fontSize: 10, fontWeight: '800', color: colors.brand } as TextStyle,
  weather: { fontSize: 11, color: colors.labelPrimary } as TextStyle,
  aqiVal: { fontSize: 11, fontWeight: '600' } as TextStyle,
  pm25: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  tomorrow: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
};
