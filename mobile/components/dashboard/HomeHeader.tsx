import React, { useState } from 'react';
import { View, Text, StyleSheet, TextStyle, TouchableOpacity, LayoutAnimation } from 'react-native';
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
  sleepScore?: number | null;
  steps?: string;
  hr?: string;
  battery?: string;
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
  tomorrowWeather, tomorrowTempRange, sleep, sleepScore, steps, hr, battery,
  onSettings, onNewChat, onHistory,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const hour = new Date().getHours();
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setCollapsed(!collapsed);
  };

  const ringSize = collapsed ? 28 : 52;
  const sw = collapsed ? 3 : 4;
  const r = (ringSize - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));

  // ── Collapsed: one-line mini bar ──
  if (collapsed) {
    return (
      <TouchableOpacity style={styles.miniBar} onPress={toggle} activeOpacity={0.7}>
        <View style={{ width: ringSize, height: ringSize, alignItems: 'center', justifyContent: 'center' }}>
          <Svg width={ringSize} height={ringSize}>
            <Defs><LinearGradient id="miniG" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor="#0A8F8F" /><Stop offset="1" stopColor="#30D158" /></LinearGradient></Defs>
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="url(#miniG)" strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`} />
          </Svg>
          <Text style={{ position: 'absolute', fontSize: 9, fontWeight: '800', color: sc(score) }}>{score}</Text>
        </View>
        <Text style={txt.miniWeather} numberOfLines={1}>{city} {temperature != null ? `${Math.round(temperature)}°` : ''} {weatherDesc || ''}</Text>
        <MiniVital color="#BF5AF2" value={sleep || '--'} />
        <MiniVital color="#FF375F" value={hr || '--'} />
        <MiniVital color="#30D158" value={battery || '--'} />
        <Ionicons name="chevron-down" size={14} color={colors.labelTertiary} />
      </TouchableOpacity>
    );
  }

  // ── Expanded: full card ──
  return (
    <View style={styles.card}>
      {/* Top: greeting + actions + score ring */}
      <View style={styles.topRow}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Text style={[txt.greeting, { flex: 1 }]}>{greeting}</Text>
            {onHistory && (
              <TouchableOpacity onPress={onHistory} style={styles.actionBtn} activeOpacity={0.6}>
                <Ionicons name="chatbubbles-outline" size={18} color={colors.labelTertiary} />
              </TouchableOpacity>
            )}
            {onNewChat && (
              <TouchableOpacity onPress={onNewChat} style={styles.actionBtn} activeOpacity={0.6}>
                <Ionicons name="create-outline" size={18} color={colors.labelTertiary} />
              </TouchableOpacity>
            )}
            {onSettings && (
              <TouchableOpacity onPress={onSettings} style={styles.actionBtn} activeOpacity={0.6}>
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
            <Defs><LinearGradient id="hdrG" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor="#0A8F8F" /><Stop offset="1" stopColor="#30D158" /></LinearGradient></Defs>
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="url(#hdrG)" strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`} />
          </Svg>
          <View style={styles.ringCenter}>
            <Text style={[txt.scoreNum, { color: sc(score) }]}>{score}</Text>
            <Text style={txt.scoreLabel}>健康</Text>
          </View>
        </View>
      </View>

      {/* Vitals strip */}
      <View style={styles.vitalsRow}>
        <Vital icon="moon-outline" color="#BF5AF2" label={sleepScore ? `睡眠 ${sleepScore}分` : '睡眠'} value={sleep || '--'} />
        <View style={styles.vDivider} />
        <Vital icon="footsteps-outline" color="#FF6723" label="步数" value={steps || '--'} />
        <View style={styles.vDivider} />
        <Vital icon="heart-outline" color="#FF375F" label="心率" value={hr || '--'} />
        <View style={styles.vDivider} />
        <Vital icon="battery-charging-outline" color="#30D158" label="电量" value={battery || '--'} />
      </View>

      {/* Collapse button */}
      <TouchableOpacity style={styles.collapseBtn} onPress={toggle} activeOpacity={0.6}>
        <Ionicons name="chevron-up" size={16} color={colors.labelTertiary} />
      </TouchableOpacity>
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

function MiniVital({ color, value }: { color: string; value: string }) {
  return <Text style={[txt.miniVital, { color }]}>{value}</Text>;
}

const styles = StyleSheet.create({
  // Expanded card
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    padding: spacing.lg,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    ...shadows.medium,
  },
  topRow: { flexDirection: 'row', alignItems: 'flex-start' },
  weatherRow: { flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 4 },
  subRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  aqiTag: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  aqiDot: { width: 6, height: 6, borderRadius: 3 },
  ringWrap: { width: 52, height: 52, alignItems: 'center', justifyContent: 'center' },
  ringCenter: { position: 'absolute', alignItems: 'center' },
  vitalsRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingTop: spacing.md, marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator,
  },
  vitalItem: { flex: 1, alignItems: 'center', gap: 2 },
  vDivider: { width: StyleSheet.hairlineWidth, height: 28, backgroundColor: colors.separator },
  actionBtn: { padding: 8, minWidth: 36, minHeight: 36, alignItems: 'center', justifyContent: 'center' },
  collapseBtn: { alignItems: 'center', paddingTop: 6 },

  // Collapsed mini bar
  miniBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.bgCard,
    borderRadius: radii.full,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    paddingHorizontal: 12,
    paddingVertical: 8,
    ...shadows.subtle,
  },
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
  miniWeather: { fontSize: 12, color: colors.labelSecondary, flex: 1 } as TextStyle,
  miniVital: { fontSize: 12, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
};
