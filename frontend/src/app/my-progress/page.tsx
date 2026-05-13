'use client';

/**
 * /my-progress —— 用户视角执行监测看板 (Web 版, 2026-05-13).
 *
 * 跟 mobile/app/my-progress.tsx 同语义, 同后端端点 /action-cards/me/progress.
 * 加了一个 mobile 没有的 "改善叙事" 顶部 section: 把 closed_cards.improved
 * 的 baseline→actual 聚合成一段话, 让用户一眼看到 "AI 让我变好了多少".
 *
 * 这是产品价值锚点 — 没这页用户给朋友讲产品时只有概念, 没有"我变好了多少"证据.
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { api } from '@/services/api/client';
import ProtectedRoute from '@/components/ProtectedRoute';

interface ProgressCard {
  id: number;
  title: string;
  status: string | null;
  user_decision: string | null;
  outcome: 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;
  effect_size: number | null;
  accuracy_score: number | null;
  metric_key: string | null;
  baseline_value: string | null;
  actual_value: string | null;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  created_at: string | null;
  completed_at: string | null;
  graded_at: string | null;
}

interface ProgressDashboard {
  window: { since: string; until: string; days: number };
  stats: {
    total_surfaced: number;
    accepted: number;
    declined: number;
    pending: number;
    completed: number;
    graded: number;
    improved: number;
    unchanged: number;
    worsened: number;
    inconclusive: number;
    safe_closed: number;
    acceptance_rate: number | null;
    verification_rate: number | null;
    improvement_rate: number | null;
  };
  closed_cards: ProgressCard[];
  verifying_cards: ProgressCard[];
}

const WINDOW_OPTIONS = [
  { label: '7 天', days: 7 },
  { label: '30 天', days: 30 },
  { label: '90 天', days: 90 },
];

const METRIC_LABEL: Record<string, string> = {
  ldl: 'LDL 胆固醇',
  hdl: 'HDL',
  hba1c: '糖化血红蛋白',
  tg: '甘油三酯',
  systolic_bp: '收缩压',
  sbp: '收缩压',
  dbp: '舒张压',
  weight_kg: '体重',
  bmi: 'BMI',
  hrv: 'HRV',
  rhr: '静息心率',
  sleep_score: '睡眠评分',
  spo2_odi: '血氧 ODI',
  hcy: '同型半胱氨酸',
  vitamin_d: '维生素 D',
  b12: '维生素 B12',
  ferritin: '铁蛋白',
};

const OUTCOME_STYLE: Record<string, { bg: string; text: string; label: string; arrow: string }> = {
  improved: { bg: 'bg-emerald-500/15', text: 'text-emerald-300', label: '改善', arrow: '↑' },
  unchanged: { bg: 'bg-slate-500/15', text: 'text-slate-300', label: '稳定', arrow: '—' },
  worsened: { bg: 'bg-rose-500/15', text: 'text-rose-300', label: '反向', arrow: '↓' },
  inconclusive: { bg: 'bg-slate-500/10', text: 'text-slate-500', label: '数据不足', arrow: '?' },
};

function pct(v: number | null): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

function MyProgressInner() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<ProgressDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.get<ProgressDashboard>(`/action-cards/me/progress?days=${days}`)
      .then(r => setData(r.data))
      .catch(e => setErr(e?.response?.data?.detail || e?.message || '加载失败'))
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => { load(); }, [load]);

  // 改善叙事: 把 improved cards 按 metric 聚合成一段
  const narrativeRows = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, { baseline: string; actual: string; effect: number | null }>();
    for (const c of data.closed_cards) {
      if (c.outcome !== 'improved') continue;
      if (!c.metric_key || !c.baseline_value || !c.actual_value) continue;
      // 只保留每个 metric 最新一条
      if (!map.has(c.metric_key)) {
        map.set(c.metric_key, {
          baseline: c.baseline_value,
          actual: c.actual_value,
          effect: c.effect_size,
        });
      }
    }
    return Array.from(map.entries()).map(([metric, v]) => ({
      metric,
      label: METRIC_LABEL[metric] || metric,
      ...v,
    }));
  }, [data]);

  if (loading && !data) {
    return <div className="min-h-screen bg-slate-950 text-slate-400 p-8 text-sm">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/" className="text-sm text-slate-400 hover:text-emerald-300">← 返回首页</Link>
          <h1 className="text-xl font-semibold">我的进度</h1>
          <div className="ml-auto flex items-center gap-1.5">
            {WINDOW_OPTIONS.map(opt => (
              <button
                key={opt.days}
                onClick={() => setDays(opt.days)}
                className={`rounded-md px-2.5 py-1 text-xs ${
                  days === opt.days
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {err && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {err}
          </div>
        )}

        {data && data.stats.total_surfaced === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center">
            <div className="text-3xl mb-2">🌱</div>
            <div className="text-base font-medium mb-1">这段时间还没有 AI 建议</div>
            <div className="text-sm text-slate-500 max-w-md mx-auto">
              Agent 主动产建议:<br />
              · Safety 触发的告警 (心率 / 睡眠 / 血压异常)<br />
              · 周日 21:07 自动生成的本周建议<br />
              · Specialist 在你提问时产出的建议
            </div>
          </div>
        ) : data && (
          <>
            {/* 改善叙事 — Web 独有, mobile 没的 */}
            {narrativeRows.length > 0 && (
              <div className="rounded-2xl bg-gradient-to-br from-emerald-500/15 to-emerald-500/5 border border-emerald-500/30 p-5 mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                  <span className="text-sm font-medium text-emerald-300">这 {days} 天 AI 让你变好的指标</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {narrativeRows.map(r => (
                    <div key={r.metric} className="rounded-xl bg-slate-900/40 border border-slate-800 p-3">
                      <div className="text-xs text-slate-500 mb-1">{r.label}</div>
                      <div className="font-mono tabular-nums text-base">
                        <span className="text-slate-300">{r.baseline}</span>
                        <span className="text-slate-600 mx-2">→</span>
                        <span className="text-emerald-300 font-semibold">{r.actual}</span>
                      </div>
                      {r.effect != null && (
                        <div className="text-[11px] text-emerald-400/70 mt-1">
                          效应 {(Math.abs(r.effect) * 100).toFixed(0)}%
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hero 数 */}
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-5 mb-4">
              <div className="text-xs text-emerald-300 uppercase tracking-wider">已闭环且改善的建议</div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-4xl font-bold text-emerald-300 tabular-nums">{data.stats.improved}</span>
                <span className="text-xl text-emerald-300/70 tabular-nums">/ {data.stats.total_surfaced}</span>
              </div>
              <div className="text-xs text-emerald-300/80 mt-1">
                AI 这 {days} 天给了 {data.stats.total_surfaced} 条建议, 你做完并改善 {data.stats.improved} 条
              </div>
            </div>

            {/* 4 数 grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <StatTile label="接受率" value={pct(data.stats.acceptance_rate)} sub={`${data.stats.accepted}/${data.stats.accepted + data.stats.declined}`} color="text-sky-400" />
              <StatTile label="完成率" value={pct(data.stats.completed && data.stats.accepted ? data.stats.completed / data.stats.accepted : null)} sub={`${data.stats.completed}/${data.stats.accepted}`} color="text-violet-400" />
              <StatTile label="验证率" value={pct(data.stats.verification_rate)} sub={`${data.stats.graded}/${data.stats.completed}`} color="text-amber-400" />
              <StatTile label="改善率" value={pct(data.stats.improvement_rate)} sub={`${data.stats.improved}/${data.stats.graded}`} color="text-emerald-400" />
            </div>

            {/* outcome 分布 */}
            <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4 mb-6">
              <div className="grid grid-cols-4 gap-3">
                <OutcomeBar label="改善" count={data.stats.improved} total={data.stats.graded} color="bg-emerald-400" />
                <OutcomeBar label="稳定" count={data.stats.unchanged} total={data.stats.graded} color="bg-slate-400" />
                <OutcomeBar label="反向" count={data.stats.worsened} total={data.stats.graded} color="bg-rose-400" />
                <OutcomeBar label="不足" count={data.stats.inconclusive} total={data.stats.graded} color="bg-slate-500/50" />
              </div>
            </div>

            {/* 验证中 */}
            {data.verifying_cards.length > 0 && (
              <div className="mb-6">
                <div className="flex items-baseline gap-2 mb-2">
                  <h2 className="text-sm font-medium">验证中 ({data.verifying_cards.length})</h2>
                  <span className="text-xs text-slate-500">已接受并做完, 等 Agent 拉数据评估</span>
                </div>
                <div className="space-y-2">
                  {data.verifying_cards.map(c => <CardRow key={c.id} card={c} />)}
                </div>
              </div>
            )}

            {/* 已闭环 */}
            {data.closed_cards.length > 0 && (
              <div>
                <div className="flex items-baseline gap-2 mb-2">
                  <h2 className="text-sm font-medium">已闭环 ({data.closed_cards.length})</h2>
                  <span className="text-xs text-slate-500">Agent 已自动评估完成</span>
                </div>
                <div className="space-y-2">
                  {data.closed_cards.map(c => <CardRow key={c.id} card={c} />)}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatTile({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-3">
      <div className="text-[11px] text-slate-500 uppercase">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      <div className="text-[11px] text-slate-500 tabular-nums">{sub}</div>
    </div>
  );
}

function OutcomeBar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const w = total > 0 ? (count / total) * 100 : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[11px] text-slate-400">{label}</span>
        <span className="text-sm font-medium tabular-nums">{count}</span>
      </div>
      <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
        <div className={color} style={{ width: `${w}%`, height: '100%' }} />
      </div>
    </div>
  );
}

function CardRow({ card }: { card: ProgressCard }) {
  const oc = card.outcome ? OUTCOME_STYLE[card.outcome] : null;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-800 bg-slate-900/40 p-3">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium leading-snug line-clamp-2">{card.title}</div>
        {card.metric_key && card.baseline_value && card.actual_value ? (
          <div className="mt-1 text-xs text-slate-500 tabular-nums font-mono">
            {METRIC_LABEL[card.metric_key] || card.metric_key} {card.baseline_value} → {card.actual_value}
          </div>
        ) : card.metric_key ? (
          <div className="mt-1 text-xs text-slate-500">等待 {METRIC_LABEL[card.metric_key] || card.metric_key} 数据</div>
        ) : null}
      </div>
      {oc && (
        <span className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-medium ${oc.bg} ${oc.text}`}>
          {oc.arrow} {oc.label}
          {card.effect_size != null && card.outcome !== 'inconclusive' && (
            <span className="ml-1 tabular-nums">{(Math.abs(card.effect_size) * 100).toFixed(0)}%</span>
          )}
        </span>
      )}
    </div>
  );
}

export default function MyProgressPage() {
  return (
    <ProtectedRoute>
      <MyProgressInner />
    </ProtectedRoute>
  );
}
