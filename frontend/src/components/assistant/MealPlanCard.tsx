'use client';

/**
 * MealPlanCard — 把 LLM 直接吐在正文里的"计划 JSON"(FuelStrategist menu_share
 * schema: {title, items[], totals?, reason?, shopping_list?}) 渲染成格式化卡片,
 * 不让裸 JSON 堆在气泡里. 对齐 mobile 的 MenuShareCard, web 暗色风格.
 */

import { UtensilsCrossed } from 'lucide-react';
import type { MealPlanData } from '@/components/assistant/assistantContent';

const r0 = (n?: number) => (n == null ? null : Math.round(n));

export default function MealPlanCard({ plan }: { plan: MealPlanData }) {
  const items = Array.isArray(plan.items) ? plan.items : [];
  const totals = plan.totals || {};
  const macros: { label: string; v?: number; unit: string }[] = [
    { label: '蛋白', v: totals.protein, unit: 'g' },
    { label: '碳水', v: totals.carbs, unit: 'g' },
    { label: '脂肪', v: totals.fat, unit: 'g' },
  ].filter(m => m.v != null);
  const shopping = Array.isArray(plan.shopping_list) ? plan.shopping_list : [];

  return (
    <div className="my-2 rounded-2xl border border-amber-300/15 bg-amber-400/[0.05] px-4 py-3">
      <div className="mb-2 flex items-center gap-2">
        <UtensilsCrossed className="h-4 w-4 text-amber-300" />
        <span className="text-sm font-semibold text-zinc-100">{plan.title || '饮食计划'}</span>
      </div>

      {plan.reason && (
        <p className="mb-2.5 text-[13px] leading-5 text-zinc-400">{plan.reason}</p>
      )}

      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-center gap-2 text-[13px]">
            <span className="h-1 w-1 shrink-0 rounded-full bg-amber-300/70" />
            <span className="min-w-0 flex-1 truncate font-medium text-zinc-100">{it.name}</span>
            {it.qty && <span className="shrink-0 text-[11px] text-zinc-500">{it.qty}</span>}
            {it.kcal != null && (
              <span className="shrink-0 font-mono text-[11px] font-semibold text-amber-300">
                {r0(it.kcal)} kcal
              </span>
            )}
          </li>
        ))}
      </ul>

      {totals.kcal != null && (
        <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-3 border-t border-white/[0.08] pt-2.5">
          <span className="font-mono text-lg font-bold text-zinc-50">
            {r0(totals.kcal)}
            <span className="ml-1 text-[11px] font-normal text-zinc-500">kcal</span>
          </span>
          {macros.length > 0 && (
            <div className="flex flex-wrap items-center gap-3">
              {macros.map(m => (
                <span key={m.label} className="flex items-center gap-1 text-[11px]">
                  <span className="text-zinc-500">{m.label}</span>
                  <span className="font-mono font-semibold text-zinc-200">
                    {r0(m.v)}
                    {m.unit}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {shopping.length > 0 && (
        <div className="mt-2.5 border-t border-white/[0.08] pt-2.5">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
            买菜清单
          </div>
          <ul className="flex flex-wrap gap-x-3 gap-y-1">
            {shopping.map((s, i) => (
              <li key={i} className="text-[12px] text-zinc-400">
                · {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
