'use client';

/**
 * /personal-outcome —— 个人健康改善档案
 *
 * 这一页回答一个问题：因为这个系统，我过去 X 个月/年里发生了什么可测量的变化？
 *
 * 视觉结构：
 *  1. 顶部摘要卡片（4 个关键指标的首-末对比 + 数据覆盖天数）
 *  2. 范围与粒度选择（6m / 1y / 2y / all × week / month）
 *  3. 时间序列折线图（可切换指标）+ 事件锚点参考线
 *  4. 事件列表（点击 → 载入前后 30 天影响对比）
 */

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  getMyOutcomeTimeline,
  getMyEventImpact,
  type OutcomeRange,
  type OutcomeGranularity,
  type OutcomeTimelineResponse,
  type TimelineEvent,
  type EventImpactResponse,
} from '@/services/api/personalOutcome';

// ---------------------------------------------------------------------------
// 指标配置
// ---------------------------------------------------------------------------

type MetricKey =
  | 'hrv'
  | 'rhr'
  | 'sleep_score'
  | 'deep_sleep_min'
  | 'body_battery_high'
  | 'steps'
  | 'weight_kg'
  | 'systolic';

interface MetricConfig {
  key: MetricKey;
  label: string;
  unit: string;
  color: string;
  desirable: 'up' | 'down' | 'flat';
}

const METRICS: MetricConfig[] = [
  { key: 'hrv', label: 'HRV', unit: 'ms', color: '#8B5CF6', desirable: 'up' },
  { key: 'rhr', label: '静息心率', unit: 'bpm', color: '#EF4444', desirable: 'down' },
  { key: 'sleep_score', label: '睡眠分', unit: '分', color: '#3B82F6', desirable: 'up' },
  { key: 'deep_sleep_min', label: '深睡时长', unit: '分钟', color: '#1E3A8A', desirable: 'up' },
  { key: 'body_battery_high', label: '身体电量峰值', unit: '', color: '#10B981', desirable: 'up' },
  { key: 'steps', label: '日步数', unit: '步', color: '#F59E0B', desirable: 'up' },
  { key: 'weight_kg', label: '体重', unit: 'kg', color: '#6B7280', desirable: 'flat' },
  { key: 'systolic', label: '收缩压', unit: 'mmHg', color: '#DC2626', desirable: 'down' },
];

// ---------------------------------------------------------------------------
// 辅助
// ---------------------------------------------------------------------------

function arrow(desirable: 'up' | 'down' | 'flat', delta: number | null): string {
  if (delta == null) return '—';
  if (desirable === 'flat') return delta > 0 ? '+' : '';
  const positive = desirable === 'up' ? delta > 0 : delta < 0;
  return positive ? '↑ 改善' : '↓ 退步';
}

function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null) return '—';
  return Number(n).toFixed(digits);
}

// ---------------------------------------------------------------------------
// 页面主体
// ---------------------------------------------------------------------------

function PersonalOutcomeInner() {
  const router = useRouter();

  const [rangeKey, setRangeKey] = useState<OutcomeRange>('2y');
  const [granularity, setGranularity] = useState<OutcomeGranularity>('month');
  const [metricKey, setMetricKey] = useState<MetricKey>('hrv');

  const [data, setData] = useState<OutcomeTimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [impact, setImpact] = useState<EventImpactResponse | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);

  // 拉取 timeline
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getMyOutcomeTimeline(rangeKey, granularity)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) {
          console.error(e);
          setError(e?.response?.data?.detail || e?.message || '加载失败');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [rangeKey, granularity]);

  // 点击事件 → 拉取 impact
  useEffect(() => {
    if (!selectedEventId) {
      setImpact(null);
      return;
    }
    let cancelled = false;
    setImpactLoading(true);
    getMyEventImpact(selectedEventId, 30)
      .then((res) => {
        if (!cancelled) setImpact(res);
      })
      .catch((e) => {
        if (!cancelled) {
          console.error(e);
          setImpact(null);
        }
      })
      .finally(() => {
        if (!cancelled) setImpactLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedEventId]);

  const metric = useMemo(
    () => METRICS.find((m) => m.key === metricKey) || METRICS[0],
    [metricKey]
  );

  // 把事件按 bucket 映射到离它最近的 timeline point（用于在图上画 ReferenceLine）
  const chartData = data?.points || [];
  const events = data?.events || [];

  // 计算事件落在哪个 bucket 上 —— ReferenceLine 要 x 值
  const eventLines = useMemo(() => {
    if (!data) return [];
    return events
      .map((e) => {
        // 找到第一个 bucket.date >= e.date
        const idx = chartData.findIndex((p) => p.date >= e.date);
        if (idx === -1) return null;
        return {
          event: e,
          bucket: chartData[idx].bucket,
        };
      })
      .filter((x): x is { event: TimelineEvent; bucket: string } => x !== null);
  }, [data, chartData, events]);

  const summary = data?.summary;

  return (
    <div className="min-h-screen bg-gray-50 pb-16">
      {/* 顶栏 */}
      <div className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <button
            onClick={() => router.back()}
            className="text-gray-600 text-sm"
          >
            ← 返回
          </button>
          <h1 className="text-base font-semibold">我的健康改善档案</h1>
          <div className="w-12" />
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 pt-4 space-y-4">
        {/* 叙事开头 */}
        <div className="bg-white rounded-2xl p-5 border">
          <div className="text-xs text-gray-500 mb-1">OUTCOME LOG</div>
          <div className="text-lg font-semibold mb-2">
            这不是今天的数据，这是你这{rangeKey === 'all' ? '几年' : rangeKey === '2y' ? '两年' : rangeKey === '1y' ? '一年' : '半年'}发生了什么
          </div>
          <div className="text-xs text-gray-500 leading-relaxed">
            把 Garmin / 体重 / 血压 / 补剂 / 体检全部放在同一个时间轴上，看干预和结果之间的因果关系。
          </div>
        </div>

        {/* 摘要卡 */}
        {summary && (
          <div className="grid grid-cols-2 gap-3">
            {(['hrv', 'rhr', 'sleep_score', 'weight'] as const).map((k) => {
              const s = summary.metrics[k];
              const label =
                k === 'hrv' ? 'HRV'
                : k === 'rhr' ? '静息心率'
                : k === 'sleep_score' ? '睡眠分'
                : '体重';
              return (
                <div key={k} className="bg-white rounded-2xl p-4 border">
                  <div className="text-[11px] text-gray-500">{label}</div>
                  <div className="text-2xl font-bold mt-1">
                    {fmt(s.last)}
                    <span className="text-xs font-normal text-gray-400 ml-1">{s.unit}</span>
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1">
                    起始 {fmt(s.first)} · 变化{' '}
                    <span
                      className={
                        s.delta == null
                          ? 'text-gray-400'
                          : (s.desirable === 'up' && s.delta > 0) ||
                            (s.desirable === 'down' && s.delta < 0)
                          ? 'text-green-600 font-semibold'
                          : (s.desirable === 'up' && s.delta < 0) ||
                            (s.desirable === 'down' && s.delta > 0)
                          ? 'text-red-600 font-semibold'
                          : 'text-gray-600'
                      }
                    >
                      {s.delta == null ? '—' : (s.delta > 0 ? '+' : '') + s.delta}
                    </span>{' '}
                    {arrow(s.desirable, s.delta)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {summary && (
          <div className="text-[11px] text-gray-500 text-center">
            数据覆盖 {summary.covered_days} / {summary.total_days} 天 ·{' '}
            {summary.total_days > 0
              ? Math.round((summary.covered_days / summary.total_days) * 100)
              : 0}
            %
          </div>
        )}

        {/* 范围 / 粒度 / 指标 切换 */}
        <div className="bg-white rounded-2xl p-4 border space-y-3">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-500">时间：</span>
            {(['6m', '1y', '2y', 'all'] as OutcomeRange[]).map((r) => (
              <button
                key={r}
                onClick={() => setRangeKey(r)}
                className={`px-3 py-1 rounded-full ${
                  rangeKey === r ? 'bg-black text-white' : 'bg-gray-100 text-gray-600'
                }`}
              >
                {r === '6m' ? '半年' : r === '1y' ? '一年' : r === '2y' ? '两年' : '全部'}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-500">粒度：</span>
            {(['week', 'month'] as OutcomeGranularity[]).map((g) => (
              <button
                key={g}
                onClick={() => setGranularity(g)}
                className={`px-3 py-1 rounded-full ${
                  granularity === g ? 'bg-black text-white' : 'bg-gray-100 text-gray-600'
                }`}
              >
                {g === 'week' ? '周' : '月'}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <span className="text-gray-500">指标：</span>
            {METRICS.map((m) => (
              <button
                key={m.key}
                onClick={() => setMetricKey(m.key)}
                className={`px-3 py-1 rounded-full ${
                  metricKey === m.key
                    ? 'text-white'
                    : 'bg-gray-100 text-gray-600'
                }`}
                style={
                  metricKey === m.key ? { background: m.color } : undefined
                }
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* 时间序列图 */}
        <div className="bg-white rounded-2xl p-4 border">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold">{metric.label}</div>
            <div className="text-[11px] text-gray-400">{metric.unit}</div>
          </div>

          {loading && (
            <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
              加载中…
            </div>
          )}
          {error && (
            <div className="h-64 flex items-center justify-center text-red-500 text-sm">
              {error}
            </div>
          )}
          {!loading && !error && chartData.length === 0 && (
            <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
              这个时间范围没有数据
            </div>
          )}

          {!loading && !error && chartData.length > 0 && (
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 8, right: 12, left: -10, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis
                    dataKey="bucket"
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip
                    formatter={(v: any) => [v, metric.label]}
                    labelFormatter={(l) => l}
                  />
                  <Line
                    type="monotone"
                    dataKey={metric.key}
                    stroke={metric.color}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                  {eventLines.map(({ event, bucket }) => (
                    <ReferenceLine
                      key={event.id}
                      x={bucket}
                      stroke={event.color || '#888'}
                      strokeDasharray="3 3"
                      label={{
                        value: event.title.length > 6 ? event.title.slice(0, 6) + '…' : event.title,
                        position: 'top',
                        fill: event.color || '#888',
                        fontSize: 9,
                      }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* 事件列表 */}
        <div className="bg-white rounded-2xl p-4 border">
          <div className="text-sm font-semibold mb-3">干预 & 里程碑 ({events.length})</div>
          {events.length === 0 && (
            <div className="text-xs text-gray-400">这个范围没有事件</div>
          )}
          <div className="space-y-2">
            {events.map((e) => (
              <button
                key={e.id}
                onClick={() =>
                  setSelectedEventId(selectedEventId === e.id ? null : e.id)
                }
                className={`w-full text-left rounded-lg border px-3 py-2 transition ${
                  selectedEventId === e.id
                    ? 'border-black bg-gray-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: e.color || '#888' }}
                    />
                    <span className="text-sm font-medium">{e.title}</span>
                  </div>
                  <span className="text-[11px] text-gray-400">{e.date}</span>
                </div>
                {e.detail && (
                  <div className="text-[11px] text-gray-500 mt-1 ml-4 truncate">
                    {e.detail}
                  </div>
                )}

                {selectedEventId === e.id && (
                  <div className="mt-3 ml-4 border-t pt-3">
                    {impactLoading && (
                      <div className="text-[11px] text-gray-400">加载对比…</div>
                    )}
                    {impact && !impactLoading && (
                      <div className="grid grid-cols-3 gap-2 text-[11px]">
                        <div className="col-span-3 text-gray-500 mb-1">
                          事件前后各 {impact.window_days} 天均值
                        </div>
                        {([
                          ['HRV', 'hrv', 'ms'],
                          ['静息心率', 'rhr', 'bpm'],
                          ['睡眠分', 'sleep_score', '分'],
                        ] as const).map(([label, k, u]) => {
                          const before = impact.before[k];
                          const after = impact.after[k];
                          const delta =
                            before != null && after != null
                              ? Math.round((after - before) * 10) / 10
                              : null;
                          return (
                            <div key={k} className="bg-white border rounded p-2">
                              <div className="text-gray-400">{label}</div>
                              <div className="font-semibold">
                                {fmt(before)} → {fmt(after)}{' '}
                                <span className="text-[10px] text-gray-400">{u}</span>
                              </div>
                              {delta != null && (
                                <div
                                  className={
                                    delta > 0
                                      ? 'text-green-600'
                                      : delta < 0
                                      ? 'text-red-600'
                                      : 'text-gray-500'
                                  }
                                >
                                  {delta > 0 ? '+' : ''}
                                  {delta}
                                </div>
                              )}
                            </div>
                          );
                        })}
                        <div className="col-span-3 text-[10px] text-gray-400">
                          * 样本：前 {impact.before.samples} 天 / 后 {impact.after.samples} 天
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* 免责声明 */}
        <div className="text-[10px] text-gray-400 text-center leading-relaxed px-4">
          这份档案是时间上的巧合观察，不是因果证据。关键决定请先咨询医生。
        </div>
      </div>
    </div>
  );
}

export default function PersonalOutcomePage() {
  return (
    <ProtectedRoute>
      <PersonalOutcomeInner />
    </ProtectedRoute>
  );
}
