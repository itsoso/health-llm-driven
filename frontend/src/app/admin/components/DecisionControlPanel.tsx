'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api/client';
import type { components } from '@/types/api.generated';

type DecisionControl = components['schemas']['DecisionControlResponse'];

const queryKey = ['admin-decision-control'];
const names = { laya: 'Laya（自部署）', jev: 'Jev', systemone: '兼容决策服务' };

export default function DecisionControlPanel() {
  const client = useQueryClient();
  const [notice, setNotice] = useState('');
  const query = useQuery<DecisionControl>({
    queryKey,
    queryFn: async () => (await api.get('/admin/decisions')).data,
    retry: false,
  });
  const save = useMutation({
    mutationFn: async (current: DecisionControl) => (
      await api.put('/admin/decisions', { enabled: !current.enabled, revision: current.revision })
    ).data as DecisionControl,
    onMutate: () => setNotice(''),
    onSuccess: (data) => {
      client.setQueryData(queryKey, data);
      setNotice('设置已保存');
    },
    onError: () => { void client.invalidateQueries({ queryKey }); },
  });
  const detail = (save.error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;

  return (
    <section className="mb-6 rounded-xl border border-white/15 bg-white/10 p-5" aria-labelledby="decision-control-title">
      <h2 id="decision-control-title" className="text-lg font-semibold text-white">意图决策服务</h2>
      <p className="mt-2 text-sm text-purple-200">
        辅助选择回答模型与查询能力。此开关影响全站后续请求；安全规则和操作权限始终有效。
      </p>
      {query.isPending && <p className="mt-4 text-purple-200" role="status">正在读取开关…</p>}
      {query.isError && (
        <div className="mt-4 text-red-200" role="alert">
          无法读取开关状态。
          <button className="ml-3 underline" onClick={() => void query.refetch()}>重试</button>
        </div>
      )}
      {query.data && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
          <div className="text-sm text-purple-100">
            <p>{names[query.data.provider]}</p>
            <p className="mt-1">
              {query.data.effective_mode === 'on' ? '已开启' : query.data.effective_mode === 'shadow' ? '观察模式：不改变实际路由' : '已关闭'}
            </p>
            {!query.data.configured && <p className="mt-1 text-amber-200">服务尚未完成配置，暂不能开启。</p>}
          </div>
          <button
            type="button"
            role="switch"
            aria-label="全站意图决策"
            aria-checked={query.data.enabled}
            disabled={save.isPending || (!query.data.configured && !query.data.enabled)}
            onClick={() => save.mutate(query.data!)}
            className={`rounded-lg px-5 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 ${query.data.enabled ? 'bg-purple-600' : 'bg-white/20'}`}
          >
            {save.isPending ? '保存中…' : query.data.enabled ? '关闭' : '开启'}
          </button>
        </div>
      )}
      {save.isError && <p className="mt-3 text-sm text-red-200" role="alert">{typeof detail === 'string' ? detail : '保存失败，请重试。'}</p>}
      {notice && <p className="mt-3 text-sm text-green-200" role="status">{notice}</p>}
    </section>
  );
}
