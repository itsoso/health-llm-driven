/**
 * 动态卡片注册表 + 派发逻辑
 *
 * 用法:
 *   // 1. 聊天结束时:
 *   const card = await dispatchCard(ctx);
 *   if (card) setMessages(prev => [...prev, cardMessage(card)]);
 *
 *   // 2. 后端主动下发 (SSE done 事件里的 cards 字段):
 *   const card = renderServerCard(descriptor);
 */
import React from 'react';
import { View, Dimensions, Pressable, StyleSheet, Text, ActivityIndicator } from 'react-native';
import type {
  CardRenderOptions,
  CardSpec,
  CardContext,
  ChatCardActionDescriptor,
  ChatCardActionRuntimeState,
  ServerCardDescriptor,
} from './types';
import { serverCardIdentity, stableServerCardId } from './cardIdentity';
import { revaColors as C, revaRadii, revaSemantic } from '../../../constants/revaTheme';
import { isSafeInternalRoute } from '../../../utils/internalRoutes';

import { VitalsCardSpec } from './VitalsCard';
import { SleepCardSpec } from './SleepCard';
import { WeightCardSpec } from './WeightCard';
import { SupplementCardSpec } from './SupplementCard';
import { WeatherCardSpec } from './WeatherCard';
import { BPCardSpec } from './BPCard';
import { ScoreCardSpec } from './ScoreCard';
import { RecordCardSpec } from './RecordCard';
import { RecordQualityCardSpec } from './RecordQualityCard';
import { MedicationDraftCardSpec } from './MedicationDraftCard';
import { SupplementDraftCardSpec } from './SupplementDraftCard';
import { DietCardSpec } from './DietCard';
import { DietDraftCardSpec } from './DietDraftCard';
import { WorkoutCardSpec } from './WorkoutCard';
import { MedicalReportCardSpec } from './MedicalReportCard';
import { MedicalExamImportResultCardSpec } from './MedicalExamImportResultCard';
import { MenuShareCardSpec } from './MenuShareCard';
import { SystemKnowledgeEvidenceCardSpec } from './SystemKnowledgeEvidenceCard';
import { RuntimeAgendaCardSpec } from './RuntimeAgendaCard';
import { OperatingReviewCardSpec } from './OperatingReviewCard';
import { MetricChartCardSpec, MetricEmptyStateCardSpec, MetricLineChartCardSpec, RevaUiLineChartCardSpec } from './MetricChartCard';
import { MetricTableCardSpec } from './MetricTableCard';
import { DietSummaryCardSpec } from './DietSummaryCard';
import { SleepSummaryCardSpec } from './SleepSummaryCard';
import { MedicationListCardSpec } from './MedicationListCard';
import { DiscoveryCardSpec } from './DiscoveryCard';
import { SafetyCardSpec } from './SafetyCard';
import { SaveRecipeCardSpec } from './SaveRecipeCard';
import { AIGCMediaJobCardSpec } from './AIGCMediaJobCard';
import { AIGCMediaConfirmationCardSpec } from './AIGCMediaConfirmationCard';

/** 全量卡片注册表. 数组前面的优先级越高时越靠前 (便于可读), 实际按 match() 返回值排序 */
export const CARD_REGISTRY: CardSpec[] = [
  RecordCardSpec,      // 记录类优先 - 避免被分析类误触
  RecordQualityCardSpec,
  MedicationDraftCardSpec,
  SupplementDraftCardSpec,
  DietDraftCardSpec,
  SleepCardSpec,
  WeightCardSpec,
  BPCardSpec,
  SupplementCardSpec,
  DietCardSpec,
  WorkoutCardSpec,
  MedicalExamImportResultCardSpec,
  MedicalReportCardSpec,
  SystemKnowledgeEvidenceCardSpec,
  RuntimeAgendaCardSpec,
  OperatingReviewCardSpec,
  MetricEmptyStateCardSpec,
  MetricLineChartCardSpec,
  RevaUiLineChartCardSpec,
  MetricChartCardSpec,
  MetricTableCardSpec, // 仅后端下发 (reva-ui fence, cap 点亮后)
  DietSummaryCardSpec, // 汇总类卡 v1 · 仅后端下发 (reva-ui fence, cap 点亮后)
  SleepSummaryCardSpec, // 汇总卡族·睡眠 · 仅后端下发 (reva-ui fence, cap 点亮后)
  MedicationListCardSpec, // 汇总卡族·在用药物 · 仅后端下发 (reva-ui fence, cap 点亮后)
  DiscoveryCardSpec,
  SafetyCardSpec,
  MenuShareCardSpec,   // 不本地匹配, 仅接受后端下发
  SaveRecipeCardSpec,  // 不本地匹配, 仅接受后端下发 (Slice 3 存为配方入口)
  AIGCMediaJobCardSpec, // 不本地匹配, 百炼异步媒体任务状态
  AIGCMediaConfirmationCardSpec, // 用户点击后才会向百炼发送绑定草稿
  WeatherCardSpec,
  ScoreCardSpec,
  VitalsCardSpec,      // 最通用的兜底
];

export const CARD_MAP: Record<string, CardSpec> = Object.fromEntries(
  CARD_REGISTRY.map((c) => [c.type, c]),
);

function isMediaCreationRequest(query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return false;
  const requestsCreation =
    /生成|制作|做成|创作|创建|画一张|做一张|剪成|剪辑|generate|create/.test(normalized);
  const requestsMedia =
    /短视频|视频|图片|图像|封面|海报|插画|动图|照片|video|image/.test(normalized);
  return requestsCreation && requestsMedia;
}

const ALLOWED_ACTIONS = new Set([
  'agenda.complete',
  'daily_plan_action.complete',
  'diet_record.create',
  'write_intent.confirm',
  'write_intent.dismiss',
  'aigc_media.confirm',
  'route.open',
  'ui.inline.expand',
]);
const WRITE_ACTIONS = new Set([
  'agenda.complete',
  'daily_plan_action.complete',
  'diet_record.create',
  'write_intent.confirm',
  'write_intent.dismiss',
  'aigc_media.confirm',
]);

/**
 * 从用户 query + 上下文挑一张卡 (本地关键词触发)
 * @returns {type, data} 或 null
 */
export async function dispatchCard(ctx: CardContext): Promise<{ type: string; data: any } | null> {
  // Local keyword cards are a read-query fallback. Media creation can mention
  // health topics as source material ("用饮食和睡眠生成短视频"); projecting a
  // diet/sleep card for those nouns competes with the authoritative creation card.
  if (isMediaCreationRequest(ctx.query_lower)) return null;

  const scored = CARD_REGISTRY
    .map((spec) => ({ spec, score: spec.match(ctx) }))
    .filter((x) => typeof x.score === 'number' && (x.score as number) > 0) as { spec: CardSpec; score: number }[];

  if (scored.length === 0) return null;
  scored.sort((a, b) => b.score - a.score);

  // 依次尝试 build, 第一个返回非 null 的就用
  for (const { spec } of scored) {
    try {
      const data = await Promise.resolve(spec.build(ctx));
      if (data != null) return { type: spec.type, data };
    } catch (e) {
      // 单张卡失败不阻塞下一张
      if (__DEV__) console.warn(`[cards] ${spec.type}.build failed`, e);
    }
  }
  return null;
}

/**
 * 渲染一张卡片 (不管本地还是后端来的)
 * 未知 type 返回 null (安全降级, 不崩)
 */
export function renderCard(
  descriptor: ServerCardDescriptor,
  options: CardRenderOptions = {},
): React.ReactElement | null {
  // cards_group: iPad(>= 768) 双列, iPhone 单列
  if (descriptor.type === 'cards_group' && Array.isArray(descriptor.data?.cards)) {
    const items = (descriptor.data.cards as ServerCardDescriptor[])
      .map((card) => ({ key: serverCardIdentity(card), el: renderCard(card, options) }))
      .filter((x) => x.el != null);
    if (items.length === 0) return null;
    if (items.length === 1) return items[0].el;
    const { width } = Dimensions.get('window');
    const isTablet = width >= 768;
    if (!isTablet) {
      return (
        <View style={{ gap: 6 }}>
          {items.map((it) => <View key={it.key}>{it.el}</View>)}
        </View>
      );
    }
    return (
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {items.map((it) => (
          <View key={it.key} style={{ width: '48%' }}>{it.el}</View>
        ))}
      </View>
    );
  }
  if (!isRenderableServerCard(descriptor)) return null;
  const spec = CARD_MAP[descriptor.type];
  if (!spec) {
    if (__DEV__) console.warn(`[cards] unknown card type: ${descriptor.type}`);
    return null;
  }
  return <StatefulCardRenderer descriptor={descriptor} spec={spec} options={options} />;
}

function StatefulCardRenderer({
  descriptor,
  spec,
  options,
}: {
  descriptor: ServerCardDescriptor;
  spec: CardSpec;
  options: CardRenderOptions;
}) {
  const [data, setData] = React.useState(descriptor.data);
  const [localDoneActionKeys, setLocalDoneActionKeys] = React.useState<Record<string, true>>({});
  const runtimeIdentity = stableServerCardId(descriptor) ?? descriptor.type;
  React.useEffect(() => {
    setData(descriptor.data);
  }, [descriptor.data]);
  React.useEffect(() => {
    setLocalDoneActionKeys({});
  }, [runtimeIdentity]);
  try {
    const actions = normalizeCardActions(descriptor.actions, descriptor.type)
      .map((action) => rewriteActionForCurrentCardData(action, descriptor.type, data));
    const currentDescriptor: ServerCardDescriptor = { ...descriptor, data, actions };
    const rendered = spec.render(data, {
      ...options,
      onCardDataChange: setData,
      cardActions: actions,
      onCardAction: (action) => {
        options.onAction?.(action, currentDescriptor);
      },
    });
    // AIGC confirmation owns its button so it can replace itself with the
    // private job projection after the one-time confirmation succeeds.
    if (descriptor.type === 'aigc_media_confirmation' || !actions.length || !options.onAction) return rendered;
    const visibleActions = actions.filter((action) => {
      const actionKey = getCardActionRuntimeKey(action, descriptor);
      const actionState = options.actionStateByKey?.[actionKey];
      const localDone = localDoneActionKeys[actionKey] === true;
      const groupKey = getCardActionRuntimeGroupKey(action, descriptor);
      const groupDone = actions.some((sibling) => (
        getCardActionRuntimeGroupKey(sibling, descriptor) === groupKey
        && (
          options.actionStateByKey?.[getCardActionRuntimeKey(sibling, descriptor)] === 'done'
          || localDoneActionKeys[getCardActionRuntimeKey(sibling, descriptor)] === true
        )
      ));
      const isDone = actionState === 'done' || localDone || groupDone;
      const terminalDecision = readMedicationDecisionStatus(data);
      if (
        isWriteIntentAction(action)
        && (isDone || (terminalDecision != null && terminalDecision !== 'pending'))
      ) {
        return false;
      }
      return !(action.action === 'diet_record.create' && isDone);
    });
    if (!visibleActions.length) return rendered;
    return (
      <View style={styles.actionShell}>
        {rendered}
        <View style={styles.actionBar}>
          {visibleActions.map((action) => {
            const actionKey = getCardActionRuntimeKey(action, descriptor);
            const actionState = options.actionStateByKey?.[actionKey];
            const localDone = localDoneActionKeys[actionKey] === true;
            const groupKey = getCardActionRuntimeGroupKey(action, descriptor);
            const groupStates = actions
              .filter((sibling) => getCardActionRuntimeGroupKey(sibling, descriptor) === groupKey)
              .map((sibling) => options.actionStateByKey?.[getCardActionRuntimeKey(sibling, descriptor)]);
            const isBusy = actionState === 'running' || groupStates.includes('running');
            const isDone = actionState === 'done' || localDone || groupStates.includes('done');
            const isDisabled = !!action.disabled_reason || isBusy || isDone;
            const visibleLabel = getActionRuntimeLabel(action, localDone ? 'done' : actionState);
            const supportText = action.disabled_reason || (actionState === 'error' ? '刚刚失败，可重试' : null);
            return (
              <View key={actionKey} style={styles.actionItem}>
                <Pressable
                  style={({ pressed }) => [
                    styles.actionButton,
                    action.style === 'primary' && styles.actionButtonPrimary,
                    isBusy && styles.actionButtonRunning,
                    isDone && styles.actionButtonDone,
                    actionState === 'error' && styles.actionButtonError,
                    isDisabled && !isBusy && !isDone && styles.actionButtonDisabled,
                    pressed && !isDisabled && { opacity: 0.82 },
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel={visibleLabel}
                  accessibilityState={{ disabled: isDisabled, busy: isBusy }}
                  disabled={isDisabled}
                  onPress={() => {
                    if (isDisabled) return;
                    if (action.action === 'ui.inline.expand') {
                      const patch = readInlineExpandPatch(action);
                      if (patch) {
                        setData((current: any) => mergeCardDataPatch(current, patch));
                        setLocalDoneActionKeys((prev) => ({ ...prev, [actionKey]: true }));
                      }
                      return;
                    }
                    options.onAction?.(action, currentDescriptor);
                  }}
                >
                  <View style={styles.actionButtonContent}>
                    {isBusy ? <ActivityIndicator size="small" color={C.green500} /> : null}
                    <Text
                      style={[
                        styles.actionText,
                        action.style === 'primary' && styles.actionTextPrimary,
                        isBusy && styles.actionTextRunning,
                        isDone && styles.actionTextDone,
                        isDisabled && !isBusy && !isDone && styles.actionTextDisabled,
                      ]}
                    >
                      {visibleLabel}
                    </Text>
                  </View>
                </Pressable>
                {supportText ? (
                  <Text maxFontSizeMultiplier={1.1} style={styles.disabledReason}>
                    {supportText}
                  </Text>
                ) : null}
              </View>
            );
          })}
        </View>
      </View>
    );
  } catch (e) {
    if (__DEV__) console.warn(`[cards] ${descriptor.type}.render failed`, e);
    return null;
  }
}

/**
 * 批量渲染后端下发的卡片 (SSE done 事件里的 cards 数组)
 */
export function renderServerCards(cards?: ServerCardDescriptor[] | null): ServerCardDescriptor[] {
  if (!Array.isArray(cards)) return [];
  return cards.filter((c) => (
    c && typeof c.type === 'string' && CARD_MAP[c.type] && isRenderableServerCard(c)
  )).map((c) => ({
    type: c.type,
    data: c.data,
    actions: normalizeCardActions(c.actions, c.type),
  }));
}

function isRenderableServerCard(descriptor: ServerCardDescriptor): boolean {
  if (descriptor.type !== 'diet_draft') return true;
  const foodItems = foodItemsValue(descriptor.data?.food_items);
  return !looksLikeDietManagementIntent(foodItems) && !looksLikeUiFoodText(foodItems);
}

function looksLikeDietManagementIntent(value?: string): boolean {
  if (!value) return false;
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  if (!normalized) return false;
  return [
    '删除',
    '删掉',
    '删了',
    '删去',
    '移除',
    '撤销',
    '取消记录',
    '取消这一餐',
    '取消这餐',
    '误删',
    '不小心删',
    '恢复',
    '找回',
  ].some((marker) => normalized.includes(marker.toLowerCase()));
}

function looksLikeUiFoodText(value?: string): boolean {
  if (!value) return false;
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  if (!normalized) return false;
  if (/^(?:和)?(?:早餐|午餐|晚餐|加餐|餐食)?(?:食品?)?营养卡$/.test(normalized)) return true;
  return [
    '营养卡',
    '保存并确认',
    '确认记录',
    '今日饮食',
    '待确认',
    '完成修正',
    '去饮食页修正',
    '看下一餐建议',
  ].some((marker) => normalized.includes(marker.toLowerCase()));
}

function normalizeCardActions(
  actions: ServerCardDescriptor['actions'],
  cardType?: string,
): ChatCardActionDescriptor[] {
  if (!Array.isArray(actions)) return [];
  return actions.filter((action): action is ChatCardActionDescriptor => (
    action != null &&
    !(cardType === 'aigc_media_job' && action.action === 'aigc_media.confirm') &&
    typeof action.label === 'string' &&
    action.label.trim().length > 0 &&
    typeof action.action === 'string' &&
    ALLOWED_ACTIONS.has(action.action) &&
    isSafeVisibleAction(action, cardType)
  )).map((action) => ({
    ...action,
    label: action.label.trim(),
    disabled_reason: typeof action.disabled_reason === 'string' && action.disabled_reason.trim()
      ? action.disabled_reason.trim()
      : null,
  }));
}

function isSafeVisibleAction(
  action: ChatCardActionDescriptor,
  cardType?: string,
): boolean {
  if (action.action === 'route.open') return isSafeInternalRoute(action.payload?.route);
  if (action.action === 'ui.inline.expand') return readInlineExpandPatch(action) != null;
  if (action.action === 'write_intent.confirm' || action.action === 'write_intent.dismiss') {
    return cardType === 'medication_draft' && isSafeMedicationBatchAction(action);
  }
  return action.requires_manual_confirm === true && hasRegisteredWritePolicy(action);
}

function isSafeMedicationBatchAction(action: ChatCardActionDescriptor): boolean {
  if (
    action.requires_manual_confirm !== true
    || action.required_receipt !== true
    || action.capability_id !== 'medication_draft.v1'
    || action.autonomy_tier !== 'manual_confirm'
    || action.policy_reason !== 'manual_confirm_write'
  ) {
    return false;
  }
  const rawIntentId = action.payload?.write_intent_id;
  const intentId = typeof rawIntentId === 'number'
    ? rawIntentId
    : typeof rawIntentId === 'string' && rawIntentId.trim()
      ? Number(rawIntentId)
      : NaN;
  if (!Number.isInteger(intentId) || intentId <= 0) return false;
  const command = action.action === 'write_intent.confirm' ? 'confirm' : 'dismiss';
  return action.endpoint === `/write-intents/${intentId}/${command}`;
}

function hasRegisteredWritePolicy(action: ChatCardActionDescriptor): boolean {
  if (!WRITE_ACTIONS.has(action.action)) return true;
  return Boolean(
    typeof action.capability_id === 'string' &&
    /^[a-z][a-z0-9_]*\.v\d+$/.test(action.capability_id) &&
    action.required_receipt === true &&
    action.autonomy_tier === 'manual_confirm' &&
    action.policy_reason === 'manual_confirm_write',
  );
}

function readInlineExpandPatch(action: ChatCardActionDescriptor): Record<string, unknown> | null {
  if (action.action !== 'ui.inline.expand') return null;
  if (action.endpoint) return null;
  const target = textValue(action.payload?.target);
  const rawPatch = action.payload?.patch;
  if (!target || !rawPatch || typeof rawPatch !== 'object' || Array.isArray(rawPatch)) return null;
  const patch = sanitizeInlinePatch(rawPatch as Record<string, unknown>);
  return Object.keys(patch).length > 0 ? patch : null;
}

const INLINE_EXPAND_SECTIONS = new Set(['next_meal', 'adjust_record']);

function sanitizeInlinePatch(source: Record<string, unknown>): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  if (Array.isArray(source.expanded_sections)) {
    const sections = source.expanded_sections
      .map(textValue)
      .filter((item): item is string => Boolean(item))
      .filter((item) => INLINE_EXPAND_SECTIONS.has(item));
    if (sections.length > 0) patch.expanded_sections = sections.slice(0, 4);
  }
  const detail = source.next_meal_detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    patch.next_meal_detail = sanitizeNextMealDetail(detail as Record<string, unknown>);
  }
  const adjust = source.adjust_record;
  if (adjust && typeof adjust === 'object' && !Array.isArray(adjust)) {
    const sanitized = sanitizeAdjustRecord(adjust as Record<string, unknown>);
    if (sanitized) patch.adjust_record = sanitized;
  }
  return patch;
}

const ADJUST_MEAL_TYPES = new Set(['breakfast', 'lunch', 'dinner', 'snack']);

function sanitizeAdjustRecord(source: Record<string, unknown>): Record<string, unknown> | null {
  const recordId = numberValue(source.record_id);
  if (recordId == null || !Number.isInteger(recordId)) return null;
  const adjust: Record<string, unknown> = { record_id: recordId };
  const mealType = textValue(source.meal_type);
  if (mealType && ADJUST_MEAL_TYPES.has(mealType)) adjust.meal_type = mealType;
  const foodItems = foodItemsValue(source.food_items);
  if (foodItems) adjust.food_items = foodItems;
  for (const key of ['calories', 'protein', 'carbs', 'fat'] as const) {
    const parsed = numberValue(source[key]);
    if (parsed != null) adjust[key] = parsed;
  }
  return adjust;
}

function sanitizeNextMealDetail(source: Record<string, unknown>): Record<string, unknown> {
  const detail: Record<string, unknown> = {};
  for (const key of ['title', 'summary', 'context', 'continue_prompt'] as const) {
    const value = textValue(source[key]);
    if (value) detail[key] = value;
  }
  for (const key of ['options', 'rationale'] as const) {
    const values = readTextList(source[key], 6);
    if (values.length > 0) detail[key] = values;
  }
  return detail;
}

function readTextList(value: unknown, limit = 4): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(textValue)
    .filter((item): item is string => Boolean(item))
    .slice(0, limit);
}

function mergeCardDataPatch(current: any, patch: Record<string, unknown>): any {
  const base = current && typeof current === 'object' && !Array.isArray(current) ? current : {};
  return { ...base, ...patch };
}

function rewriteActionForCurrentCardData(
  action: ChatCardActionDescriptor,
  cardType: string,
  data: any,
): ChatCardActionDescriptor {
  if (cardType !== 'diet_draft' || action.action !== 'diet_record.create') return action;
  const record = readDietRecordFromCardData(data, action.payload?.record);
  return {
    ...action,
    payload: {
      ...(action.payload ?? {}),
      record,
    },
  };
}

function readDietRecordFromCardData(data: any, existing: any): Record<string, unknown> {
  const record: Record<string, unknown> = (
    existing && typeof existing === 'object' && !Array.isArray(existing)
      ? { ...existing }
      : {}
  );
  const mealType = textValue(data?.meal_type);
  const foodItems = foodItemsValue(data?.food_items);
  if (mealType) record.meal_type = mealType;
  if (foodItems) record.food_items = foodItems;
  for (const key of ['calories', 'protein', 'carbs', 'fat', 'fiber'] as const) {
    const parsed = numberValue(data?.[key]);
    if (parsed != null) record[key] = parsed;
  }
  return record;
}

function textValue(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function foodItemsValue(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    const items = value.map(textValue).filter((item): item is string => Boolean(item));
    return items.length ? items.slice(0, 8).join(' + ') : undefined;
  }
  return textValue(value);
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) return Math.round(value * 10) / 10;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 10) / 10 : undefined;
  }
  return undefined;
}

export function getCardActionRuntimeKey(
  action: ChatCardActionDescriptor,
  descriptor?: Pick<ServerCardDescriptor, 'type'>,
): string {
  return action.id || `${descriptor?.type ?? 'card'}:${action.action}:${action.label}`;
}

export function getCardActionRuntimeGroupKey(
  action: ChatCardActionDescriptor,
  descriptor?: Pick<ServerCardDescriptor, 'type'>,
): string {
  if (isWriteIntentAction(action)) {
    const rawId = action.payload?.write_intent_id;
    const intentId = typeof rawId === 'number'
      ? rawId
      : typeof rawId === 'string' && rawId.trim()
        ? Number(rawId)
        : NaN;
    if (Number.isInteger(intentId) && intentId > 0) return `write_intent:${intentId}`;
  }
  return getCardActionRuntimeKey(action, descriptor);
}

function isWriteIntentAction(action: ChatCardActionDescriptor): boolean {
  return action.action === 'write_intent.confirm' || action.action === 'write_intent.dismiss';
}

function readMedicationDecisionStatus(data: unknown): string | undefined {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return undefined;
  const value = (data as Record<string, unknown>).decision_status;
  return typeof value === 'string' ? value : undefined;
}

function getActionRuntimeLabel(
  action: ChatCardActionDescriptor,
  state?: ChatCardActionRuntimeState,
): string {
  if (state === 'running') return '执行中';
  if (state === 'done') {
    if (action.action === 'route.open') return '已打开';
    if (action.action === 'ui.inline.expand') return '已展开';
    if (action.action === 'diet_record.create') return '已记录';
    if (action.action === 'write_intent.dismiss') return '已忽略';
    return '已完成';
  }
  return action.label;
}

const styles = StyleSheet.create({
  actionShell: {
    gap: 8,
  },
  actionBar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  actionItem: {
    maxWidth: '100%',
    gap: 3,
  },
  actionButton: {
    minHeight: 44,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
    paddingHorizontal: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionButtonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  actionButtonPrimary: {
    borderColor: C.green500,
    backgroundColor: C.green500,
  },
  actionButtonRunning: {
    borderColor: C.green100,
    backgroundColor: C.green50,
    opacity: 0.9,
  },
  actionButtonDone: {
    borderColor: C.green100,
    backgroundColor: C.green50,
  },
  actionButtonError: {
    borderColor: revaSemantic.risk.line,
    backgroundColor: revaSemantic.risk.bg,
  },
  actionButtonDisabled: {
    borderColor: C.line,
    backgroundColor: C.paper2,
    opacity: 0.68,
  },
  actionText: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0,
    color: C.ink2,
  },
  actionTextPrimary: {
    color: C.greenOn,
  },
  actionTextRunning: {
    color: C.green500,
  },
  actionTextDone: {
    color: C.green500,
  },
  actionTextDisabled: {
    color: C.ink3,
  },
  disabledReason: {
    maxWidth: 220,
    fontSize: 11,
    lineHeight: 15,
    color: C.ink3,
  },
});
