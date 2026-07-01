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
  const pendingItems: MedicationTodayItem[] = [];
  for (const item of items) {
    const t = targetCount(item);
    const done = Math.min(item.taken_count, t);
    if (done < t) pendingItems.push(item);
  }
  return { key, label, icon, items: pendingItems };
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
  if (categories.length === 0) return null;

  return (
    <View style={styles.wrap}>
      {categories.map((category) => (
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
