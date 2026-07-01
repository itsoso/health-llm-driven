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
import { revaColors as C, revaRadii, revaSemantic } from '../../../constants/revaTheme';

import { VitalsCardSpec } from './VitalsCard';
import { SleepCardSpec } from './SleepCard';
import { WeightCardSpec } from './WeightCard';
import { SupplementCardSpec } from './SupplementCard';
import { WeatherCardSpec } from './WeatherCard';
import { BPCardSpec } from './BPCard';
import { ScoreCardSpec } from './ScoreCard';
import { RecordCardSpec } from './RecordCard';
import { RecordQualityCardSpec } from './RecordQualityCard';
import { DietCardSpec } from './DietCard';
import { WorkoutCardSpec } from './WorkoutCard';
import { MedicalReportCardSpec } from './MedicalReportCard';
import { MedicalExamImportResultCardSpec } from './MedicalExamImportResultCard';
import { MenuShareCardSpec } from './MenuShareCard';
import { SystemKnowledgeEvidenceCardSpec } from './SystemKnowledgeEvidenceCard';
import { RuntimeAgendaCardSpec } from './RuntimeAgendaCard';
import { OperatingReviewCardSpec } from './OperatingReviewCard';
import { MetricChartCardSpec, MetricEmptyStateCardSpec, MetricLineChartCardSpec, RevaUiLineChartCardSpec } from './MetricChartCard';
import { DiscoveryCardSpec } from './DiscoveryCard';
import { SafetyCardSpec } from './SafetyCard';

/** 全量卡片注册表. 数组前面的优先级越高时越靠前 (便于可读), 实际按 match() 返回值排序 */
export const CARD_REGISTRY: CardSpec[] = [
  RecordCardSpec,      // 记录类优先 - 避免被分析类误触
  RecordQualityCardSpec,
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
  DiscoveryCardSpec,
  SafetyCardSpec,
  MenuShareCardSpec,   // 不本地匹配, 仅接受后端下发
  WeatherCardSpec,
  ScoreCardSpec,
  VitalsCardSpec,      // 最通用的兜底
];

export const CARD_MAP: Record<string, CardSpec> = Object.fromEntries(
  CARD_REGISTRY.map((c) => [c.type, c]),
);

const ALLOWED_ACTIONS = new Set([
  'agenda.complete',
  'write_intent.confirm',
  'write_intent.dismiss',
  'route.open',
]);

/**
 * 从用户 query + 上下文挑一张卡 (本地关键词触发)
 * @returns {type, data} 或 null
 */
export async function dispatchCard(ctx: CardContext): Promise<{ type: string; data: any } | null> {
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
      .map((c, i) => ({ key: i, el: renderCard(c, options) }))
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
  const spec = CARD_MAP[descriptor.type];
  if (!spec) {
    if (__DEV__) console.warn(`[cards] unknown card type: ${descriptor.type}`);
    return null;
  }
  try {
    const rendered = spec.render(descriptor.data, options);
    const actions = normalizeCardActions(descriptor.actions);
    if (!actions.length || !options.onAction) return rendered;
    return (
      <View style={styles.actionShell}>
        {rendered}
        <View style={styles.actionBar}>
          {actions.map((action) => {
            const actionKey = getCardActionRuntimeKey(action, descriptor);
            const actionState = options.actionStateByKey?.[actionKey];
            const isBusy = actionState === 'running';
            const isDone = actionState === 'done';
            const isDisabled = !!action.disabled_reason || isBusy || isDone;
            const visibleLabel = getActionRuntimeLabel(action, actionState);
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
                    options.onAction?.(action, descriptor);
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
  return cards.filter((c) => c && typeof c.type === 'string' && CARD_MAP[c.type]).map((c) => ({
    type: c.type,
    data: c.data,
    actions: normalizeCardActions(c.actions),
  }));
}

function normalizeCardActions(actions: ServerCardDescriptor['actions']): ChatCardActionDescriptor[] {
  if (!Array.isArray(actions)) return [];
  return actions.filter((action): action is ChatCardActionDescriptor => (
    action != null &&
    typeof action.label === 'string' &&
    action.label.trim().length > 0 &&
    typeof action.action === 'string' &&
    ALLOWED_ACTIONS.has(action.action) &&
    isSafeVisibleAction(action)
  )).map((action) => ({
    ...action,
    label: action.label.trim(),
    disabled_reason: typeof action.disabled_reason === 'string' && action.disabled_reason.trim()
      ? action.disabled_reason.trim()
      : null,
  }));
}

function isSafeVisibleAction(action: ChatCardActionDescriptor): boolean {
  if (action.action === 'route.open') return true;
  return action.requires_manual_confirm === true;
}

export function getCardActionRuntimeKey(
  action: ChatCardActionDescriptor,
  descriptor?: Pick<ServerCardDescriptor, 'type'>,
): string {
  return action.id || `${descriptor?.type ?? 'card'}:${action.action}:${action.label}`;
}

function getActionRuntimeLabel(
  action: ChatCardActionDescriptor,
  state?: ChatCardActionRuntimeState,
): string {
  if (state === 'running') return '执行中';
  if (state === 'done') {
    if (action.action === 'route.open') return '已打开';
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
    minHeight: 36,
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
