'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Database,
  FileText,
  KeyRound,
  RefreshCw,
  ShieldCheck,
  Watch,
} from 'lucide-react';

import ProtectedRoute from '@/components/ProtectedRoute';
import {
  connectionHealthDisplay,
  connectionStatusSummary,
  fetchDataConnections,
  type DataConnection,
} from '@/services/api/dataConnections';

function providerIcon(connection: DataConnection) {
  const text = `${connection.provider} ${connection.provider_type}`.toLowerCase();
  if (text.includes('healthkit') || text.includes('garmin') || text.includes('wearable')) {
    return <Watch className="h-5 w-5" />;
  }
  if (text.includes('fhir') || text.includes('report') || text.includes('lab')) {
    return <FileText className="h-5 w-5" />;
  }
  return <Database className="h-5 w-5" />;
}

function statusClasses(severity: string) {
  if (severity === 'ok') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (severity === 'blocked') {
    return 'border-slate-200 bg-slate-100 text-slate-600';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700';
}

function syncLine(connection: DataConnection) {
  if (connection.sync_error) return connection.sync_error;
  if (connection.last_success_at) return `最近成功 ${connection.last_success_at.slice(0, 10)}`;
  if (connection.last_attempt_at) return `最近尝试 ${connection.last_attempt_at.slice(0, 10)}`;
  return '等待首次同步';
}

function ConnectionCard({ connection }: { connection: DataConnection }) {
  const display = connectionHealthDisplay(connection);
  const health = display.health;

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
          {providerIcon(connection)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-base font-semibold text-slate-950">{connection.display_name}</h2>
            <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${statusClasses(health.severity)}`}>
              {display.label}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {connection.provider_type} · token {health.token_status ?? connection.token_status}
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-md bg-slate-50 p-3">
          <p className="text-xs font-medium text-slate-500">连接解释</p>
          <p className="mt-1 text-sm text-slate-800">{display.description}</p>
        </div>
        <div className="rounded-md bg-slate-50 p-3">
          <p className="text-xs font-medium text-slate-500">缓存策略</p>
          <div className="mt-1 flex items-center gap-2 text-sm text-slate-800">
            {health.can_use_cached_data ? (
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
            ) : (
              <Ban className="h-4 w-4 text-slate-500" />
            )}
            <span>{display.cacheLabel}</span>
          </div>
        </div>
        <div className="rounded-md bg-slate-50 p-3">
          <p className="text-xs font-medium text-slate-500">同步状态</p>
          <p className="mt-1 text-sm text-slate-800">{syncLine(connection)}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {connection.scopes.slice(0, 8).map((scope) => (
          <span key={scope} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
            {scope}
          </span>
        ))}
        {connection.scopes.length > 8 ? (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
            +{connection.scopes.length - 8}
          </span>
        ) : null}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span>降级: {health.degraded_behavior ?? connection.policy?.degraded_behavior ?? 'read_only'}</span>
        <span>最小化: {connection.policy?.data_minimization ?? 'scoped_fields_only'}</span>
        {health.needs_reconnect ? (
          <span className="inline-flex items-center gap-1 font-semibold text-amber-700">
            <RefreshCw className="h-3.5 w-3.5" />
            {display.actionLabel}
          </span>
        ) : null}
      </div>
    </article>
  );
}

function DataConnectionsContent() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['data-connections'],
    queryFn: fetchDataConnections,
    staleTime: 120_000,
  });

  const connections = data?.connections ?? [];
  const summary = connectionStatusSummary(data);
  const counts = connections.reduce(
    (acc, connection) => {
      const status = connection.connection_health?.status ?? connection.connection_status;
      if (status === 'healthy' || status === 'active') acc.healthy += 1;
      else if (status === 'revoked') acc.revoked += 1;
      else acc.attention += 1;
      return acc;
    },
    { healthy: 0, attention: 0, revoked: 0 },
  );

  return (
    <main className="min-h-screen bg-slate-50 px-4 pb-12 pt-24">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">管理中心</p>
            <h1 className="mt-1 text-3xl font-semibold text-slate-950">数据连接与授权</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              {summary}。这里统一展示数据源是否可用、是否需要重连，以及已授权缓存是否还能只读使用。
            </p>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>

        <div className="mb-5 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              可用
            </div>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{counts.healthy}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              需处理
            </div>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{counts.attention}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
              <KeyRound className="h-4 w-4 text-slate-600" />
              已撤权
            </div>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{counts.revoked}</p>
          </div>
        </div>

        {isLoading ? (
          <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
            加载中...
          </div>
        ) : isError ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            加载失败，请稍后刷新。
          </div>
        ) : connections.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-white p-8 text-center">
            <Database className="mx-auto h-9 w-9 text-slate-400" />
            <h2 className="mt-3 text-lg font-semibold text-slate-900">暂无统一连接</h2>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">
              HealthKit、Garmin、FHIR Bundle 和体检报告来源会逐步纳入这里。
            </p>
            <Link
              href="/settings"
              className="mt-4 inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              前往设置
            </Link>
          </div>
        ) : (
          <div className="grid gap-4">
            {connections.map((connection) => (
              <ConnectionCard key={connection.id} connection={connection} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function DataConnectionsPage() {
  return (
    <ProtectedRoute>
      <DataConnectionsContent />
    </ProtectedRoute>
  );
}
