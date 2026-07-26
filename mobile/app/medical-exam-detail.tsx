/**
 * 化验详情页 — 显示单次化验的项目 + 异常项 + vs 上次对比.
 *
 * P6 (2026-05-04): 用户上传化验后, 进列表点击单条 → 这个页能看到:
 * - 全部 items, 异常项排前
 * - 与上一次同指标对比 ("LDL 4.1 ↑ 17% 比 6 月升 0.6")
 * - AI overall_assessment + conclusions
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextStyle,
  ActivityIndicator, Modal, TextInput, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  listMedicalExams,
  compareExams,
  updateMedicalExamItem,
  type MedicalExam,
  type MedicalExamItem,
  type ExamComparison,
} from '../services/medicalExams';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { useRouteBiometricGate } from '../hooks/useRouteBiometricGate';

export default function MedicalExamDetailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const examId = Number(params.id);
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const queryClient = useQueryClient();

  const [editing, setEditing] = useState<MedicalExamItem | null>(null);
  const gate = useRouteBiometricGate('解锁查看化验报告');

  const examsQuery = useQuery({
    queryKey: ['medical-exams'],
    queryFn: () => listMedicalExams(50),
    staleTime: 60_000,
    enabled: gate.status === 'unlocked',
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

  if (gate.status !== 'unlocked') {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={8}>
            <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
          </Pressable>
          <Text style={txt.title}>化验详情</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={styles.lockWrap}>
          <Ionicons name="lock-closed" size={48} color={c.labelTertiary} />
          <Text style={[txt.assessmentBody, { textAlign: 'center', marginTop: spacing.md }]}>
            化验数据为敏感信息,需要 Face ID 解锁
          </Text>
          <Pressable
            onPress={gate.retry}
            style={[styles.unlockBtn, { backgroundColor: c.brand }]}
          >
            <Ionicons name="finger-print" size={18} color="#fff" />
            <Text style={{ color: '#fff', fontWeight: '600', fontSize: 15 }}>解锁</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

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

        {/* review #2: AI 完整解读包入口 (基因关联 + 行动 + 复查 + 找医生) */}
        <Pressable
          style={styles.explainEntry}
          onPress={() => router.push({ pathname: '/exam-explain/[id]' as any, params: { id: String(examId) } })}
        >
          <Ionicons name="sparkles" size={16} color="#fff" />
          <View style={{ flex: 1 }}>
            <Text style={styles.explainEntryTitle}>看 AI 完整解读</Text>
            <Text style={styles.explainEntrySub}>结合基因 / 历史 / 给出可执行行动</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color="#fff" />
        </Pressable>

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
            <ItemRow key={item.id} item={item} c={c} onPress={() => setEditing(item)} />
          ))}
        </View>
      </ScrollView>

      <EditItemSheet
        item={editing}
        c={c}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          queryClient.invalidateQueries({ queryKey: ['medical-exams'] });
        }}
      />
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

function ItemRow({ item, c, onPress }: { item: MedicalExamItem; c: ColorPalette; onPress?: () => void }) {
  const txt = createTxt(c);
  const isAbnormal = item.is_abnormal && item.is_abnormal !== 'normal';
  const tone = isAbnormal ? c.red : c.labelPrimary;
  const value = item.value != null ? String(item.value) : item.value_text || '—';
  const isOcr = item.source === 'ocr';
  const wasCorrected = !!item.manually_corrected_at;

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [itemStyles.row, pressed && { opacity: 0.6 }]}>
      <View style={{ flex: 1 }}>
        <View style={itemStyles.nameRow}>
          <Text style={txt.itemName}>{item.item_name}</Text>
          {isOcr && !wasCorrected ? (
            <View style={[itemStyles.pill, { backgroundColor: c.bgElevated }]}>
              <Text style={[txt.pill, { color: c.labelSecondary }]}>OCR</Text>
            </View>
          ) : null}
          {wasCorrected ? (
            <View style={[itemStyles.pill, { backgroundColor: c.brandLight }]}>
              <Text style={[txt.pill, { color: c.brand }]}>已校正</Text>
            </View>
          ) : null}
        </View>
        {item.reference_range ? (
          <Text style={txt.itemRef}>参考: {item.reference_range}</Text>
        ) : null}
        {wasCorrected && item.original_value != null && item.original_value !== item.value ? (
          <Text style={txt.itemRef}>原值: {item.original_value}{item.unit ? ` ${item.unit}` : ''}</Text>
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
      <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} style={{ marginLeft: 4 }} />
    </Pressable>
  );
}

const ABNORMAL_OPTIONS: Array<{ key: string; label: string }> = [
  { key: 'normal', label: '正常' },
  { key: 'high', label: '偏高' },
  { key: 'low', label: '偏低' },
  { key: 'abnormal', label: '异常' },
];

function EditItemSheet({
  item, c, onClose, onSaved,
}: {
  item: MedicalExamItem | null;
  c: ColorPalette;
  onClose: () => void;
  onSaved: () => void;
}) {
  const txt = createTxt(c);
  const [valueStr, setValueStr] = useState('');
  const [abnormal, setAbnormal] = useState<string>('normal');
  const [saving, setSaving] = useState(false);

  React.useEffect(() => {
    if (item) {
      setValueStr(item.value != null ? String(item.value) : '');
      setAbnormal((item.is_abnormal as string) || 'normal');
    }
  }, [item]);

  if (!item) return null;

  const onSave = async () => {
    const trimmed = valueStr.trim();
    const parsed = trimmed === '' ? null : Number(trimmed);
    if (trimmed !== '' && Number.isNaN(parsed)) {
      Alert.alert('请输入数字', `"${trimmed}" 不是合法数值`);
      return;
    }
    setSaving(true);
    try {
      await updateMedicalExamItem(item.id, {
        value: parsed,
        is_abnormal: abnormal,
      });
      onSaved();
    } catch (e: any) {
      Alert.alert('保存失败', e?.response?.data?.detail || e?.message || '请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={editStyles.backdrop}>
        <View style={[editStyles.sheet, { backgroundColor: c.bgCard }]}>
          <View style={editStyles.handle} />
          <Text style={txt.title}>校正 {item.item_name}</Text>
          {item.source === 'ocr' ? (
            <Text style={txt.itemRef}>OCR 抽取的原值: {item.original_value ?? item.value ?? '—'}{item.unit ? ` ${item.unit}` : ''}</Text>
          ) : null}

          <View style={{ gap: 6, marginTop: spacing.md }}>
            <Text style={txt.sectionTitle}>检测值{item.unit ? ` (${item.unit})` : ''}</Text>
            <TextInput
              value={valueStr}
              onChangeText={setValueStr}
              keyboardType="decimal-pad"
              placeholder="例如 4.1"
              placeholderTextColor={c.labelTertiary}
              style={[editStyles.input, { color: c.labelPrimary, borderColor: c.separator, backgroundColor: c.bgPrimary }]}
            />
          </View>

          <View style={{ gap: 6, marginTop: spacing.md }}>
            <Text style={txt.sectionTitle}>异常状态</Text>
            <View style={editStyles.chipRow}>
              {ABNORMAL_OPTIONS.map(opt => {
                const active = abnormal === opt.key;
                return (
                  <Pressable
                    key={opt.key}
                    onPress={() => setAbnormal(opt.key)}
                    style={[
                      editStyles.chip,
                      { backgroundColor: active ? c.brand : c.bgElevated },
                    ]}
                  >
                    <Text style={{ color: active ? '#fff' : c.labelPrimary, fontSize: 13, fontWeight: '500' }}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          <View style={editStyles.actions}>
            <Pressable
              onPress={onClose}
              style={[editStyles.btn, { backgroundColor: c.bgElevated }]}
              disabled={saving}
            >
              <Text style={{ color: c.labelPrimary, fontWeight: '500' }}>取消</Text>
            </Pressable>
            <Pressable
              onPress={onSave}
              style={[editStyles.btn, { backgroundColor: c.brand, opacity: saving ? 0.6 : 1 }]}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={{ color: '#fff', fontWeight: '600' }}>保存</Text>
              )}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
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
    alignItems: 'center',
  },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  pill: {
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: radii.sm,
  },
  valueWrap: { alignItems: 'flex-end', gap: 2 },
});

const editStyles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xl + spacing.md,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    gap: spacing.xs,
  },
  handle: {
    alignSelf: 'center',
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: 'rgba(127,127,127,0.4)',
    marginBottom: spacing.md,
  },
  input: {
    borderWidth: 1, borderRadius: radii.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    fontSize: 16,
  },
  chipRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs + 2,
    borderRadius: radii.full,
  },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg },
  btn: {
    flex: 1, alignItems: 'center', justifyContent: 'center',
    paddingVertical: spacing.md, borderRadius: radii.md,
  },
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
    lockWrap: {
      flex: 1, alignItems: 'center', justifyContent: 'center',
      paddingHorizontal: spacing.xl, gap: spacing.md,
    },
    unlockBtn: {
      flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
      paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
      borderRadius: radii.full, marginTop: spacing.md,
    },
    // review #2 入口
    explainEntry: {
      flexDirection: 'row', alignItems: 'center', gap: 10,
      backgroundColor: c.brand,
      borderRadius: radii.md,
      paddingHorizontal: spacing.md, paddingVertical: spacing.md,
      marginBottom: spacing.sm,
    },
    explainEntryTitle: { color: '#fff', fontSize: 15, fontWeight: '700' },
    explainEntrySub: { color: 'rgba(255,255,255,0.8)', fontSize: 12, marginTop: 2 },
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
    pill: { fontSize: 10, fontWeight: '600', letterSpacing: 0.3 } as TextStyle,
    empty: { fontSize: 14, color: c.labelSecondary } as TextStyle,
  };
}
