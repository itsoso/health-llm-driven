import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface VitalTileProps {
  label: string;
  value: string | number;
  unit?: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
}

export default function VitalTile({
  label,
  value,
  unit,
  icon,
  color,
}: VitalTileProps) {
  return (
    <View style={[styles.tile, { borderLeftColor: color }]}>
      <View style={styles.header}>
        <Ionicons name={icon} size={16} color={color} />
        <Text style={styles.label}>{label}</Text>
      </View>
      <View style={styles.valueRow}>
        <Text style={[styles.value, { color }]}>
          {value ?? '--'}
        </Text>
        {unit ? <Text style={styles.unit}>{unit}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  tile: {
    flex: 1,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 12,
    borderLeftWidth: 3,
    marginHorizontal: 4,
    marginVertical: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  label: {
    fontSize: 12,
    color: '#8E8E93',
    fontWeight: '500',
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginTop: 6,
  },
  value: {
    fontSize: 22,
    fontWeight: '700',
  },
  unit: {
    fontSize: 12,
    color: '#8E8E93',
    marginLeft: 3,
  },
});
