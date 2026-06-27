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
import { View, Dimensions } from 'react-native';
import type { CardSpec, CardContext, ServerCardDescriptor } from './types';

import { VitalsCardSpec } from './VitalsCard';
import { SleepCardSpec } from './SleepCard';
import { WeightCardSpec } from './WeightCard';
import { SupplementCardSpec } from './SupplementCard';
import { WeatherCardSpec } from './WeatherCard';
import { BPCardSpec } from './BPCard';
import { ScoreCardSpec } from './ScoreCard';
import { RecordCardSpec } from './RecordCard';
import { DietCardSpec } from './DietCard';
import { WorkoutCardSpec } from './WorkoutCard';
import { MedicalReportCardSpec } from './MedicalReportCard';
import { MedicalExamImportResultCardSpec } from './MedicalExamImportResultCard';
import { MenuShareCardSpec } from './MenuShareCard';
import { SystemKnowledgeEvidenceCardSpec } from './SystemKnowledgeEvidenceCard';

/** 全量卡片注册表. 数组前面的优先级越高时越靠前 (便于可读), 实际按 match() 返回值排序 */
export const CARD_REGISTRY: CardSpec[] = [
  RecordCardSpec,      // 记录类优先 - 避免被分析类误触
  SleepCardSpec,
  WeightCardSpec,
  BPCardSpec,
  SupplementCardSpec,
  DietCardSpec,
  WorkoutCardSpec,
  MedicalExamImportResultCardSpec,
  MedicalReportCardSpec,
  SystemKnowledgeEvidenceCardSpec,
  MenuShareCardSpec,   // 不本地匹配, 仅接受后端下发
  WeatherCardSpec,
  ScoreCardSpec,
  VitalsCardSpec,      // 最通用的兜底
];

export const CARD_MAP: Record<string, CardSpec> = Object.fromEntries(
  CARD_REGISTRY.map((c) => [c.type, c]),
);

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
export function renderCard(descriptor: ServerCardDescriptor): React.ReactElement | null {
  // cards_group: iPad(>= 768) 双列, iPhone 单列
  if (descriptor.type === 'cards_group' && Array.isArray(descriptor.data?.cards)) {
    const items = (descriptor.data.cards as ServerCardDescriptor[])
      .map((c, i) => ({ key: i, el: renderCard(c) }))
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
    return spec.render(descriptor.data);
  } catch (e) {
    if (__DEV__) console.warn(`[cards] ${descriptor.type}.render failed`, e);
    return null;
  }
}

/**
 * 批量渲染后端下发的卡片 (SSE done 事件里的 cards 数组)
 */
export function renderServerCards(cards?: ServerCardDescriptor[] | null): { type: string; data: any }[] {
  if (!Array.isArray(cards)) return [];
  return cards.filter((c) => c && typeof c.type === 'string' && CARD_MAP[c.type]).map((c) => ({
    type: c.type, data: c.data,
  }));
}
