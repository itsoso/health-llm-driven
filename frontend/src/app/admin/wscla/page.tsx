'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

interface WscalDashboard {
  window: { since: string; until: string; user_id: number | null };
  metrics: {
    wscla_count: number;
    suggestion_acceptance_rate: number | null;
    verification_rate: number | null;
    push_ctr: number | null;
    safety_fp_rate: number | null;
  };
  counts: Record<string, number>;
  by_severity: Record<string, number>;
  by_source_type: Record<string, number>;
  recent_cards: Array<{
    id: number;
    user_id: number;
    title: string;
    card_type: string;
    source_type: string | null;
    source_id: string | null;
    severity: string | null;
    status: string | null;
    user_decision: string | null;
    outcome: string | null;
    accuracy_score: number | null;
    created_at: string | null;
    decided_at: string | null;
    completed_at: string | null;
    graded_at: string | null;
    push_sent_at: string | null;
    push_clicked_at: string | null;
  }>;
}

function pct(v: number | null): string {
  if (v === null || v === undefined) return '—';
  return (v * 100).toFixed(1) + '%';
}

function fmtTime(s: string | null): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return s;
  }
}

export default function WsclaDashboardPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const [userFilter, setUserFilter] = useState<string>('');

  useEffect(() => {
    if (!authLoading && (!user || !user.is_admin)) {
      router.replace('/admin');
    }
  }, [user, authLoading, router]);

  const { data, isLoading, error, refetch } = useQuery<WscalDashboard>({
    queryKey: ['admin', 'wscla', userFilter],
    queryFn: async () => {
      const params = userFilter ? `?user_id=${encodeURIComponent(userFilter)}` : '';
      const res = await api.get(`/admin/wscla${params}`);
      return res.data;
    },
    enabled: !!user && user.is_admin,
    refetchInterval: 60_000,
  });

  if (authLoading || !user) {
    return <div className="p-8">加载中…</div>;
  }
  if (!user.is_admin) return null;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">WSCLA 北极星看板</h1>
          <p className="text-sm text-gray-500 mt-1">
            Weekly Safe Closed-Loop Actions — 本周用户因 App 采取、闭环完成且结果安全的行动数
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            placeholder="user_id (空=全部)"
            value={userFilter}
            onChange={(e) => setUserFilter(e.target.value.trim())}
            className="border rounded px-3 py-1 text-sm w-40"
          />
          <button
            onClick={() => refetch()}
            className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200"
          >
            刷新
          </button>
        </div>
      </div>

      {isLoading && <div>数据加载中…</div>}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 p-3 rounded">
          加载失败: {String(error)}
        </div>
      )}

      {data && (
        <>
          <div className="text-sm text-gray-500 mb-4">
            窗口: {fmtTime(data.window.since)} → {fmtTime(data.window.until)}
            {data.window.user_id && <> · 用户 #{data.window.user_id}</>}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
            <MetricCard
              label="WSCLA"
              value={String(data.metrics.wscla_count)}
              hint="闭环 + safe outcome"
              highlight
            />
            <MetricCard
              label="建议接受率"
              value={pct(data.metrics.suggestion_acceptance_rate)}
              hint={`${data.counts.accepted}/${data.counts.decided}`}
            />
            <MetricCard
              label="验证率"
              value={pct(data.metrics.verification_rate)}
              hint={`${data.counts.graded}/${data.counts.eligible_for_verify}`}
            />
            <MetricCard
              label="推送 CTR"
              value={pct(data.metrics.push_ctr)}
              hint={`${data.counts.push_clicked}/${data.counts.push_sent}`}
            />
            <MetricCard
              label="Safety 误报率"
              value={pct(data.metrics.safety_fp_rate)}
              hint={`${data.counts.safety_false_positive}/${data.counts.safety_decided}`}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <DistributionCard title="按严重度" data={data.by_severity} />
            <DistributionCard title="按来源" data={data.by_source_type} />
          </div>

          <div>
            <h2 className="text-lg font-semibold mb-3">近 20 条 action_cards</h2>
            <div className="overflow-x-auto border rounded">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-left">
                  <tr>
                    <th className="p-2">id</th>
                    <th className="p-2">user</th>
                    <th className="p-2">title</th>
                    <th className="p-2">来源 / 规则</th>
                    <th className="p-2">严重度</th>
                    <th className="p-2">决策</th>
                    <th className="p-2">outcome</th>
                    <th className="p-2">创建</th>
                    <th className="p-2">闭环</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_cards.map((c) => (
                    <tr key={c.id} className="border-t hover:bg-gray-50">
                      <td className="p-2 font-mono text-xs">{c.id}</td>
                      <td className="p-2">{c.user_id}</td>
                      <td className="p-2 max-w-xs truncate">{c.title}</td>
                      <td className="p-2 text-xs text-gray-600">
                        {c.source_type}
                        {c.source_id && <> / {c.source_id}</>}
                      </td>
                      <td className="p-2">
                        {c.severity && <SeverityBadge severity={c.severity} />}
                      </td>
                      <td className="p-2">
                        {c.user_decision && <DecisionBadge decision={c.user_decision} />}
                      </td>
                      <td className="p-2">
                        {c.outcome && <OutcomeBadge outcome={c.outcome} />}
                      </td>
                      <td className="p-2 text-xs text-gray-500">{fmtTime(c.created_at)}</td>
                      <td className="p-2 text-xs text-gray-500">{fmtTime(c.graded_at)}</td>
                    </tr>
                  ))}
                  {data.recent_cards.length === 0 && (
                    <tr>
                      <td className="p-4 text-center text-gray-500" colSpan={9}>
                        窗口内无 action_cards
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  highlight,
}: {
  label: string;
  value: string;
  hint?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`border rounded p-4 ${
        highlight ? 'border-blue-400 bg-blue-50' : 'border-gray-200 bg-white'
      }`}
    >
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-3xl font-bold mt-1 ${highlight ? 'text-blue-700' : ''}`}>
        {value}
      </div>
      {hint && <div className="text-xs text-gray-400 mt-1">{hint}</div>}
    </div>
  );
}

function DistributionCard({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  const entries = Object.entries(data).sort(([, a], [, b]) => b - a);
  return (
    <div className="border rounded p-4 bg-white">
      <div className="font-medium mb-3">{title}</div>
      {entries.length === 0 && <div className="text-sm text-gray-500">无数据</div>}
      <div className="space-y-2">
        {entries.map(([k, n]) => {
          const pctOfTotal = total > 0 ? (n / total) * 100 : 0;
          return (
            <div key={k} className="text-sm">
              <div className="flex justify-between mb-1">
                <span>{k}</span>
                <span className="text-gray-500">
                  {n} ({pctOfTotal.toFixed(0)}%)
                </span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                <div
                  className="h-full bg-blue-500"
                  style={{ width: `${pctOfTotal}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const style: Record<string, string> = {
    critical: 'bg-red-100 text-red-800',
    high: 'bg-orange-100 text-orange-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-blue-100 text-blue-800',
    info: 'bg-gray-100 text-gray-700',
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${style[severity] || ''}`}>
      {severity}
    </span>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const style: Record<string, string> = {
    accepted: 'bg-green-100 text-green-800',
    adjusted: 'bg-lime-100 text-lime-800',
    declined: 'bg-gray-200 text-gray-700',
    dismissed: 'bg-gray-100 text-gray-600',
    false_positive: 'bg-purple-100 text-purple-800',
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${style[decision] || ''}`}>
      {decision}
    </span>
  );
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const style: Record<string, string> = {
    improved: 'bg-emerald-100 text-emerald-800',
    unchanged: 'bg-slate-100 text-slate-700',
    worsened: 'bg-rose-100 text-rose-800',
    inconclusive: 'bg-zinc-100 text-zinc-600',
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${style[outcome] || ''}`}>
      {outcome}
    </span>
  );
}
