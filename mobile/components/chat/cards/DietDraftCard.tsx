import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, TextStyle, View } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { MEAL_ICONS, MACRO_HUES, MacroBar, IngredientChips } from './mealCardVisuals';
import type {
  CardRenderOptions,
  CardSpec,
  ChatCardActionDescriptor,
  ChatCardActionRuntimeState,
} from './types';
import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../../constants/revaTheme';
import { BASE_URL } from '../../../services/api';

// 饮食类目 accent (橙) = 「是饮食卡」装饰色, 保留字面量 (= legacy orange/tintOrange).
const DIET_ACCENT = '#C97A2E';
const DIET_TINT = '#F6E9DA';

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

const SOURCE_LABELS: Record<string, string> = {
  chat: '对话',
  chat_photo: '对话/图片',
  photo: '图片',
  voice: '语音',
  text: '文字',
  meal_monitor: '餐食监控',
};

interface DietDraftData {
  meal_type?: unknown;
  food_items?: unknown;
  calories?: unknown;
  protein?: unknown;
  carbs?: unknown;
  fat?: unknown;
  fiber?: unknown;
  confidence?: unknown;
  source?: unknown;
  suggestions?: unknown;
  post_meal_walk?: unknown;
  expanded_sections?: unknown;
  next_meal_detail?: unknown;
  boundary?: unknown;
  time?: unknown;
  recorded_at?: unknown;
  photo_url?: unknown;
  recorded?: unknown;
  receipt_message?: unknown;
  auto_save_fallback?: unknown;
}

interface DietDraftCardViewProps extends DietDraftData {
  onDraftChange?: (data: DietDraftData) => void;
  confirmAction?: ChatCardActionDescriptor;
  confirmActionState?: ChatCardActionRuntimeState;
  onConfirmAction?: (action: ChatCardActionDescriptor) => void;
}

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

interface DraftEditValues {
  mealType: MealType;
  food: string;
  calories: string;
  protein: string;
  carbs: string;
  fat: string;
}

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function foodText(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    const items = value.map(text).filter((item): item is string => Boolean(item));
    return items.length ? items.slice(0, 6).join(' + ') : undefined;
  }
  return text(value);
}

/** 拆 food_items 成独立食材条 (数组 or " + " 分隔的字符串), 供 chip 渲染。 */
function foodChips(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(text).filter((item): item is string => Boolean(item)).slice(0, 8);
  }
  const joined = text(value);
  if (!joined) return [];
  return joined
    .split(/\s*[+＋]\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
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

function listText(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : value == null ? [] : [value];
  return raw.map(text).filter((item): item is string => Boolean(item)).slice(0, 3);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function hasExpandedSection(value: unknown, section: string): boolean {
  return Array.isArray(value) && value.map(text).includes(section);
}

// 2×2 营养网格: 只渲染 data 里非空的 macro。热量走上面的 hero, 不重复进网格。
function macroRows(data: DietDraftData) {
  return [
    { label: '蛋白质', value: numberValue(data.protein), suffix: 'g', color: MACRO_HUES.protein },
    { label: '碳水', value: numberValue(data.carbs), suffix: 'g', color: MACRO_HUES.carbs },
    { label: '脂肪', value: numberValue(data.fat), suffix: 'g', color: MACRO_HUES.fat },
    { label: '膳食纤维', value: numberValue(data.fiber), suffix: 'g', color: MACRO_HUES.fiber },
  ].filter((row) => row.value != null && row.value >= 0);
}

function hasNutritionEstimate(data: DietDraftData): boolean {
  return [data.calories, data.protein, data.carbs, data.fat, data.fiber]
    .some((value) => numberValue(value) != null);
}

function confidenceLabel(value: unknown): string | undefined {
  const confidence = numberValue(value);
  if (confidence == null) return undefined;
  const normalized = confidence <= 1 ? confidence * 100 : confidence;
  if (normalized <= 0) return undefined;
  return `置信度 ${Math.round(Math.min(100, normalized))}%`;
}

function confidenceBadge(value: unknown): string {
  const confidence = numberValue(value);
  if (confidence == null) return '请核对';
  const normalized = confidence <= 1 ? confidence * 100 : confidence;
  return normalized >= 80 ? '高置信' : '请核对';
}

function compactMealTitle(items: string[], fallback: string): string {
  const labels = items
    .map(item => item
      .replace(/[（(][^）)]*[）)]/g, '')
      .replace(/\b\d+(?:\.\d+)?\s*(?:g|克|ml|毫升|份|个|只|碗|杯)\b/gi, '')
      .trim())
    .filter(Boolean);
  return labels.slice(0, 3).join(' · ') || fallback;
}

function sourceLabel(value: unknown): string | undefined {
  const source = text(value);
  if (!source) return undefined;
  return `来源: ${SOURCE_LABELS[source] || source}`;
}

function privatePhotoUri(value: unknown): string | undefined {
  const raw = text(value);
  if (!raw) return undefined;
  if (/^https?:\/\//i.test(raw)) return raw;
  const origin = BASE_URL.replace(/\/api\/?$/i, '');
  return `${origin}${raw.startsWith('/') ? raw : `/${raw}`}`;
}

function isPhotoSource(value: unknown): boolean {
  const source = text(value)?.toLowerCase();
  return Boolean(source && (source.includes('photo') || source.includes('image') || source.includes('vision')));
}

function nutritionStatusText(data: DietDraftData): string {
  if (!hasNutritionEstimate(data)) {
    return '确认后先记录，营养后台估算';
  }
  return isPhotoSource(data.source) ? '已带营养估算，核对后计入今日' : '已带营养估算，确认后计入今日';
}

function boundaryText(data: DietDraftData): string {
  const boundary = text(data.boundary) || '营养为估算值,确认后写入今日饮食记录。';
  return isPhotoSource(data.source) ? boundary.replace('确认后写入', '核对后写入') : boundary;
}

function editHintText(data: DietDraftData): string {
  return isPhotoSource(data.source) ? '核对前可修正餐次、食物和营养估算' : '确认前可修正餐次、食物和营养估算';
}

/** 仅当 data 里有明确时点 (time / recorded_at 的 HH:MM) 才回显, 不伪造。 */
function mealTimeLabel(data: DietDraftData): string | undefined {
  const raw = text(data.time) ?? text(data.recorded_at);
  if (!raw) return undefined;
  const match = raw.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/);
  return match ? match[0] : undefined;
}

function postMealWalkText(value: unknown): string | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const raw = value as Record<string, unknown>;
  if (raw.recommended !== true) return undefined;
  const minutes = numberValue(raw.minutes) ?? 10;
  return `餐后轻走 ${Math.round(minutes)} 分钟`;
}

function sanitizeNumberText(value: string): number | undefined {
  const parsed = Number(value.trim());
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 10) / 10 : undefined;
}

function mealTypeValue(value: unknown): MealType {
  const raw = text(value);
  return raw && raw in MEAL_LABELS ? raw as MealType : 'snack';
}

function findDietConfirmAction(actions?: ChatCardActionDescriptor[]): ChatCardActionDescriptor | undefined {
  return actions?.find((action) => action.action === 'diet_record.create' && action.style === 'primary')
    ?? actions?.find((action) => action.action === 'diet_record.create');
}

export function DietDraftCardView(data: DietDraftCardViewProps) {
  const [editing, setEditing] = React.useState(false);
  const [draftMealType, setDraftMealType] = React.useState<MealType>(() => mealTypeValue(data.meal_type));
  const [draftFood, setDraftFood] = React.useState(() => foodText(data.food_items) || '');
  const [draftCalories, setDraftCalories] = React.useState(() => editNumber(data.calories));
  const [draftProtein, setDraftProtein] = React.useState(() => editNumber(data.protein));
  const [draftCarbs, setDraftCarbs] = React.useState(() => editNumber(data.carbs));
  const [draftFat, setDraftFat] = React.useState(() => editNumber(data.fat));
  const chips = foodChips(data.food_items);
  const mealType = mealTypeValue(data.meal_type);
  const mealLabel = MEAL_LABELS[mealType] || '餐食';
  const macros = macroRows(data);
  const caloriesValue = numberValue(data.calories);
  const nutritionEstimated = hasNutritionEstimate(data);
  const nutritionStatus = nutritionStatusText(data);
  const timeLabel = mealTimeLabel(data);
  const meta = [confidenceLabel(data.confidence), sourceLabel(data.source)].filter(Boolean).join(' · ');
  const suggestions = listText(data.suggestions);
  const walkText = postMealWalkText(data.post_meal_walk);
  const nextMealDetail = objectValue(data.next_meal_detail);
  const showNextMealDetail = Boolean(
    nextMealDetail && hasExpandedSection(data.expanded_sections, 'next_meal'),
  );
  const boundary = boundaryText(data);
  const editHint = editHintText(data);
  const photoUri = privatePhotoUri(data.photo_url);
  const isRecorded = data.recorded === true || data.confirmActionState === 'done';
  const receiptMessage = text(data.receipt_message);
  const canConfirmFromEditor = Boolean(data.confirmAction && data.onConfirmAction && !data.confirmAction.disabled_reason);
  const recordedNextStep = walkText || suggestions[0] || '下一餐按目标补足蛋白和蔬菜';
  const publishDraftChange = React.useCallback((overrides: Partial<DraftEditValues> = {}) => {
    const values: DraftEditValues = {
      mealType: overrides.mealType ?? draftMealType,
      food: overrides.food ?? draftFood,
      calories: overrides.calories ?? draftCalories,
      protein: overrides.protein ?? draftProtein,
      carbs: overrides.carbs ?? draftCarbs,
      fat: overrides.fat ?? draftFat,
    };
    const { onDraftChange, confirmAction, onConfirmAction, ...baseData } = data;
    const next: DietDraftData = {
      ...baseData,
      meal_type: values.mealType,
      food_items: values.food.trim() || baseData.food_items,
    };
    const calories = sanitizeNumberText(values.calories);
    const protein = sanitizeNumberText(values.protein);
    const carbs = sanitizeNumberText(values.carbs);
    const fat = sanitizeNumberText(values.fat);
    if (calories != null) next.calories = calories;
    if (protein != null) next.protein = protein;
    if (carbs != null) next.carbs = carbs;
    if (fat != null) next.fat = fat;
    onDraftChange?.(next);
  }, [data, draftCalories, draftCarbs, draftFat, draftFood, draftMealType, draftProtein]);

  if (!isRecorded && !editing) {
    return (
      <CardShell
        icon={MEAL_ICONS[mealType]}
        iconColor={C.green600}
        title={data.auto_save_fallback === true ? `${mealLabel}草稿 · 自动保存待确认` : `${mealLabel}草稿 · 识别完成`}
        badge={confidenceBadge(data.confidence)}
        badgeColor={C.green500}
        bg={C.paper}
        style={styles.compactCard}
      >
        <View style={styles.compactTitleRow}>
          {photoUri ? (
            <Image
              testID="diet-draft-photo"
              source={{ uri: photoUri }}
              style={styles.compactPhoto}
              contentFit="cover"
              transition={120}
              accessibilityLabel="本次识别的餐食照片"
            />
          ) : null}
          <View style={styles.compactTitleCopy}>
            <Text maxFontSizeMultiplier={1.16} style={styles.compactMealTitle} numberOfLines={2}>
              {compactMealTitle(chips, draftFood || mealLabel)}
            </Text>
            <Text maxFontSizeMultiplier={1.14} style={styles.compactMealSubtitle}>
              已识别 {Math.max(chips.length, 1)} 项，可直接调整份量
            </Text>
          </View>
          <Pressable
            onPress={() => setEditing(true)}
            accessibilityRole="button"
            accessibilityLabel="修正饮食草稿"
            style={({ pressed }) => [styles.compactEditButton, pressed && styles.editButtonPressed]}
          >
            <Ionicons name="create-outline" size={13} color={C.green700} />
            <Text style={styles.compactEditText}>修正</Text>
          </Pressable>
        </View>

        <View style={styles.compactIngredientList}>
          {(chips.length > 0 ? chips : [draftFood || '待确认餐食']).slice(0, 4).map(item => (
            <View key={item} style={styles.compactIngredientRow}>
              <View style={styles.compactIngredientDot} />
              <Text maxFontSizeMultiplier={1.13} style={styles.compactIngredientText} numberOfLines={1}>
                {item}
              </Text>
            </View>
          ))}
        </View>

        <View style={styles.compactNutritionStrip}>
          <View style={styles.compactNutritionItem}>
            <Text style={styles.compactNutritionLabel}>估算热量</Text>
            <Text style={styles.compactNutritionValue}>{caloriesValue == null ? '--' : Math.round(caloriesValue)} kcal</Text>
          </View>
          <View style={styles.compactNutritionItem}>
            <Text style={styles.compactNutritionLabel}>蛋白</Text>
            <Text style={[styles.compactNutritionValue, { color: C.green600 }]}>
              {numberValue(data.protein) == null ? '--' : `${Math.round(numberValue(data.protein)!)}g`}
            </Text>
          </View>
          <View style={styles.compactNutritionItem}>
            <Text style={styles.compactNutritionLabel}>碳水</Text>
            <Text style={styles.compactNutritionValue}>
              {numberValue(data.carbs) == null ? '--' : `${Math.round(numberValue(data.carbs)!)}g`}
            </Text>
          </View>
        </View>

        {showNextMealDetail && nextMealDetail ? (
          <View style={styles.compactNextMeal}>
            <View style={styles.compactNextMealHeader}>
              <Ionicons name="restaurant-outline" size={13} color={C.green600} />
              <Text style={styles.compactNextMealTitle}>{text(nextMealDetail.title) || '下一餐建议'}</Text>
            </View>
            {text(nextMealDetail.summary) ? (
              <Text style={styles.compactNextMealSummary}>{text(nextMealDetail.summary)}</Text>
            ) : null}
            {listText(nextMealDetail.options).map((item, index) => (
              <View key={`${item}-${index}`} style={styles.compactNextMealOption}>
                <Text style={styles.compactNextMealIndex}>{index + 1}</Text>
                <Text style={styles.compactNextMealOptionText}>{item}</Text>
              </View>
            ))}
            {text(nextMealDetail.continue_prompt) ? (
              <Text style={styles.compactContinuePrompt}>{text(nextMealDetail.continue_prompt)}</Text>
            ) : null}
          </View>
        ) : null}

        <Text maxFontSizeMultiplier={1.12} style={styles.compactBoundary}>
          营养为估算值，保存前可继续修正
        </Text>
      </CardShell>
    );
  }

  return (
    <CardShell
      icon={MEAL_ICONS[mealType]}
      iconColor={DIET_ACCENT}
      title={isRecorded ? `${mealLabel}已记录` : `${mealLabel} · 待确认`}
      // 已记录态靠标题「…已记录」+ hero 勾图标表达, 不再加 badge(避免与 action-bar「已记录」撞文本);
      // 草稿态给「草稿」chip。
      badge={isRecorded ? undefined : '草稿'}
      badgeColor={revaSemantic.caution.fg}
      bg={DIET_TINT}
    >
      {photoUri ? (
        <Image
          testID="diet-draft-photo"
          source={{ uri: photoUri }}
          style={styles.detailPhoto}
          contentFit="cover"
          transition={120}
          accessibilityLabel="本次识别的餐食照片"
        />
      ) : null}
      {/* 卡尔路里 hero：大号等宽数字 + 单位。无每日目标字段 → 不造「占今日 X%」。 */}
      <View style={styles.heroRow}>
        <View style={styles.heroLeft}>
          <Text maxFontSizeMultiplier={1.18} style={styles.heroCal}>
            {caloriesValue != null ? `${Math.round(caloriesValue)}` : '--'}
            <Text style={styles.heroUnit}> kcal</Text>
          </Text>
          {timeLabel ? (
            <View style={styles.timePill}>
              <Ionicons name="time-outline" size={11} color={C.ink3} />
              <Text maxFontSizeMultiplier={1.15} style={styles.timeText}>{timeLabel}</Text>
            </View>
          ) : null}
        </View>
        {isRecorded ? (
          <Ionicons name="checkmark-circle" size={20} color={C.green500} />
        ) : null}
      </View>

      {/* 分段营养条：按热量占比 (蛋白×4 / 碳水×4 / 脂肪×9 / 纤维×2) 拆一条横条。 */}
      <MacroBar
        protein={numberValue(data.protein)}
        carbs={numberValue(data.carbs)}
        fat={numberValue(data.fat)}
        fiber={numberValue(data.fiber)}
        style={styles.macroBar}
      />

      {isRecorded ? (
        <View style={styles.recordedProgressPill}>
          <Ionicons name="checkmark-done-circle" size={13} color={C.green600} />
          <Text maxFontSizeMultiplier={1.12} style={styles.recordedProgressText}>
            {receiptMessage || '已进入今日饮食进度'}
          </Text>
        </View>
      ) : null}

      {isRecorded ? (
        <View style={styles.shareReadyRow}>
          <Text maxFontSizeMultiplier={1.1} style={styles.shareReadyLabel}>可截图分享</Text>
          <Text maxFontSizeMultiplier={1.1} style={styles.shareReadyTag}>#饮食记录 #小巴</Text>
        </View>
      ) : null}

      {isRecorded ? (
        <View style={styles.socialShareFooter}>
          <View style={styles.socialTitleRow}>
            <Text maxFontSizeMultiplier={1.08} style={styles.socialTitle}>
              今日饮食打卡
            </Text>
            <Text maxFontSizeMultiplier={1.05} style={styles.socialBadge}>
              小巴生成
            </Text>
          </View>
          <Text maxFontSizeMultiplier={1.08} style={styles.socialHint}>
            适合微信 / 小红书截图分享
          </Text>
        </View>
      ) : null}

      {/* 食材 chips */}
      <IngredientChips items={chips} fallback="待确认餐食" style={styles.chipsWrap} />

      {!isRecorded ? (
        <View style={styles.nutritionStatusRow}>
          <Ionicons
            name={nutritionEstimated ? 'analytics-outline' : 'time-outline'}
            size={13}
            color={nutritionEstimated ? C.green600 : C.ink3}
          />
          <Text
            maxFontSizeMultiplier={1.15}
            style={[
              styles.nutritionStatusText,
              { color: nutritionEstimated ? C.green600 : C.ink3 },
            ]}
          >
            {nutritionStatus}
          </Text>
        </View>
      ) : null}

      {!isRecorded ? (
        <View style={styles.inlineHeader}>
          <Text maxFontSizeMultiplier={1.15} style={styles.inlineHint}>
            {editHint}
          </Text>
          <Pressable
            onPress={() => setEditing((prev) => !prev)}
            accessibilityRole="button"
            accessibilityLabel={editing ? '收起修正' : '修正饮食草稿'}
            style={({ pressed }) => [styles.editButton, pressed && styles.editButtonPressed]}
          >
            <Ionicons name={editing ? 'chevron-up' : 'create-outline'} size={12} color={DIET_ACCENT} />
            <Text style={styles.editButtonText}>{editing ? '收起' : '修正'}</Text>
          </Pressable>
        </View>
      ) : null}

      {editing ? (
        <View
          testID="diet-draft-inline-editor"
          style={styles.editor}
          onTouchStart={(event) => event.stopPropagation()}
        >
          <View style={styles.mealTypeRow}>
            {(Object.keys(MEAL_LABELS) as MealType[]).map((key) => (
              <Pressable
                key={key}
                onPress={() => {
                  setDraftMealType(key);
                  publishDraftChange({ mealType: key });
                }}
                accessibilityRole="button"
                accessibilityLabel={`餐次 ${MEAL_LABELS[key]}`}
                style={[
                  styles.mealChip,
                  draftMealType === key && styles.mealChipActive,
                ]}
              >
                <Text style={[
                  styles.mealChipText,
                  draftMealType === key && styles.mealChipTextActive,
                ]}>
                  {MEAL_LABELS[key]}
                </Text>
              </Pressable>
            ))}
          </View>
          <TextInput
            accessibilityLabel="食物描述"
            value={draftFood}
            onChangeText={(value) => {
              setDraftFood(value);
              publishDraftChange({ food: value });
            }}
            placeholder="食物描述"
            placeholderTextColor={C.ink4}
            multiline
            style={styles.foodInput}
          />
          <View style={styles.editMacroGrid}>
            <DraftNumberInput
              label="热量"
              unit="kcal"
              value={draftCalories}
              onChangeText={(value) => {
                setDraftCalories(value);
                publishDraftChange({ calories: value });
              }}
            />
            <DraftNumberInput
              label="蛋白"
              unit="g"
              value={draftProtein}
              onChangeText={(value) => {
                setDraftProtein(value);
                publishDraftChange({ protein: value });
              }}
            />
            <DraftNumberInput
              label="碳水"
              unit="g"
              value={draftCarbs}
              onChangeText={(value) => {
                setDraftCarbs(value);
                publishDraftChange({ carbs: value });
              }}
            />
            <DraftNumberInput
              label="脂肪"
              unit="g"
              value={draftFat}
              onChangeText={(value) => {
                setDraftFat(value);
                publishDraftChange({ fat: value });
              }}
            />
          </View>
          <View style={styles.editorActionRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="完成饮食草稿修正"
              style={({ pressed }) => [
                styles.finishButton,
                !canConfirmFromEditor && styles.finishButtonFull,
                pressed && { opacity: 0.86 },
              ]}
              onPress={() => {
                publishDraftChange();
                setEditing(false);
              }}
            >
              <Text style={styles.finishButtonText}>完成修正</Text>
            </Pressable>
            {data.confirmAction ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="保存并确认饮食记录"
                accessibilityState={{ disabled: !canConfirmFromEditor }}
                disabled={!canConfirmFromEditor}
                style={({ pressed }) => [
                  styles.saveConfirmButton,
                  !canConfirmFromEditor && styles.saveConfirmButtonDisabled,
                  pressed && canConfirmFromEditor && { opacity: 0.86 },
                ]}
                onPress={() => {
                  if (!data.confirmAction || !data.onConfirmAction) return;
                  publishDraftChange();
                  setEditing(false);
                  data.onConfirmAction(data.confirmAction);
                }}
              >
                <Ionicons name="checkmark-circle" size={14} color="#fff" />
                <Text style={styles.saveConfirmButtonText}>保存并确认</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : null}

      {/* 2×2 营养网格：彩色圆点 + 标签 + 克数，只渲染存在的 macro。 */}
      {macros.length > 0 ? (
        <View style={styles.macroGrid}>
          {macros.map((row) => (
            <View key={row.label} style={styles.macroCell}>
              <View style={[styles.macroDot, { backgroundColor: row.color }]} />
              <Text maxFontSizeMultiplier={1.1} style={styles.macroLabel} numberOfLines={1}>
                {row.label}
              </Text>
              <Text maxFontSizeMultiplier={1.1} style={[styles.macroValue, { color: row.color }]}>
                {Math.round(row.value!)}{row.suffix}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {meta ? (
        <View style={styles.metaRow}>
          <Ionicons name="sparkles-outline" size={12} color={C.ink3} />
          <Text maxFontSizeMultiplier={1.15} style={styles.meta}>
            {meta}
          </Text>
        </View>
      ) : null}

      {isRecorded ? (
        <View style={styles.recordedBox}>
          <Text maxFontSizeMultiplier={1.15} style={styles.recordedNext}>下一步: {recordedNextStep}</Text>
          <Text maxFontSizeMultiplier={1.15} style={styles.recordedHelp}>
            可在记录页继续修正,小巴会把这餐纳入今日饮食进度。
          </Text>
        </View>
      ) : null}

      {(walkText || suggestions.length > 0) ? (
        <View style={styles.nextBox}>
          {walkText ? (
            <View style={styles.nextRow}>
              <Ionicons name="footsteps-outline" size={13} color={C.green600} />
              <Text maxFontSizeMultiplier={1.15} style={styles.nextText}>{walkText}</Text>
            </View>
          ) : null}
          {suggestions.map((item) => (
            <View key={item} style={styles.nextRow}>
              <Ionicons name="arrow-forward-circle-outline" size={13} color={C.green600} />
              <Text maxFontSizeMultiplier={1.15} style={styles.nextText}>{item}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {showNextMealDetail && nextMealDetail ? (
        <View style={styles.nextMealPanel}>
          <View style={styles.nextMealHeader}>
            <Ionicons name="restaurant-outline" size={14} color={C.green600} />
            <Text maxFontSizeMultiplier={1.12} style={styles.nextMealTitle}>
              {text(nextMealDetail.title) || '下一餐建议'}
            </Text>
          </View>
          {text(nextMealDetail.summary) ? (
            <Text maxFontSizeMultiplier={1.15} style={styles.nextMealSummary}>
              {text(nextMealDetail.summary)}
            </Text>
          ) : null}
          {text(nextMealDetail.context) ? (
            <Text maxFontSizeMultiplier={1.15} style={styles.nextMealContext}>
              {text(nextMealDetail.context)}
            </Text>
          ) : null}
          {listText(nextMealDetail.options).length > 0 ? (
            <View style={styles.nextMealOptions}>
              {listText(nextMealDetail.options).map((item, index) => (
                <View key={`${item}-${index}`} style={styles.nextMealOptionRow}>
                  <Text style={styles.nextMealOptionIndex}>{index + 1}</Text>
                  <Text maxFontSizeMultiplier={1.15} style={styles.nextMealOptionText}>
                    {item}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
          {listText(nextMealDetail.rationale).length > 0 ? (
            <View style={styles.nextMealRationale}>
              {listText(nextMealDetail.rationale).map((item) => (
                <View key={item} style={styles.nextMealReasonRow}>
                  <Ionicons name="checkmark-circle-outline" size={12} color={C.green600} />
                  <Text maxFontSizeMultiplier={1.15} style={styles.nextMealReasonText}>{item}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {text(nextMealDetail.continue_prompt) ? (
            <View style={styles.continuePromptPill}>
              <Ionicons name="chatbubble-ellipses-outline" size={12} color={C.green600} />
              <Text maxFontSizeMultiplier={1.1} style={styles.continuePromptText}>
                {text(nextMealDetail.continue_prompt)}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}

      <View style={styles.boundaryRow}>
        <Ionicons name="information-circle-outline" size={12} color={revaSemantic.caution.fg} />
        <Text maxFontSizeMultiplier={1.15} style={styles.boundary}>
          {boundary}
        </Text>
      </View>
    </CardShell>
  );
}

export const DietDraftCardSpec: CardSpec<DietDraftData> = {
  type: 'diet_draft',
  label: '饮食草稿',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data, options?: CardRenderOptions) => {
    const confirmAction = findDietConfirmAction(options?.cardActions);
    const confirmActionKey = confirmAction
      ? confirmAction.id || `diet_draft:${confirmAction.action}:${confirmAction.label}`
      : undefined;
    return (
      <DietDraftCardView
        {...data}
        onDraftChange={options?.onCardDataChange}
        confirmAction={confirmAction}
        confirmActionState={confirmActionKey ? options?.actionStateByKey?.[confirmActionKey] : undefined}
        onConfirmAction={options?.onCardAction}
      />
    );
  },
};

function DraftNumberInput({
  label,
  unit,
  value,
  onChangeText,
}: {
  label: string;
  unit: string;
  value: string;
  onChangeText: (value: string) => void;
}) {
  return (
    <View style={styles.editMacroCell}>
      <Text style={styles.editMacroLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        keyboardType="decimal-pad"
        placeholder="0"
        placeholderTextColor={C.ink4}
        style={styles.editMacroInput}
      />
      <Text style={styles.editMacroUnit}>{unit}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  compactCard: {
    paddingHorizontal: 13,
    paddingVertical: 12,
  },
  compactTitleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  compactPhoto: {
    width: 58,
    height: 58,
    borderRadius: revaRadii.sm,
    backgroundColor: C.paper2,
  },
  compactTitleCopy: { flex: 1, minWidth: 0, gap: 3 },
  compactMealTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '900',
    color: C.ink1,
  } as TextStyle,
  compactMealSubtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 16,
    color: C.ink3,
  } as TextStyle,
  compactEditButton: {
    minHeight: 30,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    paddingHorizontal: 9,
  },
  compactEditText: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 15,
    fontWeight: '900',
    color: C.green700,
  } as TextStyle,
  compactIngredientList: {
    marginTop: 12,
    paddingTop: 9,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    gap: 7,
  },
  compactIngredientRow: {
    minHeight: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  compactIngredientDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: C.green500,
  },
  compactIngredientText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12.5,
    lineHeight: 18,
    fontWeight: '700',
    color: C.ink2,
  } as TextStyle,
  compactNutritionStrip: {
    marginTop: 11,
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 10,
    backgroundColor: C.paper2,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  compactNutritionItem: { flex: 1, gap: 2 },
  compactNutritionLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 9.5,
    lineHeight: 13,
    fontWeight: '700',
    color: C.ink3,
  } as TextStyle,
  compactNutritionValue: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
    color: C.ink1,
  } as TextStyle,
  compactBoundary: {
    marginTop: 8,
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 15,
    color: C.ink3,
  } as TextStyle,
  compactNextMeal: {
    marginTop: 10,
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.green50,
    paddingHorizontal: 10,
    paddingVertical: 9,
    gap: 6,
  },
  compactNextMealHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  compactNextMealTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '900',
    color: C.green700,
  } as TextStyle,
  compactNextMealSummary: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 17,
    fontWeight: '700',
    color: C.ink2,
  } as TextStyle,
  compactNextMealOption: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  compactNextMealIndex: {
    width: 17,
    fontFamily: revaFonts.mono,
    fontSize: 10.5,
    lineHeight: 16,
    fontWeight: '900',
    color: C.green600,
  } as TextStyle,
  compactNextMealOptionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 17,
    color: C.ink2,
  } as TextStyle,
  compactContinuePrompt: {
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 15,
    color: C.green700,
    fontWeight: '700',
  } as TextStyle,
  heroRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  detailPhoto: {
    width: '100%',
    height: 152,
    borderRadius: revaRadii.md,
    backgroundColor: C.paper2,
    marginBottom: 10,
  },
  heroLeft: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 8,
    flexShrink: 1,
  },
  heroCal: {
    fontFamily: revaFonts.mono,
    fontSize: 30,
    fontWeight: '800',
    color: C.ink1,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  heroUnit: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '400',
    color: C.ink3,
  } as TextStyle,
  timePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    alignSelf: 'center',
  },
  timeText: {
    fontFamily: revaFonts.mono,
    fontSize: 11,
    color: C.ink3,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  macroBar: {
    marginTop: 10,
  },
  chipsWrap: {
    marginTop: 10,
  },
  nutritionStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: 9,
  },
  nutritionStatusText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 16,
    fontWeight: '800',
  } as TextStyle,
  recordedProgressPill: {
    alignSelf: 'flex-start',
    maxWidth: '100%',
    minHeight: 26,
    marginTop: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    paddingHorizontal: 9,
  },
  recordedProgressText: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 15,
    color: C.green700,
    fontWeight: '900',
  } as TextStyle,
  shareReadyRow: {
    marginTop: 7,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    borderRadius: revaRadii.sm,
    backgroundColor: 'rgba(255,255,255,0.72)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E8D6C0',
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  shareReadyLabel: {
    flexShrink: 0,
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 14,
    color: DIET_ACCENT,
    fontWeight: '900',
  } as TextStyle,
  shareReadyTag: {
    flex: 1,
    minWidth: 0,
    textAlign: 'right',
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 14,
    color: C.ink3,
    fontWeight: '800',
  } as TextStyle,
  socialShareFooter: {
    marginTop: 8,
    borderRadius: revaRadii.md,
    backgroundColor: 'rgba(255,255,255,0.82)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E8D6C0',
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  socialTitleRow: {
    minHeight: 22,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  socialTitle: {
    flex: 1,
    minWidth: 0,
    fontFamily: revaFonts.sans,
    fontSize: 13.5,
    lineHeight: 18,
    color: C.ink1,
    fontWeight: '900',
  } as TextStyle,
  socialBadge: {
    flexShrink: 0,
    fontFamily: revaFonts.sans,
    fontSize: 10.5,
    lineHeight: 14,
    color: DIET_ACCENT,
    fontWeight: '900',
  } as TextStyle,
  socialHint: {
    marginTop: 2,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 15,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  inlineHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
  },
  inlineHint: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 16,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  editButton: {
    minHeight: 28,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 9,
  },
  editButtonPressed: {
    opacity: 0.78,
  },
  editButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: DIET_ACCENT,
    fontWeight: '800',
  } as TextStyle,
  editor: {
    gap: 9,
    marginTop: 10,
    marginBottom: 2,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 10,
  },
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
    backgroundColor: DIET_ACCENT,
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
  editMacroGrid: {
    flexDirection: 'row',
    gap: 7,
  },
  editMacroCell: {
    flex: 1,
    alignItems: 'center',
    gap: 3,
  },
  editMacroLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  editMacroInput: {
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
  editMacroUnit: {
    fontFamily: revaFonts.mono,
    fontSize: 9.5,
    color: C.ink3,
  } as TextStyle,
  editorActionRow: {
    flexDirection: 'row',
    gap: 8,
  },
  finishButton: {
    flex: 0.82,
    minHeight: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
  },
  finishButtonFull: {
    flex: 1,
  },
  finishButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink2,
    fontWeight: '900',
  } as TextStyle,
  saveConfirmButton: {
    flex: 1.18,
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    borderRadius: revaRadii.sm,
    backgroundColor: DIET_ACCENT,
  },
  saveConfirmButtonDisabled: {
    opacity: 0.58,
  },
  saveConfirmButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: '#fff',
    fontWeight: '900',
  } as TextStyle,
  macroGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 10,
  },
  macroCell: {
    width: '50%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 5,
  },
  macroDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  macroLabel: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    fontWeight: '700',
  } as TextStyle,
  macroValue: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '900',
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  metaRow: {
    marginTop: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  meta: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  recordedBox: {
    gap: 5,
    marginTop: 10,
    borderRadius: revaRadii.sm,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  recordedNext: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.green700,
    fontWeight: '800',
  } as TextStyle,
  recordedHelp: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink3,
    fontWeight: '600',
  } as TextStyle,
  nextBox: {
    gap: 6,
    marginTop: 9,
    borderRadius: revaRadii.sm,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  nextRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  nextText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12.2,
    lineHeight: 17,
    color: C.ink2,
    fontWeight: '700',
  } as TextStyle,
  nextMealPanel: {
    marginTop: 10,
    gap: 8,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    padding: 11,
  },
  nextMealHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  nextMealTitle: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.green700,
    fontWeight: '900',
  } as TextStyle,
  nextMealSummary: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 19,
    color: C.ink1,
    fontWeight: '800',
  } as TextStyle,
  nextMealContext: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 17,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  nextMealOptions: {
    gap: 6,
  },
  nextMealOptionRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
  },
  nextMealOptionIndex: {
    width: 18,
    height: 18,
    borderRadius: 9,
    overflow: 'hidden',
    textAlign: 'center',
    lineHeight: 18,
    backgroundColor: C.green50,
    color: C.green700,
    fontFamily: revaFonts.mono,
    fontSize: 11,
    fontWeight: '900',
  } as TextStyle,
  nextMealOptionText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12.5,
    lineHeight: 18,
    color: C.ink2,
    fontWeight: '800',
  } as TextStyle,
  nextMealRationale: {
    gap: 4,
  },
  nextMealReasonRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
  },
  nextMealReasonText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 17,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  continuePromptPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  continuePromptText: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    color: C.green700,
    fontWeight: '900',
  } as TextStyle,
  boundaryRow: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
  },
  boundary: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink3,
  } as TextStyle,
});
