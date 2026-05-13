'use client';

/**
 * /admin/open-loop — 主动循环推送看板 (2026-05-13).
 *
 * 看 open_loop_manager 实际推了几条 / 接受率多少 / 哪类信号噪声大.
 * 没这个看板, "AI 主动盯" 就只是 Celery 跑了不知道效果.
 */

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

interface KindRow {
  kind: string;
  count: number;
  ok: number;
  opened: number;
  dismissed: number;
  done: number;
  snooze_7d: number;
  not_interested: number;
  no_action: number;
  acceptance_rate: number;
}

interface DayRow {
  date: string;
  count: number;
  ok: number;
}

interface Stats {
  window_days: number;
  total: number;
  delivered_ok: number;
  delivery_rate: number;
  acceptance_rate: number;
  active_users: number;
  by_kind: KindRow[];
  by_action: Record<string, number>;
  by_day: DayRow[];
}

interface RecentRow {
  id: number;
  user_id: number;
  kind: string;
  signal_key: string;
  score: number;
  title: string;
  body: string;
  sent_at: string;
  delivery_ok: boolean;
  delivery_error: string | null;
  user_action: string | null;
  action_at: string | null;
}

const KIND_LABEL: Record<string, string> = {
  lab_overdue: '化验复查',
  action_card_due: 'ActionCard 到期',
  sync_stale: 'Garmin 不同步',
  trend_anomaly: '趋势异常',
  plan_drift: '计划偏离',
};

function pct(n: number) { return `${(n * 100).toFixed(1)}%`; }

function rateColor(rate: number) {
  if (rate >= 0.5) return 'text-emerald-400';
  if (rate >= 0.25) return 'text-amber-400';
  return 'text-rose-400';
}

function OpenLoopInner() {
  const { token } = useAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<RecentRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [filterKind, setFilterKind] = useState<string>('');

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const recentUrl = filterKind
        ? `/api/v1/admin/open-loop/recent?limit=50&kind=${encodeURIComponent(filterKind)}`
        : `/api/v1/admin/open-loop/recent?limit=50`;
      const [statsResp, recentResp] = await Promise.all([
        fetch(`/api/v1/admin/open-loop/stats?days=${days}`, { headers }),
        fetch(recentUrl, { headers }),
      ]);
      if (!statsResp.ok) throw new Error(`stats ${statsResp.status}`);
      if (!recentResp.ok) throw new Error(`recent ${recentResp.status}`);
      setStats(await statsResp.json());
      setRecent(await recentResp.json());
    } catch (e: any) {
      setErr(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, days, filterKind]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/admin" className="text-slate-400 hover:text-emerald-300 text-sm">
            ← 返回 admin
          </Link>
          <h1 className="text-xl font-semibold">主动推送看板 (Open-Loop)</h1>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-slate-500">窗口</span>
            {[7, 14, 30].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded-md px-2 py-1 text-xs ${
                  days === d ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {d} 天
              </button>
            ))}
          </div>
        </div>

        {err && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {err}
          </div>
        )}

        {loading && !stats && (
          <div className="text-sm text-slate-500">加载中...</div>
        )}

        {stats && (
          <>
            {/* 总览卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
                <div className="text-[11px] text-slate-500 uppercase">总推送</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">{stats.total}</div>
              </div>
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
                <div className="text-[11px] text-slate-500 uppercase">送达率</div>
                <div className={`mt-1 text-2xl font-semibold tabular-nums ${rateColor(stats.delivery_rate)}`}>
                  {pct(stats.delivery_rate)}
                </div>
                <div className="text-[11px] text-slate-500">{stats.delivered_ok} / {stats.total}</div>
              </div>
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
                <div className="text-[11px] text-slate-500 uppercase">接受率</div>
                <div className={`mt-1 text-2xl font-semibold tabular-nums ${rateColor(stats.acceptance_rate)}`}>
                  {pct(stats.acceptance_rate)}
                </div>
                <div className="text-[11px] text-slate-500">opened + done</div>
              </div>
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
                <div className="text-[11px] text-slate-500 uppercase">活跃用户</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">{stats.active_users}</div>
              </div>
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
                <div className="text-[11px] text-slate-500 uppercase">日均</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">
                  {(stats.total / stats.window_days).toFixed(1)}
                </div>
                <div className="text-[11px] text-slate-500">{stats.window_days} 天</div>
              </div>
            </div>

            {/* 按 kind 分布 */}
            <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4 mb-6">
              <div className="text-sm font-medium mb-3">按信号类型分布</div>
              <table className="w-full text-sm tabular-nums">
                <thead className="text-[11px] text-slate-500 uppercase border-b border-slate-800">
                  <tr>
                    <th className="text-left py-2 px-2">类型</th>
                    <th className="text-right py-2 px-2">总数</th>
                    <th className="text-right py-2 px-2">送达</th>
                    <th className="text-right py-2 px-2">opened</th>
                    <th className="text-right py-2 px-2">done</th>
                    <th className="text-right py-2 px-2">dismissed</th>
                    <th className="text-right py-2 px-2">无响应</th>
                    <th className="text-right py-2 px-2">接受率</th>
                    <th className="px-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {stats.by_kind.length === 0 ? (
                    <tr><td colSpan={9} className="py-4 text-center text-slate-500">无数据</td></tr>
                  ) : stats.by_kind.map(r => (
                    <tr key={r.kind} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-2 px-2">
                        <span className="font-medium">{KIND_LABEL[r.kind] || r.kind}</span>
                        <span className="ml-2 text-[11px] text-slate-500">{r.kind}</span>
                      </td>
                      <td className="text-right px-2">{r.count}</td>
                      <td className="text-right px-2">{r.ok}</td>
                      <td className="text-right px-2 text-emerald-400">{r.opened}</td>
                      <td className="text-right px-2 text-emerald-400">{r.done}</td>
                      <td className="text-right px-2 text-rose-400">{r.dismissed}</td>
                      <td className="text-right px-2 text-slate-500">{r.no_action}</td>
                      <td className={`text-right px-2 font-medium ${rateColor(r.acceptance_rate)}`}>
                        {pct(r.acceptance_rate)}
                      </td>
                      <td className="px-2">
                        <button
                          onClick={() => setFilterKind(filterKind === r.kind ? '' : r.kind)}
                          className="text-[11px] text-emerald-400/70 hover:text-emerald-300"
                        >
                          {filterKind === r.kind ? '取消' : '看明细'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 按天 */}
            <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4 mb-6">
              <div className="text-sm font-medium mb-3">每日推送量 ({stats.window_days} 天)</div>
              {stats.by_day.length === 0 ? (
                <div className="text-sm text-slate-500">无数据</div>
              ) : (
                <div className="flex items-end gap-1 h-32">
                  {stats.by_day.map(d => {
                    const max = Math.max(...stats.by_day.map(x => x.count), 1);
                    const h = Math.max(2, Math.round((d.count / max) * 100));
                    return (
                      <div key={d.date} className="flex-1 flex flex-col items-center group">
                        <div
                          className="w-full bg-emerald-600/60 hover:bg-emerald-500 rounded-t-sm transition-colors"
                          style={{ height: `${h}%` }}
                          title={`${d.date}: ${d.count} 条 (${d.ok} 送达)`}
                        />
                        <div className="text-[9px] text-slate-600 mt-1 truncate w-full text-center">
                          {d.date.slice(5)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 明细 */}
            <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4">
              <div className="flex items-center mb-3">
                <div className="text-sm font-medium">
                  最近 50 条 {filterKind && <span className="ml-2 text-emerald-400">(筛选: {KIND_LABEL[filterKind] || filterKind})</span>}
                </div>
                {filterKind && (
                  <button
                    onClick={() => setFilterKind('')}
                    className="ml-auto text-xs text-slate-500 hover:text-slate-300"
                  >
                    清除筛选
                  </button>
                )}
              </div>
              <div className="space-y-2">
                {recent.length === 0 ? (
                  <div className="text-sm text-slate-500 py-4">无数据</div>
                ) : recent.map(r => (
                  <div key={r.id} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-sm">
                    <div className="flex items-center gap-2 text-[11px] text-slate-500">
                      <span className="rounded bg-slate-800 px-1.5 py-0.5">{KIND_LABEL[r.kind] || r.kind}</span>
                      <span>user={r.user_id}</span>
                      <span>score={r.score}</span>
                      <span>{r.signal_key}</span>
                      <span className="ml-auto">{new Date(r.sent_at).toLocaleString('zh-CN')}</span>
                    </div>
                    <div className="mt-1 font-medium">{r.title}</div>
                    <div className="text-slate-400 text-[13px]">{r.body}</div>
                    <div className="mt-1 flex items-center gap-2 text-[11px]">
                      <span className={r.delivery_ok ? 'text-emerald-400' : 'text-rose-400'}>
                        {r.delivery_ok ? '✓ 送达' : '✗ 失败'}
                      </span>
                      {r.user_action && (
                        <span className={
                          r.user_action === 'opened' || r.user_action === 'done'
                            ? 'text-emerald-400'
                            : r.user_action === 'dismissed' || r.user_action === 'not_interested'
                            ? 'text-rose-400'
                            : 'text-amber-400'
                        }>
                          → {r.user_action}
                        </span>
                      )}
                      {!r.user_action && <span className="text-slate-600">无响应</span>}
                      {r.delivery_error && (
                        <span className="text-rose-400 truncate">{r.delivery_error}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function OpenLoopAdminPage() {
  return (
    <ProtectedRoute>
      <OpenLoopInner />
    </ProtectedRoute>
  );
}
