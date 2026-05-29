import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { CardShell } from './CardShell';
import { useTheme } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface ScoreData {
  score: number;
  label?: string;
  sub?: string;
}

export function ScoreCardView({ score, label, sub }: ScoreData) {
  const { c } = useTheme();
  const size = 56, sw = 5;
  const r = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - Math.min(score / 100, 1));
  // 评分颜色按语义阶梯 (绿/橙/红), 不随主题切换
  const scoreColor = score >= 80 ? '#30D158' : score >= 60 ? '#FF9F0A' : '#FF453A';

  return (
    <CardShell icon="sparkles" iconColor={c.brand} title={label || '健康评分'}>
      <View style={styles.row}>
        <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
          <Svg width={size} height={size}>
            <Defs>
              <LinearGradient id="scg" x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor={c.brand} />
                <Stop offset="1" stopColor={c.green} />
              </LinearGradient>
            </Defs>
            <Circle cx={size / 2} cy={size / 2} r={r} stroke={c.fill} strokeWidth={sw} fill="none" />
            <Circle cx={size / 2} cy={size / 2} r={r} stroke="url(#scg)" strokeWidth={sw} fill="none"
              strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} />
          </Svg>
          <Text maxFontSizeMultiplier={1.3} style={[styles.scoreNum, { color: scoreColor }]}>{score}</Text>
        </View>
        <View style={{ flex: 1, marginLeft: 14 }}>
          <Text maxFontSizeMultiplier={1.3} style={[styles.scoreLabel, { color: c.labelPrimary }]}>
            {label || '健康评分'}
          </Text>
          {sub && (
            <Text maxFontSizeMultiplier={1.3} style={[styles.scoreSub, { color: c.labelTertiary }]}>
              {sub}
            </Text>
          )}
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
  scoreNum: { fontSize: 18, fontWeight: '800', position: 'absolute', fontVariant: ['tabular-nums'] as const } as TextStyle,
  scoreLabel: { fontSize: 14, fontWeight: '700' } as TextStyle,
  scoreSub: { fontSize: 10, marginTop: 2 } as TextStyle,
});
