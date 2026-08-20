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
import {
  recalculateDietRecordNutrition,
  updateDietRecord,
  type DietRecordUpdate,
  type MealType,
} from '../../../services/diet';

interface RecordQualityData {
  domain?: unknown;
  record_id?: unknown;
  title?: unknown;
  summary?: unknown;
  metrics?: unknown;
  progress?: unknown;
  goal_progress?: unknown;
  primary_judgement?: unknown;
  personal_cautions?: unknown;
  next_action?: unknown;
  expanded_sections?: unknown;
  next_meal_detail?: unknown;
  adjust_record?: unknown;
  adjust_saved?: unknown;
  meal_type?: unknown;
  food_items?: unknown;
  calories?: unknown;
  protein?: unknown;
  carbs?: unknown;
  fat?: unknown;
  fiber?: unknown;
  updated_at?: unknown;
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

function normalizeFoodText(value: string): string {
  return value.trim().replace(/\s+/g, ' ');
}

const DIET_RECALCULATION_SECURE_RANDOM_UNAVAILABLE = 'diet_recalculation_secure_random_unavailable';

interface SecureRandomCrypto {
  randomUUID?: () => string;
  getRandomValues?: (bytes: Uint8Array) => Uint8Array;
}

function createDietRecalculationOperationKey(): string {
  const cryptoApi = (globalThis as unknown as { crypto?: SecureRandomCrypto }).crypto;
  if (typeof cryptoApi?.randomUUID === 'function') {
    try {
      const key = cryptoApi.randomUUID().trim();
      if (key) return key;
    } catch {
      // Fall through to getRandomValues when the platform exposes both APIs.
    }
  }
  if (typeof cryptoApi?.getRandomValues === 'function') {
    try {
      const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    } catch {
      // The write must fail closed when secure randomness is unavailable.
    }
  }
  throw new Error(DIET_RECALCULATION_SECURE_RANDOM_UNAVAILABLE);
}

function responseStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object') return undefined;
  const response = (error as { response?: unknown }).response;
  if (!response || typeof response !== 'object') return undefined;
  const status = (response as { status?: unknown }).status;
  return typeof status === 'number' && Number.isFinite(status) ? status : undefined;
}

function clearRecordQualityDietDerivations(data: RecordQualityData): RecordQualityData {
  const next = { ...data };
  delete next.progress;
  delete next.primary_judgement;
  delete next.personal_cautions;
  delete next.next_action;
  delete next.next_meal_detail;
  return next;
}

function mealTypeValue(value: unknown): MealType {
  const raw = text(value);
  return raw && raw in MEAL_LABELS ? (raw as MealType) : 'snack';
}

function integerRecordId(value: unknown): number | undefined {
  const parsed = numberValue(value);
  return parsed != null && Number.isInteger(parsed) ? parsed : undefined;
}

function formatDisplayNumber(value: number): string {
  return String(Math.round(value * 100) / 100);
}

function formatMeasuredOn(value: unknown): string | undefined {
  const raw = text(value);
  const match = raw?.match(/^\d{4}-(\d{2})-(\d{2})$/);
  if (!match) return undefined;
  return `${Number(match[1])}月${Number(match[2])}日`;
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
  const recordedDays7d = progressValue(data.progress, 'recorded_days_7d');
  const goalProgress = objectValue(data.goal_progress);
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

      {recordedDays7d ? (
        <View style={styles.consistencyRow}>
          <Ionicons name="calendar-outline" size={13} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={styles.consistencyText}>
            近7天记录 {recordedDays7d} 天
          </Text>
          <Text maxFontSizeMultiplier={1.15} style={styles.consistencyHint}>
            规律比完美更重要
          </Text>
        </View>
      ) : null}

      {goalProgress ? <WeightGoalProgressView goal={goalProgress} /> : null}

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
          seed={{
            ...adjustRecord,
            ...(!Object.prototype.hasOwnProperty.call(adjustRecord, 'fiber')
              ? { fiber: data.fiber }
              : {}),
            ...(!Object.prototype.hasOwnProperty.call(adjustRecord, 'updated_at')
              ? { updated_at: data.updated_at }
              : {}),
          }}
          onSaved={(applied) => {
            if (!onCardDataChange) return;
            const currentData = clearRecordQualityDietDerivations(data);
            const remainingSections = (Array.isArray(data.expanded_sections) ? data.expanded_sections : [])
              .map((item) => text(item))
              .filter((item): item is string => (
                Boolean(item) && item !== 'adjust_record' && item !== 'next_meal'
              ));
            onCardDataChange({
              ...currentData,
              ...applied.adjustRecord,
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

function WeightGoalProgressView({ goal }: { goal: Record<string, unknown> }) {
  const current = numberValue(goal.current_kg);
  const target = numberValue(goal.target_kg);
  const remaining = numberValue(goal.remaining_kg);
  const progress = numberValue(goal.progress_pct);
  const change = numberValue(goal.change_7d_kg);
  const status = text(goal.status);
  const freshness = text(goal.freshness);
  const measuredOn = formatMeasuredOn(goal.measured_on);

  if (current == null || target == null) return null;
  if (status === 'target_requires_review') {
    return (
      <View style={[styles.goalBox, styles.goalReviewBox]}>
        <View style={styles.goalHeader}>
          <Ionicons name="flag-outline" size={14} color={revaSemantic.caution.fg} />
          <Text maxFontSizeMultiplier={1.2} style={styles.goalReviewTitle}>目标需要复核</Text>
        </View>
        <Text maxFontSizeMultiplier={1.25} style={styles.goalReviewText}>
          当前目标可能不适合直接推进，请先核对身高和目标体重。
        </Text>
      </View>
    );
  }

  const achieved = status === 'achieved';
  const safeProgress = progress == null ? null : Math.max(0, Math.min(100, progress));
  const showTrend = freshness !== 'stale' && change != null;
  return (
    <View style={styles.goalBox}>
      <View style={styles.goalHeader}>
        <View style={styles.goalTitleRow}>
          <Ionicons name={achieved ? 'checkmark-circle-outline' : 'flag-outline'} size={14} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={styles.goalTitle}>目标进度</Text>
        </View>
        <Text maxFontSizeMultiplier={1.15} style={styles.goalCurrent}>
          {formatDisplayNumber(current)} → {formatDisplayNumber(target)}kg
        </Text>
      </View>
      <View style={styles.goalValueRow}>
        <Text maxFontSizeMultiplier={1.2} style={styles.goalValue}>
          {achieved ? '已达到当前目标' : `距目标 ${formatDisplayNumber(remaining ?? Math.max(current - target, 0))}kg`}
        </Text>
        {showTrend ? (
          <Text maxFontSizeMultiplier={1.15} style={styles.goalTrend}>
            近7天 {change > 0 ? '+' : ''}{formatDisplayNumber(change)}kg
          </Text>
        ) : null}
      </View>
      {safeProgress != null ? (
        <View
          accessible
          accessibilityRole="progressbar"
          accessibilityLabel={`减重目标进度 ${formatDisplayNumber(safeProgress)}%`}
          accessibilityValue={{ min: 0, max: 100, now: safeProgress }}
          style={styles.goalTrack}
        >
          <View style={[styles.goalFill, { width: `${safeProgress}%` }]} />
        </View>
      ) : null}
      {freshness === 'stale' ? (
        <Text maxFontSizeMultiplier={1.2} style={styles.goalStale}>
          体重数据较旧，更新后再看趋势
        </Text>
      ) : null}
      {measuredOn ? (
        <Text maxFontSizeMultiplier={1.15} style={styles.goalMeasured}>测于 {measuredOn}</Text>
      ) : null}
      <Text maxFontSizeMultiplier={1.15} style={styles.goalBoundary}>
        体重变化来自连续测量，不归因于单次饮食。
      </Text>
    </View>
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
  const [fiber, setFiber] = React.useState(() => editNumber(seed.fiber));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<
    'save' | 'recalculate' | 'conflict' | 'secure_random' | null
  >(null);
  const [collapsed, setCollapsed] = React.useState(false);
  const initialFood = React.useRef(normalizeFoodText(text(seed.food_items) || '')).current;
  const seedHasRevision = Object.prototype.hasOwnProperty.call(seed, 'updated_at');
  const expectedUpdatedAt = seed.updated_at === null ? null : text(seed.updated_at);
  const revisionKnown = seedHasRevision && expectedUpdatedAt !== undefined;
  const recalculationOperation = React.useRef<{ signature: string; key: string } | null>(null);
  const foodChanged = normalizeFoodText(food) !== initialFood;
  const revisionMissing = foodChanged && !revisionKnown;
  const revisionConflict = error === 'conflict';
  const secureRandomUnavailable = error === 'secure_random';
  const saveBlocked = saving || revisionMissing || revisionConflict || secureRandomUnavailable;

  const buildPatch = React.useCallback((): DietRecordUpdate => {
    // food_items + meal_type 始终随保存写回; 数字仅在有效值时带上(空/负 → 不覆盖后端值)
    const patch: DietRecordUpdate = { meal_type: mealType, food_items: food.trim() };
    const cal = sanitizeNumberText(calories);
    const pro = sanitizeNumberText(protein);
    const car = sanitizeNumberText(carbs);
    const fatValue = sanitizeNumberText(fat);
    const fiberValue = sanitizeNumberText(fiber);
    if (cal != null) patch.calories = cal;
    if (pro != null) patch.protein = pro;
    if (car != null) patch.carbs = car;
    if (fatValue != null) patch.fat = fatValue;
    if (fiberValue != null) patch.fiber = fiberValue;
    return patch;
  }, [mealType, food, calories, protein, carbs, fat, fiber]);

  const handleSave = React.useCallback(async () => {
    if (saveBlocked) return; // action-lock: 防双击 / 防缺失或旧 revision 重试
    setSaving(true);
    setError(null);
    const patch = buildPatch();
    try {
      let updated;
      if (foodChanged) {
        if (!revisionKnown || expectedUpdatedAt === undefined) {
          setSaving(false);
          return;
        }
        const normalizedFood = normalizeFoodText(food);
        const signature = JSON.stringify([
          recordId,
          expectedUpdatedAt,
          mealType,
          normalizedFood,
        ]);
        if (recalculationOperation.current?.signature !== signature) {
          recalculationOperation.current = {
            signature,
            key: createDietRecalculationOperationKey(),
          };
        }
        updated = await recalculateDietRecordNutrition(recordId, {
          meal_type: mealType,
          food_items: normalizedFood,
          expected_updated_at: expectedUpdatedAt,
        }, recalculationOperation.current.key);
      } else {
        updated = await updateDietRecord(recordId, patch);
      }
      const savedMealType = (updated.meal_type as MealType) || mealType;
      const savedFood = updated.food_items || food.trim();
      const summary = buildSummary(
        savedMealType,
        updated.calories,
        updated.protein,
        updated.carbs,
        updated.fat,
        updated.fiber,
      );
      const metrics = buildMetrics(
        updated.calories,
        updated.protein,
        updated.carbs,
        updated.fat,
        updated.fiber,
      );
      const adjustRecord: Record<string, unknown> = {
        record_id: recordId,
        meal_type: savedMealType,
        food_items: savedFood,
        calories: updated.calories ?? null,
        protein: updated.protein ?? null,
        carbs: updated.carbs ?? null,
        fat: updated.fat ?? null,
        fiber: updated.fiber ?? null,
        // null is a known revision; undefined deliberately clears any stale seed.
        updated_at: Object.prototype.hasOwnProperty.call(updated, 'updated_at')
          ? updated.updated_at
          : undefined,
      };
      setCollapsed(true);
      onSaved({ cardFace: { summary, metrics }, adjustRecord });
    } catch (cause) {
      const secureRandomFailure = (
        cause instanceof Error
        && cause.message === DIET_RECALCULATION_SECURE_RANDOM_UNAVAILABLE
      );
      setError(
        secureRandomFailure
          ? 'secure_random'
          : foodChanged && responseStatus(cause) === 409
          ? 'conflict'
          : foodChanged ? 'recalculate' : 'save',
      );
      setSaving(false); // 失败保留输入, 允许重试
    }
  }, [
    saveBlocked,
    buildPatch,
    food,
    foodChanged,
    recordId,
    mealType,
    revisionKnown,
    expectedUpdatedAt,
    onSaved,
  ]);

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
        <AdjustNumberInput label="膳食纤维" unit="g" value={fiber} onChangeText={setFiber} editable={!saving} />
      </View>
      {revisionMissing || error ? (
        <Text maxFontSizeMultiplier={1.15} style={styles.adjustError}>
          {revisionMissing
            ? '记录版本缺失，请取消并重新打开或刷新后再修改'
            : error === 'conflict'
            ? '记录已在其他位置更新，请取消并重新打开后再修改'
            : error === 'secure_random'
              ? '无法安全生成保存标识，请取消并重新打开后再试'
            : error === 'recalculate' ? '营养重新计算失败，请重试' : '保存失败，请重试'}
        </Text>
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
          accessibilityState={{ disabled: saveBlocked, busy: saving }}
          disabled={saveBlocked}
          onPress={handleSave}
          style={({ pressed }) => [
            styles.saveButton,
            saving && styles.saveButtonBusy,
            (revisionMissing || revisionConflict || secureRandomUnavailable) && styles.buttonDisabled,
            pressed && !saveBlocked && { opacity: 0.86 },
          ]}
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
  fiber: number | null,
): string {
  const parts = [MEAL_LABELS[mealType] || '餐食'];
  if (calories != null) parts.push(`${formatDisplayNumber(calories)} kcal`);
  if (protein != null) parts.push(`蛋白 ${formatDisplayNumber(protein)}g`);
  if (carbs != null) parts.push(`碳水 ${formatDisplayNumber(carbs)}g`);
  if (fat != null) parts.push(`脂肪 ${formatDisplayNumber(fat)}g`);
  if (fiber != null) parts.push(`纤维 ${formatDisplayNumber(fiber)}g`);
  return parts.join(' · ');
}

function buildMetrics(
  calories: number | null,
  protein: number | null,
  carbs: number | null,
  fat: number | null,
  fiber: number | null,
): MetricItem[] {
  return [
    calories != null ? { label: '热量', value: `${formatDisplayNumber(calories)}kcal` } : null,
    protein != null ? { label: '蛋白', value: `${formatDisplayNumber(protein)}g` } : null,
    carbs != null ? { label: '碳水', value: `${formatDisplayNumber(carbs)}g` } : null,
    fat != null ? { label: '脂肪', value: `${formatDisplayNumber(fat)}g` } : null,
    fiber != null ? { label: '纤维', value: `${formatDisplayNumber(fiber)}g` } : null,
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
  goalBox: {
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    gap: 5,
  },
  consistencyRow: {
    minHeight: 36,
    marginTop: 10,
    paddingHorizontal: 11,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: revaRadii.sm,
    backgroundColor: C.green50,
  },
  consistencyText: {
    fontFamily: revaFonts.cjk,
    fontSize: 12,
    lineHeight: 17,
    color: C.green700,
    fontWeight: '600',
  },
  consistencyHint: {
    flex: 1,
    fontFamily: revaFonts.cjk,
    fontSize: 11,
    lineHeight: 15,
    color: C.ink2,
    textAlign: 'right',
  },
  goalReviewBox: {
    borderColor: revaSemantic.caution.line,
  },
  goalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  goalTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  goalTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    color: C.green700,
  } as TextStyle,
  goalReviewTitle: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
    color: revaSemantic.caution.fg,
  } as TextStyle,
  goalReviewText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink2,
  } as TextStyle,
  goalCurrent: {
    fontFamily: revaFonts.mono,
    fontSize: 11,
    color: C.ink2,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  goalValueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 8,
    flexWrap: 'wrap',
  },
  goalValue: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 19,
    color: C.ink1,
  } as TextStyle,
  goalTrend: {
    fontFamily: revaFonts.mono,
    fontSize: 10,
    color: C.green700,
  } as TextStyle,
  goalTrack: {
    height: 5,
    borderRadius: 3,
    backgroundColor: C.green100,
    overflow: 'hidden',
  },
  goalFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: C.green500,
  },
  goalStale: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '600',
    lineHeight: 14,
    color: revaSemantic.caution.fg,
  } as TextStyle,
  goalMeasured: {
    fontFamily: revaFonts.mono,
    fontSize: 9.5,
    color: C.ink3,
  } as TextStyle,
  goalBoundary: {
    fontFamily: revaFonts.sans,
    fontSize: 9.5,
    lineHeight: 13,
    color: C.ink3,
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
