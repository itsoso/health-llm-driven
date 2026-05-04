/**
 * 化验详情页 — 显示单次化验的项目 + 异常项 + vs 上次对比.
 *
 * P6 (2026-05-04): 用户上传化验后, 进列表点击单条 → 这个页能看到:
 * - 全部 items, 异常项排前
 * - 与上一次同指标对比 ("LDL 4.1 ↑ 17% 比 6 月升 0.6")
 * - AI overall_assessment + conclusions
 */
import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextStyle,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';

import {
  listMedicalExams,
  compareExams,
  type MedicalExam,
  type MedicalExamItem,
  type ExamComparison,
} from '../services/medicalExams';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';

export default function MedicalExamDetailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const examId = Number(params.id);
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const examsQuery = useQuery({
    queryKey: ['medical-exams'],
    queryFn: () => listMedicalExams(50),
    staleTime: 60_000,
  });

  const exams = examsQuery.data ?? [];
  const exam = exams.find(e => e.id === examId);
  const idx = exams.findIndex(e => e.id === examId);
  // exams 按日期倒序, idx+1 是更早的一次
  const previous = idx >= 0 && idx + 1 < exams.length ? exams[idx + 1] : null;

  const comparisons = useMemo(
    () => (exam && previous ? compareExams(exam, previous) : []),
    [exam, previous],
  );

  if (examsQuery.isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={8}>
            <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
          </Pressable>
          <Text style={txt.title}>化验详情</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="small" color={c.brand} />
        </View>
      </SafeAreaView>
    );
  }

  if (!exam) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={8}>
            <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
          </Pressable>
          <Text style={txt.title}>化验详情</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.emptyWrap}>
          <Text style={txt.empty}>记录不存在或已被删除</Text>
        </View>
      </SafeAreaView>
    );
  }

  // 异常项排前, 然后是正常项
  const sortedItems = [...(exam.items || [])].sort((a, b) => {
    const aAb = a.is_abnormal && a.is_abnormal !== 'normal' ? 1 : 0;
    const bAb = b.is_abnormal && b.is_abnormal !== 'normal' ? 1 : 0;
    return bAb - aAb;
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>{exam.exam_date}</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {exam.hospital_name ? (
          <Text style={txt.subtitle}>{exam.hospital_name}</Text>
        ) : null}

        {/* AI overall assessment */}
        {exam.overall_assessment ? (
          <View style={styles.assessmentCard}>
            <View style={styles.assessmentHeader}>
              <Ionicons name="sparkles" size={14} color={c.brand} />
              <Text style={txt.sectionTitle}>AI 解读</Text>
            </View>
            <Text style={txt.assessmentBody}>{exam.overall_assessment}</Text>
          </View>
        ) : null}

        {/* vs 上次对比 — 突出变化最大的指标 */}
        {comparisons.length > 0 && previous ? (
          <View style={styles.compareCard}>
            <View style={styles.assessmentHeader}>
              <Ionicons name="trending-up" size={14} color={c.brand} />
              <Text style={txt.sectionTitle}>
                vs 上次 ({previous.exam_date})
              </Text>
            </View>
            {comparisons.slice(0, 5).map(comp => (
              <ComparisonRow key={comp.item_name} comp={comp} c={c} />
            ))}
          </View>
        ) : null}

        {/* 全部 items */}
        <View style={styles.itemsCard}>
          <Text style={txt.sectionTitle}>检查项目 ({sortedItems.length})</Text>
          {sortedItems.map(item => (
            <ItemRow key={item.id} item={item} c={c} />
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function ComparisonRow({ comp, c }: { comp: ExamComparison; c: ColorPalette }) {
  const txt = createTxt(c);
  const positive = comp.delta_pct >= 0;
  // 升降本身没"好坏" — 看 abnormal 状态. 没变 abnormal 状态走中性, 否则 red
  const tone =
    !comp.previous_abnormal && comp.current_abnormal ? 'bad' :
    comp.previous_abnormal && !comp.current_abnormal ? 'good' :
    'neutral';
  const toneColor = tone === 'bad' ? c.red : tone === 'good' ? c.green : c.labelSecondary;
  const arrow = positive ? '↑' : '↓';
  const sign = positive ? '+' : '';

  return (
    <View style={comparisonStyles.row}>
      <View style={{ flex: 1 }}>
        <Text style={txt.compareItem}>{comp.item_name}</Text>
        <Text style={txt.compareDelta}>
          {comp.previous_value} → {comp.current_value}
          {comp.unit ? ` ${comp.unit}` : ''}
        </Text>
      </View>
      <View style={[comparisonStyles.chipTone, { backgroundColor: c.bgPrimary }]}>
        <Text style={[txt.compareDeltaPct, { color: toneColor }]}>
          {arrow} {sign}
          {comp.delta_pct.toFixed(0)}%
        </Text>
      </View>
    </View>
  );
}

function ItemRow({ item, c }: { item: MedicalExamItem; c: ColorPalette }) {
  const txt = createTxt(c);
  const isAbnormal = item.is_abnormal && item.is_abnormal !== 'normal';
  const tone = isAbnormal ? c.red : c.labelPrimary;
  const value = item.value != null ? String(item.value) : item.value_text || '—';

  return (
    <View style={itemStyles.row}>
      <View style={{ flex: 1 }}>
        <Text style={txt.itemName}>{item.item_name}</Text>
        {item.reference_range ? (
          <Text style={txt.itemRef}>参考: {item.reference_range}</Text>
        ) : null}
      </View>
      <View style={itemStyles.valueWrap}>
        <Text style={[txt.itemValue, { color: tone }]}>
          {value}
          {item.unit ? ` ${item.unit}` : ''}
        </Text>
        {isAbnormal ? (
          <Text style={[txt.itemAbnormal, { color: c.red }]}>
            {item.is_abnormal === 'high' ? '↑ 偏高' :
             item.is_abnormal === 'low' ? '↓ 偏低' : '⚠️ 异常'}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const comparisonStyles = StyleSheet.create({
  row: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  chipTone: {
    paddingHorizontal: spacing.md, paddingVertical: 4,
    borderRadius: radii.full,
  },
});

const itemStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  valueWrap: { alignItems: 'flex-end', gap: 2 },
});

function createStyles(c: ColorPalette, _isDark: boolean) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    content: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 40 },
    loadingWrap: { paddingVertical: 60, alignItems: 'center' },
    emptyWrap: { paddingVertical: 80, alignItems: 'center' },
    assessmentCard: {
      backgroundColor: c.brandLight,
      borderRadius: radii.md,
      padding: spacing.lg,
      gap: spacing.sm,
    },
    assessmentHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    compareCard: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      padding: spacing.lg,
      gap: 4,
      ...shadows.subtle,
    },
    itemsCard: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      padding: spacing.lg,
      gap: 4,
      ...shadows.subtle,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    subtitle: { fontSize: 14, color: c.labelSecondary, marginBottom: -spacing.xs } as TextStyle,
    sectionTitle: { fontSize: 13, fontWeight: '600', color: c.labelSecondary, letterSpacing: 0.3 } as TextStyle,
    assessmentBody: { fontSize: 14, lineHeight: 20, color: c.labelPrimary } as TextStyle,
    compareItem: { fontSize: 14, fontWeight: '500', color: c.labelPrimary } as TextStyle,
    compareDelta: { fontSize: 12, color: c.labelTertiary, marginTop: 1 } as TextStyle,
    compareDeltaPct: { fontSize: 13, fontWeight: '600' } as TextStyle,
    itemName: { fontSize: 14, color: c.labelPrimary } as TextStyle,
    itemRef: { fontSize: 11, color: c.labelTertiary, marginTop: 1 } as TextStyle,
    itemValue: { fontSize: 14, fontWeight: '500' } as TextStyle,
    itemAbnormal: { fontSize: 11, fontWeight: '500' } as TextStyle,
    empty: { fontSize: 14, color: c.labelSecondary } as TextStyle,
  };
}
