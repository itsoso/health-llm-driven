import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';

import MealForm from '../diet/MealForm';
import type { DailyDietSummary, DietRecord, DietRecordCreate } from '../../services/diet';
import type { DietRepository } from '../../services/dietRepository';
import type { LocalDietDraft } from '../../services/localDietDraft';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../constants/revaTheme';
import { formatDisplayNumber } from '../../utils/displayNumber';
import type { LocalFoodPhotoCandidate } from '../../modules/local-health-kernel';
import { localModelRouter } from '../../services/localModelRouter';

function today(): string {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

const MEAL_LABEL = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' } as const;

type NutritionField = 'calories' | 'protein' | 'carbs' | 'fat';

function completeDailyMetric(
  summary: DailyDietSummary | null,
  totalField: 'total_calories' | 'total_protein' | 'total_carbs' | 'total_fat',
  recordField: NutritionField,
): number | null {
  if (!summary) return null;
  if (summary.meals.length === 0) return 0;
  if (summary.meals.some((meal) => meal[recordField] === null)) return null;
  return summary[totalField];
}

function recordNutritionText(record: DietRecord): string {
  if (record.calories === null) return '营养未知';
  const parts = [`${formatDisplayNumber(record.calories)} kcal`];
  if (record.protein !== null) parts.push(`蛋白 ${formatDisplayNumber(record.protein)}g`);
  return parts.join(' · ');
}

export default function LocalDietScreen({
  repository,
  onBack,
}: {
  repository: DietRepository;
  onBack: () => void;
}) {
  const date = useMemo(today, []);
  const [summary, setSummary] = useState<DailyDietSummary | null>(null);
  const [input, setInput] = useState('');
  const [draft, setDraft] = useState<LocalDietDraft | null>(null);
  const [editingDraft, setEditingDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoCandidates, setPhotoCandidates] = useState<LocalFoodPhotoCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setSummary(await repository.getDailyDiet(date));
      setError(null);
    } catch {
      setError('本地记录读取失败，请先解锁设备后重试。');
    }
  }, [date, repository]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const generateDraft = () => {
    const text = input.trim();
    if (!text) return;
    try {
      setDraft(localModelRouter.createTextDraft(text, date).draft);
      setEditingDraft(false);
      setError(null);
    } catch {
      setError('这段文字暂时无法生成草稿，请直接填写餐食内容。');
    }
  };

  const recognizePhoto = async () => {
    if (photoBusy) return;
    setPhotoBusy(true);
    setPhotoCandidates([]);
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setError('需要你允许读取选中的照片；其他照片不会被读取。');
        return;
      }
      const selection = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsMultipleSelection: false,
        quality: 1,
      });
      if (selection.canceled || !selection.assets[0]?.uri) return;
      const { recognition: result } = await localModelRouter.recognizePhoto(selection.assets[0].uri);
      setPhotoCandidates(result.decision === 'candidate' ? result.candidates : []);
      setError(result.decision === 'candidate'
        ? null
        : result.decision === 'non_food'
          ? '这张照片看起来不是食物。'
          : '本地模型没有给出可用候选，请用文字记录。');
    } catch {
      setError('本地图片识别没有完成，照片不会上传。');
    } finally {
      setPhotoBusy(false);
    }
  };

  const choosePhotoCandidate = (candidate: LocalFoodPhotoCandidate) => {
    setInput(candidate.displayName);
    setPhotoCandidates([]);
    setDraft(null);
    setEditingDraft(false);
    setError(null);
  };

  const confirmDraft = async () => {
    if (!draft || busy) return;
    setBusy(true);
    try {
      await repository.createDietRecord({
        ...draft.record,
        idempotency_key: draft.record.idempotency_key
          ?? `local-diet-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      });
      setDraft(null);
      setInput('');
      setEditingDraft(false);
      await reload();
    } catch {
      setError('没有保存成功；草稿仍保留在本页，可以再次确认。');
    } finally {
      setBusy(false);
    }
  };

  const applyDraftRevision = (record: DietRecordCreate) => {
    if (!draft) return;
    setDraft({
      ...draft,
      mealType: record.meal_type,
      nutritionComplete: [record.calories, record.protein, record.carbs, record.fat]
        .every((value) => typeof value === 'number' && Number.isFinite(value)),
      record: { ...draft.record, ...record, source: 'local_user_confirmed' },
    });
    setEditingDraft(false);
  };

  const requestDelete = (record: DietRecord) => {
    Alert.alert('删除本地饮食记录', `确定删除“${record.food_items}”吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => void repository.deleteDietRecord(record.id).then(reload).catch(() => {
          setError('删除没有完成，请稍后重试。');
        }),
      },
    ]);
  };

  const meals = summary?.meals ?? [];
  return (
    <View style={styles.safe}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={styles.headerButton} accessibilityLabel="返回本地首页">
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </Pressable>
        <Text style={styles.headerTitle}>本地饮食</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.privacyStrip}>
          <Ionicons name="shield-checkmark" size={17} color={C.green600} />
          <Text style={styles.privacyText}>全程写入本机加密保险库，不需要账号或网络</Text>
        </View>

        <View style={styles.summaryCard}>
          <Metric label="热量" value={completeDailyMetric(summary, 'total_calories', 'calories')} unit="kcal" />
          <Metric label="蛋白质" value={completeDailyMetric(summary, 'total_protein', 'protein')} unit="g" />
          <Metric label="碳水" value={completeDailyMetric(summary, 'total_carbs', 'carbs')} unit="g" />
          <Metric label="脂肪" value={completeDailyMetric(summary, 'total_fat', 'fat')} unit="g" />
        </View>

        <View style={styles.captureCard}>
          <Text style={styles.sectionTitle}>记录这一餐</Text>
          <Text style={styles.sectionHint}>例如：午饭半碗米饭两个鸡蛋</Text>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="输入吃了什么和大致份量"
            placeholderTextColor={C.ink3}
            multiline
            maxLength={500}
            style={styles.input}
          />
          <Pressable
            onPress={() => void recognizePhoto()}
            disabled={photoBusy || busy}
            style={({ pressed }) => [styles.photoButton, pressed && styles.pressed]}
            accessibilityRole="button"
          >
            {photoBusy
              ? <ActivityIndicator color={C.green600} />
              : <Ionicons name="image-outline" size={18} color={C.green600} />}
            <Text style={styles.photoButtonText}>从照片识别</Text>
          </Pressable>
          <Pressable
            onPress={generateDraft}
            disabled={!input.trim() || busy}
            style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
            accessibilityRole="button"
          >
            <Text style={styles.primaryButtonText}>生成本地草稿</Text>
          </Pressable>
        </View>

        {photoCandidates.length ? (
          <View style={styles.candidateCard}>
            <Text style={styles.sectionTitle}>可能是什么</Text>
            <Text style={styles.warningText}>只给候选，不会估算份量或自动保存</Text>
            <View style={styles.candidateList}>
              {photoCandidates.map((candidate) => (
                <Pressable
                  key={candidate.canonicalFoodId}
                  onPress={() => choosePhotoCandidate(candidate)}
                  style={styles.candidateButton}
                >
                  <Text style={styles.candidateText}>{candidate.displayName}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}

        {draft && !editingDraft ? (
          <View style={styles.draftCard}>
            <View style={styles.draftHeader}>
              <Text style={styles.sectionTitle}>待你确认</Text>
              <Text style={styles.mealChip}>{MEAL_LABEL[draft.record.meal_type]}</Text>
            </View>
            <Text style={styles.draftFood}>{draft.record.food_items}</Text>
            {draft.items.map((item, index) => (
              <View key={`${item.raw}-${index}`} style={styles.itemRow}>
                <Text style={styles.itemName}>{item.canonicalName ?? item.name}</Text>
                <Text style={item.matchStatus === 'matched' ? styles.itemValue : styles.unknownText}>
                  {item.matchStatus === 'matched'
                    ? `${formatDisplayNumber(item.grams ?? 0)}g`
                    : '营养未知'}
                </Text>
              </View>
            ))}
            <Text style={draft.nutritionComplete ? styles.sourceText : styles.warningText}>
              {draft.nutritionComplete
                ? '营养来自本地 USDA 表；估计份量仍需你核对。'
                : '有食物或份量无法匹配，营养保持未知，不会按 0 计算。'}
            </Text>
            <View style={styles.actionRow}>
              <Pressable style={styles.secondaryButton} onPress={() => setEditingDraft(true)}>
                <Text style={styles.secondaryButtonText}>修改</Text>
              </Pressable>
              <Pressable style={styles.primaryButtonSmall} onPress={() => void confirmDraft()} disabled={busy}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryButtonText}>确认记录</Text>}
              </Pressable>
            </View>
          </View>
        ) : null}

        {draft && editingDraft ? (
          <MealForm
            date={date}
            initialMealType={draft.record.meal_type}
            initialDescription={draft.record.food_items}
            initialCalories={draft.record.calories}
            initialProtein={draft.record.protein}
            initialCarbs={draft.record.carbs}
            initialFat={draft.record.fat}
            assistiveHint="本地估算仅作草稿；请修正食物、份量或营养后再确认。"
            onSubmit={applyDraftRevision}
            onCancel={() => setEditingDraft(false)}
          />
        ) : null}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.recordsHeader}>
          <Text style={styles.sectionTitle}>今天的记录</Text>
          <Text style={styles.sectionHint}>{meals.length} 餐</Text>
        </View>
        {summary === null && !error ? <ActivityIndicator color={C.green500} /> : null}
        {meals.map((record) => (
          <View key={record.id} style={styles.recordCard}>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.recordMeal}>{MEAL_LABEL[record.meal_type]}</Text>
              <Text style={styles.recordFood}>{record.food_items}</Text>
              <Text style={styles.recordNutrition}>{recordNutritionText(record)}</Text>
            </View>
            <Pressable onPress={() => requestDelete(record)} accessibilityLabel={`删除${record.food_items}`}>
              <Ionicons name="trash-outline" size={20} color={revaSemantic.risk.fg} />
            </Pressable>
          </View>
        ))}
        {!meals.length && summary ? <Text style={styles.empty}>今天还没有记录</Text> : null}
      </ScrollView>
    </View>
  );
}

function Metric({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value === null ? '—' : formatDisplayNumber(value)}</Text>
      <Text style={styles.metricUnit}>{unit}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { height: 52, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { color: C.ink1, fontSize: 18, fontWeight: '700', fontFamily: revaFonts.sans },
  content: { padding: revaSpacing.s5, paddingBottom: 60, gap: revaSpacing.s4 },
  privacyStrip: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: revaRadii.md, backgroundColor: C.green50 },
  privacyText: { flex: 1, color: C.green700, fontSize: 12, lineHeight: 17, fontWeight: '600' },
  summaryCard: { flexDirection: 'row', backgroundColor: C.surface, borderRadius: revaRadii.lg, paddingVertical: 15, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  metric: { flex: 1, alignItems: 'center', gap: 2 },
  metricValue: { color: C.ink1, fontSize: 18, fontWeight: '700', fontFamily: revaFonts.mono },
  metricUnit: { color: C.ink3, fontSize: 10, fontFamily: revaFonts.mono },
  metricLabel: { color: C.ink2, fontSize: 11 },
  captureCard: { backgroundColor: C.surface, borderRadius: revaRadii.lg, padding: 16, gap: 10, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  sectionTitle: { color: C.ink1, fontSize: 17, fontWeight: '700' },
  sectionHint: { color: C.ink3, fontSize: 12 },
  input: { minHeight: 72, borderRadius: revaRadii.md, backgroundColor: C.paper2, padding: 12, color: C.ink1, fontSize: 15, lineHeight: 21, textAlignVertical: 'top' },
  primaryButton: { minHeight: 46, borderRadius: revaRadii.md, backgroundColor: C.green500, alignItems: 'center', justifyContent: 'center' },
  photoButton: { minHeight: 44, borderRadius: revaRadii.md, backgroundColor: C.green50, flexDirection: 'row', gap: 7, alignItems: 'center', justifyContent: 'center' },
  photoButtonText: { color: C.green700, fontSize: 14, fontWeight: '700' },
  primaryButtonSmall: { flex: 1, minHeight: 44, borderRadius: revaRadii.md, backgroundColor: C.green500, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  pressed: { opacity: 0.75 },
  draftCard: { backgroundColor: C.surface, borderRadius: revaRadii.lg, padding: 16, gap: 11, borderWidth: 1, borderColor: C.green100 },
  draftHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  mealChip: { color: C.green700, backgroundColor: C.green50, paddingHorizontal: 10, paddingVertical: 4, borderRadius: revaRadii.pill, overflow: 'hidden', fontSize: 12, fontWeight: '700' },
  draftFood: { color: C.ink1, fontSize: 16, lineHeight: 23, fontWeight: '600' },
  itemRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  itemName: { color: C.ink2, fontSize: 13 },
  itemValue: { color: C.green600, fontSize: 13, fontFamily: revaFonts.mono },
  unknownText: { color: revaSemantic.caution.fg, fontSize: 13 },
  sourceText: { color: C.ink3, fontSize: 12, lineHeight: 17 },
  warningText: { color: revaSemantic.caution.fg, fontSize: 12, lineHeight: 17 },
  candidateCard: { backgroundColor: C.surface, borderRadius: revaRadii.lg, padding: 16, gap: 10, borderWidth: 1, borderColor: C.green100 },
  candidateList: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  candidateButton: { backgroundColor: C.green50, borderRadius: revaRadii.pill, paddingHorizontal: 14, paddingVertical: 9 },
  candidateText: { color: C.green700, fontSize: 14, fontWeight: '700' },
  actionRow: { flexDirection: 'row', gap: 10 },
  secondaryButton: { flex: 1, minHeight: 44, borderRadius: revaRadii.md, backgroundColor: C.paper2, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: C.ink2, fontSize: 15, fontWeight: '600' },
  error: { color: revaSemantic.risk.fg, fontSize: 13, lineHeight: 18 },
  recordsHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  recordCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderRadius: revaRadii.md, padding: 14, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  recordMeal: { color: C.green600, fontSize: 11, fontWeight: '700' },
  recordFood: { color: C.ink1, fontSize: 15, lineHeight: 20 },
  recordNutrition: { color: C.ink3, fontSize: 12 },
  empty: { color: C.ink3, fontSize: 14, textAlign: 'center', paddingVertical: 24 },
});
