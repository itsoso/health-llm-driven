'use client';
import React from 'react';
import type { CardSpec, CardContext, ServerCardDescriptor } from './types';
import {
  VitalsCardSpec, SleepCardSpec, WeightCardSpec, SupplementCardSpec,
  WeatherCardSpec, BPCardSpec, ScoreCardSpec, RecordCardSpec,
} from './cards';

/** 全量卡片注册表. 数组顺序不决定优先级, 以 match() 返回值为准. */
export const CARD_REGISTRY: CardSpec[] = [
  RecordCardSpec,
  SleepCardSpec,
  WeightCardSpec,
  BPCardSpec,
  SupplementCardSpec,
  WeatherCardSpec,
  ScoreCardSpec,
  VitalsCardSpec,
];

export const CARD_MAP: Record<string, CardSpec> = Object.fromEntries(
  CARD_REGISTRY.map(c => [c.type, c]),
);

/** 派发: 本地关键词 + 数据可用性双门限, 第一张 build 成功的卡片胜出 */
export async function dispatchCard(ctx: CardContext): Promise<{ type: string; data: any } | null> {
  const scored = CARD_REGISTRY
    .map(spec => ({ spec, score: spec.match(ctx) }))
    .filter(x => typeof x.score === 'number' && (x.score as number) > 0) as { spec: CardSpec; score: number }[];
  if (scored.length === 0) return null;
  scored.sort((a, b) => b.score - a.score);
  for (const { spec } of scored) {
    try {
      const data = await Promise.resolve(spec.build(ctx));
      if (data != null) return { type: spec.type, data };
    } catch (e) {
      if (process.env.NODE_ENV !== 'production') console.warn(`[cards] ${spec.type}.build failed`, e);
    }
  }
  return null;
}

/** 渲染一张卡片 - 未知 type 安全降级返回 null. 特殊 type: cards_group 渲染网格 */
export function renderCard(desc: ServerCardDescriptor): React.ReactElement | null {
  // 多卡片组: iPad 上双列, 手机上单列
  if (desc.type === 'cards_group' && Array.isArray(desc.data?.cards)) {
    const items = (desc.data.cards as ServerCardDescriptor[])
      .map((c, i) => ({ key: i, el: renderCard(c) }))
      .filter(x => x.el != null);
    if (items.length === 0) return null;
    if (items.length === 1) return items[0].el;
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 w-full">
        {items.map(it => <div key={it.key}>{it.el}</div>)}
      </div>
    );
  }
  const spec = CARD_MAP[desc.type];
  if (!spec) return null;
  try {
    return spec.render(desc.data);
  } catch (e) {
    if (process.env.NODE_ENV !== 'production') console.warn(`[cards] ${desc.type}.render failed`, e);
    return null;
  }
}

/** 批量过滤后端下发的卡片 */
export function renderServerCards(cards?: ServerCardDescriptor[] | null): { type: string; data: any }[] {
  if (!Array.isArray(cards)) return [];
  return cards.filter(c => c && typeof c.type === 'string' && CARD_MAP[c.type])
              .map(c => ({ type: c.type, data: c.data }));
}
