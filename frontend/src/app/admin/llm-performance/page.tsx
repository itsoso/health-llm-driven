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

interface Failure {
  id: number;
  provider: string;
  model: string;
  caller: string | null;
  user_id: number | null;
  latency_ms: number | null;
  created_at: string;
}

function LLMPerformanceInner() {
  const { token } = useAuth();
  const [stats, setStats] = useState<PerfRow[]>([]);
  const [failures, setFailures] = useState<Failure[]>([]);
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
      const [statsResp, failResp] = await Promise.all([
        fetch(`/api/v1/admin/llm/performance-stats?days=${days}&group_by=${groupBy}`, { headers }),
        fetch(`/api/v1/admin/llm/performance-failures?days=${days}&limit=30`, { headers }),
      ]);
      if (!statsResp.ok) throw new Error(`stats ${statsResp.status}`);
      if (!failResp.ok) throw new Error(`failures ${failResp.status}`);
      const sj = await statsResp.json();
      const fj = await failResp.json();
      setStats(sj.stats || []);
      setFailures(fj.failures || []);
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
  const pctColor = (v: number | null) => v == null ? 'text-slate-400'
    : v >= 0.95 ? 'text-emerald-500'
    : v >= 0.85 ? 'text-amber-500'
    : 'text-rose-500';

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center gap-3">
          <Link href="/admin" className="text-sm text-slate-500 hover:text-emerald-600">← admin</Link>
          <h1 className="text-2xl font-bold text-slate-900">LLM 性能监控</h1>
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
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
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
