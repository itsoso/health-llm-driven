'use client';

interface Props {
  data: {
    last_sync_at: string | null;
    last_sync_age_hours: number | null;
    active_users: number;
    invalid_cred_users: number;
    distinct_users_24h: number;
    stale_users_7d: number;
    status: 'ok' | 'stale' | 'no_data' | 'observing';
    note?: string;
  };
}

const STATUS_STYLE: Record<string, string> = {
  ok: 'border-emerald-400/40 bg-emerald-500/10',
  stale: 'border-red-400/40 bg-red-500/10',
  no_data: 'border-slate-400/40 bg-slate-500/10',
  observing: 'border-amber-400/40 bg-amber-500/10',
};

const STATUS_LABEL: Record<string, string> = {
  ok: '正常',
  stale: '失联',
  no_data: '无数据',
  observing: '观察中',
};

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function Stat({
  label,
  value,
  danger,
}: {
  label: string;
  value: string | number;
  danger?: boolean;
}) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-3">
      <div className="text-xs text-purple-200/70">{label}</div>
      <div className={`text-2xl font-semibold ${danger ? 'text-red-300' : 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}

export default function GarminSyncHealthBlock({ data }: Props) {
  return (
    <div className={`border rounded-xl p-5 ${STATUS_STYLE[data.status] ?? STATUS_STYLE.no_data}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-white">I. Garmin 同步健康</h3>
        <span className="text-sm font-mono text-white/80">
          {STATUS_LABEL[data.status] ?? data.status}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Stat label="active 用户" value={data.active_users} />
        <Stat label="24h 有数据" value={data.distinct_users_24h} />
        <Stat
          label="7 天零数据"
          value={data.stale_users_7d}
          danger={data.stale_users_7d > 0}
        />
        <Stat
          label="凭据失效"
          value={data.invalid_cred_users}
          danger={data.invalid_cred_users > 0}
        />
      </div>

      <div className="text-xs text-purple-200/60">
        最近成功同步: <span className="text-white/80">{fmtTime(data.last_sync_at)}</span>
        {data.last_sync_age_hours !== null && (
          <span className="ml-2 text-white/60">({data.last_sync_age_hours}h 前)</span>
        )}
      </div>

      {data.note && (
        <p className="text-xs text-purple-200/50 mt-3 leading-relaxed">{data.note}</p>
      )}
    </div>
  );
}
