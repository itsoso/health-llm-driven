import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { CardShell } from './CardShell';
import { colors } from '../../../constants/theme';
import type { CardSpec } from './types';

interface ScoreData {
  score: number;
  label?: string;
  sub?: string;
}

export function ScoreCardView({ score, label, sub }: ScoreData) {
  const size = 56, sw = 5;
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(score / 100, 1));
  const color = score >= 80 ? '#30D158' : score >= 60 ? '#FF9F0A' : '#FF453A';

  return (
    <CardShell icon="sparkles" iconColor="#0A8F8F" title={label || '健康评分'}>
      <View style={styles.row}>
        <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
          <Svg width={size} height={size}>
            <Defs><LinearGradient id="scg" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor="#0A8F8F" /><Stop offset="1" stopColor="#30D158" /></LinearGradient></Defs>
            <Circle cx={size / 2} cy={size / 2} r={r} stroke="#F2F2F7" strokeWidth={sw} fill="none" />
            <Circle cx={size / 2} cy={size / 2} r={r} stroke="url(#scg)" strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
          </Svg>
          <Text style={[txt.scoreNum, { color }]}>{score}</Text>
        </View>
        <View style={{ flex: 1, marginLeft: 14 }}>
          <Text style={txt.scoreLabel}>{label || '健康评分'}</Text>
          {sub && <Text style={txt.scoreSub}>{sub}</Text>}
        </View>
      </View>
    </CardShell>
  );
}

export const ScoreCardSpec: CardSpec<ScoreData> = {
  type: 'score',
  label: '健康评分',
  match({ query_lower }) {
    if (/评分|打分|健康分|分数|健康度/.test(query_lower)) return 15;
    return null;
  },
  build({ data }) {
    const s = data.score?.total_score;
    if (s == null) return null;
    const subs: string[] = [];
    if (data.score?.sleep_score) subs.push(`睡眠 ${data.score.sleep_score}`);
    if (data.score?.activity_score) subs.push(`活动 ${data.score.activity_score}`);
    if (data.score?.recovery_score) subs.push(`恢复 ${data.score.recovery_score}`);
    return { score: s, sub: subs.join(' · ') || undefined };
  },
  render: (d) => <ScoreCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
});

const txt = {
  scoreNum: { fontSize: 18, fontWeight: '800', position: 'absolute', fontVariant: ['tabular-nums'] as const } as TextStyle,
  scoreLabel: { fontSize: 14, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  scoreSub: { fontSize: 10, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
};
