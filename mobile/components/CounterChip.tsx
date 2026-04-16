import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface CounterChipProps {
  label: string;
  value: string | number;
  target?: number;
  color?: string;
}

export default function CounterChip({
  label,
  value,
  target,
  color = '#007AFF',
}: CounterChipProps) {
  const numVal = typeof value === 'string' ? parseFloat(value) || 0 : value;
  const pct = target ? Math.min(numVal / target, 1) : 0;

  return (
    <View style={styles.chip}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, { color }]}>{value}</Text>
      {target ? (
        <View style={styles.barBg}>
          <View
            style={[styles.barFill, { width: `${pct * 100}%`, backgroundColor: color }]}
          />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    alignItems: 'center',
    flex: 1,
    paddingVertical: 8,
    paddingHorizontal: 4,
  },
  label: {
    fontSize: 10,
    color: '#8E8E93',
    fontWeight: '500',
    marginBottom: 2,
  },
  value: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  barBg: {
    height: 3,
    width: '80%',
    backgroundColor: '#E5E5EA',
    borderRadius: 2,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 2,
  },
});
