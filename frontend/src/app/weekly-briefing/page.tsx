'use client';

/**
 * /weekly-briefing — 本周 AI 给你的 3-5 件事 (Web, 2026-05-14).
 *
 * 跟 mobile 的 weekly-briefing 同语义, 走 GET /me/weekly-briefing.
 * 没卡可手动触发 (POST /me/weekly-briefing/trigger), 后台 ~30s 跑完.
 *
 * 用户最初愿景的最后一公里: 主动告诉用户"基于你的基因+主目标, 这周做这 3-5 件事"
 * 而不是被动等用户问.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/services/api/client';
import ProtectedRoute from '@/components/ProtectedRoute';

interface BriefingCard {
  id: number;
  title: string;
  content: string;
  metric_key: string | null;
  baseline_value: string | null;
  target_value: string | null;
  actual_value: string | null;
  verification_days: number | null;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  outcome: string | null;
  status: string | null;
  user_decision: string | null;
  created_at: string | null;
  completed_at: string | null;
  graded_at: string | null;
}

interface BriefingResponse {
  week_start: string;
  primary_goal: string | null;
  cards: BriefingCard[];
  stats: { total: number; accepted: number; completed: number; improved: number };
  last_run_at: string | null;
  can_trigger: boolean;
}

const GOAL_LABEL: Record<string, string> = {
  weight_loss: '减肥/控重',
  glucose: '降血糖',
  blood_pressure: '降血压',
  sleep: '改善睡眠',
  hrv: '提升 HRV',
  rhinitis: '管理鼻炎',
  general: '总体健康',
};

const EVIDENCE_LABEL: Record<string, { label: string; color: string }> = {
  high: { label: '强证据', color: 'bg-emerald-500/15 text-emerald-300' },
  medium: { label: '中等', color: 'bg-sky-500/15 text-sky-300' },
  low: { label: '弱证据', color: 'bg-slate-500/15 text-slate-400' },
  medical_grade: { label: '医生介入', color: 'bg-rose-500/15 text-rose-300' },
};

const METRIC_LABEL: Record<string, string> = {
  ldl: 'LDL', hdl: 'HDL', hba1c: '糖化', tg: 'TG',
  systolic_bp: '收缩压', sbp: '收缩压', dbp: '舒张压', bp: '血压',
  weight: '体重', bmi: 'BMI', hrv: 'HRV', rhr: '静息心率',
  sleep_score: '睡眠', spo2: 'SpO2', spo2_odi: 'ODI',
  hcy: '同型半胱氨酸', vitamin_d: '维 D', b12: 'B12', ferritin: '铁蛋白',
  vd: '维 D', custom: '自定义',
};

function MyBriefingInner() {
  const [data, setData] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setErr(null);
    api.get<BriefingResponse>('/me/weekly-briefing')
      .then(r => setData(r.data))
      .catch(e => setErr(e?.response?.data?.detail || e?.message || '加载失败'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const trigger = useCallback(async () => {
    setTriggering(true);
    setErr(null);
    try {
      const r = await api.post<{ queued: boolean; reason?: string }>('/me/weekly-briefing/trigger');
      if (r.data.queued) {
        setToast('AI 正在生成本周建议, 约 30 秒后回来刷新');
        setTimeout(() => setToast(null), 4000);
        // 自动 30s 后 reload
        setTimeout(() => load(), 35000);
      } else {
        setToast(r.data.reason || '本周已有建议');
        setTimeout(() => setToast(null), 3000);
        load();
      }
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || '触发失败');
    } finally {
      setTriggering(false);
    }
  }, [load]);

  if (loading && !data) {
    return <div className="min-h-screen bg-slate-950 text-slate-400 p-8 text-sm">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/" className="text-sm text-slate-400 hover:text-emerald-300">← 返回首页</Link>
          <h1 className="text-xl font-semibold">本周建议</h1>
        </div>

        {toast && (
          <div className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
            {toast}
          </div>
        )}
        {err && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{err}</div>
        )}

        {data && (
          <>
            {/* 主目标提示 */}
            {data.primary_goal && (
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-indigo-500/15 border border-indigo-500/30 px-3 py-1 text-xs text-indigo-300">
                <span>🎯</span>
                <span>当前主目标: {GOAL_LABEL[data.primary_goal] || data.primary_goal}</span>
                <Link href="/onboarding" className="ml-1 underline opacity-70 hover:opacity-100">改</Link>
              </div>
            )}

            {/* 没建议 / 可触发 */}
            {data.cards.length === 0 ? (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-8 text-center">
                <div className="text-3xl mb-2">📅</div>
                <div className="text-base font-medium mb-1">本周还没有 AI 建议</div>
                <div className="text-sm text-slate-500 max-w-md mx-auto mb-4">
                  系统每周日 21:07 自动生成 3-5 条本周可执行建议.<br />
                  现在可以手动触发一次, AI 会基于你的基因 / 化验 / 主目标给方案.
                </div>
                {data.can_trigger && (
                  <button
                    onClick={trigger}
                    disabled={triggering}
                    className="rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-5 py-2 text-sm font-medium text-white"
                  >
                    {triggering ? '生成中…' : '现在生成本周建议'}
                  </button>
                )}
              </div>
            ) : (
              <>
                {/* 进度 stats */}
                <div className="grid grid-cols-4 gap-3 mb-5">
                  <StatTile label="本周建议" value={data.stats.total} color="text-slate-200" />
                  <StatTile label="已接受" value={data.stats.accepted} color="text-sky-400" />
                  <StatTile label="已完成" value={data.stats.completed} color="text-violet-400" />
                  <StatTile label="已改善" value={data.stats.improved} color="text-emerald-400" />
                </div>

                {/* cards */}
                <div className="space-y-3">
                  {data.cards.map(c => {
                    const ev = c.evidence_level ? EVIDENCE_LABEL[c.evidence_level] : null;
                    return (
                      <div key={c.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
                        <div className="flex items-start gap-2 mb-2">
                          <h3 className="text-base font-semibold flex-1">{c.title}</h3>
                          {ev && (
                            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${ev.color}`}>
                              {ev.label}
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{c.content}</p>
                        {c.metric_key && c.baseline_value && (
                          <div className="mt-3 inline-flex items-center gap-2 rounded-lg bg-slate-800/60 px-3 py-1.5 text-xs tabular-nums">
                            <span className="text-slate-500">
                              {METRIC_LABEL[c.metric_key] || c.metric_key}
                            </span>
                            <span className="text-slate-300">{c.baseline_value}</span>
                            {c.target_value && (
                              <>
                                <span className="text-slate-600">→</span>
                                <span className="text-emerald-400 font-semibold">{c.target_value}</span>
                              </>
                            )}
                            {c.actual_value && (
                              <>
                                <span className="text-slate-600">实测</span>
                                <span className="text-amber-400 font-semibold">{c.actual_value}</span>
                              </>
                            )}
                            {c.verification_days && (
                              <span className="text-slate-500">({c.verification_days} 天)</span>
                            )}
                          </div>
                        )}
                        {(c.user_decision || c.outcome) && (
                          <div className="mt-2 flex items-center gap-2 text-[11px]">
                            {c.user_decision && (
                              <span className="text-slate-500">决策: {c.user_decision}</span>
                            )}
                            {c.outcome && (
                              <span className={
                                c.outcome === 'improved' ? 'text-emerald-400' :
                                c.outcome === 'worsened' ? 'text-rose-400' : 'text-slate-500'
                              }>
                                结果: {c.outcome}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* 上次跑时间 */}
            {data.last_run_at && (
              <div className="mt-6 text-xs text-slate-600 text-center">
                生成于 {new Date(data.last_run_at).toLocaleString('zh-CN')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatTile({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-3 text-center">
      <div className={`text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      <div className="text-[11px] text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}

export default function WeeklyBriefingPage() {
  return (
    <ProtectedRoute>
      <MyBriefingInner />
    </ProtectedRoute>
  );
}
