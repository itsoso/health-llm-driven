import React from 'react';
import { View, Text, StyleSheet, TextStyle, TouchableOpacity } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii, shadows } from '@/constants/theme';

interface Props {
  score: number;
  city?: string;
  temperature?: number | null;
  weatherDesc?: string;
  aqiValue?: number | null;
  pm25?: number | null;
  tomorrowWeather?: string;
  tomorrowTempRange?: string;
  sleep?: string;
  steps?: string;
  hr?: string;
  battery?: string;
  onSyncGarmin?: () => void;
  syncing?: boolean;
  onSettings?: () => void;
  onNewChat?: () => void;
  onHistory?: () => void;
}

function getAqiColor(v?: number | null): string {
  if (!v) return colors.labelTertiary;
  if (v <= 50) return '#30D158';
  if (v <= 100) return '#FF9F0A';
  return '#FF453A';
}

function sc(score: number): string {
  if (score >= 80) return '#30D158';
  if (score >= 60) return '#FF9F0A';
  return '#FF453A';
}

export default function HomeHeader({
  score, city, temperature, weatherDesc, aqiValue, pm25,
  tomorrowWeather, tomorrowTempRange, sleep, steps, hr, battery,
  onSyncGarmin, syncing, onSettings, onNewChat, onHistory,
}: Props) {
  const hour = new Date().getHours();
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';

  const ringSize = 52;
  const sw = 4;
  const r = (ringSize - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));

  return (
    <View style={styles.card}>
      {/* Top: greeting + settings + score ring */}
      <View style={styles.topRow}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Text style={[txt.greeting, { flex: 1 }]}>{greeting}</Text>
            {onHistory && (
              <TouchableOpacity onPress={onHistory} style={styles.settingsBtn} activeOpacity={0.6}>
                <Ionicons name="chatbubbles-outline" size={18} color={colors.labelTertiary} />
              </TouchableOpacity>
            )}
            {onNewChat && (
              <TouchableOpacity onPress={onNewChat} style={styles.settingsBtn} activeOpacity={0.6}>
                <Ionicons name="create-outline" size={18} color={colors.labelTertiary} />
              </TouchableOpacity>
            )}
            {onSettings && (
              <TouchableOpacity onPress={onSettings} style={styles.settingsBtn} activeOpacity={0.6}>
                <Ionicons name="settings-outline" size={18} color={colors.labelTertiary} />
              </TouchableOpacity>
            )}
          </View>
          {/* Weather line */}
          <View style={styles.weatherRow}>
            <Ionicons name="location-outline" size={12} color={colors.brand} />
            <Text style={txt.weatherMain}>
              {city || '--'} {temperature != null ? `${Math.round(temperature)}°C` : ''} {weatherDesc || ''}
            </Text>
          </View>
          {/* AQI + tomorrow */}
          <View style={styles.subRow}>
            {aqiValue != null && (
              <View style={styles.aqiTag}>
                <View style={[styles.aqiDot, { backgroundColor: getAqiColor(aqiValue) }]} />
                <Text style={[txt.aqiText, { color: getAqiColor(aqiValue) }]}>AQI {aqiValue}</Text>
                {pm25 != null && <Text style={txt.pm25}>PM2.5 {Math.round(pm25)}</Text>}
              </View>
            )}
            {tomorrowWeather && (
              <Text style={txt.tomorrow}>明天 {tomorrowWeather} {tomorrowTempRange}</Text>
            )}
          </View>
        </View>

        {/* Score ring */}
        <View style={styles.ringWrap}>
          <Svg width={ringSize} height={ringSize}>
            <Defs>
              <LinearGradient id="hdrG" x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor="#0A8F8F" />
                <Stop offset="1" stopColor="#30D158" />
              </LinearGradient>
            </Defs>
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="url(#hdrG)" strokeWidth={sw} fill="none"
              strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
              transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`} />
          </Svg>
          <View style={styles.ringCenter}>
            <Text style={[txt.scoreNum, { color: sc(score) }]}>{score}</Text>
            <Text style={txt.scoreLabel}>健康</Text>
          </View>
        </View>
      </View>

      {/* Vitals strip */}
      <View style={styles.vitalsRow}>
        <Vital icon="moon-outline" color="#BF5AF2" label="睡眠" value={sleep || '--'} />
        <View style={styles.vDivider} />
        <Vital icon="footsteps-outline" color="#FF6723" label="步数" value={steps || '--'} />
        <View style={styles.vDivider} />
        <Vital icon="heart-outline" color="#FF375F" label="心率" value={hr || '--'} />
        <View style={styles.vDivider} />
        <Vital icon="battery-charging-outline" color="#30D158" label="电量" value={battery || '--'} />
      </View>

      {/* Garmin sync */}
      {onSyncGarmin && (
        <TouchableOpacity style={styles.syncBtn} onPress={onSyncGarmin} disabled={syncing} activeOpacity={0.6}>
          <Ionicons name="sync-outline" size={13} color={syncing ? colors.labelTertiary : colors.brand} style={syncing ? { opacity: 0.5 } : undefined} />
          <Text style={[txt.syncText, syncing && { color: colors.labelTertiary }]}>{syncing ? '同步中...' : '同步 Garmin'}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

function Vital({ icon, color, label, value }: { icon: any; color: string; label: string; value: string }) {
  return (
    <View style={styles.vitalItem}>
      <Ionicons name={icon} size={14} color={color} />
      <Text style={[txt.vitalVal, { color }]}>{value}</Text>
      <Text style={txt.vitalLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    padding: spacing.lg,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    ...shadows.medium,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
  },
  weatherRow: {
    flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 4,
  },
  subRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4,
  },
  aqiTag: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  aqiDot: { width: 6, height: 6, borderRadius: 3 },
  ringWrap: {
    width: 52, height: 52, alignItems: 'center', justifyContent: 'center',
  },
  ringCenter: { position: 'absolute', alignItems: 'center' },
  vitalsRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingTop: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator,
  },
  vitalItem: { flex: 1, alignItems: 'center', gap: 2 },
  vDivider: { width: StyleSheet.hairlineWidth, height: 28, backgroundColor: colors.separator },
  syncBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
    marginTop: spacing.sm, paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator,
  },
  settingsBtn: { padding: 4 },
});

const txt = {
  greeting: { fontSize: 22, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  weatherMain: { fontSize: 13, color: colors.labelPrimary } as TextStyle,
  aqiText: { fontSize: 11, fontWeight: '600' } as TextStyle,
  pm25: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  tomorrow: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  scoreNum: { fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  scoreLabel: { fontSize: 8, fontWeight: '500', color: colors.labelTertiary, marginTop: -2 } as TextStyle,
  vitalVal: { fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  vitalLabel: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
  syncText: { fontSize: 12, color: colors.brand, fontWeight: '500' } as TextStyle,
};
