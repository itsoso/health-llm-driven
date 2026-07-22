'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api/client';
import CeleryHealthBlock from './CeleryHealthBlock';
import GarminSyncHealthBlock from './GarminSyncHealthBlock';

type WindowDays = 1 | 7 | 14 | 30;

interface OpenLoopStats {
  total_sent: number;
  by_kind: Record<string, number>;
  by_action: Record<string, number>;
  delivery_fail: number;
  avg_score: number | null;
  last_sent: string | null;
}

interface ClinicalJournalStats {
  total_entries: number;
  by_creator: Record<string, number>;
  by_theme: Record<string, number>;
  active_case_threads: number;
  complete_soap_pct: number | null;
  last_entry: string | null;
}

interface MemoryKgStats {
  facts_total: number;
  facts_by_tier: Record<string, number>;
  facts_new: number;
  entities_total: number;
  entities_by_type: Record<string, number>;
  entities_new: number;
  relations_total: number;
  relations_top_predicates: Record<string, number>;
  relations_new: number;
}

interface DoctorReportStats {
  total_attempts: number;
  unique_users: number;
  last_attempt: string | null;
}

interface ActionCardStats {
  created_in_window: number;
  graded_in_window: number;
  avg_accuracy: number | null;
  by_specialist: Record<string, number>;
}

interface SafetyStats {
  evaluations: number;
  total_alerts_raised: number;
}

interface ToolValidatorStats {
  skipped?: boolean;
  reason?: string;
  coerced?: number;
  rejected?: number;
  log_lines?: number;
}

interface MemoryInjectionStageRow {
  ok: number;
  fail: number;
  error: number;
  ok_rate: number;
  avg_chars: number;
  avg_count: number;
}

interface MemoryInjectionStats {
  total_invocations: number;
  by_stage: Record<string, MemoryInjectionStageRow>;
  avg_chars_added: number;
}

interface AIGCMediaStats {
  total_jobs: number;
  by_status: Record<string, number>;
  by_model: Record<string, number>;
  by_error_code: Record<string, number>;
  auth_failures: number;
  submission_unknown: number;
  safe_retryable: number;
  success_rate_pct: number | null;
  last_job_at: string | null;
  last_failure_at: string | null;
  status: 'ok' | 'warning' | 'critical' | 'no_data';
}

interface DashboardReport {
  open_loop: OpenLoopStats;
  clinical_journal: ClinicalJournalStats;
  memory_kg: MemoryKgStats;
  doctor_report: DoctorReportStats;
  action_card: ActionCardStats;
  safety_guardian: SafetyStats;
  memory_injection?: MemoryInjectionStats;
  aigc_media?: AIGCMediaStats;
  tool_validator?: ToolValidatorStats;
}

interface CeleryHealth {
  tasks: Array<{
    task: string;
    expected_per_day: number | null;
    expected_per_week: number | null;
    window_hours: number;
    observed: number;
    last_run: string | null;
    status: 'ok' | 'stale' | 'no_data' | 'observing';
  }>;
  note?: string;
}

interface GarminSyncHealth {
  last_sync_at: string | null;
  last_sync_age_hours: number | null;
  active_users: number;
  invalid_cred_users: number;
  distinct_users_24h: number;
  stale_users_7d: number;
  status: 'ok' | 'stale' | 'no_data' | 'observing';
  note?: string;
}

interface DashboardResponse {
  generated_at: string;
  window_days: number;
  user_id: number | null;
  report: DashboardReport;
  suggestions: string[];
  celery_health?: CeleryHealth;
  garmin_sync_health?: GarminSyncHealth;
  cached?: boolean;
}

const WINDOW_OPTIONS: WindowDays[] = [1, 7, 14, 30];

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function suggestionTone(line: string): string {
  if (line.startsWith('🔴')) return 'border-l-red-400 bg-red-500/10 text-red-100';
  if (line.startsWith('🟡')) return 'border-l-amber-400 bg-amber-500/10 text-amber-100';
  if (line.startsWith('🟢')) return 'border-l-emerald-400 bg-emerald-500/10 text-emerald-100';
  if (line.startsWith('✅')) return 'border-l-emerald-400 bg-emerald-500/10 text-emerald-100';
  return 'border-l-slate-400 bg-slate-500/10 text-slate-100';
}

function StatCard({ title, value, hint }: { title: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4">
      <div className="text-xs text-purple-200/70 mb-1">{title}</div>
      <div className="text-2xl font-semibold text-white">{value}</div>
      {hint && <div className="text-xs text-purple-200/60 mt-1">{hint}</div>}
    </div>
  );
}

function KvList({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  if (!entries.length) return <div className="text-xs text-purple-200/50">—</div>;
  return (
    <div className="space-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between text-sm">
          <span className="text-purple-100/90 truncate mr-2">{k}</span>
          <span className="text-white font-mono tabular-nums">{v}</span>
        </div>
      ))}
    </div>
  );
}

function Section({ title, badge, children }: { title: string; badge?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {badge && (
          <span className="text-xs bg-purple-500/30 text-purple-100 px-2 py-0.5 rounded">{badge}</span>
        )}
      </div>
      {children}
    </div>
  );
}

export default function ObservabilityTab() {
  const [days, setDays] = useState<WindowDays>(7);
  const [userIdInput, setUserIdInput] = useState<string>('');
  const [bypassCacheOnce, setBypassCacheOnce] = useState(false);

  const trimmed = userIdInput.trim();
  const parsedUid = trimmed ? Number(trimmed) : NaN;
  const userId = !Number.isNaN(parsedUid) && parsedUid > 0 ? parsedUid : undefined;
  const userIdInvalid = trimmed !== '' && userId === undefined;

  const { data, isLoading, isError, error, isFetching } = useQuery<DashboardResponse>({
    queryKey: ['admin-observability', days, userId, bypassCacheOnce],
    queryFn: async () => {
      const params = new URLSearchParams({ days: String(days) });
      if (userId) params.append('user_id', String(userId));
      if (bypassCacheOnce) params.append('refresh', 'true');
      const res = await api.get(`/admin/observability/dashboard?${params}`);
      // reset bypass flag so subsequent polls use cache again
      if (bypassCacheOnce) setBypassCacheOnce(false);
      return res.data;
    },
    refetchOnWindowFocus: false,
  });

  const forceRefresh = () => {
    setBypassCacheOnce(true);
    // queryKey change triggers refetch; no manual refetch() call needed
  };

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-wrap items-center gap-3">
        <span className="text-sm text-purple-200">窗口:</span>
        {WINDOW_OPTIONS.map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              days === d
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-purple-200 hover:bg-white/20'
            }`}
          >
            {d} 天
          </button>
        ))}
        <div className="ml-4 flex items-center gap-2">
          <span className="text-sm text-purple-200">user_id:</span>
          <input
            type="text"
            inputMode="numeric"
            placeholder="留空=全量"
            value={userIdInput}
            onChange={(e) => setUserIdInput(e.target.value)}
            className={`bg-white/10 border rounded px-2 py-1 text-sm text-white w-28 placeholder:text-purple-200/40 ${
              userIdInvalid ? 'border-red-400/60' : 'border-white/20'
            }`}
          />
          {userIdInvalid && (
            <span className="text-xs text-red-300">需正整数</span>
          )}
        </div>
        <button
          onClick={forceRefresh}
          disabled={isFetching}
          title="强制跳过 Redis 缓存 (180s TTL)"
          className="ml-auto px-3 py-1 rounded text-sm bg-purple-500/30 text-purple-100 hover:bg-purple-500/40 disabled:opacity-40"
        >
          {isFetching ? '刷新中…' : '🔄 强制刷新'}
        </button>
        {data && (
          <span className="text-xs text-purple-200/70">
            生成于 {fmtTime(data.generated_at)}
            {data.cached && <span className="ml-2 text-emerald-300">· 缓存命中</span>}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="text-center text-purple-200 py-12">读取观察期数据中…</div>
      )}

      {isError && (
        <div className="bg-red-500/20 border border-red-400/40 rounded-lg p-4 text-red-100">
          加载失败: {(error as Error)?.message ?? '未知错误'}
        </div>
      )}

      {data && (
        <>
          {/* 行动建议 — 永远在最上面 */}
          <div className="bg-gradient-to-r from-amber-500/10 to-purple-500/10 border border-white/10 rounded-xl p-5">
            <h3 className="text-lg font-semibold text-white mb-3">💡 自动行动建议</h3>
            <div className="space-y-2">
              {data.suggestions.map((s, i) => (
                <div key={i} className={`border-l-4 ${suggestionTone(s)} px-3 py-2 rounded-r text-sm`}>
                  {s}
                </div>
              ))}
            </div>
          </div>

          {data.report.aigc_media && (
            <Section
              title="AIGC 媒体生成"
              badge={
                data.report.aigc_media.status === 'critical'
                  ? '授权故障'
                  : data.report.aigc_media.status === 'warning'
                    ? '需关注'
                    : data.report.aigc_media.status === 'ok'
                      ? '正常'
                      : '暂无数据'
              }
            >
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
                <StatCard title="任务总数" value={data.report.aigc_media.total_jobs} />
                <StatCard
                  title="成功率"
                  value={
                    data.report.aigc_media.success_rate_pct === null
                      ? '—'
                      : `${data.report.aigc_media.success_rate_pct}%`
                  }
                />
                <StatCard title="授权失败" value={data.report.aigc_media.auth_failures} />
                <StatCard title="提交待核验" value={data.report.aigc_media.submission_unknown} />
                <StatCard title="可安全重试" value={data.report.aigc_media.safe_retryable} />
              </div>
              <div className="grid md:grid-cols-3 gap-4">
                <div>
                  <div className="text-xs text-purple-200/70 mb-2">任务状态</div>
                  <KvList data={data.report.aigc_media.by_status} />
                </div>
                <div>
                  <div className="text-xs text-purple-200/70 mb-2">模型分布</div>
                  <KvList data={data.report.aigc_media.by_model} />
                </div>
                <div>
                  <div className="text-xs text-purple-200/70 mb-2">供应商错误码</div>
                  <KvList data={data.report.aigc_media.by_error_code} />
                </div>
              </div>
              <div className="mt-4 text-xs text-purple-200/60">
                最近任务 {fmtTime(data.report.aigc_media.last_job_at)}
                {' · '}最近失败 {fmtTime(data.report.aigc_media.last_failure_at)}
              </div>
            </Section>
          )}

          {/* A. Open-Loop */}
          <Section title="A. Open-Loop Manager 推送" badge="APNs">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <StatCard title="推送总数" value={data.report.open_loop.total_sent} />
              <StatCard
                title="投递失败"
                value={data.report.open_loop.delivery_fail}
                hint={
                  data.report.open_loop.total_sent > 0
                    ? `${((data.report.open_loop.delivery_fail / data.report.open_loop.total_sent) * 100).toFixed(1)}%`
                    : undefined
                }
              />
              <StatCard
                title="平均分数"
                value={data.report.open_loop.avg_score ?? '—'}
              />
              <StatCard title="最近一条" value={fmtTime(data.report.open_loop.last_sent)} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-purple-200/70 mb-2">按 kind</div>
                <KvList data={data.report.open_loop.by_kind} />
              </div>
              <div>
                <div className="text-xs text-purple-200/70 mb-2">按用户反馈</div>
                <KvList data={data.report.open_loop.by_action} />
              </div>
            </div>
          </Section>

          {/* B. Clinical Journal */}
          <Section title="B. Clinical Journal SOAP" badge="阶段 3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <StatCard title="SOAP 条数" value={data.report.clinical_journal.total_entries} />
              <StatCard
                title="完整率"
                value={
                  data.report.clinical_journal.complete_soap_pct !== null
                    ? `${data.report.clinical_journal.complete_soap_pct}%`
                    : '—'
                }
              />
              <StatCard title="活跃 case" value={data.report.clinical_journal.active_case_threads} />
              <StatCard title="最近一条" value={fmtTime(data.report.clinical_journal.last_entry)} />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-purple-200/70 mb-2">按 creator</div>
                <KvList data={data.report.clinical_journal.by_creator} />
              </div>
              <div>
                <div className="text-xs text-purple-200/70 mb-2">按 theme</div>
                <KvList data={data.report.clinical_journal.by_theme} />
              </div>
            </div>
          </Section>

          {/* C. Memory / KG */}
          <Section title="C. Memory / KG (Sprint 5)" badge="L5 Memory">
            <div className="grid grid-cols-3 gap-3 mb-4">
              <StatCard
                title="Facts"
                value={data.report.memory_kg.facts_total}
                hint={`+${data.report.memory_kg.facts_new} 窗口内`}
              />
              <StatCard
                title="Entities"
                value={data.report.memory_kg.entities_total}
                hint={`+${data.report.memory_kg.entities_new} 窗口内`}
              />
              <StatCard
                title="Relations"
                value={data.report.memory_kg.relations_total}
                hint={`+${data.report.memory_kg.relations_new} 窗口内`}
              />
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-purple-200/70 mb-2">Fact tier 分布</div>
                <KvList data={data.report.memory_kg.facts_by_tier} />
              </div>
              <div>
                <div className="text-xs text-purple-200/70 mb-2">Entity type 分布</div>
                <KvList data={data.report.memory_kg.entities_by_type} />
              </div>
              <div>
                <div className="text-xs text-purple-200/70 mb-2">Relation Top predicates</div>
                <KvList data={data.report.memory_kg.relations_top_predicates} />
              </div>
            </div>
          </Section>

          {/* D. Doctor Weekly */}
          <Section title="D. Doctor Weekly Report" badge="阶段 4">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <StatCard title="周报 SOAP 落盘" value={data.report.doctor_report.total_attempts} />
              <StatCard title="覆盖用户数" value={data.report.doctor_report.unique_users} />
              <StatCard title="最近一次" value={fmtTime(data.report.doctor_report.last_attempt)} />
            </div>
          </Section>

          {/* E. ActionCard 信任循环 */}
          <Section title="E. ActionCard 信任循环" badge="信任循环">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
              <StatCard title="窗口新建" value={data.report.action_card.created_in_window} />
              <StatCard title="窗口已评分" value={data.report.action_card.graded_in_window} />
              <StatCard
                title="平均 accuracy"
                value={data.report.action_card.avg_accuracy ?? '—'}
              />
            </div>
            <div>
              <div className="text-xs text-purple-200/70 mb-2">按 specialist</div>
              <KvList data={data.report.action_card.by_specialist} />
            </div>
          </Section>

          {/* F. Safety Guardian */}
          <Section title="F. Safety Guardian" badge="51 规则">
            <div className="grid grid-cols-2 gap-3">
              <StatCard title="评估次数" value={data.report.safety_guardian.evaluations} />
              <StatCard
                title="告警累计"
                value={data.report.safety_guardian.total_alerts_raised}
                hint={
                  data.report.safety_guardian.evaluations > 0
                    ? `${(data.report.safety_guardian.total_alerts_raised / data.report.safety_guardian.evaluations).toFixed(2)} 条/次`
                    : undefined
                }
              />
            </div>
          </Section>

          {/* G. Memory 注入 (T1.1) */}
          {data.report.memory_injection && (
            <Section title="G. Memory 注入诊断" badge="T1.1">
              {data.report.memory_injection.total_invocations === 0 ? (
                <div className="text-sm text-purple-200/70">
                  窗口内无 orchestrator 调用 — 用户没用 AI 对话, 或 _inject_memory 没在主链路触发
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
                    <StatCard
                      title="orchestrator 调用次数"
                      value={data.report.memory_injection.total_invocations}
                    />
                    <StatCard
                      title="平均注入字符数"
                      value={data.report.memory_injection.avg_chars_added}
                      hint="prompt 增量"
                    />
                  </div>
                  <div className="text-xs text-purple-200/70 mb-2">每个 stage 命中率</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {(['conversation', 'case_timeline', 'directives', 'hybrid'] as const).map((s) => {
                      const row = data.report.memory_injection!.by_stage[s];
                      if (!row) return null;
                      const pct = Math.round(row.ok_rate * 100);
                      const tone = pct >= 60 ? 'text-emerald-300' : pct >= 30 ? 'text-amber-300' : 'text-red-300';
                      return (
                        <div key={s} className="bg-white/5 border border-white/10 rounded p-3">
                          <div className="flex justify-between items-baseline mb-1">
                            <span className="text-sm font-medium text-white">{s}</span>
                            <span className={`text-base font-mono font-semibold ${tone}`}>
                              {pct}%
                            </span>
                          </div>
                          <div className="text-xs text-purple-200/60">
                            ok {row.ok} / fail {row.fail}
                            {row.error > 0 ? ` · ${row.error} 真错` : ''}
                            {row.ok > 0 ? ` · 均 ${row.avg_chars} 字 / ${row.avg_count} 项` : ''}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </Section>
          )}

          {/* H. tool_validator */}
          <Section title="H. tool_validator" badge="弱点 B">
            {data.report.tool_validator?.skipped !== false ? (
              <div className="text-sm text-purple-200/70">
                {data.report.tool_validator?.skipped
                  ? `已跳过 (${data.report.tool_validator?.reason ?? '本地无 journalctl'})`
                  : '需在生产机请求 ?include_journalctl=true 触发'}
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                <StatCard title="coerced" value={data.report.tool_validator.coerced ?? 0} />
                <StatCard title="rejected" value={data.report.tool_validator.rejected ?? 0} />
                <StatCard title="日志行数" value={data.report.tool_validator.log_lines ?? 0} />
              </div>
            )}
          </Section>

          {/* H. Celery Beat 健康 */}
          {data.celery_health && (
            <CeleryHealthBlock
              tasks={data.celery_health.tasks}
              note={data.celery_health.note}
            />
          )}

          {/* I. Garmin 同步健康 */}
          {data.garmin_sync_health && (
            <GarminSyncHealthBlock data={data.garmin_sync_health} />
          )}
        </>
      )}
    </div>
  );
}
