import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import HealthCard from '../design-system/HealthCard';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../../constants/revaTheme';

interface Props {
  date?: string;
  odi?: number | null;
  minSpO2?: number | null;
  eventCount?: number | null;
  onOpenAnalysis: () => void;
}

// ODI / 最低血氧严重度 → 三步临床语义(好不好)。
function metricTone(metric: 'odi' | 'spo2', value: number | null | undefined): string {
  if (value == null) return C.ink1;
  if (metric === 'odi') {
    if (value >= 15) return revaSemantic.risk.fg;
    if (value >= 5) return revaSemantic.caution.fg;
    return revaSemantic.normal.fg;
  }
  if (value < 85) return revaSemantic.risk.fg;
  if (value < 90) return revaSemantic.caution.fg;
  return revaSemantic.normal.fg;
}

export default function SleepBreathingSummary({
  date,
  odi,
  minSpO2,
  eventCount,
  onOpenAnalysis,
}: Props) {
  return (
    <HealthCard
      title="睡眠呼吸"
      icon="pulse-outline"
      iconColor={C.blue500}
      iconBg={C.blue50}
      rightAccessory={date ? <Text style={styles.dateText}>{date}</Text> : null}
    >
      <View style={styles.metricRow}>
        <BreathingMetric label="ODI" value={odi != null ? odi.toFixed(1) : '--'} unit="/h" color={metricTone('odi', odi)} />
        <BreathingMetric label="最低 SpO2" value={minSpO2 != null ? `${minSpO2}` : '--'} unit="%" color={metricTone('spo2', minSpO2)} />
        <BreathingMetric label="氧降事件" value={eventCount != null ? String(eventCount) : '--'} unit="次" color={C.ink1} />
      </View>
      <Pressable
        style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
        onPress={onOpenAnalysis}
        accessibilityRole="button"
        accessibilityLabel="打开夜间血氧根因分析"
      >
        <Ionicons name="analytics-outline" size={15} color={C.green500} />
        <Text style={styles.actionText}>查看根因与今晚实验</Text>
        <Ionicons name="chevron-forward" size={15} color={C.green500} />
      </Pressable>
    </HealthCard>
  );
}

function BreathingMetric({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, { color }]}>{value}<Text style={styles.metricUnit}>{unit}</Text></Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

// Reva 设计语言:暖 paper2 指标底 / 活力绿 action / 数字指标走等宽 mono。
const styles = StyleSheet.create({
  metricRow: { flexDirection: 'row', gap: revaSpacing.s2 },
  metric: {
    flex: 1,
    minHeight: 68,
    borderRadius: revaRadii.md,
    backgroundColor: C.paper2,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  actionBtn: {
    minHeight: 40,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: revaSpacing.s3,
  },
  actionBtnPressed: { opacity: 0.82 },
  dateText: { fontFamily: revaFonts.mono, fontSize: 11, color: C.ink3 },
  metricValue: { fontFamily: revaFonts.mono, fontSize: 20, fontWeight: '800', fontVariant: ['tabular-nums'] },
  metricUnit: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '600', color: C.ink3 },
  metricLabel: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink2, marginTop: 3 },
  actionText: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.green500 },
});
