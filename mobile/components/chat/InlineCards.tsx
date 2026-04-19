import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii, shadows } from '@/constants/theme';

// ── Mini Score Card ──
export function ScoreCard({ score, label }: { score: number; label?: string }) {
  const size = 48;
  const sw = 4;
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));
  const color = score >= 80 ? '#30D158' : score >= 60 ? '#FF9F0A' : '#FF453A';

  return (
    <View style={styles.scoreCard}>
      <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={size} height={size}>
          <Defs><LinearGradient id="cg" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor="#0A8F8F" /><Stop offset="1" stopColor="#30D158" /></LinearGradient></Defs>
          <Circle cx={size / 2} cy={size / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
          <Circle cx={size / 2} cy={size / 2} r={r} stroke="url(#cg)" strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        </Svg>
        <Text style={[txt.scoreNum, { color }]}>{score}</Text>
      </View>
      <Text style={txt.scoreLabel}>{label || '健康评分'}</Text>
    </View>
  );
}

// ── Vitals Card (inline in chat) ──
export function VitalsCard({ sleep, hr, hrv, battery, steps }: { sleep?: string; hr?: string; hrv?: string; battery?: string; steps?: string }) {
  return (
    <View style={styles.vitalsCard}>
      {sleep && <Metric icon="moon" color="#BF5AF2" label="睡眠" value={sleep} />}
      {hr && <Metric icon="heart" color="#FF375F" label="心率" value={hr} />}
      {hrv && <Metric icon="pulse" color="#5AC8FA" label="HRV" value={hrv} />}
      {battery && <Metric icon="battery-charging" color="#30D158" label="电量" value={battery} />}
      {steps && <Metric icon="footsteps" color="#FF6723" label="步数" value={steps} />}
    </View>
  );
}

function Metric({ icon, color, label, value }: { icon: string; color: string; label: string; value: string }) {
  return (
    <View style={styles.metricItem}>
      <Ionicons name={icon as any} size={12} color={color} />
      <Text style={[txt.metricVal, { color }]}>{value}</Text>
      <Text style={txt.metricLabel}>{label}</Text>
    </View>
  );
}

// ── Record Confirmation Card ──
export function RecordCard({ type, detail }: { type: string; detail: string }) {
  const icons: Record<string, { icon: string; color: string }> = {
    water: { icon: 'water', color: '#64D2FF' },
    supplement: { icon: 'medical', color: '#AF52DE' },
    diet: { icon: 'restaurant', color: '#FF6723' },
    exercise: { icon: 'fitness', color: '#FF375F' },
    weight: { icon: 'scale', color: '#0A8F8F' },
    blood_pressure: { icon: 'heart', color: '#FF453A' },
    rhinitis: { icon: 'water', color: '#5AC8FA' },
    default: { icon: 'checkmark-circle', color: '#30D158' },
  };
  const cfg = icons[type] || icons.default;

  return (
    <View style={styles.recordCard}>
      <Ionicons name={cfg.icon as any} size={16} color={cfg.color} />
      <Text style={txt.recordText}>{detail}</Text>
      <Ionicons name="checkmark-circle" size={14} color="#30D158" />
    </View>
  );
}

const styles = StyleSheet.create({
  scoreCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: '#F8FFFE', borderRadius: radii.md,
    padding: 10, marginVertical: 6,
  },
  vitalsCard: {
    flexDirection: 'row', flexWrap: 'wrap', gap: 8,
    backgroundColor: '#F8FFFE', borderRadius: radii.md,
    padding: 10, marginVertical: 6,
  },
  metricItem: { alignItems: 'center', gap: 2, minWidth: 50 },
  recordCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#F0FFF4', borderRadius: radii.md,
    padding: 10, marginVertical: 4,
  },
});

const txt = {
  scoreNum: { fontSize: 16, fontWeight: '800', position: 'absolute', fontVariant: ['tabular-nums'] as const } as TextStyle,
  scoreLabel: { fontSize: 13, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  metricVal: { fontSize: 14, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  metricLabel: { fontSize: 9, color: colors.labelTertiary } as TextStyle,
  recordText: { fontSize: 13, color: colors.labelPrimary, flex: 1 } as TextStyle,
};
