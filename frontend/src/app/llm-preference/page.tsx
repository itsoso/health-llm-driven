'use client';

/**
 * /llm-preference — Web 用户级 LLM 模型偏好 (2026-05-13).
 *
 * 跟 mobile/app/llm-preference.tsx 同语义.
 * 后端 GET/PUT /me/llm-preference, 持久化到 user_profiles.llm_model_id.
 */

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/services/api/client';
import ProtectedRoute from '@/components/ProtectedRoute';

interface ModelOption {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: 'fast' | 'balanced' | 'reasoning';
  note: string;
}

interface PreferenceResponse {
  model_id: string | null;
  options: ModelOption[];
}

const TIER_LABEL: Record<string, string> = { fast: '快', balanced: '均衡', reasoning: '推理' };
const TIER_COLOR: Record<string, string> = {
  fast: 'text-emerald-400 bg-emerald-400/10',
  balanced: 'text-sky-400 bg-sky-400/10',
  reasoning: 'text-violet-400 bg-violet-400/10',
};

function LlmPreferenceInner() {
  const router = useRouter();
  const [data, setData] = useState<PreferenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api.get('/me/llm-preference')
      .then(r => setData(r.data))
      .catch(e => setErr(e?.response?.data?.detail || e?.message || '加载失败'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const pick = useCallback(async (model_id: string | null) => {
    if (data?.model_id === model_id) return;
    setSaving(model_id || '__reset__');
    setErr(null);
    try {
      const r = await api.put<PreferenceResponse>('/me/llm-preference', { model_id });
      setData(r.data);
      const lbl = model_id
        ? r.data.options.find(o => o.id === model_id)?.label || model_id
        : '系统默认';
      // 2026-05-14 FIX-6: 切换后做自检
      try {
        const t = await api.post<{
          ok: boolean;
          actual_model?: string | null;
          actual_provider?: string | null;
          latency_ms?: number | null;
          sample_reply?: string | null;
          error?: string | null;
        }>('/me/llm-preference/selftest');
        if (t.data.ok) {
          setToast(
            `已切换到 ${lbl}\n实测: ${t.data.actual_model} · ${t.data.latency_ms}ms · "${(t.data.sample_reply || '').slice(0, 60)}"`,
          );
        } else {
          setToast(`已切换, 但自检失败: ${t.data.error || '?'}`);
        }
      } catch {
        setToast(`已切换到 ${lbl}, 自检请求失败`);
      }
      setTimeout(() => setToast(null), 5000);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || '切换失败');
    } finally {
      setSaving(null);
    }
  }, [data]);

  if (loading) {
    return <div className="min-h-screen bg-slate-950 text-slate-300 p-8 text-sm">加载中...</div>;
  }
  if (err && !data) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-300 p-8">
        <button onClick={() => router.back()} className="text-sm text-slate-400 hover:text-emerald-300 mb-4">
          ← 返回
        </button>
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{err}</div>
      </div>
    );
  }
  if (!data) return null;

  const activeId = data.model_id;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <button onClick={() => router.back()} className="text-sm text-slate-400 hover:text-emerald-300">
            ← 返回
          </button>
          <h1 className="text-xl font-semibold">AI 模型</h1>
        </div>

        {toast && (
          <div className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300 whitespace-pre-line">
            {toast}
          </div>
        )}
        {err && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{err}</div>
        )}

        {/* 当前 */}
        <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-4 mb-4">
          <div className="text-[11px] text-slate-500 uppercase">当前我的选择</div>
          <div className="mt-1 text-lg font-semibold">
            {activeId
              ? data.options.find(m => m.id === activeId)?.label || activeId
              : '系统默认'}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {activeId
              ? '只对我自己的对话生效, 不影响其他用户.'
              : '走 admin 全局或服务器默认配置.'}
          </div>
          {activeId && (
            <button
              onClick={() => pick(null)}
              disabled={saving !== null}
              className="mt-3 rounded-md bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-50"
            >
              {saving === '__reset__' ? '恢复中…' : '恢复默认'}
            </button>
          )}
        </div>

        {/* 选项 */}
        <div className="space-y-2">
          {data.options.length === 0 ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500 text-center">
              暂无可用模型, 请联系管理员配置 API Key.
            </div>
          ) : data.options.map(m => {
            const isActive = m.id === activeId;
            const isSaving = saving === m.id;
            return (
              <button
                key={m.id}
                onClick={() => pick(m.id)}
                disabled={saving !== null || isActive}
                className={`w-full text-left rounded-xl border p-3 transition-colors ${
                  isActive
                    ? 'border-emerald-500/50 bg-emerald-500/10'
                    : 'border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/60'
                } ${saving !== null && !isActive ? 'opacity-50' : ''}`}
              >
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${TIER_COLOR[m.speed_tier]}`}>
                    {TIER_LABEL[m.speed_tier]}
                  </span>
                  <span className="font-medium text-[15px]">{m.label}</span>
                  {isActive && (
                    <span className="ml-auto text-emerald-400 text-sm">✓</span>
                  )}
                  {isSaving && <span className="ml-auto text-xs text-slate-400">切换中…</span>}
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-1">{m.provider} · {m.model}</div>
                {m.note && <div className="text-xs text-slate-500 mt-1">{m.note}</div>}
              </button>
            );
          })}
        </div>

        <Link
          href="/admin/llm-performance"
          className="mt-6 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-emerald-300"
        >
          看模型性能 (admin) →
        </Link>
      </div>
    </div>
  );
}

export default function LlmPreferencePage() {
  return (
    <ProtectedRoute>
      <LlmPreferenceInner />
    </ProtectedRoute>
  );
}
