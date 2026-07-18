'use client';
import React from 'react';
import type { CardSpec, CardContext, ChatCardActionDescriptor, ServerCardDescriptor } from './types';
import {
  VitalsCardSpec, SleepCardSpec, WeightCardSpec, SupplementCardSpec,
  WeatherCardSpec, BPCardSpec, ScoreCardSpec, RecordCardSpec, DietCardSpec,
  MedicalExamImportResultCardSpec, RecordQualityCardSpec,
  AIGCMediaJobCardSpec,
  AIGCMediaConfirmationCardSpec,
} from './cards';

/** 全量卡片注册表. 数组顺序不决定优先级, 以 match() 返回值为准. */
export const CARD_REGISTRY: CardSpec[] = [
  RecordCardSpec,
  RecordQualityCardSpec,
  AIGCMediaJobCardSpec,
  AIGCMediaConfirmationCardSpec,
  MedicalExamImportResultCardSpec,
  SleepCardSpec,
  WeightCardSpec,
  BPCardSpec,
  SupplementCardSpec,
  DietCardSpec,
  WeatherCardSpec,
  ScoreCardSpec,
  VitalsCardSpec,
];

export const CARD_MAP: Record<string, CardSpec> = Object.fromEntries(
  CARD_REGISTRY.map(c => [c.type, c]),
);

const ALLOWED_ACTIONS = new Set(['route.open', 'ui.inline.expand']);

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
    const rendered = spec.render(desc.data);
    const actions = normalizeCardActions(desc.actions);
    if (actions.length === 0) return rendered;
    return (
      <div className="space-y-2">
        {rendered}
        <div className="flex flex-wrap gap-2">
          {actions.map((action) => {
            const route = readRouteAction(action);
            if (action.action === 'ui.inline.expand') {
              return renderInlineExpandAction(action);
            }
            if (!route) return null;
            return (
              <a
                key={action.id || `${action.action}:${action.label}`}
                href={route}
                className={[
                  'inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors',
                  action.style === 'primary'
                    ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                ].join(' ')}
              >
                {action.label}
              </a>
            );
          })}
        </div>
      </div>
    );
  } catch (e) {
    if (process.env.NODE_ENV !== 'production') console.warn(`[cards] ${desc.type}.render failed`, e);
    return null;
  }
}

/** 批量过滤后端下发的卡片 */
export function renderServerCards(cards?: ServerCardDescriptor[] | null): ServerCardDescriptor[] {
  if (!Array.isArray(cards)) return [];
  return cards.filter(c => c && typeof c.type === 'string' && CARD_MAP[c.type])
              .map(c => {
                const actions = normalizeCardActions(c.actions);
                return actions.length > 0
                  ? { type: c.type, data: c.data, actions }
                  : { type: c.type, data: c.data };
              });
}

function normalizeCardActions(actions: ServerCardDescriptor['actions']): ChatCardActionDescriptor[] {
  if (!Array.isArray(actions)) return [];
  return actions
    .filter((action): action is ChatCardActionDescriptor => (
      action != null &&
      typeof action.label === 'string' &&
      action.label.trim().length > 0 &&
      typeof action.action === 'string' &&
      ALLOWED_ACTIONS.has(action.action) &&
      isSafeAction(action)
    ))
    .map(action => ({
      ...action,
      label: action.label.trim(),
      disabled_reason: typeof action.disabled_reason === 'string' && action.disabled_reason.trim()
        ? action.disabled_reason.trim()
        : null,
    }));
}

function isSafeAction(action: ChatCardActionDescriptor): boolean {
  if (action.action === 'route.open') return readRouteAction(action) != null;
  if (action.action === 'ui.inline.expand') return readInlineNextMealDetail(action) != null;
  return false;
}

function readRouteAction(action: ChatCardActionDescriptor): string | null {
  const route = action.payload?.route;
  if (typeof route !== 'string') return null;
  if (!route.startsWith('/')) return null;
  if (route.startsWith('//')) return null;
  if (/[\u0000-\u001f\u007f]/.test(route)) return null;
  return route;
}

function renderInlineExpandAction(action: ChatCardActionDescriptor): React.ReactElement | null {
  const detail = readInlineNextMealDetail(action);
  if (!detail) return null;
  return (
    <details
      key={action.id || `${action.action}:${action.label}`}
      className={[
        'w-full rounded-2xl border px-3 py-2 text-xs',
        action.style === 'primary'
          ? 'border-emerald-200 bg-emerald-50 text-slate-800'
          : 'border-slate-200 bg-white text-slate-700',
      ].join(' ')}
    >
      <summary className="cursor-pointer list-none font-semibold text-emerald-700">
        {action.label}
      </summary>
      <div className="mt-2 space-y-2">
        <div className="font-bold text-slate-900">{detail.title || '下一餐建议'}</div>
        {detail.context ? <div className="text-[11px] leading-5 text-slate-500">{detail.context}</div> : null}
        {detail.summary ? <div className="font-semibold leading-5 text-emerald-700">{detail.summary}</div> : null}
        {detail.options.length > 0 ? (
          <ol className="space-y-1 pl-4 text-[11px] leading-5 text-slate-800">
            {detail.options.map((item) => <li key={item}>{item}</li>)}
          </ol>
        ) : null}
        {detail.rationale.length > 0 ? (
          <div className="space-y-1 rounded-xl bg-white/70 px-2 py-2 text-[11px] leading-5 text-slate-600">
            {detail.rationale.map((item) => <div key={item}>依据：{item}</div>)}
          </div>
        ) : null}
        {detail.continue_prompt ? <div className="text-[11px] leading-5 text-slate-500">{detail.continue_prompt}</div> : null}
      </div>
    </details>
  );
}

function readInlineNextMealDetail(action: ChatCardActionDescriptor): {
  title: string;
  summary: string;
  context: string;
  options: string[];
  rationale: string[];
  continue_prompt: string;
} | null {
  if (action.action !== 'ui.inline.expand') return null;
  if (action.endpoint) return null;
  const patch = action.payload?.patch;
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) return null;
  const detail = (patch as Record<string, unknown>).next_meal_detail;
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null;
  const raw = detail as Record<string, unknown>;
  return {
    title: text(raw.title),
    summary: text(raw.summary),
    context: text(raw.context),
    options: textList(raw.options, 6),
    rationale: textList(raw.rationale, 6),
    continue_prompt: text(raw.continue_prompt),
  };
}

function text(value: unknown): string {
  if (typeof value !== 'string') return '';
  return value.trim().slice(0, 500);
}

function textList(value: unknown, limit: number): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(text)
    .filter(Boolean)
    .slice(0, limit);
}
