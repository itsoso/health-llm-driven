import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardRenderOptions, CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';
import { updateDietRecord, type DietRecordCreate, type MealType } from '../../../services/diet';

interface RecordQualityData {
  domain?: unknown;
  title?: unknown;
  summary?: unknown;
  metrics?: unknown;
  progress?: unknown;
  primary_judgement?: unknown;
  personal_cautions?: unknown;
  next_action?: unknown;
  expanded_sections?: unknown;
  next_meal_detail?: unknown;
  adjust_record?: unknown;
  adjust_saved?: unknown;
  boundary?: unknown;
}

export interface MetricItem {
  label: string;
  value: string;
}

interface RecordQualityViewProps extends RecordQualityData {
  onCardDataChange?: (data: RecordQualityData) => void;
}

const ADJUST_ACCENT = '#C97A2E';

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function textList(value: unknown, limit = 2): string[] {
  const items = Array.isArray(value) ? value : value == null ? [] : [value];
  return items
    .map((item) => text(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, limit);
}

function metricList(value: unknown): MetricItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const raw = item as Record<string, unknown>;
      const label = text(raw.label);
      const metricValue = text(raw.value);
      return label && metricValue ? { label, value: metricValue } : null;
    })
    .filter((item): item is MetricItem => Boolean(item))
    .slice(0, 5);
}

function progressValue(progress: unknown, key: string): string | undefined {
  if (!progress || typeof progress !== 'object') return undefined;
  return text((progress as Record<string, unknown>)[key]);
}

function hasExpandedSection(value: unknown, section: string): boolean {
  return Array.isArray(value) && value.some((item) => text(item) === section);
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return undefined;
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function editNumber(value: unknown): string {
  const parsed = numberValue(value);
  return parsed == null ? '' : String(Math.round(parsed * 10) / 10);
}

/** 非负数字文本 → 保留一位小数; 空/负/非数字 → undefined (不写该字段) */
function sanitizeNumberText(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 10) / 10 : undefined;
}

function mealTypeValue(value: unknown): MealType {
  const raw = text(value);
  return raw && raw in MEAL_LABELS ? (raw as MealType) : 'snack';
}

function integerRecordId(value: unknown): number | undefined {
  const parsed = numberValue(value);
  return parsed != null && Number.isInteger(parsed) ? parsed : undefined;
}

function domainMeta(domain?: unknown): { icon: string; fg: string; bg: string; badge: string } {
  if (text(domain) === 'exercise') {
    return { icon: 'fitness-outline', fg: '#C2487A', bg: '#F7E4EC', badge: '运动' };
  }
  return { icon: 'restaurant-outline', fg: '#C97A2E', bg: '#F6E9DA', badge: '饮食' };
}

export function RecordQualityCardView(props: RecordQualityViewProps) {
  const { onCardDataChange, ...data } = props;
  const meta = domainMeta(data.domain);
  const title = text(data.title) || '已记录';
  const summary = text(data.summary);
  const metrics = metricList(data.metrics);
  const proteinTotal = progressValue(data.progress, 'protein_total_g');
  const proteinTarget = progressValue(data.progress, 'protein_target_g');
  const remainingProtein = progressValue(data.progress, 'remaining_protein_g');
  const caloriesTotal = progressValue(data.progress, 'calories_total');
  const mealsCount = progressValue(data.progress, 'meals_count');
  const hasProgress = Boolean(proteinTotal && proteinTarget);
  // 蛋白进度条填充比(截图目标):total/target 折算 0–100%,越界钳住;非数值不画条。
  const proteinPct = (() => {
    const t = parseFloat(String(proteinTotal ?? ''));
    const g = parseFloat(String(proteinTarget ?? ''));
    if (!isFinite(t) || !isFinite(g) || g <= 0) return null;
    return Math.max(0, Math.min(100, (t / g) * 100));
  })();
  const judgement = text(data.primary_judgement);
  const cautions = textList(data.personal_cautions);
  const nextAction = text(data.next_action);
  const showDietShareStrip = text(data.domain) !== 'exercise' && Boolean(caloriesTotal || hasProgress || nextAction);
  const nextMealDetail = objectValue(data.next_meal_detail);
  const showNextMealDetail = Boolean(hasExpandedSection(data.expanded_sections, 'next_meal') && nextMealDetail);
  const adjustRecord = objectValue(data.adjust_record);
  const adjustRecordId = adjustRecord ? integerRecordId(adjustRecord.record_id) : undefined;
  const showAdjustEditor = Boolean(
    hasExpandedSection(data.expanded_sections, 'adjust_record') && adjustRecord && adjustRecordId != null,
  );
  const savedMarker = data.adjust_saved === true && !showAdjustEditor;
  const boundary = text(data.boundary) || '健康管理建议，不替代医生诊断、处方或治疗。';

  return (
    <CardShell
      icon={meta.icon}
      iconColor={meta.fg}
      title={title}
      badge={meta.badge}
      badgeColor={meta.fg}
      bg={meta.bg}
    >
      {summary ? (
        <Text maxFontSizeMultiplier={1.2} style={styles.summary} numberOfLines={2}>
          {summary}
        </Text>
      ) : null}

      {metrics.length > 0 ? (
        <View style={styles.metricRow}>
          {metrics.map((item) => (
            <View key={`${item.label}-${item.value}`} style={styles.metricPill}>
              <Text maxFontSizeMultiplier={1.1} style={styles.metricLabel}>
                {item.label}
              </Text>
              <Text maxFontSizeMultiplier={1.1} style={styles.metricValue}>
                {item.value}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {hasProgress ? (
        <View style={styles.progressBox}>
          <View style={styles.progressLine}>
            <Text maxFontSizeMultiplier={1.1} style={styles.progressLabel}>
              今日蛋白
            </Text>
            <Text maxFontSizeMultiplier={1.1} style={styles.progressValue}>
              {proteinTotal}/{proteinTarget}g
            </Text>
          </View>
          {proteinPct != null ? (
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${proteinPct}%` }]} />
            </View>
          ) : null}
          <Text maxFontSizeMultiplier={1.1} style={styles.progressHint}>
            {[
              caloriesTotal ? `已记 ${caloriesTotal} kcal` : null,
              mealsCount ? `${mealsCount} 餐` : null,
              remainingProtein ? `还差约 ${remainingProtein}g 蛋白` : null,
            ].filter(Boolean).join(' · ')}
          </Text>
        </View>
      ) : null}

      {judgement ? (
        <Text maxFontSizeMultiplier={1.25} style={styles.judgement}>
          {judgement}
        </Text>
      ) : null}

      {cautions.length > 0 ? (
        <View style={styles.cautionList}>
          {cautions.map((item, index) => (
            <View key={`${item}-${index}`} style={styles.cautionItem}>
              <Ionicons name="shield-checkmark-outline" size={12} color={revaSemantic.caution.fg} />
              <Text maxFontSizeMultiplier={1.2} style={styles.cautionText}>
                {item}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {nextAction ? (
        <View style={styles.nextAction}>
          <Ionicons name="arrow-forward-circle-outline" size={13} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={styles.nextActionText}>
            {nextAction}
          </Text>
        </View>
      ) : null}

      {showDietShareStrip ? (
        <View style={styles.shareStrip}>
          <View style={styles.shareStripHeader}>
            <Text maxFontSizeMultiplier={1.1} style={styles.shareStripEyebrow}>
              可截图分享
            </Text>
            <Text maxFontSizeMultiplier={1.1} style={styles.shareStripTag}>
              #饮食记录 #小巴
            </Text>
          </View>
          <View style={styles.shareMetricRow}>
            {caloriesTotal ? (
              <View style={styles.shareMetric}>
                <Text maxFontSizeMultiplier={1.05} style={styles.shareMetricLabel}>今日摄入</Text>
                <Text maxFontSizeMultiplier={1.1} style={styles.shareMetricValue}>
                  {caloriesTotal} kcal
                </Text>
              </View>
            ) : null}
            {hasProgress ? (
              <View style={styles.shareMetric}>
                <Text maxFontSizeMultiplier={1.05} style={styles.shareMetricLabel}>蛋白进度</Text>
                <Text maxFontSizeMultiplier={1.1} style={styles.shareMetricValue}>
                  {proteinTotal}/{proteinTarget}g
                </Text>
              </View>
            ) : null}
          </View>
          {nextAction ? (
            <View style={styles.shareNextRow}>
              <Text maxFontSizeMultiplier={1.05} style={styles.shareNextLabel}>下一餐</Text>
              <Text maxFontSizeMultiplier={1.12} style={styles.shareNextText}>
                {nextAction}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}

      {showAdjustEditor && adjustRecord && adjustRecordId != null ? (
        <DietRecordAdjustEditor
          recordId={adjustRecordId}
          seed={adjustRecord}
          onSaved={(applied) => {
            if (!onCardDataChange) return;
            const remainingSections = (Array.isArray(data.expanded_sections) ? data.expanded_sections : [])
              .map((item) => text(item))
              .filter((item): item is string => Boolean(item) && item !== 'adjust_record');
            onCardDataChange({
              ...data,
              ...applied.cardFace,
              adjust_record: applied.adjustRecord,
              expanded_sections: remainingSections,
              adjust_saved: true,
            });
          }}
        />
      ) : null}

      {savedMarker ? (
        <View style={styles.savedRow}>
          <Ionicons name="checkmark-circle" size={13} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={styles.savedText}>已更新</Text>
        </View>
      ) : null}

      {showNextMealDetail && nextMealDetail ? (
        <View style={styles.nextMealPanel}>
          <Text maxFontSizeMultiplier={1.15} style={styles.nextMealTitle}>
            {text(nextMealDetail.title) || '下一餐建议'}
          </Text>
          {text(nextMealDetail.context) ? (
            <Text maxFontSizeMultiplier={1.15} style={styles.nextMealContext}>
              {text(nextMealDetail.context)}
            </Text>
          ) : null}
          {text(nextMealDetail.summary) ? (
            <Text maxFontSizeMultiplier={1.18} style={styles.nextMealSummary}>
              {text(nextMealDetail.summary)}
            </Text>
          ) : null}
          {textList(nextMealDetail.options, 4).length > 0 ? (
            <View style={styles.nextMealList}>
              {textList(nextMealDetail.options, 4).map((item, index) => (
                <View key={`${item}-${index}`} style={styles.nextMealListItem}>
                  <Text maxFontSizeMultiplier={1.1} style={styles.nextMealIndex}>
                    {index + 1}
                  </Text>
                  <Text maxFontSizeMultiplier={1.18} style={styles.nextMealListText}>
                    {item}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
          {textList(nextMealDetail.rationale, 4).length > 0 ? (
            <View style={styles.rationaleBox}>
              {textList(nextMealDetail.rationale, 4).map((item, index) => (
                <View key={`${item}-${index}`} style={styles.rationaleItem}>
                  <Ionicons name="sparkles-outline" size={11} color={C.green600} />
                  <Text maxFontSizeMultiplier={1.15} style={styles.rationaleText}>
                    {item}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
          {text(nextMealDetail.continue_prompt) ? (
            <Text maxFontSizeMultiplier={1.15} style={styles.continuePrompt}>
              {text(nextMealDetail.continue_prompt)}
            </Text>
          ) : null}
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        {boundary}
      </Text>
    </CardShell>
  );
}

export interface DietAdjustApplied {
  /** 更新后卡面的 summary + metrics(就地刷新用) */
  cardFace: { summary: string; metrics: MetricItem[] };
  /** 更新后的 adjust_record seed(下次再展开时以最新值填充) */
  adjustRecord: Record<string, unknown>;
}

/** 聊天内饮食记录调整器 — 就地编辑并直接 updateDietRecord, 不离开聊天 */
export function DietRecordAdjustEditor({
  recordId,
  seed,
  onSaved,
}: {
  recordId: number;
  seed: Record<string, unknown>;
  onSaved: (applied: DietAdjustApplied) => void;
}) {
  const [mealType, setMealType] = React.useState<MealType>(() => mealTypeValue(seed.meal_type));
  const [food, setFood] = React.useState(() => text(seed.food_items) || '');
  const [calories, setCalories] = React.useState(() => editNumber(seed.calories));
  const [protein, setProtein] = React.useState(() => editNumber(seed.protein));
  const [carbs, setCarbs] = React.useState(() => editNumber(seed.carbs));
  const [fat, setFat] = React.useState(() => editNumber(seed.fat));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);

  const buildPatch = React.useCallback((): Partial<DietRecordCreate> => {
    // food_items + meal_type 始终随保存写回; 数字仅在有效值时带上(空/负 → 不覆盖后端值)
    const patch: Partial<DietRecordCreate> = { meal_type: mealType, food_items: food.trim() };
    const cal = sanitizeNumberText(calories);
    const pro = sanitizeNumberText(protein);
    const car = sanitizeNumberText(carbs);
    const fatValue = sanitizeNumberText(fat);
    if (cal != null) patch.calories = cal;
    if (pro != null) patch.protein = pro;
    if (car != null) patch.carbs = car;
    if (fatValue != null) patch.fat = fatValue;
    return patch;
  }, [mealType, food, calories, protein, carbs, fat]);

  const handleSave = React.useCallback(async () => {
    if (saving) return; // action-lock: 防双击
    setSaving(true);
    setError(false);
    const patch = buildPatch();
    try {
      const updated = await updateDietRecord(recordId, patch);
      const savedMealType = (updated.meal_type as MealType) || mealType;
      const savedFood = updated.food_items || food.trim();
      const summary = buildSummary(savedMealType, updated.calories, updated.protein, updated.carbs, updated.fat);
      const metrics = buildMetrics(updated.calories, updated.protein, updated.carbs, updated.fat);
      const adjustRecord: Record<string, unknown> = { record_id: recordId, meal_type: savedMealType, food_items: savedFood };
      if (updated.calories != null) adjustRecord.calories = updated.calories;
      if (updated.protein != null) adjustRecord.protein = updated.protein;
      if (updated.carbs != null) adjustRecord.carbs = updated.carbs;
      if (updated.fat != null) adjustRecord.fat = updated.fat;
      setCollapsed(true);
      onSaved({ cardFace: { summary, metrics }, adjustRecord });
    } catch {
      setError(true);
      setSaving(false); // 失败保留输入, 允许重试
    }
  }, [saving, buildPatch, recordId, mealType, food, onSaved]);

  if (collapsed) return null;

  return (
    <View
      testID="diet-adjust-inline-editor"
      style={styles.adjustPanel}
      onTouchStart={(event) => event.stopPropagation()}
    >
      <Text maxFontSizeMultiplier={1.15} style={styles.adjustHint}>就地修正这条记录，保存后直接更新</Text>
      <View style={styles.mealTypeRow}>
        {(Object.keys(MEAL_LABELS) as MealType[]).map((key) => (
          <Pressable
            key={key}
            onPress={() => setMealType(key)}
            disabled={saving}
            accessibilityRole="button"
            accessibilityLabel={`餐次 ${MEAL_LABELS[key]}`}
            accessibilityState={{ selected: mealType === key }}
            style={[styles.mealChip, mealType === key && styles.mealChipActive]}
          >
            <Text style={[styles.mealChipText, mealType === key && styles.mealChipTextActive]}>
              {MEAL_LABELS[key]}
            </Text>
          </Pressable>
        ))}
      </View>
      <TextInput
        accessibilityLabel="食物描述"
        value={food}
        onChangeText={setFood}
        editable={!saving}
        placeholder="食物描述"
        placeholderTextColor={C.ink4}
        multiline
        style={styles.foodInput}
      />
      <View style={styles.macroGrid}>
        <AdjustNumberInput label="热量" unit="kcal" value={calories} onChangeText={setCalories} editable={!saving} />
        <AdjustNumberInput label="蛋白" unit="g" value={protein} onChangeText={setProtein} editable={!saving} />
        <AdjustNumberInput label="碳水" unit="g" value={carbs} onChangeText={setCarbs} editable={!saving} />
        <AdjustNumberInput label="脂肪" unit="g" value={fat} onChangeText={setFat} editable={!saving} />
      </View>
      {error ? (
        <Text maxFontSizeMultiplier={1.15} style={styles.adjustError}>保存失败，请重试</Text>
      ) : null}
      <View style={styles.adjustActionRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="取消修正"
          disabled={saving}
          onPress={() => setCollapsed(true)}
          style={({ pressed }) => [styles.cancelButton, saving && styles.buttonDisabled, pressed && !saving && { opacity: 0.86 }]}
        >
          <Text style={styles.cancelButtonText}>取消</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="保存修正"
          accessibilityState={{ disabled: saving, busy: saving }}
          disabled={saving}
          onPress={handleSave}
          style={({ pressed }) => [styles.saveButton, saving && styles.saveButtonBusy, pressed && !saving && { opacity: 0.86 }]}
        >
          {saving ? <ActivityIndicator size="small" color="#fff" /> : (
            <Ionicons name="checkmark-circle" size={14} color="#fff" />
          )}
          <Text style={styles.saveButtonText}>{saving ? '保存中' : '保存修正'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function AdjustNumberInput({
  label,
  unit,
  value,
  onChangeText,
  editable,
}: {
  label: string;
  unit: string;
  value: string;
  onChangeText: (value: string) => void;
  editable: boolean;
}) {
  return (
    <View style={styles.macroCell}>
      <Text style={styles.macroCellLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        editable={editable}
        keyboardType="decimal-pad"
        placeholder="0"
        placeholderTextColor={C.ink4}
        style={styles.macroCellInput}
      />
      <Text style={styles.macroCellUnit}>{unit}</Text>
    </View>
  );
}

function buildSummary(
  mealType: MealType,
  calories: number | null,
  protein: number | null,
  carbs: number | null,
  fat: number | null,
): string {
  const parts = [MEAL_LABELS[mealType] || '餐食'];
  if (calories != null) parts.push(`${Math.round(calories)} kcal`);
  if (protein != null) parts.push(`蛋白 ${Math.round(protein)}g`);
  if (carbs != null) parts.push(`碳水 ${Math.round(carbs)}g`);
  if (fat != null) parts.push(`脂肪 ${Math.round(fat)}g`);
  return parts.join(' · ');
}

function buildMetrics(
  calories: number | null,
  protein: number | null,
  carbs: number | null,
  fat: number | null,
): MetricItem[] {
  return [
    calories != null ? { label: '热量', value: `${Math.round(calories)}kcal` } : null,
    protein != null ? { label: '蛋白', value: `${Math.round(protein)}g` } : null,
    carbs != null ? { label: '碳水', value: `${Math.round(carbs)}g` } : null,
    fat != null ? { label: '脂肪', value: `${Math.round(fat)}g` } : null,
  ].filter((item): item is MetricItem => item != null);
}

export const RecordQualityCardSpec: CardSpec<RecordQualityData> = {
  type: 'record_quality',
  label: '记录后建议',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data, options?: CardRenderOptions) => (
    <RecordQualityCardView {...data} onCardDataChange={options?.onCardDataChange} />
  ),
};

const styles = StyleSheet.create({
  summary: {
    fontFamily: revaFonts.mono,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 17,
  } as TextStyle,
  judgement: {
    marginTop: 8,
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 20,
  } as TextStyle,
  // 等宽临床网格(截图目标):label 在上、value 在下,数字等宽 tabular 列对齐。
  metricRow: {
    marginTop: 10,
    flexDirection: 'row',
    gap: 6,
  },
  metricPill: {
    flex: 1,
    flexBasis: 0,
    minWidth: 0,
    flexDirection: 'column',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 3,
    paddingVertical: 9,
    borderRadius: revaRadii.sm,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  metricLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 13,
  } as TextStyle,
  metricValue: {
    fontFamily: revaFonts.mono,
    fontSize: 13.5,
    fontWeight: '600',
    color: C.ink1,
    lineHeight: 17,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  progressBox: {
    marginTop: 8,
    gap: 3,
    paddingHorizontal: 9,
    paddingVertical: 8,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  progressLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  progressLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.green700,
    lineHeight: 15,
  } as TextStyle,
  progressValue: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '700',
    color: C.green700,
    lineHeight: 16,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  progressTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: C.green100,
    overflow: 'hidden',
    marginTop: 3,
    marginBottom: 1,
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: C.green500,
  },
  progressHint: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
  cautionList: {
    marginTop: 9,
    gap: 6,
  },
  cautionItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 7,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: C.surface,
  },
  cautionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 17,
  } as TextStyle,
  nextAction: {
    marginTop: 9,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    paddingHorizontal: 8,
    paddingVertical: 7,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  nextActionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
    color: C.green700,
    lineHeight: 17,
  } as TextStyle,
  shareStrip: {
    marginTop: 10,
    gap: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: revaRadii.md,
    backgroundColor: 'rgba(255,255,255,0.82)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E8D6C0',
  },
  shareStripHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  shareStripEyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '800',
    color: ADJUST_ACCENT,
    letterSpacing: 0,
    lineHeight: 14,
  } as TextStyle,
  shareStripTag: {
    flexShrink: 1,
    textAlign: 'right',
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
  shareMetricRow: {
    flexDirection: 'row',
    gap: 8,
  },
  shareMetric: {
    flex: 1,
    minHeight: 48,
    justifyContent: 'center',
    gap: 3,
    paddingHorizontal: 9,
    paddingVertical: 7,
    borderRadius: revaRadii.sm,
    backgroundColor: C.paper,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  shareMetricLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
  shareMetricValue: {
    fontFamily: revaFonts.mono,
    fontSize: 15,
    fontWeight: '600',
    color: C.ink1,
    lineHeight: 19,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  shareNextRow: {
    gap: 3,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#E8D6C0',
  },
  shareNextLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '800',
    color: ADJUST_ACCENT,
    lineHeight: 14,
  } as TextStyle,
  shareNextText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 17,
  } as TextStyle,
  nextMealPanel: {
    marginTop: 8,
    gap: 7,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  nextMealTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '900',
    color: C.ink1,
    lineHeight: 18,
  } as TextStyle,
  nextMealContext: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  nextMealSummary: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.green700,
    lineHeight: 17,
  } as TextStyle,
  nextMealList: {
    gap: 6,
  },
  nextMealListItem: {
    flexDirection: 'row',
    gap: 7,
    alignItems: 'flex-start',
  },
  nextMealIndex: {
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    overflow: 'hidden',
    textAlign: 'center',
    fontFamily: revaFonts.mono,
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 18,
    color: C.green700,
    backgroundColor: C.green50,
  } as TextStyle,
  nextMealListText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink1,
    lineHeight: 16,
  } as TextStyle,
  rationaleBox: {
    gap: 4,
    paddingTop: 6,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  rationaleItem: {
    flexDirection: 'row',
    gap: 5,
    alignItems: 'flex-start',
  },
  rationaleText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink2,
    lineHeight: 15,
  } as TextStyle,
  continuePrompt: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  adjustPanel: {
    marginTop: 9,
    gap: 9,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  adjustHint: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    fontWeight: '700',
    color: C.ink3,
    lineHeight: 16,
  } as TextStyle,
  mealTypeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  mealChip: {
    minHeight: 30,
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
    paddingHorizontal: 11,
  },
  mealChipActive: {
    backgroundColor: ADJUST_ACCENT,
  },
  mealChipText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    fontWeight: '800',
  } as TextStyle,
  mealChipTextActive: {
    color: '#fff',
  } as TextStyle,
  foodInput: {
    minHeight: 44,
    borderRadius: revaRadii.sm,
    backgroundColor: C.paper2,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink1,
  } as TextStyle,
  macroGrid: {
    flexDirection: 'row',
    gap: 7,
  },
  macroCell: {
    flex: 1,
    alignItems: 'center',
    gap: 3,
  },
  macroCellLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  macroCellInput: {
    width: '100%',
    minHeight: 34,
    borderRadius: revaRadii.sm,
    backgroundColor: C.paper2,
    paddingHorizontal: 6,
    paddingVertical: 5,
    fontFamily: revaFonts.mono,
    fontSize: 13,
    color: C.ink1,
    textAlign: 'center',
  } as TextStyle,
  macroCellUnit: {
    fontFamily: revaFonts.mono,
    fontSize: 9.5,
    color: C.ink3,
  } as TextStyle,
  adjustError: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
    color: revaSemantic.risk.fg,
    lineHeight: 16,
  } as TextStyle,
  adjustActionRow: {
    flexDirection: 'row',
    gap: 8,
  },
  cancelButton: {
    flex: 0.82,
    minHeight: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
  },
  cancelButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink2,
    fontWeight: '900',
  } as TextStyle,
  saveButton: {
    flex: 1.18,
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    borderRadius: revaRadii.sm,
    backgroundColor: C.green500,
  },
  saveButtonBusy: {
    opacity: 0.72,
  },
  saveButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: '#fff',
    fontWeight: '900',
  } as TextStyle,
  buttonDisabled: {
    opacity: 0.58,
  },
  savedRow: {
    marginTop: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  savedText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '900',
    color: C.green700,
    lineHeight: 16,
  } as TextStyle,
});
