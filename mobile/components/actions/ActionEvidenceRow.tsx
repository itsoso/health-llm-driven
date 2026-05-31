import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface EvidenceTierMeta {
  label: string;
  color: string;
}

function tierMeta(c: ColorPalette): Record<string, EvidenceTierMeta> {
  return {
    clinical_guideline: { label: '临床指南', color: c.green },
    strong_behavioral: { label: '行为证据', color: c.teal },
    wearable_proxy: { label: '穿戴推断', color: c.blue },
    genetic_association: { label: '基因关联', color: c.purple },
    experimental: { label: '实验性', color: c.amber },
    default: { label: '一般', color: c.labelSecondary },
  };
}

interface Props {
  tier?: string;
  confidence?: string;
  note?: string;
}

export default function ActionEvidenceRow({ tier, confidence, note }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const meta = tierMeta(c);
  const m = meta[tier || 'default'] || meta.default;
  return (
    <View style={styles.row}>
      <View style={[styles.chip, { backgroundColor: m.color + '22' }]}>
        <Text style={[styles.chipText, { color: m.color }]}>{m.label}</Text>
      </View>
      {confidence ? <Text style={styles.label}>{confidence}</Text> : null}
      {note ? <Text style={styles.note}>{note}</Text> : null}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingVertical: 4,
    },
    chip: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: radii.sm,
      backgroundColor: c.bgPrimary,
    },
    chipText: { fontSize: 11, fontWeight: '600' as const },
    label: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    note: { fontSize: 12, color: c.labelSecondary, flex: 1 } as TextStyle,
  });
}
