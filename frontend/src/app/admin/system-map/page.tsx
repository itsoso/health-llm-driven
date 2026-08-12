'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';
import { SystemMapGraph } from './SystemMapGraph';
import type {
  SystemMapCoverage,
  SystemMapData,
  SystemMapEntity,
  SystemMapEntityKind,
  SystemMapRelation,
} from './types';


type ViewKey = 'overview' | 'dependencies' | 'flows' | 'quality';

const VIEWS: Array<{ key: ViewKey; label: string; eyebrow: string }> = [
  { key: 'overview', label: '系统总览', eyebrow: 'STRUCTURE' },
  { key: 'dependencies', label: '依赖关系', eyebrow: 'COUPLING' },
  { key: 'flows', label: '业务流', eyebrow: 'FLOW' },
  { key: 'quality', label: '地图质量', eyebrow: 'COVERAGE' },
];

const KIND_LABELS: Record<SystemMapEntityKind, string> = {
  component: '组件',
  surface: '界面',
  api: 'API',
  resource: '资源',
  job: '后台任务',
};

const COVERAGE_LABELS: Record<SystemMapCoverage, string> = {
  complete: '完整',
  partial: '部分',
  declaration: '声明',
};


function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-36 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-normal normal-case tracking-normal text-slate-200 outline-none transition focus:border-cyan-400"
      >
        {children}
      </select>
    </label>
  );
}

function relationTouches(relation: SystemMapRelation, ids: Set<string>): boolean {
  return ids.has(relation.from) && ids.has(relation.to);
}

export default function SystemMapPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const isAdmin = isAuthenticated && Boolean(user?.is_admin);
  const [view, setView] = useState<ViewKey>('overview');
  const [kind, setKind] = useState('all');
  const [coverage, setCoverage] = useState('all');
  const [owner, setOwner] = useState('all');
  const [dataClass, setDataClass] = useState('all');
  const [selectedFlow, setSelectedFlow] = useState('');
  const [selectedEntity, setSelectedEntity] = useState<SystemMapEntity | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) router.push('/login');
    if (!authLoading && isAuthenticated && !user?.is_admin) router.push('/');
  }, [authLoading, isAuthenticated, router, user?.is_admin]);

  const query = useQuery<SystemMapData>({
    queryKey: ['admin-system-map'],
    queryFn: async () => {
      const response = await api.get('/admin/system-map');
      return response.data;
    },
    enabled: isAdmin,
  });

  const owners = useMemo(
    () => [...new Set(query.data?.entities.map((entity) => entity.owner).filter(Boolean) as string[])].sort(),
    [query.data],
  );
  const dataClasses = useMemo(
    () => [...new Set(query.data?.entities.flatMap((entity) => entity.data_classes ?? []) ?? [])].sort(),
    [query.data],
  );
  const flows = useMemo(
    () => [...new Set(query.data?.relations.flatMap((relation) => relation.flows ?? []) ?? [])].sort(),
    [query.data],
  );
  const activeFlow = selectedFlow || flows[0] || '';

  const filteredEntities = useMemo(() => {
    const entities = query.data?.entities ?? [];
    return entities.filter((entity) => (
      (kind === 'all' || entity.kind === kind)
      && (coverage === 'all' || entity.coverage === coverage)
      && (owner === 'all' || entity.owner === owner)
      && (dataClass === 'all' || entity.data_classes?.includes(dataClass as 'L1'))
    ));
  }, [coverage, dataClass, kind, owner, query.data]);

  const viewModel = useMemo(() => {
    const relations = query.data?.relations ?? [];
    const filteredIds = new Set(filteredEntities.map((entity) => entity.id));
    if (view === 'flows') {
      const flowRelations = relations.filter((relation) => relation.flows?.includes(activeFlow));
      const flowIds = new Set(flowRelations.flatMap((relation) => [relation.from, relation.to]));
      return {
        entities: filteredEntities.filter((entity) => flowIds.has(entity.id)),
        relations: flowRelations.filter((relation) => relationTouches(relation, filteredIds)),
      };
    }
    if (view === 'dependencies') {
      const dependencyRelations = relations.filter(
        (relation) => relation.type !== 'renders' && relationTouches(relation, filteredIds),
      );
      const dependencyIds = new Set(dependencyRelations.flatMap((relation) => [relation.from, relation.to]));
      return {
        entities: filteredEntities.filter((entity) => dependencyIds.has(entity.id)),
        relations: dependencyRelations,
      };
    }
    return {
      entities: filteredEntities,
      relations: relations.filter((relation) => relationTouches(relation, filteredIds)),
    };
  }, [activeFlow, filteredEntities, query.data, view]);

  const selectedRelations = useMemo(() => {
    if (!selectedEntity || !query.data) return { upstream: [], downstream: [] };
    return {
      upstream: query.data.relations.filter((relation) => relation.to === selectedEntity.id),
      downstream: query.data.relations.filter((relation) => relation.from === selectedEntity.id),
    };
  }, [query.data, selectedEntity]);

  if (authLoading || !isAdmin) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#060c13] text-slate-300">
        <div className="grid justify-items-center gap-4">
          <span className="h-8 w-8 animate-spin rounded-full border border-cyan-300/20 border-t-cyan-300" />
          <p className="font-mono text-xs uppercase tracking-[0.22em]">验证管理员权限中…</p>
        </div>
      </main>
    );
  }

  if (query.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#060c13] text-cyan-100">
        <p role="status" className="font-mono text-xs uppercase tracking-[0.22em]">正在装载系统结构…</p>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#060c13] px-6">
        <div role="alert" className="max-w-md border-l-2 border-rose-400 bg-rose-400/5 p-6 text-slate-200">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-rose-300">MAP OFFLINE</p>
          <h1 className="mt-3 text-xl font-semibold">系统地图暂时不可用</h1>
          <p className="mt-2 text-sm text-slate-400">生成物未通过服务器校验，请检查部署版本或验证闸门。</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="mt-5 rounded-md border border-rose-300/40 px-4 py-2 text-sm text-rose-100 transition hover:bg-rose-300/10"
          >
            重新加载系统地图
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#060c13] text-slate-100">
      <div className="border-b border-slate-800 bg-[radial-gradient(circle_at_18%_-20%,rgba(34,211,238,0.18),transparent_32%),linear-gradient(180deg,#09131e_0%,#060c13_100%)]">
        <div className="mx-auto max-w-[1800px] px-5 pb-7 pt-5 lg:px-9">
          <button type="button" onClick={() => router.push('/admin')} className="font-mono text-[10px] uppercase tracking-[0.2em] text-cyan-300 hover:text-white">
            ← ADMIN CONTROL
          </button>
          <div className="mt-8 flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-cyan-400">REVA / GENERATED STRUCTURE / V{query.data.schema_version}</p>
              <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-white">System Map</h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">代码派生的实体、关系与覆盖度。结构事实只读，叙事理由仍回到权威文档。</p>
            </div>
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-slate-800 bg-slate-800 sm:grid-cols-4">
              {[
                ['ENTITIES', query.data.entities.length],
                ['RELATIONS', query.data.relations.length],
                ['FLOWS', flows.length],
                ['FILTERED', viewModel.entities.length],
              ].map(([label, value]) => (
                <div key={label} className="min-w-24 bg-[#0b1520] px-4 py-3">
                  <div className="font-mono text-[9px] tracking-[0.18em] text-slate-500">{label}</div>
                  <div className="mt-1 text-xl font-semibold tabular-nums text-slate-100">{value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1800px] px-5 py-6 lg:px-9">
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-800 pb-4">
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="系统地图视角">
            {VIEWS.map((item) => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-label={item.label}
                aria-selected={view === item.key}
                onClick={() => setView(item.key)}
                className={`group rounded-md px-4 py-2 text-left transition ${view === item.key ? 'bg-cyan-300 text-slate-950' : 'text-slate-400 hover:bg-slate-900 hover:text-white'}`}
              >
                <span className="block font-mono text-[8px] tracking-[0.18em] opacity-60">{item.eyebrow}</span>
                <span className="block text-xs font-semibold">{item.label}</span>
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-3">
            <FilterSelect label="实体类型" value={kind} onChange={setKind}>
              <option value="all">全部</option>
              {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </FilterSelect>
            <FilterSelect label="覆盖度" value={coverage} onChange={setCoverage}>
              <option value="all">全部</option>
              {Object.entries(COVERAGE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </FilterSelect>
            <FilterSelect label="负责人" value={owner} onChange={setOwner}>
              <option value="all">全部</option>
              {owners.map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
            <FilterSelect label="数据级别" value={dataClass} onChange={setDataClass}>
              <option value="all">全部</option>
              {dataClasses.map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </div>
        </div>

        {view === 'flows' ? (
          <div className="my-4 flex flex-wrap gap-2" aria-label="业务流选择">
            {flows.length > 0 ? flows.map((flow) => (
              <button key={flow} type="button" onClick={() => setSelectedFlow(flow)} className={`rounded-full border px-3 py-1 font-mono text-[10px] ${activeFlow === flow ? 'border-amber-300 bg-amber-300/10 text-amber-200' : 'border-slate-700 text-slate-500'}`}>
                {flow}
              </button>
            )) : <p className="text-sm text-slate-500">当前生成物没有声明业务流。</p>}
          </div>
        ) : null}

        {view === 'quality' ? (
          <section className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-label="地图覆盖质量">
            {Object.entries(query.data.coverage).map(([area, item]) => (
              <article key={area} className="border border-slate-800 bg-slate-950/50 p-5">
                <div className="flex items-start justify-between gap-4">
                  <h2 className="font-mono text-sm text-slate-200">{area}</h2>
                  <span className="rounded-full border border-cyan-300/20 px-2 py-0.5 text-[9px] uppercase tracking-[0.15em] text-cyan-300">{COVERAGE_LABELS[item.status]}</span>
                </div>
                <p className="mt-4 break-all font-mono text-[10px] text-slate-500">{item.source}</p>
                {item.limitations ? <p className="mt-3 text-xs leading-5 text-amber-200/70">{item.limitations}</p> : null}
              </article>
            ))}
          </section>
        ) : (
          <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <SystemMapGraph entities={viewModel.entities} relations={viewModel.relations} onSelect={setSelectedEntity} />
            <aside className="min-h-56 border border-slate-800 bg-slate-950/50 p-5">
              {selectedEntity ? (
                <div>
                  <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-cyan-400">SELECTED ENTITY</p>
                  <h2 className="mt-2 text-lg font-semibold text-white">{selectedEntity.name}</h2>
                  <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{selectedEntity.id}</p>
                  <dl className="mt-5 grid gap-4 text-xs">
                    <div><dt className="text-slate-500">来源</dt><dd className="mt-1 break-all font-mono text-slate-300">{selectedEntity.source.path}{selectedEntity.source.symbol ? `#${selectedEntity.source.symbol}` : ''}</dd></div>
                    <div><dt className="text-slate-500">覆盖度</dt><dd className="mt-1 text-slate-300">{COVERAGE_LABELS[selectedEntity.coverage]}</dd></div>
                    <div><dt className="text-slate-500">上游关系</dt><dd className="mt-1 text-slate-300">{selectedRelations.upstream.length}</dd></div>
                    <div><dt className="text-slate-500">下游关系</dt><dd className="mt-1 text-slate-300">{selectedRelations.downstream.length}</dd></div>
                  </dl>
                  <div className="mt-5 space-y-2 border-t border-slate-800 pt-4">
                    {[...selectedRelations.upstream, ...selectedRelations.downstream].slice(0, 12).map((relation) => (
                      <div key={`${relation.from}:${relation.type}:${relation.to}`} className="font-mono text-[9px] leading-4 text-slate-500">
                        {relation.from} <span className="text-cyan-500">{relation.type}</span> {relation.to}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex h-full min-h-48 items-center justify-center text-center">
                  <div><p className="font-mono text-[9px] tracking-[0.2em] text-slate-600">NO ENTITY SELECTED</p><p className="mt-2 text-xs text-slate-500">选择图中节点查看来源与上下游关系。</p></div>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}
