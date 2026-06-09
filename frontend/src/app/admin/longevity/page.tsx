'use client';

/**
 * /admin/longevity — 抗衰证据看板(plan-toward-goal-v2 支柱 A:路演弹药)。
 *
 * 把已上线但无前端的三个去标识端点聚成一页:
 *   - /admin/observability/eval   主动 Agent 命中/推送 + orchestrator p50/p95 + 闭环分布
 *   - /admin/observability/funnel 注册→改善 漏斗 + 转化
 *   - /admin/longevity/cohort     生物年龄群体证据(observational)
 * 全部去标识,只读。给自己/投资人看"产品在起作用"的证据。
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import { api } from '@/services/api/client';

function pct(n: number | null | undefined) {
  return n == null ? '—' : `${(n * 100).toFixed(1)}%`;
}

function Inner() {
  const [evalData, setEvalData] = useState<any>(null);
  const [funnel, setFunnel] = useState<any>(null);
  const [cohort, setCohort] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [harm, setHarm] = useState<any>(null);
  const [safetyEval, setSafetyEval] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [e, f, c, h, s] = await Promise.all([
        api.get('/admin/observability/eval'),
        api.get('/admin/observability/funnel'),
        api.get('/admin/longevity/cohort'),
        api.get('/admin/longevity/cohort/harm'),
        api.get('/admin/observability/safety-eval'),
      ]);
      setEvalData(e.data);
      setFunnel(f.data);
      setCohort(c.data);
      setHarm(h.data);
      setSafetyEval(s.data);
    } catch (ex: any) {
      setErr(ex?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">抗衰证据看板</h1>
        <div className="flex gap-3 text-sm">
          <button onClick={load} className="px-3 py-1 rounded bg-gray-100 hover:bg-gray-200">刷新</button>
          <Link href="/admin" className="px-3 py-1 rounded bg-gray-100 hover:bg-gray-200">← 后台</Link>
        </div>
      </div>
      <p className="text-xs text-gray-400 mb-4">去标识聚合;群体/漏斗为 observational,不构成疗效证明。</p>

      {loading && <div className="text-gray-500">加载中…</div>}
      {err && <div className="text-red-500">加载失败:{err}</div>}

      {!loading && !err && (
        <div className="grid gap-5 md:grid-cols-2">
          {/* 主动 Agent + 性能 */}
          <section className="border rounded-lg p-4">
            <h2 className="font-semibold mb-2">主动 Agent / 性能</h2>
            <ul className="text-sm space-y-1">
              <li>主动触发:{evalData?.proactive_agent?.triggers ?? '—'}</li>
              <li>显著率:{pct(evalData?.proactive_agent?.notable_rate)} · 推送率:{pct(evalData?.proactive_agent?.notified_rate)}</li>
              <li>orchestrator 延迟 p50/p95:{evalData?.orchestrator_latency_ms?.p50 ?? '—'} / {evalData?.orchestrator_latency_ms?.p95 ?? '—'} ms</li>
            </ul>
          </section>

          {/* 闭环 outcome */}
          <section className="border rounded-lg p-4">
            <h2 className="font-semibold mb-2">闭环 outcome</h2>
            <ul className="text-sm space-y-1">
              <li>已评分:{evalData?.closed_loop?.graded_total ?? '—'}</li>
              <li>改善率:{pct(evalData?.closed_loop?.improvement_rate)}</li>
              <li className="text-gray-500">{JSON.stringify(evalData?.closed_loop?.distribution ?? {})}</li>
            </ul>
          </section>

          {/* 激活漏斗 */}
          <section className="border rounded-lg p-4">
            <h2 className="font-semibold mb-2">激活漏斗(注册→改善)</h2>
            <ul className="text-sm space-y-1">
              {funnel?.funnel && Object.entries(funnel.funnel).map(([k, v]) => (
                <li key={k}>{k}:{v as number}</li>
              ))}
              <li className="text-gray-500">register→improved:{pct(funnel?.overall_register_to_improved)}</li>
            </ul>
          </section>

          {/* 群体证据 */}
          <section className="border rounded-lg p-4">
            <h2 className="font-semibold mb-2">生物年龄群体证据</h2>
            <ul className="text-sm space-y-1">
              {cohort?.metrics && Object.keys(cohort.metrics).length > 0 ? (
                Object.entries(cohort.metrics).map(([m, d]: any) => (
                  <li key={m}>
                    {m}:{d.suppressed ? `样本不足(n=${d.n},去标识抑制)` :
                      `n=${d.n} · 改善率 ${pct(d.improvement_rate)}${d.mean_improvement_years != null ? ` · 平均年轻 ${d.mean_improvement_years} 岁` : ''}`}
                  </li>
                ))
              ) : (
                <li className="text-gray-500">暂无已评分的生物年龄 N-of-1(需真实用户数据)</li>
              )}
            </ul>
          </section>

          {/* 反向飞轮 — 群体 harm 信号 */}
          <section className="border rounded-lg p-4">
            <h2 className="font-semibold mb-2">⚠️ 群体 harm 信号(反向飞轮)</h2>
            <ul className="text-sm space-y-1">
              {harm?.harm_signals && harm.harm_signals.length > 0 ? (
                harm.harm_signals.map((h: any) => (
                  <li key={h.metric} className="text-red-600">
                    {h.metric}:worsened {pct(h.worsened_rate)}(n={h.n},恶化 {h.worsened} &gt; 改善 {h.improved})
                  </li>
                ))
              ) : (
                <li className="text-gray-500">无 harm 信号(observational;需足量数据)</li>
              )}
            </ul>
          </section>

          {/* 安全 eval — red-team 规则覆盖 */}
          <section className="border rounded-lg p-4">
            <h2 className="font-semibold mb-2">安全 eval(red-team 规则)</h2>
            <ul className="text-sm space-y-1">
              <li>通过率:{pct(safetyEval?.pass_rate)}({safetyEval?.passed ?? '—'}/{safetyEval?.total ?? '—'})</li>
              {safetyEval?.scenarios && safetyEval.scenarios.filter((s: any) => !s.passed).map((s: any) => (
                <li key={s.name} className="text-red-600">未覆盖:{s.name}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}

export default function LongevityEvidencePage() {
  return (
    <ProtectedRoute>
      <Inner />
    </ProtectedRoute>
  );
}
