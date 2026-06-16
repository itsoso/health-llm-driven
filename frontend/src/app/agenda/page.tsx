'use client';

import {
  CalendarCheck,
  Circle,
  Dumbbell,
  Droplets,
  GitCompare,
  Loader2,
  Pill,
  RefreshCw,
  Utensils,
  Wrench,
  Moon,
  Check,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import { api } from '@/services/api/client';
import {
  agendaItemPresentation,
  agendaSummary,
  type AgendaItem,
  type AgendaSource,
  type AgendaToday,
} from '@/components/agenda/agendaPresentation';

const ICONS = {
  CalendarCheck,
  Circle,
  Dumbbell,
  Droplets,
  GitCompare,
  Pill,
  Utensils,
  Wrench,
  Moon,
};

const TONE_CLASS = {
  green: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  yellow: 'border-amber-200 bg-amber-50 text-amber-700',
  red: 'border-red-200 bg-red-50 text-red-700',
  blue: 'border-sky-200 bg-sky-50 text-sky-700',
  gray: 'border-gray-200 bg-gray-50 text-gray-700',
};

function AgendaContent() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['agenda', 'today'],
    queryFn: async () => (await api.get<AgendaToday>('/agenda/today')).data,
    staleTime: 60_000,
  });
  const complete = useMutation({
    mutationFn: async (source: AgendaSource) => {
      await api.post('/agenda/complete', {
        object_type: source.object_type,
        object_id: source.object_id,
        track: 'protocol',
        value: null,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agenda', 'today'] }),
  });

  const items = data?.items ?? [];
  const summary = agendaSummary(items);

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <section className="flex flex-col gap-3 border-b border-slate-200 pb-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-500">Health Agenda</p>
            <h1 className="mt-1 text-3xl font-bold tracking-normal text-slate-950">今日议程</h1>
            <p className="mt-2 text-sm text-slate-600">
              {data ? `${data.agenda_date} · ${summary.total} 项` : '协议、复查、训练灯和设备数据质量的一处视图'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm disabled:opacity-60"
          >
            {isRefetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            刷新
          </button>
        </section>

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <SummaryTile label="全部" value={summary.total} />
          <SummaryTile label="待执行" value={summary.actionable} />
          <SummaryTile label="逾期复查" value={summary.overdue} tone="red" />
          <SummaryTile label="只读建议" value={summary.info} tone="yellow" />
        </section>

        {isLoading ? (
          <StatePanel icon={<Loader2 className="h-5 w-5 animate-spin" />} title="正在加载今日议程" />
        ) : isError ? (
          <StatePanel title="加载失败" description="请稍后重试或检查登录状态。" />
        ) : items.length === 0 ? (
          <StatePanel title="今天没有待办" description="系统暂未生成协议、复查或训练灯项目。" />
        ) : (
          <section className="space-y-3">
            {items.map((item, index) => (
              <AgendaRow
                key={`${item.source.object_type}-${item.source.object_id}-${item.type}-${index}`}
                item={item}
                onComplete={() => complete.mutate(item.source)}
                completing={complete.isPending}
              />
            ))}
          </section>
        )}
      </div>
    </main>
  );
}

function SummaryTile({ label, value, tone = 'blue' }: { label: string; value: number; tone?: 'blue' | 'red' | 'yellow' }) {
  const toneClass = tone === 'red' ? 'text-red-700' : tone === 'yellow' ? 'text-amber-700' : 'text-sky-700';
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className={`text-2xl font-bold ${toneClass}`}>{value}</div>
      <div className="mt-1 text-xs font-semibold text-slate-500">{label}</div>
    </div>
  );
}

function AgendaRow({ item, onComplete, completing }: { item: AgendaItem; onComplete: () => void; completing: boolean }) {
  const presentation = agendaItemPresentation(item);
  const Icon = ICONS[presentation.icon as keyof typeof ICONS] ?? Circle;
  const toneClass = TONE_CLASS[presentation.tone];

  return (
    <article className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-[44px_1fr_auto] md:items-center">
      <div className={`flex h-11 w-11 items-center justify-center rounded-lg border ${toneClass}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold text-slate-950">{item.title}</h2>
          <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${toneClass}`}>
            {presentation.statusLabel}
          </span>
        </div>
        <p className="mt-1 text-sm text-slate-600">
          {item.detail || presentation.meta || item.time_window || '暂无补充说明'}
        </p>
        {presentation.meta && item.detail ? (
          <p className="mt-1 text-xs text-slate-500">{presentation.meta}</p>
        ) : null}
      </div>
      {presentation.canComplete ? (
        <button
          type="button"
          onClick={onComplete}
          disabled={completing}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-slate-950 px-3 text-sm font-semibold text-white disabled:opacity-60"
        >
          <Check className="h-4 w-4" />
          完成
        </button>
      ) : null}
    </article>
  );
}

function StatePanel({ icon, title, description }: { icon?: React.ReactNode; title: string; description?: string }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-8 text-center">
      {icon ? <div className="mb-3 flex justify-center text-slate-500">{icon}</div> : null}
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      {description ? <p className="mt-2 text-sm text-slate-500">{description}</p> : null}
    </section>
  );
}

export default function AgendaPage() {
  return (
    <ProtectedRoute>
      <AgendaContent />
    </ProtectedRoute>
  );
}
