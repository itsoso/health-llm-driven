'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api/client';
import { format, differenceInDays } from 'date-fns';

type Status = 'active' | 'improving' | 'resolved';

interface IllnessUpdate {
  id: number;
  update_date: string;
  severity: number | null;
  status: string | null;
  notes: string | null;
}

interface IllnessEpisode {
  id: number;
  name: string;
  start_date: string;
  end_date: string | null;
  status: Status;
  severity: number | null;
  notes: string | null;
  created_at: string;
  updates?: IllnessUpdate[];
}

const STATUS_LABEL: Record<string, string> = {
  active: '发作中',
  improving: '好转中',
  resolved: '已痊愈',
};

const STATUS_COLOR: Record<string, string> = {
  active: 'bg-red-500/10 text-red-400',
  improving: 'bg-yellow-500/10 text-yellow-400',
  resolved: 'bg-green-500/10 text-green-400',
};

function daysSince(dateStr: string) {
  return differenceInDays(new Date(), new Date(dateStr)) + 1;
}

function today() {
  return format(new Date(), 'yyyy-MM-dd');
}

function severityText(severity: number | null) {
  return severity === null ? '未记录' : `${severity}/10`;
}

function adjustedSeverity(severity: number | null, delta: number) {
  if (severity === null) return undefined;
  return Math.max(1, Math.min(10, severity + delta));
}

export default function IllnessPage() {
  const qc = useQueryClient();
  const [view, setView] = useState<'list' | 'detail' | 'create'>('list');
  const [detailId, setDetailId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  // 新建表单
  const [newName, setNewName] = useState('');
  const [newSeverity, setNewSeverity] = useState(5);
  const [newNotes, setNewNotes] = useState('');

  const { data: active = [], isLoading } = useQuery<IllnessEpisode[]>({
    queryKey: ['illness', 'active'],
    queryFn: () => api.get('/illness/episodes').then(r => r.data),
  });

  const { data: all = [] } = useQuery<IllnessEpisode[]>({
    queryKey: ['illness', 'all'],
    queryFn: () => api.get('/illness/episodes/all').then(r => r.data),
  });

  const { data: detail } = useQuery<IllnessEpisode>({
    queryKey: ['illness', 'detail', detailId],
    queryFn: () => api.get(`/illness/episodes/${detailId}`).then(r => r.data),
    enabled: !!detailId,
  });

  const history = all.filter(e => e.status === 'resolved');

  const createMutation = useMutation({
    mutationFn: (data: any) => api.post('/illness/episodes', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['illness'] });
      setView('list');
      setNewName(''); setNewSeverity(5); setNewNotes('');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => api.put(`/illness/episodes/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['illness'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/illness/episodes/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['illness'] });
      setView('list');
      setDetailId(null);
    },
  });

  function quickUpdate(ep: IllnessEpisode, status: Status, severity?: number) {
    const body: any = { status };
    if (severity !== undefined) body.severity = severity;
    updateMutation.mutate({ id: ep.id, data: body });
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <p className="text-slate-400">加载中...</p>
      </div>
    );
  }

  // ── 详情视图 ────────────────────────────────────────────────────
  if (view === 'detail' && detail) {
    const days = daysSince(detail.start_date);
    return (
      <div className="min-h-screen bg-slate-900 p-4 pb-24">
        <div className="flex items-center gap-3 mb-4">
          <button onClick={() => setView('list')} className="text-slate-400 text-2xl px-2">‹</button>
          <h1 className="text-white text-2xl font-bold flex-1">{detail.name}</h1>
          <button
            onClick={() => { if (confirm('确认删除？')) deleteMutation.mutate(detail.id); }}
            className="text-red-400 text-sm px-3 py-1 rounded-lg bg-red-500/10"
          >删除</button>
        </div>

        <div className="bg-slate-800 rounded-xl p-4 mb-4">
          <div className="flex flex-wrap gap-4 text-sm text-slate-300">
            <span>📅 发作：{detail.start_date}</span>
            <span>⏱ {days} 天</span>
            <span>严重度：{severityText(detail.severity)}</span>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLOR[detail.status]}`}>
              {STATUS_LABEL[detail.status]}
            </span>
          </div>
          {detail.notes && <p className="text-slate-400 text-sm mt-2">{detail.notes}</p>}
        </div>

        {/* 严重度条 */}
        <div className="bg-slate-800 rounded-xl p-4 mb-4">
          <div className="flex justify-between text-xs text-slate-400 mb-1">
            <span>严重程度</span><span>{severityText(detail.severity)}</span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-green-400 via-yellow-400 to-red-400"
              style={{ width: `${(detail.severity ?? 0) * 10}%` }}
            />
          </div>
        </div>

        {detail.status !== 'resolved' && (
          <div className="flex gap-2 mb-4 flex-wrap">
            <button onClick={() => quickUpdate(detail, 'improving', adjustedSeverity(detail.severity, -2))}
              className="px-4 py-2 rounded-lg bg-yellow-500/10 text-yellow-400 text-sm">好转了</button>
            <button onClick={() => quickUpdate(detail, 'resolved')}
              className="px-4 py-2 rounded-lg bg-green-500/10 text-green-400 text-sm">已痊愈</button>
            <button onClick={() => quickUpdate(detail, 'active', adjustedSeverity(detail.severity, 1))}
              className="px-4 py-2 rounded-lg bg-red-500/10 text-red-400 text-sm">加重了</button>
          </div>
        )}

        <h3 className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2">进展记录</h3>
        {!detail.updates?.length ? (
          <p className="text-slate-500 text-sm">暂无进展记录</p>
        ) : (
          <div className="flex flex-col gap-2">
            {[...detail.updates].reverse().map(u => (
              <div key={u.id} className="bg-slate-800 rounded-lg px-4 py-3 flex gap-3">
                <span className="text-slate-500 text-xs mt-1">·</span>
                <div>
                  <p className="text-slate-400 text-xs">{u.update_date}</p>
                  <p className="text-slate-300 text-sm mt-0.5">
                    {u.status ? (STATUS_LABEL[u.status] ?? u.status) : ''}
                    {u.severity ? ` 严重度${u.severity}/10` : ''}
                    {u.notes ? ` — ${u.notes}` : ''}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── 新建表单 ────────────────────────────────────────────────────
  if (view === 'create') {
    return (
      <div className="min-h-screen bg-slate-900 p-4 pb-24">
        <div className="flex items-center gap-3 mb-4">
          <button onClick={() => setView('list')} className="text-slate-400 text-2xl px-2">‹</button>
          <h1 className="text-white text-2xl font-bold">记录病症</h1>
        </div>

        <div className="bg-slate-800 rounded-xl p-4 mb-4 flex flex-col gap-4">
          <div>
            <label className="text-slate-300 text-sm block mb-1">病症名称 *</label>
            <input
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white text-sm outline-none"
              placeholder="如：口腔溃疡、嘴唇起泡、扁桃体发炎..."
              value={newName}
              onChange={e => setNewName(e.target.value)}
            />
          </div>

          <div>
            <label className="text-slate-300 text-sm block mb-2">
              严重程度：<span className="text-blue-400 font-semibold">{newSeverity}/10</span>
              <span className="text-slate-500 ml-2 text-xs">（1=轻微  10=剧烈）</span>
            </label>
            <div className="flex gap-2 flex-wrap">
              {[1,2,3,4,5,6,7,8,9,10].map(n => (
                <button
                  key={n}
                  onClick={() => setNewSeverity(n)}
                  className={`w-9 h-9 rounded-lg text-sm font-medium transition-colors ${
                    newSeverity === n
                      ? 'bg-blue-500 text-white'
                      : 'bg-white/5 text-slate-400 hover:bg-white/10'
                  }`}
                >{n}</button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-slate-300 text-sm block mb-1">备注（可选）</label>
            <input
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white text-sm outline-none"
              placeholder="如：右侧两个、进食时疼痛..."
              value={newNotes}
              onChange={e => setNewNotes(e.target.value)}
            />
          </div>
        </div>

        <button
          disabled={!newName.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate({
            name: newName.trim(),
            start_date: today(),
            severity: newSeverity,
            status: 'active',
            notes: newNotes.trim() || undefined,
          })}
          className="w-full py-4 rounded-xl bg-gradient-to-r from-blue-500 to-indigo-500 text-white font-semibold disabled:opacity-50"
        >
          {createMutation.isPending ? '记录中...' : '确认记录'}
        </button>
      </div>
    );
  }

  // ── 列表视图 ────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-900 p-4 pb-24">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-white text-2xl font-bold">当前病症</h1>
        <button
          onClick={() => setView('create')}
          className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-semibold"
        >+ 记录</button>
      </div>

      {active.length === 0 ? (
        <div className="flex flex-col items-center py-20 text-center">
          <span className="text-6xl mb-4">💪</span>
          <p className="text-slate-400 text-lg">目前身体状况良好</p>
          <p className="text-slate-500 text-sm mt-1">如有不适，点右上角记录</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {active.map(ep => (
            <EpisodeCard
              key={ep.id}
              episode={ep}
              onDetail={() => { setDetailId(ep.id); setView('detail'); }}
              onImprove={() => quickUpdate(ep, 'improving', adjustedSeverity(ep.severity, -2))}
              onResolve={() => quickUpdate(ep, 'resolved')}
              onWorsen={() => quickUpdate(ep, 'active', adjustedSeverity(ep.severity, 1))}
              onDelete={() => { if (confirm('确认删除？')) deleteMutation.mutate(ep.id); }}
            />
          ))}
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-6">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-slate-400 text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-1"
          >
            历史病症（{history.length}）
            <span className="text-slate-500">{showHistory ? '▲' : '▼'}</span>
          </button>
          {showHistory && (
            <div className="flex flex-col gap-3">
              {history.map(ep => (
                <EpisodeCard
                  key={ep.id}
                  episode={ep}
                  onDetail={() => { setDetailId(ep.id); setView('detail'); }}
                  onDelete={() => { if (confirm('确认删除？')) deleteMutation.mutate(ep.id); }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EpisodeCard({
  episode, onDetail, onImprove, onResolve, onWorsen, onDelete,
}: {
  episode: IllnessEpisode;
  onDetail: () => void;
  onImprove?: () => void;
  onResolve?: () => void;
  onWorsen?: () => void;
  onDelete: () => void;
}) {
  const days = daysSince(episode.start_date);
  return (
    <div className="bg-slate-800 rounded-xl p-4">
      <div className="flex justify-between items-start mb-3">
        <span className="text-white text-lg font-bold">{episode.name}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[episode.status]}`}>
          {STATUS_LABEL[episode.status]}
        </span>
      </div>

      <div className="mb-2">
        <div className="flex justify-between text-xs text-slate-400 mb-1">
          <span>严重程度</span><span>{severityText(episode.severity)}</span>
        </div>
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-green-400 via-yellow-400 to-red-400"
            style={{ width: `${(episode.severity ?? 0) * 10}%` }}
          />
        </div>
      </div>

      <p className="text-slate-500 text-xs mb-3">
        发作于 {episode.start_date}，已持续 {days} 天
        {episode.end_date ? `，痊愈：${episode.end_date}` : ''}
      </p>

      <div className="flex gap-2 flex-wrap">
        {episode.status !== 'resolved' && onImprove && (
          <button onClick={onImprove} className="text-xs px-3 py-1.5 rounded-lg bg-yellow-500/10 text-yellow-400">好转</button>
        )}
        {episode.status !== 'resolved' && onResolve && (
          <button onClick={onResolve} className="text-xs px-3 py-1.5 rounded-lg bg-green-500/10 text-green-400">痊愈</button>
        )}
        {episode.status === 'improving' && onWorsen && (
          <button onClick={onWorsen} className="text-xs px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400">加重</button>
        )}
        <button onClick={onDetail} className="text-xs px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-400">详情</button>
        <button onClick={onDelete} className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 text-slate-400">删除</button>
      </div>
    </div>
  );
}
