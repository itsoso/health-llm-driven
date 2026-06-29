import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import MedicationCheckin from '../dashboard/MedicationCheckin';
import type { MedicationTodayItem } from '../../services/medications';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';

interface Props {
  items: MedicationTodayItem[] | null | undefined;
  onChanged?: () => void;
}

interface CategorySummary {
  key: 'medication' | 'supplement';
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  items: MedicationTodayItem[];
  taken: number;
  target: number;
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
  let taken = 0;
  let target = 0;
  let pending = 0;
  for (const item of items) {
    const t = targetCount(item);
    const done = Math.min(item.taken_count, t);
    taken += done;
    target += t;
    if (done < t) pending += 1;
  }
  return { key, label, icon, items, taken, target, pending };
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
  const completed = categories.filter((category) => category.pending === 0);
  const pending = categories.filter((category) => category.pending > 0);

  return (
    <View style={styles.wrap}>
      {completed.length > 0 ? <CompactSummary categories={completed} allDone={pending.length === 0} /> : null}
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

function CompactSummary({
  categories,
  allDone,
}: {
  categories: CategorySummary[];
  allDone: boolean;
}) {
  return (
    <View
      style={styles.summary}
      accessibilityRole="summary"
      accessibilityLabel="今日用药补剂摘要"
    >
      <View style={styles.summaryIcon}>
        <Ionicons name="checkmark-circle" size={16} color={C.green500} />
      </View>
      <View style={styles.summaryBody}>
        <Text style={txt.summaryTitle}>用药 / 补剂</Text>
        <Text style={txt.summarySub}>{allDone ? '今日已全部完成' : '已完成项目'}</Text>
      </View>
      <View style={styles.pills}>
        {categories.map((category) => (
          <View key={category.key} style={styles.pill}>
            <Text style={txt.pillText}>
              {category.label} {category.taken}/{category.target}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: revaSpacing.s3 },
  summary: {
    minHeight: 62,
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s3,
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  summaryIcon: {
    width: 30,
    height: 30,
    borderRadius: revaRadii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  summaryBody: { flex: 1, minWidth: 0 },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end', maxWidth: '48%' },
  pill: {
    borderRadius: revaRadii.pill,
    paddingHorizontal: 8,
    paddingVertical: 4,
    backgroundColor: revaSemantic.normal.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.normal.line,
  },
});

const txt = {
  summaryTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  summarySub: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
    color: C.ink3,
  } as TextStyle,
  pillText: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 15,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
};
