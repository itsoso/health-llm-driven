import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { useTheme, type ColorPalette } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface VitalsData {
  sleep?: string;
  hr?: string;
  hrv?: string;
  battery?: string;
  steps?: string;
  stress?: string;
}

function Metric({
  icon, color, label, value, c,
}: { icon: string; color: string; label: string; value: string; c: ColorPalette }) {
  return (
    <View style={styles.item}>
      <Ionicons name={icon as any} size={12} color={color} />
      <Text maxFontSizeMultiplier={1.3} style={[styles.val, { color }]}>{value}</Text>
      <Text maxFontSizeMultiplier={1.3} style={[styles.label, { color: c.labelTertiary }]}>{label}</Text>
    </View>
  );
}

export function VitalsCardView({ sleep, hr, hrv, battery, steps, stress }: VitalsData) {
  const { c } = useTheme();
  return (
    <CardShell icon="pulse" iconColor={c.brand} title="今日生理数据">
      <View style={styles.grid}>
        {sleep && <Metric icon="moon" color={c.purple} label="睡眠" value={sleep} c={c} />}
        {hr && <Metric icon="heart" color={c.pink} label="心率" value={hr} c={c} />}
        {hrv && <Metric icon="pulse" color={c.teal} label="HRV" value={hrv} c={c} />}
        {battery && <Metric icon="battery-charging" color={c.green} label="电量" value={battery} c={c} />}
        {steps && <Metric icon="footsteps" color={c.orange} label="步数" value={steps} c={c} />}
        {stress && <Metric icon="cloudy" color={c.amber} label="压力" value={stress} c={c} />}
      </View>
    </CardShell>
  );
}

export const VitalsCardSpec: CardSpec<VitalsData> = {
  type: 'vitals',
  label: '今日综合',
  match({ query_lower, toolsUsed }) {
    if (/记录|打卡|吃了|喝了|服药|补剂|体重/.test(query_lower)) return null;
    if (/综合|今日如何|整体|所有数据|健康如何/.test(query_lower)) return 10;
    const hits = ['睡眠','心率','hrv','电量','步数','压力'].filter(k => query_lower.includes(k)).length;
    if (hits >= 2) return 8;
    return null;
  },
  build({ data }) {
    const g = data.garmin;
    const cardData: VitalsData = {};
    if (g?.total_sleep_duration) cardData.sleep = `${(g.total_sleep_duration / 60).toFixed(1)}h`;
    if (g?.resting_heart_rate) cardData.hr = `${g.resting_heart_rate}bpm`;
    if (g?.hrv != null) cardData.hrv = `${Number(g.hrv).toFixed(1)}ms`;
    if (g?.body_battery_most_charged) cardData.battery = `${g.body_battery_most_charged}`;
    if (g?.steps) cardData.steps = g.steps.toLocaleString();
    if (g?.average_stress_level != null) cardData.stress = `${g.average_stress_level}`;
    if (Object.keys(cardData).length === 0 && data.score?.total_score) cardData.sleep = `评分${data.score.total_score}`;
    return Object.keys(cardData).length > 0 ? cardData : null;
  },
  render: (d) => <VitalsCardView {...d} />,
};

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  item: { alignItems: 'center', gap: 2, minWidth: 50 },
  val: { fontSize: 14, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  label: { fontSize: 9 } as TextStyle,
});
