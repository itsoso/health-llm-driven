'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

interface PerfRow {
  label: string;
  n: number;
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  success_rate: number | null;
  total_tokens: number;
  cost_usd: number;
}

interface UsageRollup {
  calls: number;
  success_calls: number;
  failed_calls: number;
  success_rate: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  tokenplan_calls: number;
  tokenplan_tokens: number;
  cost_usd: number;
  allocated_plan_cost_cny: number;
  effective_cny_per_1k_tokens: number | null;
  avg_latency_ms: number;
  last_seen_at: string | null;
}

interface UsageByUser extends UsageRollup {
  user_id: number | null;
  name: string | null;
  email: string | null;
  username: string | null;
  share_pct: number;
}

interface UsageByModel extends UsageRollup {
  provider: string;
  model: string;
}

interface UsageByCaller extends UsageRollup {
  provider: string;
  caller: string;
}

interface UsageByDay extends UsageRollup {
  day: string;
}

interface QuotaGuard {
  monthly_token_quota: number;
  tokens_used_month: number;
  quota_utilization_pct: number | null;
  projected_month_tokens: number | null;
  projected_quota_utilization_pct: number | null;
  level: 'unknown' | 'ok' | 'watch' | 'warn' | 'critical';
  recommended_runtime_policy: string;
  suggested_actions: string[];
}

interface UsageDashboard {
  window: {
    days: number;
    since: string;
    until: string;
    user_id: number | null;
  };
  plan: {
    name: string;
    currency: string;
    monthly_budget_cny: number;
    allocation_basis: string;
    tokenplan_model_names: string[];
    legacy_provider_note: string;
    quota_guard: QuotaGuard;
  };
  overall: UsageRollup;
  by_user: UsageByUser[];
  by_provider: Array<UsageRollup & { provider: string }>;
  by_model: UsageByModel[];
  by_caller: UsageByCaller[];
  by_day: UsageByDay[];
}

interface Failure {
  id: number;
  provider: string;
  model: string;
  caller: string | null;
  user_id: number | null;
  latency_ms: number | null;
  run_id?: string | null;
  error_class?: string | null;
  error_type?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  recovery_action?: string | null;
  recovery_model?: string | null;
  created_at: string;
}

interface RecentCall extends Failure {
  name: string | null;
  email: string | null;
  username: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  success: boolean;
}

function LLMPerformanceInner() {
  const { token } = useAuth();
  const [usage, setUsage] = useState<UsageDashboard | null>(null);
  const [stats, setStats] = useState<PerfRow[]>([]);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [recentCalls, setRecentCalls] = useState<RecentCall[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [groupBy, setGroupBy] = useState<'model' | 'provider' | 'caller'>('model');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [usageResp, statsResp, failResp, recentResp] = await Promise.all([
        fetch(`/api/v1/admin/llm/usage-dashboard?days=${days}`, { headers }),
        fetch(`/api/v1/admin/llm/performance-stats?days=${days}&group_by=${groupBy}`, { headers }),
        fetch(`/api/v1/admin/llm/performance-failures?days=${days}&limit=30`, { headers }),
        fetch(`/api/v1/admin/llm/recent-calls?days=${days}&limit=50`, { headers }),
      ]);
      if (!usageResp.ok) throw new Error(`usage ${usageResp.status}`);
      if (!statsResp.ok) throw new Error(`stats ${statsResp.status}`);
      if (!failResp.ok) throw new Error(`failures ${failResp.status}`);
      if (!recentResp.ok) throw new Error(`recent ${recentResp.status}`);
      const uj = await usageResp.json();
      const sj = await statsResp.json();
      const fj = await failResp.json();
      const rj = await recentResp.json();
      setUsage(uj);
      setStats(sj.stats || []);
      setFailures(fj.failures || []);
      setRecentCalls(rj.calls || []);
    } catch (e: any) {
      setErr(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, days, groupBy]);

  useEffect(() => {
    load();
  }, [load]);

  const fmt = (v: number | null | undefined) => v == null ? '—' : String(v);
  const fmtPct = (v: number | null) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
  const fmtTokens = (v: number) => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(2)}M` : `${(v / 1000).toFixed(1)}k`;
  const fmtCny = (v: number | null | undefined) => v == null ? '—' : `¥${v.toFixed(2)}`;
  const fmtUsd = (v: number | null | undefined) => v == null ? '—' : `$${v.toFixed(4)}`;
  const fmtTrace = (v: string | null | undefined) => v ? v.slice(0, 18) : '—';
  const pctColor = (v: number | null) => v == null ? 'text-slate-400'
    : v >= 0.95 ? 'text-emerald-500'
    : v >= 0.85 ? 'text-amber-500'
    : 'text-rose-500';
  const guardTone = (level: QuotaGuard['level'] | undefined) => {
    switch (level) {
      case 'critical': return 'border-rose-200 bg-rose-50 text-rose-800';
      case 'warn': return 'border-amber-200 bg-amber-50 text-amber-800';
      case 'watch': return 'border-sky-200 bg-sky-50 text-sky-800';
      case 'ok': return 'border-emerald-200 bg-emerald-50 text-emerald-800';
      default: return 'border-slate-200 bg-slate-50 text-slate-700';
    }
  };
  const maxDayTokens = Math.max(1, ...(usage?.by_day || []).map(d => d.total_tokens));

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center gap-3">
          <Link href="/admin" className="text-sm text-slate-500 hover:text-emerald-600">← admin</Link>
          <h1 className="text-2xl font-bold text-slate-900">LLM Token / 成本监控</h1>
        </div>

        <div className="mb-4 flex gap-3 flex-wrap">
          {[3, 7, 14, 30].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
                days === d ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 border'
              }`}
            >{d} 天</button>
          ))}
          <div className="border-l mx-2" />
          {(['model', 'provider', 'caller'] as const).map(g => (
            <button
              key={g}
              onClick={() => setGroupBy(g)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
                groupBy === g ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 border'
              }`}
            >按 {g}</button>
          ))}
        </div>

        {err && (
          <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-sm">
            {err}
          </div>
        )}

        {loading ? (
          <div className="text-slate-400 text-center py-12">加载中…</div>
        ) : (
          <>
            {usage && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                  <div className="bg-white rounded-lg border p-4">
                    <p className="text-xs text-slate-500">套餐</p>
                    <p className="mt-1 text-xl font-semibold text-slate-900">{usage.plan.name}</p>
                    <p className="mt-2 text-sm text-slate-500">{fmtCny(usage.plan.monthly_budget_cny)} / 月</p>
                  </div>
                  <div className="bg-white rounded-lg border p-4">
                    <p className="text-xs text-slate-500">全局调用</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">{usage.overall.calls}</p>
                    <p className={`mt-2 text-sm ${pctColor(usage.overall.success_rate)}`}>
                      成功率 {fmtPct(usage.overall.success_rate)} · 失败 {usage.overall.failed_calls}
                    </p>
                  </div>
                  <div className="bg-white rounded-lg border p-4">
                    <p className="text-xs text-slate-500">TokenPlan tokens</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">{fmtTokens(usage.overall.tokenplan_tokens)}</p>
                    <p className="mt-2 text-sm text-slate-500">全部 tokens {fmtTokens(usage.overall.total_tokens)}</p>
                  </div>
                  <div className="bg-white rounded-lg border p-4">
                    <p className="text-xs text-slate-500">有效单价</p>
                    <p className="mt-1 text-2xl font-semibold text-emerald-700">
                      {usage.overall.effective_cny_per_1k_tokens == null ? '—' : fmtCny(usage.overall.effective_cny_per_1k_tokens)}
                    </p>
                    <p className="mt-2 text-sm text-slate-500">每 1k TokenPlan token</p>
                  </div>
                </div>

                <div className={`rounded-lg border p-4 mb-6 ${guardTone(usage.plan.quota_guard?.level)}`}>
                  <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
                    <div>
                      <div className="text-xs font-medium opacity-80">TokenPlan 额度治理</div>
                      <div className="mt-1 text-xl font-semibold">
                        {usage.plan.quota_guard.level.toUpperCase()} · {usage.plan.quota_guard.recommended_runtime_policy}
                      </div>
                      <div className="mt-1 text-sm opacity-80">
                        本月 {fmtTokens(usage.plan.quota_guard.tokens_used_month)}
                        {usage.plan.quota_guard.monthly_token_quota > 0
                          ? ` / ${fmtTokens(usage.plan.quota_guard.monthly_token_quota)} (${fmtPct(usage.plan.quota_guard.quota_utilization_pct)})`
                          : ' · 未配置月 token 额度'}
                        {usage.plan.quota_guard.projected_month_tokens != null
                          ? ` · 预计 ${fmtTokens(usage.plan.quota_guard.projected_month_tokens)}`
                          : ''}
                      </div>
                    </div>
                    <div className="max-w-xl text-sm">
                      {usage.plan.quota_guard.suggested_actions.map(action => (
                        <div key={action}>· {action}</div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-lg border overflow-hidden mb-6">
                  <div className="px-4 py-3 border-b bg-slate-50 flex flex-col md:flex-row md:items-end md:justify-between gap-2">
                    <div>
                      <h2 className="font-semibold text-slate-900">用户使用排行</h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {usage.plan.allocation_basis}; {usage.plan.legacy_provider_note}
                      </p>
                    </div>
                    <div className="text-xs text-slate-500">
                      {new Date(usage.window.since).toLocaleDateString('zh-CN')} - {new Date(usage.window.until).toLocaleDateString('zh-CN')}
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr className="text-left text-xs text-slate-500 uppercase">
                          <th className="px-4 py-2">用户</th>
                          <th className="px-4 py-2 text-right">调用</th>
                          <th className="px-4 py-2 text-right">tokens</th>
                          <th className="px-4 py-2 text-right">TokenPlan</th>
                          <th className="px-4 py-2 text-right">份额</th>
                          <th className="px-4 py-2 text-right">摊销成本</th>
                          <th className="px-4 py-2 text-right">成功率</th>
                          <th className="px-4 py-2 text-right">最近</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usage.by_user.length === 0 ? (
                          <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">无用户用量</td></tr>
                        ) : usage.by_user.map(row => (
                          <tr key={row.user_id ?? 'unknown'} className="border-t hover:bg-slate-50">
                            <td className="px-4 py-2">
                              <div className="font-medium text-slate-900">{row.name || row.username || `User ${row.user_id ?? 'unknown'}`}</div>
                              <div className="text-xs text-slate-500">{row.email || row.username || '未绑定身份'}</div>
                            </td>
                            <td className="px-4 py-2 text-right font-mono">{row.calls}</td>
                            <td className="px-4 py-2 text-right font-mono">{fmtTokens(row.total_tokens)}</td>
                            <td className="px-4 py-2 text-right font-mono">{fmtTokens(row.tokenplan_tokens)}</td>
                            <td className="px-4 py-2 text-right font-mono">{(row.share_pct * 100).toFixed(1)}%</td>
                            <td className="px-4 py-2 text-right font-mono text-emerald-700">{fmtCny(row.allocated_plan_cost_cny)}</td>
                            <td className={`px-4 py-2 text-right font-mono ${pctColor(row.success_rate)}`}>{fmtPct(row.success_rate)}</td>
                            <td className="px-4 py-2 text-right text-xs text-slate-500">
                              {row.last_seen_at ? new Date(row.last_seen_at).toLocaleString('zh-CN', { hour12: false }) : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                  <div className="bg-white rounded-lg border overflow-hidden">
                    <div className="px-4 py-3 border-b bg-slate-50">
                      <h2 className="font-semibold text-slate-900">模型成本排行</h2>
                      <p className="text-xs text-slate-500 mt-0.5">按窗口内 total tokens 排序, TokenPlan 模型按 ¥698 月费分摊</p>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-slate-50">
                          <tr className="text-left text-xs text-slate-500 uppercase">
                            <th className="px-4 py-2">模型</th>
                            <th className="px-4 py-2 text-right">调用</th>
                            <th className="px-4 py-2 text-right">tokens</th>
                            <th className="px-4 py-2 text-right">¥摊销</th>
                          </tr>
                        </thead>
                        <tbody>
                          {usage.by_model.slice(0, 10).map(row => (
                            <tr key={`${row.provider}:${row.model}`} className="border-t hover:bg-slate-50">
                              <td className="px-4 py-2">
                                <div className="font-mono text-slate-900">{row.model}</div>
                                <div className="text-xs text-slate-500">{row.provider}</div>
                              </td>
                              <td className="px-4 py-2 text-right font-mono">{row.calls}</td>
                              <td className="px-4 py-2 text-right font-mono">{fmtTokens(row.total_tokens)}</td>
                              <td className="px-4 py-2 text-right font-mono text-emerald-700">{fmtCny(row.allocated_plan_cost_cny)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="bg-white rounded-lg border overflow-hidden">
                    <div className="px-4 py-3 border-b bg-slate-50">
                      <h2 className="font-semibold text-slate-900">调用方消耗</h2>
                      <p className="text-xs text-slate-500 mt-0.5">定位最耗 token 的业务链路</p>
                    </div>
                    <div className="divide-y">
                      {usage.by_caller.slice(0, 10).map(row => (
                        <div key={row.caller} className="px-4 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="font-mono text-sm text-slate-900 truncate">{row.caller}</div>
                            <div className="text-sm font-mono text-slate-600">{fmtTokens(row.total_tokens)}</div>
                          </div>
                          <div className="mt-2 h-2 rounded-full bg-slate-100 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-emerald-500"
                              style={{ width: `${Math.min(100, (row.total_tokens / Math.max(usage.overall.total_tokens, 1)) * 100)}%` }}
                            />
                          </div>
                          <div className="mt-1 text-xs text-slate-500">
                            {row.provider} · {row.calls} 次 · {fmtCny(row.allocated_plan_cost_cny)} · {fmtUsd(row.cost_usd)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-lg border p-4 mb-6">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h2 className="font-semibold text-slate-900">每日 Token 趋势</h2>
                      <p className="text-xs text-slate-500 mt-0.5">绿色为 TokenPlan token, 灰色为全量 token</p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {usage.by_day.map(row => (
                      <div key={row.day} className="grid grid-cols-[88px_1fr_84px] items-center gap-3 text-xs">
                        <div className="font-mono text-slate-500">{row.day.slice(5)}</div>
                        <div className="h-7 rounded bg-slate-100 overflow-hidden relative">
                          <div className="absolute inset-y-0 left-0 bg-slate-300" style={{ width: `${(row.total_tokens / maxDayTokens) * 100}%` }} />
                          <div className="absolute inset-y-0 left-0 bg-emerald-500" style={{ width: `${(row.tokenplan_tokens / maxDayTokens) * 100}%` }} />
                        </div>
                        <div className="text-right font-mono text-slate-600">{fmtTokens(row.total_tokens)}</div>
                      </div>
                    ))}
                    {usage.by_day.length === 0 && <div className="text-sm text-slate-400 py-6 text-center">暂无趋势数据</div>}
                  </div>
                </div>
              </>
            )}

            {/* Perf table */}
            <div className="bg-white rounded-lg border overflow-hidden mb-6">
              <div className="px-4 py-3 border-b bg-slate-50">
                <h2 className="font-semibold text-slate-900">延迟 / 成功率 / token 聚合</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  近 {days} 天所有 LLM 调用, 按 {groupBy} 分组, p50/p95 单位毫秒
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-xs text-slate-500 uppercase">
                      <th className="px-4 py-2">{groupBy}</th>
                      <th className="px-4 py-2 text-right">N</th>
                      <th className="px-4 py-2 text-right">avg</th>
                      <th className="px-4 py-2 text-right">p50</th>
                      <th className="px-4 py-2 text-right">p95</th>
                      <th className="px-4 py-2 text-right">p99</th>
                      <th className="px-4 py-2 text-right">成功率</th>
                      <th className="px-4 py-2 text-right">tokens</th>
                      <th className="px-4 py-2 text-right">成本 $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.length === 0 ? (
                      <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-400">无数据</td></tr>
                    ) : stats.map(r => (
                      <tr key={r.label} className="border-t hover:bg-slate-50">
                        <td className="px-4 py-2 font-mono text-slate-900">{r.label || '—'}</td>
                        <td className="px-4 py-2 text-right font-mono">{r.n}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmt(r.avg_ms)}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmt(r.p50_ms)}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmt(r.p95_ms)}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmt(r.p99_ms)}</td>
                        <td className={`px-4 py-2 text-right font-mono ${pctColor(r.success_rate)}`}>
                          {fmtPct(r.success_rate)}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-slate-500">
                          {(r.total_tokens / 1000).toFixed(1)}k
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-slate-500">
                          {r.cost_usd.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Failures */}
            <div className="bg-white rounded-lg border overflow-hidden">
              <div className="px-4 py-3 border-b bg-slate-50">
                <h2 className="font-semibold text-slate-900">最近失败调用 (limit 30)</h2>
              </div>
              {failures.length === 0 ? (
                <div className="px-4 py-8 text-center text-emerald-500 text-sm">
                  近 {days} 天没有失败调用 ✓
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr className="text-left text-xs text-slate-500 uppercase">
                        <th className="px-4 py-2">时间</th>
                        <th className="px-4 py-2">provider</th>
                        <th className="px-4 py-2">model</th>
                        <th className="px-4 py-2">caller</th>
                        <th className="px-4 py-2 text-right">user</th>
                        <th className="px-4 py-2 text-right">latency</th>
                        <th className="px-4 py-2">错误摘要</th>
                        <th className="px-4 py-2">恢复</th>
                      </tr>
                    </thead>
                    <tbody>
                      {failures.map(f => (
                        <tr key={f.id} className="border-t hover:bg-slate-50">
                          <td className="px-4 py-2 font-mono text-xs text-slate-500">
                            {new Date(f.created_at).toLocaleString('zh-CN', { hour12: false })}
                          </td>
                          <td className="px-4 py-2 font-mono">{f.provider}</td>
                          <td className="px-4 py-2 font-mono">{f.model}</td>
                          <td className="px-4 py-2 font-mono text-slate-500">{f.caller || '—'}</td>
                          <td className="px-4 py-2 text-right font-mono text-slate-400">{f.user_id ?? '—'}</td>
                          <td className="px-4 py-2 text-right font-mono text-rose-500">
                            {f.latency_ms != null ? `${f.latency_ms}ms` : '—'}
                          </td>
                          <td className="px-4 py-2 text-xs text-rose-600 max-w-[280px]">
                            <div className="font-mono">{f.error_code || f.error_type || f.error_class || '—'}</div>
                            {f.error_message && (
                              <div className="mt-1 text-slate-500 line-clamp-2">{f.error_message}</div>
                            )}
                          </td>
                          <td className="px-4 py-2 text-xs text-slate-500">
                            <div className="font-mono">{f.recovery_action || '—'}</div>
                            {f.recovery_model && <div className="font-mono">{f.recovery_model}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="bg-white rounded-lg border overflow-hidden mt-6">
              <div className="px-4 py-3 border-b bg-slate-50">
                <h2 className="font-semibold text-slate-900">最近逐次调用</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  用于追踪单次请求的用户、模型、token、延迟和上游错误摘要
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-xs text-slate-500 uppercase">
                      <th className="px-4 py-2">时间</th>
                      <th className="px-4 py-2">用户</th>
                      <th className="px-4 py-2">run / caller</th>
                      <th className="px-4 py-2">模型</th>
                      <th className="px-4 py-2 text-right">tokens</th>
                      <th className="px-4 py-2 text-right">延迟</th>
                      <th className="px-4 py-2">状态</th>
                      <th className="px-4 py-2">错误摘要</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentCalls.length === 0 ? (
                      <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">暂无调用</td></tr>
                    ) : recentCalls.map(call => (
                      <tr key={call.id} className="border-t hover:bg-slate-50">
                        <td className="px-4 py-2 font-mono text-xs text-slate-500 whitespace-nowrap">
                          {new Date(call.created_at).toLocaleString('zh-CN', { hour12: false })}
                        </td>
                        <td className="px-4 py-2">
                          <div className="font-medium text-slate-900">{call.name || call.username || `User ${call.user_id ?? 'unknown'}`}</div>
                          <div className="text-xs text-slate-500">{call.email || call.username || '—'}</div>
                        </td>
                        <td className="px-4 py-2">
                          <div className="font-mono text-slate-900">{fmtTrace(call.run_id)}</div>
                          <div className="font-mono text-xs text-slate-500">{call.caller || '—'}</div>
                        </td>
                        <td className="px-4 py-2">
                          <div className="font-mono text-slate-900">{call.model}</div>
                          <div className="text-xs text-slate-500">{call.provider}</div>
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          <div>{fmtTokens(call.total_tokens)}</div>
                          <div className="text-xs text-slate-400">in {fmtTokens(call.prompt_tokens)} / out {fmtTokens(call.completion_tokens)}</div>
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-slate-500">
                          {call.latency_ms != null ? `${call.latency_ms}ms` : '—'}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                            call.success ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
                          }`}>
                            {call.success ? '成功' : '失败'}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-xs max-w-[320px]">
                          <div className="font-mono text-rose-600">{call.error_code || call.error_type || call.error_class || '—'}</div>
                          {call.error_message && (
                            <div className="mt-1 text-slate-500 line-clamp-2">{call.error_message}</div>
                          )}
                          {(call.recovery_action || call.recovery_model) && (
                            <div className="mt-1 font-mono text-slate-500">
                              {call.recovery_action || 'recovery'} {call.recovery_model ? `→ ${call.recovery_model}` : ''}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function LLMPerformancePage() {
  return (
    <ProtectedRoute>
      <LLMPerformanceInner />
    </ProtectedRoute>
  );
}
