'use client';

interface Task {
  task: string;
  expected_per_day: number | null;
  expected_per_week: number | null;
  window_hours: number;
  observed: number;
  last_run: string | null;
  status: 'ok' | 'stale' | 'no_data' | 'observing';
}

interface Props {
  tasks: Task[];
  note?: string;
}

const STATUS_STYLE: Record<string, string> = {
  ok: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/40',
  stale: 'bg-red-500/20 text-red-200 border-red-400/40',
  no_data: 'bg-slate-500/20 text-slate-200 border-slate-400/40',
  observing: 'bg-amber-500/20 text-amber-200 border-amber-400/40',
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
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function expected(t: Task): string {
  if (t.expected_per_day) return `~ ${t.expected_per_day}/天`;
  if (t.expected_per_week) return `~ ${t.expected_per_week}/周`;
  return '未知频次';
}

export default function CeleryHealthBlock({ tasks, note }: Props) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-5">
      <h3 className="text-lg font-semibold text-white mb-1">H. Celery Beat 健康</h3>
      {note && <p className="text-xs text-purple-200/60 mb-3">{note}</p>}
      <div className="grid gap-2">
        {tasks.map((t) => (
          <div
            key={t.task}
            className={`border rounded-md px-3 py-2 flex justify-between items-center ${
              STATUS_STYLE[t.status] ?? STATUS_STYLE.no_data
            }`}
          >
            <div>
              <div className="font-medium text-sm">{t.task}</div>
              <div className="text-xs opacity-70">
                {expected(t)} · 窗口 {t.window_hours}h · observed {t.observed} · 最近 {fmtTime(t.last_run)}
              </div>
            </div>
            <div className="text-sm font-mono">
              {STATUS_LABEL[t.status] ?? t.status}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
