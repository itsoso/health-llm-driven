import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { colors, spacing, radii, shadows } from '@/constants/theme';

interface Dimension {
  name: string;
  score: number;
  color: string;
}

interface Props {
  totalScore: number;
  dimensions?: Dimension[];
}

const defaultDimensions: Dimension[] = [
  { name: '运动', score: 0, color: '#FF6723' },
  { name: '睡眠', score: 0, color: '#BF5AF2' },
  { name: '体征', score: 0, color: '#FF375F' },
  { name: '体重', score: 0, color: '#0A8F8F' },
];

function sc(score: number): string {
  if (score >= 80) return '#30D158';
  if (score >= 60) return '#FF9F0A';
  return '#FF453A';
}

function grade(score: number): string {
  if (score >= 90) return '优秀';
  if (score >= 80) return '良好';
  if (score >= 60) return '一般';
  if (score >= 40) return '较差';
  return '需关注';
}

export default function HealthScoreHero({ totalScore, dimensions = defaultDimensions }: Props) {
  const size = 160;
  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(totalScore / 100, 1);
  const dashOffset = circumference * (1 - progress);

  // Mini arcs for dimensions
  const miniSize = 36;
  const miniStroke = 3;
  const miniR = (miniSize - miniStroke) / 2;
  const miniC = 2 * Math.PI * miniR;

  return (
    <View style={styles.card}>
      <View style={styles.layout}>
        {/* Score Ring */}
        <View style={styles.ringWrap}>
          <Svg width={size} height={size}>
            <Defs>
              <LinearGradient id="heroGrad" x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor="#0A8F8F" />
                <Stop offset="1" stopColor="#30D158" />
              </LinearGradient>
            </Defs>
            <Circle cx={size / 2} cy={size / 2} r={radius}
              stroke="#F2F2F7" strokeWidth={strokeWidth} fill="none" />
            <Circle cx={size / 2} cy={size / 2} r={radius}
              stroke="url(#heroGrad)" strokeWidth={strokeWidth} fill="none"
              strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={dashOffset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`} />
          </Svg>
          <View style={styles.ringCenter}>
            <Text style={[txt.score, { color: sc(totalScore) }]}>{totalScore}</Text>
            <Text style={txt.grade}>{grade(totalScore)}</Text>
          </View>
        </View>

        {/* Dimensions */}
        <View style={styles.dimList}>
          {dimensions.map((d) => (
            <View key={d.name} style={styles.dimItem}>
              <Svg width={miniSize} height={miniSize}>
                <Circle cx={miniSize / 2} cy={miniSize / 2} r={miniR}
                  stroke="#F2F2F7" strokeWidth={miniStroke} fill="none" />
                <Circle cx={miniSize / 2} cy={miniSize / 2} r={miniR}
                  stroke={d.color} strokeWidth={miniStroke} fill="none"
                  strokeLinecap="round"
                  strokeDasharray={miniC}
                  strokeDashoffset={miniC * (1 - Math.min(d.score / 100, 1))}
                  transform={`rotate(-90 ${miniSize / 2} ${miniSize / 2})`} />
              </Svg>
              <View style={styles.dimText}>
                <Text style={txt.dimName}>{d.name}</Text>
                <Text style={[txt.dimScore, { color: sc(d.score) }]}>{d.score}</Text>
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.xxl,
    padding: spacing.xl,
    marginBottom: spacing.lg,
    ...shadows.medium,
  },
  layout: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  ringWrap: {
    width: 160, height: 160,
    alignItems: 'center', justifyContent: 'center',
  },
  ringCenter: {
    position: 'absolute', alignItems: 'center',
  },
  dimList: {
    flex: 1,
    marginLeft: spacing.lg,
    gap: 6,
  },
  dimItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dimText: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    justifyContent: 'space-between',
  },
});

const txt = {
  score: { fontSize: 52, fontWeight: '800', letterSpacing: -2, fontVariant: ['tabular-nums'] as const } as TextStyle,
  grade: { fontSize: 12, fontWeight: '600', color: colors.labelSecondary, marginTop: -6 } as TextStyle,
  dimName: { fontSize: 14, color: colors.labelSecondary } as TextStyle,
  dimScore: { fontSize: 18, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
};
