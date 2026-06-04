/**
 * Personal Health OS — 代谢画像 / 干预周期 屏 (P2, 接 biomarkers + intervention-cycles API).
 * 对应交互稿 ①代谢画像 / ②90天周期 / ④复查对比。复用 RevaKit 组件 + Reva 设计语言。
 */
import React from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';
import { revaColors as C, type RevaStatus } from '../../constants/revaTheme';
import { Button, Card, Chip, DayProgress, Icon, LabRow, MetricTile, SectionLabel, TopBar } from './RevaKit';
import { useActiveCycle, useMetabolicProfile, useRecheckCycle, useStartCycle } from '../../hooks/useHealthOs';
import type { BiomarkerObs, OutcomeMetric } from '../../services/healthOs';

const body = { padding: 16, paddingBottom: 32, gap: 22 } as const;

function obsStatus(o: BiomarkerObs): RevaStatus {
  if (o.is_risk) return o.flag === 'high' ? 'risk' : 'caution';
  if (o.abnormal) return 'caution';
  return 'normal';
}

function riskStatus(level?: string): RevaStatus {
  if (!level) return 'info';
  if (level.includes('极高') || level.includes('高')) return 'risk';
  if (level.includes('中')) return 'caution';
  if (level.includes('低')) return 'normal';
  return 'info';
}

function Loading() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: C.paper }}>
      <ActivityIndicator color={C.green500} />
    </View>
  );
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

// ── ① 代谢健康画像 ────────────────────────────────────────────────────────
export function MetabolicProfileView() {
  const { data, isLoading } = useMetabolicProfile();
  if (isLoading) return <Loading />;
  const risk = data?.risk ?? {};
  const level: string = risk.overall_risk_level ?? '未知';
  const fr = risk.cardiovascular?.['10yr_event_probability'];
  const ms = risk.metabolic_syndrome;
  const obs = data?.biomarkers ?? [];
  const abnormal = data?.abnormal ?? [];
  const tiles = obs.slice(0, 6);

  return (
    <>
      <TopBar sub="慢病风险 + 标准化指标" title="代谢健康画像" />
      <ScrollView contentContainerStyle={body}>
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Chip status={riskStatus(level)}>{level} 风险</Chip>
            <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 12, color: C.ink3 }}>
              {data?.abnormal_count ?? 0} 项异常
            </Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {fr != null ? (
              <View style={{ backgroundColor: C.paper2, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4 }}>
                <Text style={{ fontSize: 11, color: C.ink2 }}>Framingham 10y · {fr}%</Text>
              </View>
            ) : null}
            {ms ? (
              <View style={{ backgroundColor: C.paper2, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4 }}>
                <Text style={{ fontSize: 11, color: C.ink2 }}>
                  代谢综合征 {ms.criteria_met ?? 0}/{ms.criteria_total ?? 5} 项
                </Text>
              </View>
            ) : null}
          </View>
        </Card>

        {tiles.length ? (
          <View>
            <SectionLabel>关键指标</SectionLabel>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              {tiles.map((o) => (
                <View key={o.code} style={{ width: '31%' }}>
                  <MetricTile
                    icon="activity"
                    label={o.display}
                    value={fmt(o.normalized_value)}
                    unit={o.normalized_unit}
                    status={obsStatus(o)}
                  />
                </View>
              ))}
            </View>
          </View>
        ) : null}

        <View>
          <SectionLabel action={abnormal.length ? `${abnormal.length} 项` : undefined}>异常项</SectionLabel>
          <Card pad={0}>
            {abnormal.length ? (
              abnormal.map((o, i) => (
                <LabRow
                  key={o.code}
                  status={obsStatus(o)}
                  name={o.display}
                  sub={`${o.domain ?? ''} · 参考 ${fmt(o.ref_low)}–${fmt(o.ref_high)}`}
                  value={fmt(o.normalized_value)}
                  unit={o.normalized_unit}
                  last={i === abnormal.length - 1}
                />
              ))
            ) : (
              <Text style={{ fontSize: 13.5, color: C.ink3, padding: 16 }}>
                {obs.length ? '本次未见异常项。' : '还没有体检数据 —— 上传体检报告后这里会显示标准化指标。'}
              </Text>
            )}
          </Card>
        </View>
      </ScrollView>
    </>
  );
}

// ── ②④ 干预周期 + 复查对比 ────────────────────────────────────────────────
function daysBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  if (Number.isNaN(da) || Number.isNaN(db)) return null;
  return Math.round((db - da) / 86400000);
}

const STATUS_LABEL: Record<OutcomeMetric['status'], { t: string; s: RevaStatus }> = {
  pending: { t: '待复查', s: 'info' },
  improving: { t: '改善中', s: 'normal' },
  worsening: { t: '恶化', s: 'risk' },
  flat: { t: '持平', s: 'caution' },
  met: { t: '已达标', s: 'normal' },
};

export function InterventionCycleView() {
  const { data: cycle, isLoading } = useActiveCycle();
  const start = useStartCycle();
  const recheck = useRecheckCycle();
  if (isLoading) return <Loading />;

  if (!cycle) {
    return (
      <>
        <TopBar sub="代谢健康 + 运动恢复" title="干预周期" />
        <ScrollView contentContainerStyle={body}>
          <Card>
            <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 16, color: C.ink1 }}>
              还没有进行中的干预周期
            </Text>
            <Text style={{ fontSize: 13, lineHeight: 19, color: C.ink2, marginTop: 6 }}>
              开启一个 90 天代谢干预:锁定当前体检为基线,设定目标指标,复元会安排每周计划并在第 84 天提示复查。
            </Text>
            <View style={{ marginTop: 14 }}>
              <Button full icon="play" onPress={() => start.mutate(90)}>
                {start.isPending ? '正在开启…' : '开始 90 天代谢干预'}
              </Button>
            </View>
          </Card>
        </ScrollView>
      </>
    );
  }

  const total = daysBetween(cycle.start_date, cycle.planned_end_date) ?? 90;
  const elapsed = daysBetween(cycle.start_date, new Date().toISOString()) ?? 0;
  const day = Math.max(1, Math.min(total, elapsed + 1));
  const rechecked = cycle.latest_snapshot_id != null;

  return (
    <>
      <TopBar sub={cycle.status === 'active' ? '进行中' : cycle.status} title="代谢干预 · 90 天" />
      <ScrollView contentContainerStyle={body}>
        <Card><DayProgress day={day} total={total} /></Card>

        <View>
          <SectionLabel action={rechecked ? 'baseline → latest' : 'baseline → target'}>目标指标</SectionLabel>
          <Card pad={0}>
            {cycle.outcomes.map((om, i) => {
              const meta = STATUS_LABEL[om.status] ?? STATUS_LABEL.pending;
              const sub = rechecked && om.latest_value != null
                ? `${fmt(om.baseline_value)} → ${fmt(om.latest_value)}${om.delta_pct != null ? `  (${om.delta_pct > 0 ? '+' : ''}${om.delta_pct}%)` : ''}`
                : `${fmt(om.baseline_value)} → 目标 ${fmt(om.target_value)}`;
              return (
                <LabRow
                  key={om.metric_code}
                  status={meta.s}
                  name={`${om.display}`}
                  sub={sub}
                  value={meta.t}
                  unit=""
                  last={i === cycle.outcomes.length - 1}
                />
              );
            })}
          </Card>
        </View>

        {cycle.stop_conditions?.length ? (
          <View>
            <SectionLabel>停止 / 升级条件</SectionLabel>
            <Card>
              {cycle.stop_conditions.map((s, i) => (
                <View key={i} style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start', marginTop: i ? 6 : 0 }}>
                  <Icon name="alert-triangle" size={14} color={C.green600} />
                  <Text style={{ flex: 1, fontSize: 12.5, lineHeight: 18, color: C.ink2 }}>{s}</Text>
                </View>
              ))}
            </Card>
          </View>
        ) : null}

        <Button full variant="secondary" icon="refresh-cw" onPress={() => recheck.mutate(cycle.id)}>
          {recheck.isPending ? '正在复查…' : rechecked ? '重新复查' : '记录复查 (导入新体检后)'}
        </Button>
      </ScrollView>
    </>
  );
}
