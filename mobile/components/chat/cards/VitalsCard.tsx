import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { revaColors as C, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 每指标的装饰性 hue (睡眠紫 / 心率粉 / HRV 青 / 电量绿 / 步数橙 / 压力琥珀) ——
// 这是「区分指标」的色码, 不是「指标好坏」的临床语义, 故保留 Reva 亮色调色板字面量.
const HUES = {
  purple: '#7C5CBF',
  pink: '#C2487A',
  teal: '#2F9E8F',
  green: C.green500,
  orange: '#C97A2E',
  amber: '#C98A1E',
} as const;

interface VitalsData {
  sleep?: string;
  hr?: string;
  hrv?: string;
  battery?: string;
  steps?: string;
  stress?: string;
}

function Metric({
  icon, color, label, value,
}: { icon: string; color: string; label: string; value: string }) {
  return (
    <View style={styles.item}>
      <Ionicons name={icon as any} size={12} color={color} />
      <Text maxFontSizeMultiplier={1.3} style={[styles.val, { color }]}>{value}</Text>
      <Text maxFontSizeMultiplier={1.3} style={styles.label}>{label}</Text>
    </View>
  );
}

export function VitalsCardView({ sleep, hr, hrv, battery, steps, stress }: VitalsData) {
  return (
    <CardShell icon="pulse" iconColor={C.green500} title="今日生理数据">
      <View style={styles.grid}>
        {sleep && <Metric icon="moon" color={HUES.purple} label="睡眠" value={sleep} />}
        {hr && <Metric icon="heart" color={HUES.pink} label="心率" value={hr} />}
        {hrv && <Metric icon="pulse" color={HUES.teal} label="HRV" value={hrv} />}
        {battery && <Metric icon="battery-charging" color={HUES.green} label="电量" value={battery} />}
        {steps && <Metric icon="footsteps" color={HUES.orange} label="步数" value={steps} />}
        {stress && <Metric icon="cloudy" color={HUES.amber} label="压力" value={stress} />}
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
  val: { fontFamily: revaFonts.mono, fontSize: 14, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  label: { fontFamily: revaFonts.sans, fontSize: 9, color: C.ink3 } as TextStyle,
});
