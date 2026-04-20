import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Rect } from 'react-native-svg';
import { colors, spacing, radii } from '@/constants/theme';
import { scoreColor } from '@/constants/theme';

interface ChartItem {
  date: string;
  duration_hours: number | null;
  score: number | null;
}

interface Props {
  data: ChartItem[];
  height?: number;
}

const DAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

export default function SleepWeeklyChart({ data, height = 140 }: Props) {
  const last7 = data.slice(-7);
  const maxHours = Math.max(10, ...last7.map(d => d.duration_hours ?? 0));
  const barW = 28;
  const gap = (280 - barW * 7) / 6;
  const chartH = height - 24;

  return (
    <View style={styles.container}>
      <Svg width={280} height={height}>
        {last7.map((d, i) => {
          const h = d.duration_hours ?? 0;
          const barH = Math.max(2, (h / maxHours) * chartH);
          const x = i * (barW + gap);
          const color = d.score != null ? scoreColor(d.score) : colors.labelTertiary;
          return (
            <React.Fragment key={i}>
              <Rect x={x} y={chartH - barH} width={barW} height={barH} rx={4} fill={color} opacity={0.85} />
            </React.Fragment>
          );
        })}
      </Svg>
      <View style={styles.labelRow}>
        {last7.map((d, i) => (
          <Text key={i} style={[txt.dayLabel, { width: barW, marginRight: i < 6 ? gap : 0 }]}>
            {DAY_LABELS[new Date(d.date).getDay() === 0 ? 6 : new Date(d.date).getDay() - 1] ?? ''}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: 'center', paddingVertical: spacing.sm },
  labelRow: { flexDirection: 'row', marginTop: 4 },
});

const txt = {
  dayLabel: { fontSize: 10, color: colors.labelTertiary, textAlign: 'center' } as TextStyle,
};
