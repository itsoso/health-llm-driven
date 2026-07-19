import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, TextStyle, Alert, ActivityIndicator } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import ReanimatedSwipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import { useDailyDiet } from '../hooks/useDiet';
import { useDietEstimate, type EstimateSource } from '../hooks/useDietEstimate';
import { createDietRecord, updateDietRecord, deleteDietRecord, dietRecordImageUrls, discardDietPhotoDraft, getDietPhotoDraftStatus, getFrequentFoods, recognizeFood, type DietRecord, type DietRecordCreate, type DietRecordUpdate, type FoodItem, type FrequentFood } from '../services/diet';
import { computeDietTotals, isPendingNutrition } from '../utils/dietTotals';
import * as ImagePicker from 'expo-image-picker';
import type { ImagePickerAsset } from 'expo-image-picker';
import MealForm from '../components/diet/MealForm';
import DietFAB from '../components/diet/DietFAB';
import FrequentFoodsRow from '../components/diet/FrequentFoodsRow';
import { DietShareSheet } from '../components/diet/DietShareCard';
import { useToast } from '../hooks/useToast';
import { useAuth } from '../hooks/useAuth';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import { createDietAgentContext, pushChatWithContext } from '../utils/agentContext';
import { todayStr, offsetDate } from '../utils/dietDate';
import { assertDietFoodItemsAllowed } from '../utils/dietIntakeGuard';
import { buildChatImageSource } from '../utils/chatImageSource';
import { BASE_URL } from '../services/api';
import { emitClientEvent } from '../services/clientEvents';
import {
  clearDietPhotoDraft,
  loadDietPhotoDraft,
  saveDietPhotoDraft,
} from '../services/dietPhotoDraftStorage';
import {
  base64DecodedByteLength,
  cleanupPreparedUploadImages,
  imagePickerEncodingOptions,
  prepareImageForUploadSafe,
} from '../utils/imageUpload';
import type { PreparedUploadImage } from '../utils/imageUpload';

const MEAL_LABEL: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };
const VALID_MEAL_TYPES = new Set(['breakfast', 'lunch', 'dinner', 'snack']);
const EMPTY_MEALS: DietRecord[] = [];

type DietRouteParams = {
  capture?: string | string[];
  return_to?: string | string[];
  date?: string | string[];
  share_record_id?: string | string[];
  draft?: string | string[];
  meal_type?: string | string[];
  food_items?: string | string[];
  calories?: string | string[];
  protein?: string | string[];
  carbs?: string | string[];
  fat?: string | string[];
};

type DietQuickDraft = {
  record: DietRecordCreate;
  source: EstimateSource | null;
};

type PhotoCaptureStage = 'idle' | 'capturing' | 'selecting' | 'preparing' | 'recognizing' | 'draft_ready' | 'saving' | 'saved' | 'failed';
const BUSY_PHOTO_CAPTURE_STAGES = new Set<PhotoCaptureStage>([
  'capturing',
  'selecting',
  'preparing',
  'recognizing',
  'saving',
]);
const PHOTO_RECOGNITION_SLOW_MS = 6000;
const PORTION_REVIEW_ASSISTIVE_HINT = '优先核对食物份量；热量和三大营养会随份量一起修正。';
const POST_CONFIRM_DIET_REVIEW_PROMPT = '请先查询今天数据库里的所有饮食记录，并核验 created_id 对应的刚保存记录是否存在；再结合这条刚保存的饮食记录，汇总全天饮食、总热量和蛋白质/碳水/脂肪，并给出下一餐最小调整建议。如果数据库里查不到这条记录，请明确提示同步失败，不要只凭本页缓存或本轮对话猜测。';
const PHOTO_CAPTURE_STEPS = [
  { key: 'preparing', label: '优化照片' },
  { key: 'recognizing', label: '识别食物' },
  { key: 'draft', label: '生成草稿' },
] as const;

const NON_DIET_DRAFT_ALERT = {
  title: '这不是饮食记录',
  message: '这条内容更像用药或补剂,请从用药/补剂入口确认。',
};
const HEALTH_METRIC_DRAFT_ALERT = {
  title: '这不是饮食记录',
  message: '这条内容更像体重、运动、睡眠或血压等健康指标,请从对应记录入口确认。',
};
const NON_FOOD_DRAFT_ALERT = {
  title: '这不是饮食记录',
  message: '这条内容不像具体食物,请重新描述这一餐吃了什么。',
};

function alertForDietFoodItemsError(error: unknown): typeof NON_DIET_DRAFT_ALERT {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message === 'invalid_diet_food_items_health_metric') return HEALTH_METRIC_DRAFT_ALERT;
  if (message === 'invalid_diet_food_items_non_diet') return NON_DIET_DRAFT_ALERT;
  return NON_FOOD_DRAFT_ALERT;
}

function guessMealType(): DietRecordCreate['meal_type'] {
  const h = new Date().getHours();
  if (h < 10) return 'breakfast';
  if (h < 16) return 'lunch';
  if (h < 22) return 'dinner';
  return 'snack';
}

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function readRouteText(value: string | string[] | undefined): string | undefined {
  const raw = firstParam(value)?.trim();
  if (!raw) return undefined;
  const normalized = raw.replace(/\+/g, ' ');
  try {
    return decodeURIComponent(normalized).trim().slice(0, 500) || undefined;
  } catch {
    return normalized.slice(0, 500);
  }
}

function readRouteNumber(value: string | string[] | undefined): number | undefined {
  const raw = readRouteText(value);
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 10) / 10 : undefined;
}

function readRouteMealType(value: string | string[] | undefined): DietRecordCreate['meal_type'] | undefined {
  const raw = readRouteText(value);
  return raw && VALID_MEAL_TYPES.has(raw) ? raw as DietRecordCreate['meal_type'] : undefined;
}

function readRouteDate(value: string | string[] | undefined): string | undefined {
  const raw = readRouteText(value);
  return raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : undefined;
}

function readRoutePositiveInt(value: string | string[] | undefined): number | undefined {
  const raw = readRouteText(value);
  if (!raw || !/^\d+$/.test(raw)) return undefined;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function needsNutritionBackfill(record: Partial<DietRecordCreate>): boolean {
  return [record.calories, record.protein, record.carbs, record.fat]
    .some((value) => typeof value !== 'number' || !Number.isFinite(value));
}

function buildDietDraft(defaults: Partial<DietRecordCreate>, recordDate = todayStr()): DietRecordCreate {
  return {
    record_date: defaults.record_date ?? recordDate,
    meal_type: defaults.meal_type ?? guessMealType(),
    food_items: defaults.food_items?.trim() || '未命名餐食',
    food_id: defaults.food_id,
    source: defaults.source,
    calories: defaults.calories,
    protein: defaults.protein,
    carbs: defaults.carbs,
    fat: defaults.fat,
    fiber: defaults.fiber,
    alcohol_units: defaults.alcohol_units,
    notes: defaults.notes,
    image_base64: defaults.image_base64,
    image_type: defaults.image_type,
    photo_draft_token: defaults.photo_draft_token,
    idempotency_key: defaults.idempotency_key,
    ai_recognized: defaults.ai_recognized,
    ai_confidence: defaults.ai_confidence,
    ai_raw_result: defaults.ai_raw_result,
    health_tips: defaults.health_tips,
  };
}

function formatDraftMetric(value: number | undefined, precision = 0): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const rounded = precision > 0 ? Math.round(value * 10 ** precision) / 10 ** precision : Math.round(value);
  return `${rounded}`;
}

function formatTimingSeconds(ms: number | null | undefined): string | null {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return null;
  return `${Math.round(ms / 100) / 10}s`;
}

function foodNeedsPortionReview(food: FoodItem): boolean {
  const hasQuantity = Boolean(food.quantity?.trim());
  const identityConfidence = typeof food.confidence === 'number' && Number.isFinite(food.confidence)
    ? food.confidence
    : null;
  const portionConfidence = typeof food.portion_confidence === 'number' && Number.isFinite(food.portion_confidence)
    ? food.portion_confidence
    : null;
  return !hasQuantity
    || (identityConfidence !== null && identityConfidence < 0.7)
    || (portionConfidence !== null && portionConfidence < 0.7);
}

function normalizedDraftConfidence(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const normalized = value > 1 ? value / 100 : value;
  return normalized >= 0 && normalized <= 1 ? normalized : null;
}

function quickDraftNeedsWholeReview(draft: Partial<DietRecordCreate>): boolean {
  const confidence = normalizedDraftConfidence(draft.ai_confidence);
  return confidence !== null && confidence < 0.7;
}

function quickDraftNeedsPortionReview(draft: Partial<DietRecordCreate>): boolean {
  return (draft.ai_raw_result?.foods ?? []).some(foodNeedsPortionReview);
}

function quickDraftNeedsReview(draft: Partial<DietRecordCreate>): boolean {
  return quickDraftNeedsPortionReview(draft) || quickDraftNeedsWholeReview(draft);
}

function buildQuickDraftReviewHint(draft: DietRecordCreate): string {
  const foods = draft.ai_raw_result?.foods ?? [];
  const needsReview = quickDraftNeedsReview(draft);
  const writeVerb = needsReview ? '核对后' : '确认后';
  const portionCheckNames = foods
    .filter(foodNeedsPortionReview)
    .map(food => food.name?.trim())
    .filter((name): name is string => Boolean(name));
  if (portionCheckNames.length > 0) {
    const visibleNames = portionCheckNames.slice(0, 2).join('、');
    const suffix = portionCheckNames.length > 2 ? `等 ${portionCheckNames.length} 项` : '';
    return `小巴建议先核对：${visibleNames}${suffix}的份量；${writeVerb}才写入今天饮食。`;
  }
  if (quickDraftNeedsWholeReview(draft)) {
    return `小巴建议先核对整餐识别结果和份量；${writeVerb}才写入今天饮食。`;
  }
  if (foods.length > 0) {
    return `小巴已拆出 ${foods.length} 项食物；${writeVerb}才写入今天饮食。`;
  }
  return `先核对食物和份量；${writeVerb}才写入今天饮食。`;
}

function quickDraftReviseLabel(draft: DietRecordCreate): string {
  return quickDraftNeedsPortionReview(draft) ? '修正份量' : '修正';
}

function averageRecognitionConfidence(foods: { confidence: number | null }[] | undefined): number | undefined {
  const values = (foods ?? [])
    .map(food => food.confidence)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (!values.length) return undefined;
  return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 1000) / 1000;
}

function recognitionNutritionSource(foods: FoodItem[] | undefined): string {
  const sources = new Set(
    (foods ?? [])
      .map(food => food.source?.trim())
      .filter((source): source is string => Boolean(source)),
  );
  if (sources.size === 1) return [...sources][0];
  if (sources.size > 1) return 'mixed';
  return 'ai_estimate';
}

function assertPersistedDietRecord(record: DietRecord): DietRecord {
  if (!record?.id || !Number.isFinite(record.id)) {
    throw new Error('diet_record_missing_id');
  }
  return record;
}

function buildShareRecordFromConfirmation(created: DietRecord, draft: DietRecordCreate): DietRecord {
  return {
    id: created.id,
    user_id: created.user_id ?? 0,
    record_date: created.record_date ?? draft.record_date,
    meal_type: created.meal_type ?? draft.meal_type,
    food_items: created.food_items ?? draft.food_items,
    food_id: created.food_id ?? draft.food_id ?? null,
    source: created.source ?? draft.source ?? null,
    calories: created.calories ?? draft.calories ?? null,
    protein: created.protein ?? draft.protein ?? null,
    carbs: created.carbs ?? draft.carbs ?? null,
    fat: created.fat ?? draft.fat ?? null,
    fiber: created.fiber ?? draft.fiber ?? null,
    alcohol_units: created.alcohol_units ?? draft.alcohol_units ?? null,
    image_url: created.image_url ?? null,
    image_urls: created.image_urls ?? [],
    photo_assets: created.photo_assets ?? [],
    notes: created.notes ?? draft.notes ?? null,
    health_tips: created.health_tips ?? draft.health_tips ?? null,
    ai_recognized: created.ai_recognized ?? draft.ai_recognized ?? null,
    ai_confidence: created.ai_confidence ?? draft.ai_confidence ?? null,
  };
}

function buildPostConfirmDietReviewContext(record: DietRecord) {
  return {
    from: 'diet/post_confirm',
    must_query_database: true,
    created_id: record.id,
    verify_record_id: record.id,
    database_verification: {
      required: true,
      date: record.record_date,
      verify_record_id: record.id,
      query_scope: 'daily_diet_records',
      totals_source: 'database',
      forbid_cached_totals: true,
      missing_record_instruction: '如果数据库里查不到 verify_record_id 对应记录，明确提示同步失败，不要凭本页缓存或对话内容猜测。',
    },
    expected_record: {
      id: record.id,
      record_date: record.record_date,
      meal_type: record.meal_type,
      food_items: record.food_items,
    },
    record: {
      record_date: record.record_date,
      meal_type: record.meal_type,
      food_items: record.food_items,
      calories: record.calories ?? null,
      protein: record.protein ?? null,
      carbs: record.carbs ?? null,
      fat: record.fat ?? null,
      fiber: record.fiber ?? null,
      alcohol_units: record.alcohol_units ?? null,
      notes: record.notes ?? null,
      source: record.source ?? null,
    },
  };
}

function mergeRevisedDraft(
  original: Partial<DietRecordCreate>,
  revision: DietRecordCreate,
): DietRecordCreate {
  const merged = { ...original, ...revision } as DietRecordCreate;
  if (!original.photo_draft_token) return merged;
  const normalized = (value: unknown) => String(value ?? '').trim().replace(/\s+/g, ' ');
  const foodChanged = normalized(original.food_items) !== normalized(revision.food_items);
  const nutritionChanged = (['calories', 'protein', 'carbs', 'fat'] as const)
    .some(key => original[key] !== revision[key]);
  const reviewedRiskyDraft = quickDraftNeedsReview(original);
  if (!foodChanged && !nutritionChanged && !reviewedRiskyDraft) return merged;
  const corrected: DietRecordCreate = {
    ...merged,
    food_id: foodChanged ? undefined : original.food_id,
    fiber: foodChanged ? revision.fiber : merged.fiber,
    source: 'user_corrected',
    ai_recognized: 0,
    ai_confidence: undefined,
    ai_raw_result: undefined,
    health_tips: undefined,
  };
  if (foodChanged) {
    for (const key of ['calories', 'protein', 'carbs', 'fat', 'fiber'] as const) {
      corrected[key] = revision[key] === original[key] ? undefined : revision[key];
    }
  }
  return corrected;
}

function photoDraftWasCorrected(
  original: Partial<DietRecordCreate>,
  revision: DietRecordCreate,
): boolean {
  const normalizedText = (value: unknown) => String(value ?? '').trim().replace(/\s+/g, ' ');
  if (original.meal_type !== revision.meal_type) return true;
  if (normalizedText(original.food_items) !== normalizedText(revision.food_items)) return true;
  return (['calories', 'protein', 'carbs', 'fat', 'fiber'] as const)
    .some(key => (original[key] ?? null) !== (revision[key] ?? null));
}

export function buildEditedDietPatch(
  original: DietRecord,
  revision: DietRecordCreate,
): DietRecordUpdate {
  const normalized = (value: unknown) => String(value ?? '').trim().replace(/\s+/g, ' ');
  const foodChanged = normalized(original.food_items) !== normalized(revision.food_items);
  const editableNutrientFields = ['calories', 'protein', 'carbs', 'fat'] as const;
  const nutritionChanged = editableNutrientFields.some(
    key => (revision[key] ?? null) !== (original[key] ?? null),
  );
  const patch: DietRecordUpdate = {
    meal_type: revision.meal_type,
    food_items: revision.food_items,
    calories: revision.calories ?? null,
    protein: revision.protein ?? null,
    carbs: revision.carbs ?? null,
    fat: revision.fat ?? null,
    alcohol_units: revision.alcohol_units ?? null,
  };
  if (foodChanged) {
    patch.food_id = null;
    patch.fiber = null;
    for (const key of editableNutrientFields) {
      patch[key] = revision[key] === original[key] ? null : (revision[key] ?? null);
    }
  }
  if (foodChanged || nutritionChanged) {
    patch.source = 'user_corrected';
    patch.ai_recognized = 0;
    patch.ai_confidence = null;
    patch.ai_raw_result = null;
    patch.health_tips = null;
  }
  return patch;
}

function isUnavailablePhotoDraftError(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status;
  return status === 404 || status === 409 || status === 410;
}

function absoluteApiAssetUrl(url: string | null | undefined): string | null {
  const value = String(url ?? '').trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) return value;
  const origin = BASE_URL.replace(/\/api\/?$/i, '');
  return `${origin}${value.startsWith('/') ? value : `/${value}`}`;
}

export default function DietScreen() {
  const router = useRouter();
  const { token: authToken, user: authUser, isLoading: authLoading } = useAuth();
  const authUserId = authUser?.id;
  const params = useLocalSearchParams<DietRouteParams>();
  const returnToChatAfterConfirm = firstParam(params.return_to) === 'chat';
  const captureConsumedRef = useRef(false);
  const draftConsumedRef = useRef(false);
  const qc = useQueryClient();
  const toast = useToast();
  const [date, setDate] = useState(() => readRouteDate(params.date) ?? todayStr());
  const { data: daily, refetch, isRefetching } = useDailyDiet(date);
  const { estimate, pendingIds, failedIds } = useDietEstimate();
  // 记住每条记录的估算来源, 让「点重试」用同一来源 (photo/voice/text) 重跑.
  const sourceMapRef = useRef<Map<number, EstimateSource>>(new Map());
  const reconciledRef = useRef<Set<number>>(new Set());
  const frequentQuery = useQuery({
    queryKey: ['diet', 'frequent'],
    queryFn: () => getFrequentFoods(8, 30),
    staleTime: 10 * 60 * 1000,
  });
  const [showForm, setShowForm] = useState(false);
  const [formDefaults, setFormDefaults] = useState<Partial<DietRecordCreate>>({});
  const [editingRecord, setEditingRecord] = useState<DietRecord | null>(null);
  const [draftEstimateSource, setDraftEstimateSource] = useState<EstimateSource | null>(null);
  const [quickDraft, setQuickDraft] = useState<DietQuickDraft | null>(null);
  const [photoCaptureStage, setPhotoCaptureStage] = useState<PhotoCaptureStage>('idle');
  const [photoRecognitionSlow, setPhotoRecognitionSlow] = useState(false);
  const photoRecognitionSlowRef = useRef(false);
  const [quickDraftSaving, setQuickDraftSaving] = useState(false);
  const [shareRecord, setShareRecord] = useState<DietRecord | null>(null);
  const [shareImageUriOverride, setShareImageUriOverride] = useState<string | null>(null);
  const shareRecordParamConsumedRef = useRef<string | null>(null);
  const [photoDraftRestoreReady, setPhotoDraftRestoreReady] = useState(false);
  const quickDraftSavingRef = useRef(false);
  const activeDraftRef = useRef(false);
  const authOwnerScopeRef = useRef<string | null>(null);

  const openDietDraft = useCallback(async (
    defaults: Partial<DietRecordCreate>,
    source: EstimateSource | null,
    toastMessage = '已生成草稿,确认后写入',
  ) => {
    const foodItems = defaults.food_items?.trim();
    // Photo candidates already passed the backend's structured food sanitizer.
    // Re-running the text heuristic here misclassifies food names such as "橙子片" as tablets.
    if (foodItems && source?.kind !== 'photo') {
      try {
        assertDietFoodItemsAllowed(foodItems);
      } catch (error) {
        const alert = alertForDietFoodItemsError(error);
        Alert.alert(alert.title, alert.message);
        return;
      }
    }
    const idempotencyKey = defaults.idempotency_key
      ?? (defaults.photo_draft_token
        ? `diet-photo:${defaults.photo_draft_token}`
        : `diet-draft:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`);
    const record = buildDietDraft({ ...defaults, idempotency_key: idempotencyKey });
    setDate(record.record_date);
    setEditingRecord(null);
    setDraftEstimateSource(source);
    setFormDefaults(record);
    activeDraftRef.current = true;
    setQuickDraft({ record, source });
    setShowForm(false);
    if (record.photo_draft_token && authUserId) {
      await saveDietPhotoDraft(authUserId, { ...record, image_base64: undefined }).catch(() => {
        toast.show('草稿仅保留在当前页面，请尽快确认', 'info');
      });
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    toast.show(toastMessage, 'success');
  }, [authUserId, toast]);

  useEffect(() => {
    if (photoCaptureStage !== 'recognizing') {
      if (photoRecognitionSlowRef.current) {
        photoRecognitionSlowRef.current = false;
        setPhotoRecognitionSlow(false);
      }
      return undefined;
    }
    const timer = setTimeout(() => {
      photoRecognitionSlowRef.current = true;
      setPhotoRecognitionSlow(true);
    }, PHOTO_RECOGNITION_SLOW_MS);
    return () => clearTimeout(timer);
  }, [photoCaptureStage]);

  useEffect(() => {
    let active = true;
    setPhotoDraftRestoreReady(false);
    const captureMode = firstParam(params.capture);
    const hasCaptureDeepLink = Boolean(captureMode && firstParam(params.draft) !== 'diet');
    if (hasCaptureDeepLink) {
      setPhotoDraftRestoreReady(true);
      return () => { active = false; };
    }
    if (authLoading) return () => { active = false; };
    const nextOwnerScope = authUserId ? `user:${authUserId}` : 'anonymous';
    const ownerChanged = authOwnerScopeRef.current !== null
      && authOwnerScopeRef.current !== nextOwnerScope;
    authOwnerScopeRef.current = nextOwnerScope;
    if (ownerChanged) {
      activeDraftRef.current = false;
      setQuickDraft(null);
      setShowForm(false);
      setEditingRecord(null);
      setFormDefaults({});
      setDraftEstimateSource(null);
      setShareRecord(null);
      setShareImageUriOverride(null);
      setPhotoCaptureStage('idle');
    }
    if (!authUserId) {
      setPhotoDraftRestoreReady(true);
      return () => { active = false; };
    }
    void loadDietPhotoDraft(authUserId)
      .then(async (snapshot) => {
        if (!active || !snapshot || activeDraftRef.current) return;
        try {
          await getDietPhotoDraftStatus(snapshot.record.photo_draft_token!);
        } catch (error) {
          if (isUnavailablePhotoDraftError(error)) {
            await clearDietPhotoDraft(authUserId).catch(() => undefined);
            return;
          }
          throw error;
        }
        if (!active || activeDraftRef.current) return;
        const record = buildDietDraft(snapshot.record, snapshot.record.record_date);
        setDate(record.record_date);
        setEditingRecord(null);
        setDraftEstimateSource({ kind: 'photo' });
        setFormDefaults(record);
        const restoredDraft: DietQuickDraft = { record, source: { kind: 'photo' } };
        activeDraftRef.current = true;
        setQuickDraft(restoredDraft);
        setShowForm(false);
        setPhotoCaptureStage('draft_ready');
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setPhotoDraftRestoreReady(true);
      });
    return () => { active = false; };
  // Restore exactly when the authenticated owner changes.
  }, [authLoading, authUserId, params.capture, params.draft]);

  const saveNewDietRecord = useCallback(async (
    record: DietRecordCreate,
    source: EstimateSource | null,
  ) => {
    const created = assertPersistedDietRecord(await createDietRecord(record));
    if (record.photo_draft_token && authUserId) {
      await clearDietPhotoDraft(authUserId).catch(() => {
        toast.show('记录已保存，本地草稿稍后自动清理', 'info');
      });
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    qc.invalidateQueries({ queryKey: ['diet'] });
    if (created?.id && source && source.kind !== 'photo' && needsNutritionBackfill(record)) {
      sourceMapRef.current.set(created.id, source);
      toast.show('已保存 · 营养后台估算中', 'success');
      estimate(created.id, source);
    } else {
      toast.show('已保存饮食', 'success');
    }
    return created;
  }, [authUserId, estimate, qc, toast]);

  const retryEstimate = useCallback((record: DietRecord) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const source = sourceMapRef.current.get(record.id)
      ?? { kind: 'text', description: record.food_items } as EstimateSource;
    estimate(record.id, source);
  }, [estimate]);

  const handleSave = useCallback(async (record: DietRecordCreate) => {
    const isPhotoCorrection = !editingRecord && (
      draftEstimateSource?.kind === 'photo' || Boolean(formDefaults.photo_draft_token)
    );
    const corrected = isPhotoCorrection && photoDraftWasCorrected(formDefaults, record);
    const confirmationStartedAt = Date.now();
    try {
      if (editingRecord) {
        await updateDietRecord(editingRecord.id, buildEditedDietPatch(editingRecord, record));
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        qc.invalidateQueries({ queryKey: ['diet'] });
      } else {
        const revised = mergeRevisedDraft(formDefaults, record);
        if (revised.photo_draft_token && authUserId) {
          await saveDietPhotoDraft(authUserId, revised).catch(() => {
            toast.show('恢复缓存写入失败，仍继续确认记录', 'info');
          });
        }
        const saveSource = corrected && needsNutritionBackfill(revised)
          ? { kind: 'text' as const, description: revised.food_items }
          : draftEstimateSource;
        const created = await saveNewDietRecord(revised, saveSource);
        if (isPhotoCorrection) {
          void emitClientEvent('diet_photo_confirmation_terminal', {
            phase: 'completed',
            duration_ms: Date.now() - confirmationStartedAt,
            verified: true,
            corrected,
          });
        }
        if (!returnToChatAfterConfirm) {
          setShareImageUriOverride(
            !created.image_url && draftEstimateSource?.kind === 'photo'
              ? draftEstimateSource.imageUri ?? null
              : null,
          );
          setShareRecord(buildShareRecordFromConfirmation(created, revised));
        }
      }
      setShowForm(false);
      setEditingRecord(null);
      setFormDefaults({});
      setDraftEstimateSource(null);
      setQuickDraft(null);
      activeDraftRef.current = false;
    } catch (error) {
      if (isPhotoCorrection) {
        void emitClientEvent('diet_photo_confirmation_terminal', {
          phase: 'failed',
          duration_ms: Date.now() - confirmationStartedAt,
          verified: false,
          corrected,
          error_code: 'record_write_failed',
        });
      }
      if (formDefaults.photo_draft_token && isUnavailablePhotoDraftError(error)) {
        if (authUserId) await clearDietPhotoDraft(authUserId).catch(() => undefined);
        activeDraftRef.current = false;
        setShowForm(false);
        setFormDefaults({});
        setDraftEstimateSource(null);
        setPhotoCaptureStage('idle');
        Alert.alert('照片草稿已失效', '请重新拍照识别这一餐。');
        return;
      }
      if (!editingRecord && formDefaults.photo_draft_token && authUserId) {
        const recoverable = mergeRevisedDraft(formDefaults, record);
        await saveDietPhotoDraft(authUserId, recoverable).catch(() => {
          toast.show('当前草稿仍在页面中，请不要退出后再试', 'info');
        });
      }
      Alert.alert(editingRecord ? '更新失败' : '保存失败', '请稍后再试');
    }
  }, [authUserId, draftEstimateSource, editingRecord, formDefaults, qc, returnToChatAfterConfirm, saveNewDietRecord, toast]);

  const handleConfirmQuickDraft = useCallback(async () => {
    if (!quickDraft) return;
    if (quickDraftSavingRef.current) return;
    quickDraftSavingRef.current = true;
    setQuickDraftSaving(true);
    const confirmationStartedAt = Date.now();
    const isPhotoDraft = quickDraft.source?.kind === 'photo' || Boolean(quickDraft.record.photo_draft_token);
    try {
      const draftRecord = quickDraft.record;
      if (isPhotoDraft) setPhotoCaptureStage('saving');
      const created = await saveNewDietRecord(draftRecord, quickDraft.source);
      const confirmedRecord = buildShareRecordFromConfirmation(created, draftRecord);
      if (isPhotoDraft) {
        void emitClientEvent('diet_photo_confirmation_terminal', {
          phase: 'completed',
          duration_ms: Date.now() - confirmationStartedAt,
          verified: true,
          corrected: false,
        });
      }
      activeDraftRef.current = false;
      setQuickDraft(null);
      setShowForm(false);
      setEditingRecord(null);
      setFormDefaults({});
      setDraftEstimateSource(null);
      if (isPhotoDraft) setPhotoCaptureStage('saved');
      if (returnToChatAfterConfirm) {
        pushChatWithContext(router, {
          prompt: POST_CONFIRM_DIET_REVIEW_PROMPT,
          context: buildPostConfirmDietReviewContext(confirmedRecord),
          badge: '刚记录饮食',
        });
      } else {
        setShareImageUriOverride(
          !created.image_url && quickDraft.source?.kind === 'photo'
            ? quickDraft.source.imageUri ?? null
            : null,
        );
        setShareRecord(confirmedRecord);
      }
    } catch (error) {
      if (isPhotoDraft) {
        setPhotoCaptureStage('failed');
        void emitClientEvent('diet_photo_confirmation_terminal', {
          phase: 'failed',
          duration_ms: Date.now() - confirmationStartedAt,
          verified: false,
          error_code: 'record_write_failed',
        });
      }
      if (isPhotoDraft && isUnavailablePhotoDraftError(error)) {
        if (authUserId) await clearDietPhotoDraft(authUserId).catch(() => undefined);
        activeDraftRef.current = false;
        setQuickDraft(null);
        setFormDefaults({});
        setDraftEstimateSource(null);
        setPhotoCaptureStage('idle');
        Alert.alert('照片草稿已失效', '请重新拍照识别这一餐。');
        return;
      }
      if (isPhotoDraft && authUserId) {
        await saveDietPhotoDraft(authUserId, quickDraft.record).catch(() => {
          toast.show('当前草稿仍在页面中，请不要退出后再试', 'info');
        });
      }
      Alert.alert('保存失败', '请稍后再试');
    } finally {
      quickDraftSavingRef.current = false;
      setQuickDraftSaving(false);
    }
  }, [authUserId, quickDraft, returnToChatAfterConfirm, router, saveNewDietRecord, toast]);

  const handleReviseQuickDraft = useCallback(() => {
    if (!quickDraft) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setFormDefaults(quickDraft.record);
    setDraftEstimateSource(quickDraft.source);
    setEditingRecord(null);
    setQuickDraft(null);
    if (quickDraft.source?.kind === 'photo' || quickDraft.record.source === 'photo') {
      setPhotoCaptureStage('draft_ready');
    }
    setShowForm(true);
  }, [quickDraft]);

  const handleCancelQuickDraft = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (quickDraftSavingRef.current) return;
    quickDraftSavingRef.current = true;
    setQuickDraftSaving(true);
    const photoDraftToken = quickDraft?.record.photo_draft_token;
    const [serverResult, localResult] = await Promise.allSettled([
      photoDraftToken ? discardDietPhotoDraft(photoDraftToken) : Promise.resolve(),
      authUserId ? clearDietPhotoDraft(authUserId) : Promise.resolve(),
    ]);
    if (serverResult.status === 'rejected') {
      toast.show('草稿已在本机关闭，服务器图片将自动过期清理', 'info');
    }
    if (localResult.status === 'rejected') {
      toast.show('本地草稿清理失败，下次打开会再次校验', 'info');
    }
    setQuickDraft(null);
    activeDraftRef.current = false;
    setFormDefaults({});
    setDraftEstimateSource(null);
    setPhotoCaptureStage('idle');
    quickDraftSavingRef.current = false;
    setQuickDraftSaving(false);
    toast.show('已取消草稿', 'info');
  }, [authUserId, quickDraft, toast]);

  const handleCancelForm = useCallback(async () => {
    const photoDraftToken = formDefaults.photo_draft_token;
    const [serverResult, localResult] = await Promise.allSettled([
      photoDraftToken ? discardDietPhotoDraft(photoDraftToken) : Promise.resolve(),
      authUserId ? clearDietPhotoDraft(authUserId) : Promise.resolve(),
    ]);
    if (serverResult.status === 'rejected') {
      toast.show('草稿已在本机关闭，服务器图片将自动过期清理', 'info');
    }
    if (localResult.status === 'rejected') {
      toast.show('本地草稿清理失败，下次打开会再次校验', 'info');
    }
    setShowForm(false);
    setEditingRecord(null);
    setFormDefaults({});
    setDraftEstimateSource(null);
    setQuickDraft(null);
    activeDraftRef.current = false;
    setPhotoCaptureStage('idle');
  }, [authUserId, formDefaults.photo_draft_token, toast]);

  // P1-b: 点「常吃」chip → 直接入库(用历史营养素中位数)+ 5s undo. 失败要让用户感知 (rule#1).
  // 「常吃」也是「我现在又吃了这个」= 现在, 同 recordThenEstimate 在 submit 时现取 todayStr(),
  // 不用回翻过的 selector `date` (数据完整性 belt-and-suspenders).
  const handlePickFrequent = useCallback(async (f: FrequentFood) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    let created: DietRecord;
    try {
      created = await createDietRecord({
        record_date: todayStr(),
        meal_type: f.meal_type,
        food_items: f.food_items,
        calories: f.calories ?? undefined,
        protein: f.protein ?? undefined,
        carbs: f.carbs ?? undefined,
        fat: f.fat ?? undefined,
      });
    } catch {
      toast.show('记录失败,请重试', 'error');
      return;
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    qc.invalidateQueries({ queryKey: ['diet'] });
    setShareImageUriOverride(null);
    setShareRecord(created);
    toast.showUndoable(
      `已记录「${f.food_items.slice(0, 14)}」`,
      async () => {
        try {
          await deleteDietRecord(created.id);
          qc.invalidateQueries({ queryKey: ['diet'] });
          setShareRecord((current) => (current?.id === created.id ? null : current));
        } catch {
          toast.show('撤销失败,请重试', 'error');
        }
      },
      5000,
    );
  }, [qc, toast]);

  const handleEdit = useCallback((r: DietRecord) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    activeDraftRef.current = true;
    setEditingRecord(r);
    setFormDefaults({});
    setQuickDraft(null);
    setDraftEstimateSource(null);
    setShowForm(true);
  }, []);

  const handleDelete = useCallback((r: DietRecord) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const preview = (r.food_items || '').slice(0, 30);
    Alert.alert(
      '删除饮食记录',
      `确定删除 ${MEAL_LABEL[r.meal_type] || r.meal_type}: ${preview} 吗?`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteDietRecord(r.id);
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
              qc.invalidateQueries({ queryKey: ['diet'] });
            } catch {
              Alert.alert('删除失败', '请稍后再试');
            }
          },
        },
      ],
    );
  }, [qc]);

  const handleText = useCallback(() => {
    Alert.prompt('文字记录', '描述你吃的食物（如：鸡胸肉200g + 糙米饭一碗）', (text) => {
      const raw = text?.trim();
      if (!raw) return;
      void openDietDraft(
        { meal_type: guessMealType(), food_items: raw },
        { kind: 'text', description: raw },
      );
    });
  }, [openDietDraft]);

  const handleVoiceText = useCallback(() => {
    Alert.prompt('语音记录饮食', '说完后保留转写文本，例如: "晚饭吃了鸡胸肉和一碗米饭"', (text) => {
      const raw = text?.trim();
      if (!raw) return;
      void openDietDraft(
        { meal_type: guessMealType(), food_items: raw },
        { kind: 'voice', rawText: raw },
      );
    });
  }, [openDietDraft]);

  const recognizeDietPhoto = useCallback(async (asset: ImagePickerAsset) => {
    const recognitionStartedAt = Date.now();
    let clientPrepareMs = 0;
    let payloadBytes = 0;
    let preparedImage: PreparedUploadImage | null = null;
    const elapsedSinceRecognition = () => Date.now() - recognitionStartedAt;
    try {
      setPhotoCaptureStage('preparing');
      const prepareStartedAt = Date.now();
      preparedImage = await prepareImageForUploadSafe(asset);
      clientPrepareMs = Date.now() - prepareStartedAt;
      if (!preparedImage) {
        setPhotoCaptureStage('failed');
        void emitClientEvent('diet_photo_recognition_terminal', {
          phase: 'failed', duration_ms: elapsedSinceRecognition(),
          client_prepare_ms: clientPrepareMs, payload_bytes: 0,
          food_count: 0, table_calibrated_count: 0, error_code: 'image_prepare_failed',
        });
        Alert.alert('照片处理失败', '请换一张清晰、完整的餐食照片。');
        return;
      }
      const imageBase64 = preparedImage.base64;
      payloadBytes = base64DecodedByteLength(imageBase64);
      setPhotoCaptureStage('recognizing');
      const recognized = await recognizeFood(imageBase64);
      if (!recognized.success) {
        setPhotoCaptureStage('failed');
        Alert.alert('识别失败', recognized.error || '没有识别出可记录的餐食,请换一张照片或改用文字记录。');
        void emitClientEvent('diet_photo_recognition_terminal', {
          phase: 'failed', duration_ms: elapsedSinceRecognition(),
          server_total_ms: recognized.timing_ms?.total,
          client_prepare_ms: clientPrepareMs, payload_bytes: payloadBytes,
          food_count: 0, table_calibrated_count: 0, error_code: 'recognition_failed',
        });
        return;
      }
      const description = recognized.meal_description
        || (recognized.foods ?? []).map((food) => food.name).filter(Boolean).join(' + ');
      if (!description) {
        setPhotoCaptureStage('failed');
        Alert.alert('识别失败', '没有识别出可记录的餐食,请换一张照片或改用文字记录。');
        void emitClientEvent('diet_photo_recognition_terminal', {
          phase: 'failed', duration_ms: elapsedSinceRecognition(),
          server_total_ms: recognized.timing_ms?.total,
          client_prepare_ms: clientPrepareMs, payload_bytes: payloadBytes,
          food_count: 0, table_calibrated_count: 0, error_code: 'empty_recognition',
        });
        return;
      }
      void emitClientEvent('diet_photo_recognition_terminal', {
        phase: 'completed',
        duration_ms: elapsedSinceRecognition(),
        server_total_ms: recognized.timing_ms?.total,
        client_prepare_ms: clientPrepareMs,
        payload_bytes: payloadBytes,
        food_count: recognized.foods.length,
        table_calibrated_count: recognized.foods.filter(food => food.nutrition_basis === 'food_table').length,
      });
      const draftConfidence = normalizedDraftConfidence(recognized.ai_confidence ?? recognized.confidence)
        ?? averageRecognitionConfidence(recognized.foods)
        ?? null;
      const photoDraftNeedsReview = recognized.foods.some(foodNeedsPortionReview)
        || (draftConfidence !== null && draftConfidence < 0.7);
      await openDietDraft({
        meal_type: guessMealType(),
        food_items: description,
        food_id: recognized.foods.length === 1 ? recognized.foods[0].food_id ?? undefined : undefined,
        source: recognitionNutritionSource(recognized.foods),
        calories: recognized.total_calories ?? undefined,
        protein: recognized.total_protein ?? undefined,
        carbs: recognized.total_carbs ?? undefined,
        fat: recognized.total_fat ?? undefined,
        fiber: recognized.total_fiber ?? undefined,
        image_base64: recognized.photo_draft_token ? undefined : imageBase64,
        image_type: 'jpeg',
        photo_draft_token: recognized.photo_draft_token ?? undefined,
        idempotency_key: recognized.photo_draft_token
          ? `diet-photo:${recognized.photo_draft_token}`
          : undefined,
        ai_recognized: 1,
        ai_confidence: draftConfidence ?? undefined,
        ai_raw_result: recognized,
        health_tips: recognized.health_tips ?? undefined,
      }, { kind: 'photo', imageBase64, imageUri: asset.uri ?? preparedImage.uri }, photoDraftNeedsReview ? '已识别餐食,核对后写入' : '已识别餐食,确认后写入');
      setPhotoCaptureStage('draft_ready');
    } catch {
      setPhotoCaptureStage('failed');
      void emitClientEvent('diet_photo_recognition_terminal', {
        phase: 'failed', duration_ms: elapsedSinceRecognition(),
        client_prepare_ms: clientPrepareMs, payload_bytes: payloadBytes,
        food_count: 0, table_calibrated_count: 0, error_code: 'capture_pipeline_failed',
      });
      Alert.alert('照片识别失败', '请稍后重试');
    } finally {
      await cleanupPreparedUploadImages([preparedImage]);
    }
  }, [openDietDraft]);

  const handlePhotoLibrary = useCallback(async () => {
    const selectionStartedAt = Date.now();
    try {
      setPhotoCaptureStage('selecting');
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsMultipleSelection: false,
        ...imagePickerEncodingOptions(),
      });
      if (result.canceled || !result.assets[0]) {
        setPhotoCaptureStage('idle');
        void emitClientEvent('diet_photo_recognition_terminal', {
          phase: 'cancelled', duration_ms: Date.now() - selectionStartedAt,
          food_count: 0, table_calibrated_count: 0,
        });
        return;
      }
      await recognizeDietPhoto(result.assets[0]);
    } catch {
      setPhotoCaptureStage('failed');
      void emitClientEvent('diet_photo_recognition_terminal', {
        phase: 'failed', duration_ms: Date.now() - selectionStartedAt,
        food_count: 0, table_calibrated_count: 0, error_code: 'photo_library_failed',
      });
      Alert.alert('选择照片失败', '请稍后重试');
    }
  }, [recognizeDietPhoto]);

  const handlePhoto = useCallback(async () => {
    const captureStartedAt = Date.now();
    try {
      setPhotoCaptureStage('capturing');
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        setPhotoCaptureStage('idle');
        Alert.alert('需要相机权限', '请在设置中开启相机权限');
        void emitClientEvent('diet_photo_recognition_terminal', {
          phase: 'cancelled', duration_ms: Date.now() - captureStartedAt,
          food_count: 0, table_calibrated_count: 0, error_code: 'camera_permission_denied',
        });
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ['images'],
        ...imagePickerEncodingOptions(),
      });
      if (result.canceled || !result.assets[0]) {
        setPhotoCaptureStage('idle');
        void emitClientEvent('diet_photo_recognition_terminal', {
          phase: 'cancelled', duration_ms: Date.now() - captureStartedAt,
          food_count: 0, table_calibrated_count: 0,
        });
        return;
      }
      await recognizeDietPhoto(result.assets[0]);
    } catch {
      setPhotoCaptureStage('failed');
      void emitClientEvent('diet_photo_recognition_terminal', {
        phase: 'failed', duration_ms: Date.now() - captureStartedAt,
        food_count: 0, table_calibrated_count: 0, error_code: 'camera_capture_failed',
      });
      Alert.alert('拍照失败', '请稍后重试');
    }
  }, [recognizeDietPhoto]);

  useEffect(() => {
    if (!photoDraftRestoreReady || quickDraft) return;
    if (captureConsumedRef.current || firstParam(params.draft) === 'diet') return;
    const captureMode = firstParam(params.capture);
    if (!captureMode) return;
    captureConsumedRef.current = true;
    if (captureMode === 'photo') {
      handlePhoto();
    } else if (captureMode === 'library') {
      handlePhotoLibrary();
    } else if (captureMode === 'text') {
      handleText();
    } else if (captureMode === 'voice') {
      handleVoiceText();
    } else {
      captureConsumedRef.current = false;
    }
  }, [
    handlePhoto,
    handlePhotoLibrary,
    handleText,
    handleVoiceText,
    params.capture,
    params.draft,
    photoDraftRestoreReady,
    quickDraft,
  ]);

  useEffect(() => {
    if (firstParam(params.draft) !== 'diet' || draftConsumedRef.current) return;
    const foodItems = readRouteText(params.food_items);
    if (!foodItems) return;
    draftConsumedRef.current = true;
    try {
      assertDietFoodItemsAllowed(foodItems);
    } catch (error) {
      const alert = alertForDietFoodItemsError(error);
      Alert.alert(alert.title, alert.message);
      return;
    }
    setDate(todayStr());
    setEditingRecord(null);
    setQuickDraft(null);
    setDraftEstimateSource(null);
    setFormDefaults({
      meal_type: readRouteMealType(params.meal_type) ?? guessMealType(),
      food_items: foodItems,
      calories: readRouteNumber(params.calories),
      protein: readRouteNumber(params.protein),
      carbs: readRouteNumber(params.carbs),
      fat: readRouteNumber(params.fat),
    });
    setShowForm(true);
  }, [
    params.calories,
    params.carbs,
    params.draft,
    params.fat,
    params.food_items,
    params.meal_type,
    params.protein,
  ]);

  useEffect(() => {
    const routeDate = readRouteDate(params.date);
    if (routeDate && routeDate !== date) {
      setDate(routeDate);
    }
  }, [date, params.date]);

  // 进入/刷新时对账: 任何 calories==null 的当日记录 (含上次中途退出卡住的),
  // 若本会话尚未跑过 → 用已知来源或文字兜底自动重试一次. 不让一餐永远空着.
  useEffect(() => {
    const meals = daily?.meals;
    if (!meals || date !== todayStr()) return;
    for (const r of meals) {
      if (!isPendingNutrition(r)) { reconciledRef.current.delete(r.id); continue; }
      if (pendingIds.has(r.id) || failedIds.has(r.id) || reconciledRef.current.has(r.id)) continue;
      reconciledRef.current.add(r.id);
      const source = sourceMapRef.current.get(r.id)
        ?? { kind: 'text', description: r.food_items } as EstimateSource;
      estimate(r.id, source);
    }
  }, [daily?.meals, date, estimate, pendingIds, failedIds]);

  const meals = daily?.meals ?? EMPTY_MEALS;

  useEffect(() => {
    const targetId = readRoutePositiveInt(params.share_record_id);
    if (!targetId || shareRecordParamConsumedRef.current === String(targetId)) return;
    const record = meals.find(item => item.id === targetId);
    if (!record) return;
    shareRecordParamConsumedRef.current = String(targetId);
    setShareImageUriOverride(null);
    setShareRecord(record);
  }, [meals, params.share_record_id]);

  const totals = useMemo(() => computeDietTotals(meals), [meals]);
  const isToday = date === todayStr();
  const dateLabel = isToday ? '今天' : new Date(date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' });
  const photoCaptureBusy = BUSY_PHOTO_CAPTURE_STAGES.has(photoCaptureStage);
  const showPhotoCaptureStatus = !showForm && !quickDraft && (photoCaptureBusy || photoCaptureStage === 'failed');
  const showDietFab = !showForm && !quickDraft && !photoCaptureBusy && photoCaptureStage !== 'failed';
  const shareImageSource = shareRecord
    ? buildChatImageSource(
      absoluteApiAssetUrl(dietRecordImageUrls(shareRecord)[0]) ?? shareImageUriOverride ?? '',
      authToken,
    )
    : undefined;

  const handleChatDiet = useCallback(() => {
    if (!daily) return;
    pushChatWithContext(router, {
      prompt: `${dateLabel}饮食结构怎么样? 蛋白质够吗? 帮我给出下一餐调整建议。`,
      context: createDietAgentContext(daily),
      badge: `基于${dateLabel}饮食 ${daily.meals_count ?? daily.meals?.length ?? 0} 餐`,
    });
  }, [daily, dateLabel, router]);

  const handleAskRevaFromShare = useCallback((record: DietRecord) => {
    const baseContext = daily
      ? createDietAgentContext(daily)
      : {
        from: `diet/${record.record_date}`,
        date: record.record_date,
        totals: null,
        meals: [],
      };
    pushChatWithContext(router, {
      prompt: POST_CONFIRM_DIET_REVIEW_PROMPT,
      context: {
        ...baseContext,
        ...buildPostConfirmDietReviewContext(record),
        just_recorded: {
          id: record.id,
          record_date: record.record_date,
          meal_type: record.meal_type,
          food_items: record.food_items,
          calories: record.calories ?? null,
          protein: record.protein ?? null,
          carbs: record.carbs ?? null,
          fat: record.fat ?? null,
          fiber: record.fiber ?? null,
          source: record.source ?? null,
        },
      },
      badge: '今日饮食复盘',
    });
    setShareRecord(null);
    setShareImageUriOverride(null);
  }, [daily, router]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>饮食记录</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Date selector */}
      <View style={styles.dateRow}>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, -1))}>
          <Ionicons name="chevron-back-circle-outline" size={28} color={C.ink2} />
        </TouchableOpacity>
        <Text style={txt.dateText}>{dateLabel}</Text>
        <TouchableOpacity onPress={() => setDate(d => offsetDate(d, 1))} disabled={isToday}>
          <Ionicons name="chevron-forward-circle-outline" size={28} color={isToday ? C.ink4 : C.ink2} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={C.green500} />}
        showsVerticalScrollIndicator={false}>

        {/* Summary — pending 记录不计入, 单独标注 (不假装成功) */}
        {daily && (
          <>
            <View style={styles.summaryCard}>
              <NutriPill label="热量" value={`${totals.calories.toFixed(0)}`} unit="kcal" color="#FF6723" />
              <NutriPill label="蛋白质" value={`${totals.protein.toFixed(1)}`} unit="g" color="#FF375F" />
              <NutriPill label="碳水" value={`${totals.carbs.toFixed(1)}`} unit="g" color="#FF9F0A" />
              <NutriPill label="脂肪" value={`${totals.fat.toFixed(1)}`} unit="g" color="#BF5AF2" />
            </View>
            {totals.pendingMeals > 0 && (
              <Text style={txt.pendingNote}>含 {totals.pendingMeals} 项营养估算中,暂未计入总量</Text>
            )}
          </>
        )}
        {daily && (
          <TouchableOpacity
            style={[styles.agentLink, { borderColor: C.line }]}
            onPress={handleChatDiet}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="跟小巴详细聊今日饮食"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={16} color={C.green500} />
            <Text style={[txt.agentLinkText, { color: C.green500 }]}>跟小巴详细聊{dateLabel}饮食</Text>
            <Ionicons name="chevron-forward" size={15} color={C.green500} style={{ marginLeft: 'auto' }} />
          </TouchableOpacity>
        )}

        {/* 常吃一键复用 (P1-b): 不在编辑/表单态时显示 */}
        {!showForm && !quickDraft && (
          <FrequentFoodsRow
            foods={frequentQuery.data ?? []}
            onPick={handlePickFrequent}
          />
        )}

        {showPhotoCaptureStatus && (
          <PhotoCaptureStatusCard
            stage={photoCaptureStage}
            slowRecognition={photoRecognitionSlow}
            onRetryPhoto={handlePhoto}
            onPickLibrary={handlePhotoLibrary}
            onManualText={handleText}
          />
        )}

        {quickDraft && !showForm && (
          <QuickDietDraftCard
            draft={quickDraft.record}
            onConfirm={handleConfirmQuickDraft}
            onRevise={handleReviseQuickDraft}
            onCancel={handleCancelQuickDraft}
            isSaving={quickDraftSaving}
          />
        )}

        {/* Meal form */}
        {showForm && (
          <MealForm date={date}
            initialRecord={editingRecord || undefined}
            initialMealType={formDefaults.meal_type}
            assistiveHint={quickDraftNeedsReview(formDefaults) ? PORTION_REVIEW_ASSISTIVE_HINT : undefined}
            onSubmit={handleSave}
            onCancel={handleCancelForm}
            initialDescription={formDefaults.food_items}
            initialCalories={formDefaults.calories}
            initialProtein={formDefaults.protein}
            initialCarbs={formDefaults.carbs}
            initialFat={formDefaults.fat} />
        )}

        {/* Meal records — 左滑暴露 编辑 + 删除 */}
        {meals.length > 0 ? (
          meals.map((r) => {
            const pending = isPendingNutrition(r);
            const isEstimating = pendingIds.has(r.id);
            const failed = failedIds.has(r.id);
            const imageUrls = dietRecordImageUrls(r);
            const primaryImageUrl = absoluteApiAssetUrl(imageUrls[0]);
            return (
              <ReanimatedSwipeable
                key={r.id}
                friction={2}
                rightThreshold={40}
                renderRightActions={() => (
                  <View style={styles.swipeActions}>
                    <TouchableOpacity
                      style={[styles.swipeBtn, { backgroundColor: C.green500 }]}
                      onPress={() => handleEdit(r)}
                      activeOpacity={0.85}
                      accessibilityLabel="编辑"
                    >
                      <Ionicons name="pencil" size={18} color="#fff" />
                      <Text style={txt.swipeText}>编辑</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.swipeBtn, { backgroundColor: revaSemantic.risk.fg }]}
                      onPress={() => handleDelete(r)}
                      activeOpacity={0.85}
                      accessibilityLabel="删除"
                    >
                      <Ionicons name="trash" size={18} color="#fff" />
                      <Text style={txt.swipeText}>删除</Text>
                    </TouchableOpacity>
                  </View>
                )}
              >
                <View style={styles.mealRow}>
                  <View style={styles.mealDot} />
                  {primaryImageUrl ? (
                    <View style={styles.mealPhotoWrap} accessibilityLabel={`本餐包含 ${imageUrls.length} 张照片`}>
                      <Image
                        source={{ uri: primaryImageUrl }}
                        style={styles.mealPhoto}
                        contentFit="cover"
                        transition={120}
                        accessibilityLabel="饮食记录照片"
                      />
                      {imageUrls.length > 1 ? (
                        <View style={styles.mealPhotoCount}>
                          <Text style={txt.mealPhotoCount}>+{imageUrls.length - 1}</Text>
                        </View>
                      ) : null}
                    </View>
                  ) : null}
                  <View style={{ flex: 1 }}>
                    <Text style={txt.mealType}>{MEAL_LABEL[r.meal_type] || r.meal_type}</Text>
                    <Text style={txt.mealFood} numberOfLines={2}>{r.food_items}</Text>
                  </View>
                  {pending ? (
                    failed && !isEstimating ? (
                      <TouchableOpacity
                        style={styles.retryBtn}
                        onPress={() => retryEstimate(r)}
                        activeOpacity={0.7}
                        accessibilityRole="button"
                        accessibilityLabel="营养估算失败,点击重试"
                      >
                        <Ionicons name="refresh" size={13} color={revaSemantic.risk.fg} />
                        <Text style={[txt.retryText, { color: revaSemantic.risk.fg }]}>估算失败 · 重试</Text>
                      </TouchableOpacity>
                    ) : (
                      <View style={styles.pendingChip}>
                        <ActivityIndicator size="small" color={C.ink3} />
                        <Text style={txt.pendingChipText}>估算中…</Text>
                      </View>
                    )
                  ) : (
                    <View style={styles.mealTail}>
                      <Text style={txt.mealCal}>{r.calories != null ? `${Math.round(r.calories)}kcal` : ''}</Text>
                      <TouchableOpacity
                        style={styles.mealShareButton}
                        onPress={() => {
                          setShareImageUriOverride(null);
                          setShareRecord(r);
                        }}
                        activeOpacity={0.72}
                        accessibilityRole="button"
                        accessibilityLabel={`分享${MEAL_LABEL[r.meal_type] ?? '这餐'}饮食`}
                      >
                        <Ionicons name="share-outline" size={16} color={C.green600} />
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              </ReanimatedSwipeable>
            );
          })
        ) : (
          <Text style={txt.empty}>{date === todayStr() ? '今天还没有饮食记录' : '当日无记录'}</Text>
        )}

        <View style={{ height: 140 }} />
      </ScrollView>

      {showDietFab ? (
        <DietFAB onPhoto={handlePhoto} onLibrary={handlePhotoLibrary} onText={handleText} onVoice={handleVoiceText} />
      ) : null}
      {shareRecord ? (
        <DietShareSheet
          visible
          record={shareRecord}
          dateLabel={`${shareRecord.record_date.replace(/-/g, '.')} · ${MEAL_LABEL[shareRecord.meal_type] ?? '餐食'}`}
          imageSource={shareImageSource}
          onClose={() => {
            setShareRecord(null);
            setShareImageUriOverride(null);
          }}
          onAskReva={() => handleAskRevaFromShare(shareRecord)}
          onShareTerminal={(meta) => {
            void emitClientEvent('diet_share_terminal', meta);
          }}
          onShareFeedback={(hint) => {
            toast.show(hint.title, hint.tone === 'success' ? 'success' : 'error');
          }}
        />
      ) : null}
    </SafeAreaView>
  );
}

function NutriPill({ label, value, unit, color }: { label: string; value: string; unit: string; color: string }) {
  return (
    <View style={styles.nutriItem}>
      <Text style={[txt.nutriVal, { color }]}>{value}</Text>
      <Text style={txt.nutriUnit}>{unit}</Text>
      <Text style={txt.nutriLabel}>{label}</Text>
    </View>
  );
}

function PhotoCaptureStatusCard({
  stage,
  slowRecognition = false,
  onRetryPhoto,
  onPickLibrary,
  onManualText,
}: {
  stage: PhotoCaptureStage;
  slowRecognition?: boolean;
  onRetryPhoto?: () => void;
  onPickLibrary?: () => void;
  onManualText?: () => void;
}) {
  const failed = stage === 'failed';
  const label = stage === 'saving'
    ? '正在保存饮食'
    : failed
      ? '照片识别失败'
    : stage === 'capturing'
      ? '正在打开相机'
      : stage === 'selecting'
        ? '正在打开相册'
      : stage === 'preparing'
        ? '正在优化照片'
        : '正在识别餐食';
  const detail = stage === 'saving'
    ? '保存成功后会立即更新今日饮食进度。'
    : failed
      ? '换一张照片、从相册选择，或直接手动录入，不会重复提交。'
    : slowRecognition && stage === 'recognizing'
      ? '仍在识别照片；完成后会先给你确认草稿，不会自动写入。'
    : '识别完成后先给你确认草稿，不会自动写入。';
  const activeIndex = stage === 'saving'
    ? PHOTO_CAPTURE_STEPS.length
    : stage === 'recognizing'
      ? 1
    : stage === 'preparing'
      ? 0
      : 0;
  return (
    <View style={styles.photoStatusCard}>
      {failed ? (
        <View style={styles.photoStatusFailedIcon}>
          <Ionicons name="refresh" size={16} color={revaSemantic.caution.fg} />
        </View>
      ) : (
        <ActivityIndicator size="small" color={C.green500} />
      )}
      <View style={{ flex: 1 }}>
        <Text style={txt.photoStatusTitle}>{label}</Text>
        <Text style={txt.photoStatusDetail}>{detail}</Text>
        {!failed ? (
          <View style={styles.photoStatusSteps}>
            {PHOTO_CAPTURE_STEPS.map((step, index) => {
              const completed = activeIndex > index;
              const active = activeIndex === index;
              return (
                <View
                  key={step.key}
                  style={[
                    styles.photoStatusStep,
                    completed && styles.photoStatusStepDone,
                    active && styles.photoStatusStepActive,
                  ]}
                >
                  <View
                    style={[
                      styles.photoStatusStepDot,
                      completed && styles.photoStatusStepDotDone,
                      active && styles.photoStatusStepDotActive,
                    ]}
                  />
                  <Text
                    style={[
                      txt.photoStatusStepText,
                      completed && txt.photoStatusStepTextDone,
                      active && txt.photoStatusStepTextActive,
                    ]}
                  >
                    {step.label}
                  </Text>
                </View>
              );
            })}
          </View>
        ) : (
          <View style={styles.photoRecoveryRow}>
            <TouchableOpacity
              style={[styles.photoRecoveryBtn, styles.photoRecoveryBtnPrimary]}
              onPress={onRetryPhoto}
              activeOpacity={0.78}
              accessibilityRole="button"
              accessibilityLabel="重新拍照记录饮食"
            >
              <Ionicons name="camera-outline" size={14} color={C.surface} />
              <Text style={txt.photoRecoveryPrimaryText}>重新拍照</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.photoRecoveryBtn}
              onPress={onPickLibrary}
              activeOpacity={0.78}
              accessibilityRole="button"
              accessibilityLabel="从相册重新选择饮食照片"
            >
              <Ionicons name="images-outline" size={14} color={C.green700} />
              <Text style={txt.photoRecoveryText}>相册</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.photoRecoveryBtn}
              onPress={onManualText}
              activeOpacity={0.78}
              accessibilityRole="button"
              accessibilityLabel="手动录入饮食"
            >
              <Ionicons name="create-outline" size={14} color={C.green700} />
              <Text style={txt.photoRecoveryText}>手动录入</Text>
            </TouchableOpacity>
          </View>
        )}
        {slowRecognition && stage === 'recognizing' ? (
          <Text style={txt.photoStatusTrust}>深度识别中，不会重复提交</Text>
        ) : null}
      </View>
    </View>
  );
}

function QuickDietDraftCard({
  draft,
  onConfirm,
  onRevise,
  onCancel,
  isSaving = false,
}: {
  draft: DietRecordCreate;
  onConfirm: () => void;
  onRevise: () => void;
  onCancel: () => void;
  isSaving?: boolean;
}) {
  const calories = formatDraftMetric(draft.calories);
  const protein = formatDraftMetric(draft.protein);
  const carbs = formatDraftMetric(draft.carbs);
  const fat = formatDraftMetric(draft.fat);
  const primaryMetrics = [
    calories ? `${calories} kcal` : null,
    protein ? `蛋白 ${protein}g` : null,
  ].filter(Boolean).join(' · ');
  const secondaryMetrics = [
    carbs ? `碳水 ${carbs}g` : null,
    fat ? `脂肪 ${fat}g` : null,
  ].filter(Boolean).join(' · ');
  const recognizedFoods = draft.ai_raw_result?.foods ?? [];
  const reviewItemCount = recognizedFoods.filter(foodNeedsPortionReview).length;
  const needsWholeReview = quickDraftNeedsWholeReview(draft);
  const needsReview = reviewItemCount > 0 || needsWholeReview;
  const hasNutritionEstimate = [draft.calories, draft.protein, draft.carbs, draft.fat, draft.fiber]
    .some((value) => typeof value === 'number' && Number.isFinite(value));
  const nutritionStatusText = hasNutritionEstimate
    ? (needsReview ? '已带营养估算，核对后计入今日' : '已带营养估算，确认后计入今日')
    : '确认后先记录，营养后台估算';
  const reviewHint = buildQuickDraftReviewHint(draft);
  const reviseLabel = quickDraftReviseLabel(draft);
  const recognitionTotalSeconds = formatTimingSeconds(draft.ai_raw_result?.timing_ms?.total);
  const calibrationSeconds = formatTimingSeconds(draft.ai_raw_result?.timing_ms?.calibration);
  const showRecognitionTiming = Boolean(recognitionTotalSeconds || calibrationSeconds);
  const confirmLabel = needsReview ? '核对后确认' : '确认记录';
  const primaryAccessibilityLabel = needsReview ? '核对后确认饮食' : '确认记录饮食';
  const sharePromiseText = needsReview
    ? '核对后自动生成微信 / 小红书分享图'
    : '确认后自动生成微信 / 小红书分享图';

  return (
    <View style={styles.quickDraftCard}>
      <View style={styles.quickDraftHeader}>
        <View style={styles.quickIcon}>
          <Ionicons name="sparkles" size={17} color={C.green500} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={txt.quickOverline}>草稿待确认</Text>
          <Text style={txt.quickTitle}>待确认饮食</Text>
        </View>
        <View style={styles.quickMealChip}>
          <Text style={txt.quickMealChipText}>{MEAL_LABEL[draft.meal_type] ?? '餐食'}</Text>
        </View>
      </View>

      <Text style={txt.quickFood}>{draft.food_items}</Text>
      {primaryMetrics ? <Text style={txt.quickMacro}>{primaryMetrics}</Text> : null}
      {secondaryMetrics ? <Text style={txt.quickMacroMuted}>{secondaryMetrics}</Text> : null}
      {reviewItemCount > 0 ? (
        <TouchableOpacity
          style={styles.quickReviewSummary}
          onPress={onRevise}
          activeOpacity={0.78}
          accessibilityRole="button"
          accessibilityLabel="核对饮食份量"
          accessibilityHint="打开修正表单，优先核对食物份量"
        >
          <Ionicons name="alert-circle-outline" size={14} color={revaSemantic.caution.fg} />
          <Text style={txt.quickReviewSummaryStrong}>{reviewItemCount} 项需核对</Text>
          <Text style={txt.quickReviewSummaryText}>重点核对份量</Text>
        </TouchableOpacity>
      ) : needsWholeReview ? (
        <TouchableOpacity
          style={styles.quickReviewSummary}
          onPress={onRevise}
          activeOpacity={0.78}
          accessibilityRole="button"
          accessibilityLabel="核对整餐识别结果"
          accessibilityHint="打开修正表单，核对整餐识别结果和份量"
        >
          <Ionicons name="alert-circle-outline" size={14} color={revaSemantic.caution.fg} />
          <Text style={txt.quickReviewSummaryStrong}>整体识别待核对</Text>
          <Text style={txt.quickReviewSummaryText}>先核对食物和份量</Text>
        </TouchableOpacity>
      ) : null}
      {recognizedFoods.length > 0 ? (
        <View style={styles.recognitionDetail}>
          <View style={styles.recognitionDetailHeader}>
            <Text style={txt.recognitionDetailTitle}>识别明细</Text>
            <Text style={txt.recognitionDetailCount}>{recognizedFoods.length} 项</Text>
          </View>
          {recognizedFoods.map((food, index) => (
            <RecognizedFoodRow
              key={`${food.food_id ?? food.name}-${index}`}
              food={food}
              index={index}
              onRevise={onRevise}
            />
          ))}
        </View>
      ) : null}
      {showRecognitionTiming ? (
        <View style={styles.recognitionTimingRow}>
          <Ionicons name="speedometer-outline" size={14} color={C.green600} />
          {recognitionTotalSeconds ? (
            <Text style={txt.recognitionTimingText}>识别完成 · {recognitionTotalSeconds}</Text>
          ) : null}
          {calibrationSeconds ? (
            <Text style={txt.recognitionTimingMuted}>营养校准 {calibrationSeconds}</Text>
          ) : null}
        </View>
      ) : null}
      <View style={styles.quickTrustRow}>
        <Ionicons
          name={hasNutritionEstimate ? 'analytics-outline' : 'time-outline'}
          size={14}
          color={hasNutritionEstimate ? C.green600 : C.ink3}
        />
        <Text style={[txt.quickTrustText, { color: hasNutritionEstimate ? C.green600 : C.ink3 }]}>
          {nutritionStatusText}
        </Text>
      </View>
      <View style={styles.quickSharePromiseRow}>
        <Ionicons name="images-outline" size={14} color={C.green600} />
        <Text style={txt.quickSharePromiseText}>{sharePromiseText}</Text>
      </View>
      {isSaving ? (
        <View style={styles.quickSavingStatusRow}>
          <Ionicons name="cloud-upload-outline" size={14} color={C.green600} />
          <Text style={txt.quickSavingStatusText}>正在写入饮食记录，完成后生成分享图</Text>
        </View>
      ) : null}
      <Text style={txt.quickHint}>{reviewHint}</Text>

      <View style={styles.quickActions}>
        <TouchableOpacity
          style={[styles.quickConfirmBtn, isSaving && styles.quickConfirmBtnDisabled]}
          onPress={onConfirm}
          disabled={isSaving}
          activeOpacity={0.82}
          accessibilityRole="button"
          accessibilityLabel={primaryAccessibilityLabel}
        >
          {isSaving ? (
            <ActivityIndicator size="small" color={C.greenOn} />
          ) : (
            <Ionicons name="checkmark" size={17} color={C.greenOn} />
          )}
          <Text style={txt.quickConfirmText}>{isSaving ? '保存中' : confirmLabel}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickSecondaryBtn}
          onPress={onRevise}
          disabled={isSaving}
          activeOpacity={0.75}
          accessibilityRole="button"
          accessibilityLabel="修正饮食草稿"
        >
          <Text style={txt.quickSecondaryText}>{reviseLabel}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.quickGhostBtn}
          onPress={onCancel}
          disabled={isSaving}
          activeOpacity={0.75}
          accessibilityRole="button"
          accessibilityLabel="取消饮食草稿"
        >
          <Text style={txt.quickGhostText}>取消</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function RecognizedFoodRow({ food, index, onRevise }: { food: FoodItem; index: number; onRevise: () => void }) {
  const isTableCalibrated = food.nutrition_basis === 'food_table';
  const isMixed = food.nutrition_basis === 'mixed';
  const hasQuantity = Boolean(food.quantity?.trim());
  const hasTrustedPortion = food.portion_basis === 'measured' || food.portion_basis === 'label';
  const isEstimatedPortion = hasQuantity && !hasTrustedPortion;
  const needsPortionReview = foodNeedsPortionReview(food);
  const basisLabel = isTableCalibrated
    ? isEstimatedPortion
      ? '表值 × 估算份量'
      : '营养表校准'
    : isMixed
      ? isEstimatedPortion
        ? '部分表值 × 估算'
        : '部分表值校准'
      : '视觉估算';
  const confidence = typeof food.confidence === 'number' && Number.isFinite(food.confidence)
    ? Math.round(food.confidence * 100)
    : null;
  const portionConfidence = typeof food.portion_confidence === 'number' && Number.isFinite(food.portion_confidence)
    ? Math.round(food.portion_confidence * 100)
    : null;
  const identitySignal = confidence === null
    ? null
    : confidence >= 85
      ? '识别较稳'
      : confidence >= 70
        ? '识别一般'
        : '识别待核对';
  const portionSignal = !hasQuantity
    ? '份量待确认'
    : (portionConfidence !== null && portionConfidence < 70) || (confidence !== null && confidence < 70)
      ? '请核对份量'
      : isEstimatedPortion
        ? '份量为估算'
        : null;
  const portionBasisLabel = food.portion_basis === 'vision_estimate'
    ? '视觉估份'
    : food.portion_basis === 'measured'
      ? '称量份量'
      : food.portion_basis === 'label'
        ? '标签份量'
        : food.portion_basis === 'unknown'
          ? '份量来源待核对'
          : null;
  const portionEvidence = portionBasisLabel
    ? portionConfidence !== null
      ? `${portionBasisLabel} ${portionConfidence}%`
      : portionBasisLabel
    : null;
  const basisIsFullyTrusted = isTableCalibrated && hasTrustedPortion;
  const portion = food.quantity?.trim() || '份量待确认';
  const calories = typeof food.calories === 'number' && Number.isFinite(food.calories)
    ? `${Math.round(food.calories)} kcal`
    : '热量待确认';

  const rowContent = (
    <>
      <View style={styles.recognizedFoodMain}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={txt.recognizedFoodName} numberOfLines={2}>{food.name}</Text>
          <Text style={txt.recognizedFoodMeta}>{portion} · {calories}</Text>
        </View>
        <View style={[
          styles.recognitionBasisChip,
          basisIsFullyTrusted ? styles.recognitionBasisTable : styles.recognitionBasisEstimate,
        ]}>
          <Ionicons
            name={basisIsFullyTrusted ? 'shield-checkmark-outline' : 'scan-outline'}
            size={13}
            color={basisIsFullyTrusted ? C.green600 : revaSemantic.caution.fg}
          />
          <Text style={[
            txt.recognitionBasisText,
            { color: basisIsFullyTrusted ? C.green600 : revaSemantic.caution.fg },
          ]}>
            {basisLabel}
          </Text>
        </View>
      </View>
      <View style={styles.recognizedFoodSignals}>
        {identitySignal ? <Text style={txt.recognizedConfidence}>{identitySignal}</Text> : null}
        {portionEvidence ? (
          <View style={styles.portionEvidenceRow}>
            <Ionicons name="resize-outline" size={13} color={C.ink3} />
            <Text style={txt.portionEvidenceText}>{portionEvidence}</Text>
          </View>
        ) : null}
        {portionSignal ? (
          <View style={styles.verifyPortionRow}>
            <Ionicons name="alert-circle-outline" size={13} color={revaSemantic.caution.fg} />
            <Text style={txt.verifyPortionText}>{portionSignal}</Text>
            {needsPortionReview ? (
              <Ionicons name="chevron-forward" size={13} color={revaSemantic.caution.fg} />
            ) : null}
          </View>
        ) : null}
      </View>
    </>
  );

  const rowStyle = [
    styles.recognizedFoodRow,
    needsPortionReview && styles.recognizedFoodRowAction,
    index > 0 && styles.recognizedFoodRowDivided,
  ];

  if (needsPortionReview) {
    return (
      <TouchableOpacity
        style={rowStyle}
        onPress={onRevise}
        activeOpacity={0.78}
        accessibilityRole="button"
        accessibilityLabel={`核对${food.name}份量`}
        accessibilityHint="打开修正表单，优先核对这项食物的份量"
      >
        {rowContent}
      </TouchableOpacity>
    );
  }

  return (
    <View style={rowStyle}>
      {rowContent}
    </View>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-lg 18 / 数字等宽 mono / light-first 软阴影。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2 },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  dateRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, paddingVertical: revaSpacing.s2 },
  content: { padding: revaSpacing.s4 },
  summaryCard: {
    flexDirection: 'row', justifyContent: 'space-around',
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s4, ...revaShadows.sm,
  },
  nutriItem: { alignItems: 'center', gap: 2 },
  mealRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: C.surface, borderRadius: revaRadii.md,
    padding: revaSpacing.s4, marginBottom: revaSpacing.s2, ...revaShadows.sm,
  },
  mealDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: C.green500 },
  mealPhotoWrap: { width: 54, height: 54, position: 'relative' },
  mealPhoto: { width: 54, height: 54, borderRadius: revaRadii.sm, backgroundColor: C.paper2 },
  mealPhotoCount: {
    position: 'absolute', right: -3, bottom: -3,
    minWidth: 19, height: 19, borderRadius: 10,
    paddingHorizontal: 4, alignItems: 'center', justifyContent: 'center',
    backgroundColor: C.green700, borderWidth: 1, borderColor: C.surface,
  },
  pendingChip: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  retryBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: revaRadii.pill, backgroundColor: C.paper,
  },
  swipeActions: {
    flexDirection: 'row', alignItems: 'stretch',
    marginBottom: revaSpacing.s2,
  },
  swipeBtn: {
    width: 76,
    alignItems: 'center', justifyContent: 'center',
    gap: 4,
    marginLeft: 6,
    borderRadius: revaRadii.md,
  },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    marginTop: -revaSpacing.s2,
    marginBottom: revaSpacing.s4,
  },
  quickDraftCard: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    marginBottom: revaSpacing.s4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  photoStatusCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s3,
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    marginBottom: revaSpacing.s4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  photoStatusFailedIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: revaSemantic.caution.bg,
  },
  photoStatusSteps: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: revaSpacing.s3,
  },
  photoStatusStep: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 999,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  photoStatusStepActive: {
    backgroundColor: C.green50,
    borderColor: C.green100,
  },
  photoStatusStepDone: {
    backgroundColor: C.surface,
    borderColor: C.green100,
  },
  photoStatusStepDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: C.ink4,
  },
  photoStatusStepDotActive: {
    backgroundColor: C.green500,
  },
  photoStatusStepDotDone: {
    backgroundColor: C.green300,
  },
  photoRecoveryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: revaSpacing.s3,
  },
  photoRecoveryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minHeight: 34,
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  photoRecoveryBtnPrimary: {
    backgroundColor: C.green600,
    borderColor: C.green600,
  },
  quickDraftHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: revaSpacing.s3 },
  mealTail: { alignItems: 'flex-end', justifyContent: 'center', gap: 7 },
  mealShareButton: {
    width: 32, height: 32, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: C.green50,
  },
  quickIcon: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: C.green50,
    alignItems: 'center', justifyContent: 'center',
  },
  quickMealChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
  },
  recognitionDetail: {
    marginTop: revaSpacing.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  recognitionDetailHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
  },
  recognizedFoodRow: { paddingVertical: revaSpacing.s3 },
  recognizedFoodRowAction: { borderRadius: revaRadii.md },
  recognizedFoodRowDivided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line },
  recognizedFoodMain: { flexDirection: 'row', alignItems: 'flex-start', gap: revaSpacing.s2 },
  recognizedFoodSignals: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginTop: 6,
  },
  quickReviewSummary: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: revaRadii.pill,
    backgroundColor: revaSemantic.caution.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
  },
  recognitionBasisChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 5, borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
  },
  recognitionBasisTable: { backgroundColor: C.green50, borderColor: C.green100 },
  recognitionBasisEstimate: { backgroundColor: revaSemantic.caution.bg, borderColor: revaSemantic.caution.line },
  portionEvidenceRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  verifyPortionRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  recognitionTimingRow: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  quickTrustRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: revaSpacing.s3,
  },
  quickSharePromiseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  quickSavingStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  quickActions: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2, marginTop: revaSpacing.s4 },
  quickConfirmBtn: {
    flex: 1.5,
    minHeight: 42,
    borderRadius: revaRadii.md,
    backgroundColor: C.green500,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  quickConfirmBtnDisabled: {
    opacity: 0.72,
  },
  quickSecondaryBtn: {
    flex: 1,
    minHeight: 42,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quickGhostBtn: {
    minHeight: 42,
    paddingHorizontal: revaSpacing.s3,
    borderRadius: revaRadii.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

// 数字/计数/指标值/单位/日期走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1, textAlign: 'center' } as TextStyle,
  dateText: { fontFamily: revaFonts.mono, fontSize: 16, fontWeight: '600', color: C.ink1 } as TextStyle,
  nutriVal: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  nutriUnit: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink2 } as TextStyle,
  nutriLabel: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 } as TextStyle,
  pendingNote: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, textAlign: 'center', marginTop: -revaSpacing.s3, marginBottom: revaSpacing.s4 } as TextStyle,
  mealType: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.ink1 } as TextStyle,
  mealFood: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, marginTop: 2 } as TextStyle,
  mealPhotoCount: { fontFamily: revaFonts.mono, fontSize: 9, fontWeight: '800', color: C.surface } as TextStyle,
  mealCal: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '600', color: '#FF6723' } as TextStyle,
  pendingChipText: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3 } as TextStyle,
  retryText: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600' } as TextStyle,
  swipeText: { fontFamily: revaFonts.sans, fontSize: 11, color: '#fff', fontWeight: '600' } as TextStyle,
  agentLinkText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600' } as TextStyle,
  photoStatusTitle: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '800', color: C.ink1 } as TextStyle,
  photoStatusDetail: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 2 } as TextStyle,
  photoStatusStepText: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, fontWeight: '700' } as TextStyle,
  photoStatusStepTextActive: { color: C.green700 } as TextStyle,
  photoStatusStepTextDone: { color: C.green600 } as TextStyle,
  photoStatusTrust: { fontFamily: revaFonts.sans, fontSize: 11, color: C.green700, fontWeight: '700', marginTop: 8 } as TextStyle,
  photoRecoveryText: { fontFamily: revaFonts.sans, fontSize: 12, color: C.green700, fontWeight: '800' } as TextStyle,
  photoRecoveryPrimaryText: { fontFamily: revaFonts.sans, fontSize: 12, color: C.surface, fontWeight: '900' } as TextStyle,
  quickOverline: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, fontWeight: '700' } as TextStyle,
  quickTitle: { fontFamily: revaFonts.sans, fontSize: 17, color: C.ink1, fontWeight: '800', marginTop: 2 } as TextStyle,
  quickMealChipText: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, fontWeight: '700' } as TextStyle,
  quickFood: { fontFamily: revaFonts.sans, fontSize: 16, lineHeight: 22, color: C.ink1, fontWeight: '700' } as TextStyle,
  quickMacro: { fontFamily: revaFonts.mono, fontSize: 14, color: C.ink1, fontWeight: '700', marginTop: revaSpacing.s2 } as TextStyle,
  quickMacroMuted: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3, marginTop: 2 } as TextStyle,
  quickReviewSummaryStrong: { fontFamily: revaFonts.sans, fontSize: 11, color: revaSemantic.caution.fg, fontWeight: '900' } as TextStyle,
  quickReviewSummaryText: { fontFamily: revaFonts.sans, fontSize: 10.5, color: C.ink3, fontWeight: '800' } as TextStyle,
  recognitionDetailTitle: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, fontWeight: '800' } as TextStyle,
  recognitionDetailCount: { fontFamily: revaFonts.mono, fontSize: 11, color: C.ink3 } as TextStyle,
  recognizedFoodName: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 19, color: C.ink1, fontWeight: '700' } as TextStyle,
  recognizedFoodMeta: { fontFamily: revaFonts.mono, fontSize: 11, color: C.ink3, marginTop: 3 } as TextStyle,
  recognitionBasisText: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '800' } as TextStyle,
  recognizedConfidence: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3 } as TextStyle,
  portionEvidenceText: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3, fontWeight: '700' } as TextStyle,
  verifyPortionText: { fontFamily: revaFonts.sans, fontSize: 10, color: revaSemantic.caution.fg, fontWeight: '700' } as TextStyle,
  recognitionTimingText: { fontFamily: revaFonts.sans, fontSize: 11, color: C.green700, fontWeight: '900' } as TextStyle,
  recognitionTimingMuted: { fontFamily: revaFonts.sans, fontSize: 10.5, color: C.ink3, fontWeight: '700' } as TextStyle,
  quickTrustText: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, fontWeight: '800' } as TextStyle,
  quickSharePromiseText: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, color: C.green700, fontWeight: '800' } as TextStyle,
  quickSavingStatusText: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, color: C.green700, fontWeight: '800' } as TextStyle,
  quickHint: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, color: C.ink3, marginTop: revaSpacing.s3 } as TextStyle,
  quickConfirmText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.greenOn, fontWeight: '800' } as TextStyle,
  quickSecondaryText: { fontFamily: revaFonts.sans, fontSize: 14, color: C.green600, fontWeight: '800' } as TextStyle,
  quickGhostText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink3, fontWeight: '700' } as TextStyle,
  empty: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3, textAlign: 'center', paddingVertical: 30 } as TextStyle,
};
