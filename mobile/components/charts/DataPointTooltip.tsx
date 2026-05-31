import React, { useMemo } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { spacing, radii, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  date: string;
  value: number;
  unit: string;
  label: string;
  color: string;
  isAbnormal?: boolean;
  x: number;
  y: number;
  chartWidth: number;
}

export default function DataPointTooltip({
  date,
  value,
  unit,
  label,
  color,
  isAbnormal,
  x,
  y,
  chartWidth,
}: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const tooltipW = 120;
  const left = Math.min(Math.max(x - tooltipW / 2, 0), chartWidth - tooltipW);
  const above = y > 60;

  return (
    <View
      testID="data-point-tooltip"
      style={[
        styles.container,
        {
          left,
          top: above ? y - 58 : y + 12,
          borderColor: color,
        },
      ]}
    >
      <Text style={styles.date}>{date}</Text>
      <Text style={[styles.value, isAbnormal && { color: c.red }]}>
        {label}: {value}
        {unit ? ` ${unit}` : ''}
      </Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    container: {
      position: 'absolute',
      width: 120,
      backgroundColor: c.bgCard,
      borderRadius: radii.sm,
      borderWidth: 1,
      padding: spacing.sm,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.12,
      shadowRadius: 6,
      elevation: 3,
      zIndex: 100,
    },
    date: {
      ...typography.caption,
      color: c.labelTertiary,
      marginBottom: 2,
    },
    value: {
      ...typography.bodySmall,
      fontWeight: '600',
      color: c.labelPrimary,
    },
  });
}
