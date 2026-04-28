import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { CardShell } from './CardShell';
import { colors } from '../../../constants/theme';
import type { CardSpec } from './types';

interface SleepData {
  score?: number;
  duration_h?: number;
  deep_min?: number;
  rem_min?: number;
  light_min?: number;
  awake_min?: number;
}

function ScoreRing({ score }: { score: number }) {
  const size = 52, sw = 5;
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));
  const color = score >= 80 ? '#30D158' : score >= 60 ? '#FF9F0A' : '#FF453A';
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </Svg>
      <Text style={[txt.scoreNum, { color }]}>{score}</Text>
    </View>
  );
}

function Stage({ label, min, color }: { label: string; min?: number; color: string }) {
  if (min == null) return null;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return (
    <View style={styles.stage}>
      <View style={[styles.stageDot, { backgroundColor: color }]} />
      <Text style={txt.stageLabel}>{label}</Text>
      <Text style={txt.stageVal}>{h > 0 ? `${h}h${m}m` : `${m}m`}</Text>
    </View>
  );
}

export function SleepCardView({ score, duration_h, deep_min, rem_min, light_min, awake_min }: SleepData) {
  return (
    <CardShell icon="moon" iconColor="#BF5AF2" title="睡眠分析" bg="#FAF5FF">
      <View style={styles.row}>
        {score != null && <ScoreRing score={score} />}
        <View style={{ flex: 1, marginLeft: 12 }}>
          {duration_h != null && <Text style={txt.duration}>{duration_h.toFixed(1)}h</Text>}
          <View style={styles.stages}>
            <Stage label="深睡" min={deep_min} color="#5856D6" />
            <Stage label="REM" min={rem_min} color="#BF5AF2" />
            <Stage label="浅睡" min={light_min} color="#AF52DE" />
            <Stage label="清醒" min={awake_min} color="#FF9F0A" />
          </View>
        </View>
      </View>
    </CardShell>
  );
}

export const SleepCardSpec: CardSpec<SleepData> = {
  type: 'sleep',
  label: '睡眠分析',
  match({ query_lower }) {
    if (/记录|打卡/.test(query_lower)) return null;
    if (/睡眠|深睡|rem|浅睡|睡得|入睡|清醒/.test(query_lower)) return 20;
    return null;
  },
  build({ data }) {
    const g = data.garmin;
    if (!g) return null;
    const cardData: SleepData = {};
    if (g.sleep_score != null) cardData.score = g.sleep_score;
    if (g.total_sleep_duration) cardData.duration_h = g.total_sleep_duration / 60;
    if (g.deep_sleep_duration != null) cardData.deep_min = Math.round(g.deep_sleep_duration);
    if (g.rem_sleep_duration != null) cardData.rem_min = Math.round(g.rem_sleep_duration);
    if (g.light_sleep_duration != null) cardData.light_min = Math.round(g.light_sleep_duration);
    if (g.awake_duration != null) cardData.awake_min = Math.round(g.awake_duration);
    return Object.keys(cardData).length > 0 ? cardData : null;
  },
  render: (d) => <SleepCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  stages: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 4 },
  stage: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  stageDot: { width: 6, height: 6, borderRadius: 3 },
});

const txt = {
  scoreNum: { fontSize: 16, fontWeight: '800', position: 'absolute', fontVariant: ['tabular-nums'] as const } as TextStyle,
  duration: { fontSize: 18, fontWeight: '800', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  stageLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  stageVal: { fontSize: 10, fontWeight: '600', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
};
