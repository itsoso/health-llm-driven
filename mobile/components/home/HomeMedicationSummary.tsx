import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import MedicationCheckin from '../dashboard/MedicationCheckin';
import type { MedicationTodayItem } from '../../services/medications';
import { revaSpacing } from '../../constants/revaTheme';

interface Props {
  items: MedicationTodayItem[] | null | undefined;
  onChanged?: () => void;
}

interface CategorySummary {
  key: 'medication' | 'supplement';
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  items: MedicationTodayItem[];
  pending: number;
}

function targetCount(item: MedicationTodayItem): number {
  return Math.max(item.total_count ?? 1, 1);
}

function summarize(
  key: CategorySummary['key'],
  label: string,
  icon: keyof typeof Ionicons.glyphMap,
  items: MedicationTodayItem[],
): CategorySummary {
  let pending = 0;
  for (const item of items) {
    const t = targetCount(item);
    const done = Math.min(item.taken_count, t);
    if (done < t) pending += 1;
  }
  return { key, label, icon, items, pending };
}

export default function HomeMedicationSummary({ items, onChanged }: Props) {
  const all = Array.isArray(items) ? items.filter(Boolean) : [];
  if (all.length === 0) return null;

  const medication = summarize(
    'medication',
    '用药',
    'medkit',
    all.filter((item) => item.category !== 'supplement'),
  );
  const supplement = summarize(
    'supplement',
    '补剂',
    'leaf',
    all.filter((item) => item.category === 'supplement'),
  );

  const categories = [medication, supplement].filter((category) => category.items.length > 0);
  const pending = categories.filter((category) => category.pending > 0);
  if (pending.length === 0) return null;

  return (
    <View style={styles.wrap}>
      {pending.map((category) => (
        <MedicationCheckin
          key={category.key}
          title={category.label}
          icon={category.icon}
          items={category.items}
          onChanged={onChanged}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: revaSpacing.s3 },
});
