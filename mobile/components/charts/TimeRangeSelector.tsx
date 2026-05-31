import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { spacing, radii, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { TimeRange } from '../../services/trends';

const RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y'];

const RANGE_LABELS: Record<TimeRange, string> = {
  '1W': '1周',
  '1M': '1月',
  '3M': '3月',
  '6M': '6月',
  '1Y': '1年',
};

interface Props {
  selected: TimeRange;
  onChange: (range: TimeRange) => void;
}

export default function TimeRangeSelector({ selected, onChange }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.container}>
      {RANGES.map((r) => {
        const active = r === selected;
        return (
          <TouchableOpacity
            key={r}
            testID={`range-${r}`}
            style={[styles.pill, active && styles.pillActive]}
            onPress={() => onChange(r)}
            activeOpacity={0.7}
          >
            <Text style={[styles.label, active && styles.labelActive]}>
              {RANGE_LABELS[r]}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    container: {
      flexDirection: 'row',
      justifyContent: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.md,
    },
    pill: {
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.xs + 2,
      borderRadius: radii.full,
      backgroundColor: c.fill,
    },
    pillActive: {
      backgroundColor: c.brand,
    },
    label: {
      ...typography.bodySmall,
      color: c.labelSecondary,
    },
    labelActive: {
      color: '#FFFFFF',
      fontWeight: '600',
    },
  });
}
