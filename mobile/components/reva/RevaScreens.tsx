/**
 * 复元 Reva — screen views.
 *
 * Today / Data / Me are wired to REAL data via `useRevaData()` (with honest
 * fallbacks where no source exists — see that hook). RiskDetail + Onboarding stay
 * as the design's showcase/flow (illustrative content). Faithful to the Reva UI
 * kit (`docs/design/reva/ui_kits/mobile-app/screens.jsx`).
 */
import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { revaColors as C, revaRadii, revaShadows } from '../../constants/revaTheme';
import {
  Button, Card, Chip, DayProgress, Icon, LabRow, MetricTile, PlanItem,
  ReadinessRing, RevaMark, SectionLabel, Sparkline, TopBar, TrendChart,
} from './RevaKit';
import { useRevaData } from './useRevaData';

// Illustrative labs used by the onboarding flow + risk-detail showcase only.
export const LABS = [
  { id: 'ldl', status: 'risk' as const, name: '低密度脂蛋白 LDL-C', sub: '偏高 · 优先处理', value: '3.8', unit: 'mmol/L' },
  { id: 'glu', status: 'caution' as const, name: '空腹血糖', sub: '临界 · 注意', value: '6.3', unit: 'mmol/L' },
  { id: 'bmi', status: 'caution' as const, name: '体重指数 BMI', sub: '偏高 · 注意', value: '26.4', unit: '' },
];

const body = { padding: 16, paddingBottom: 28, gap: 22 } as const;

function greeting(): string {
  const h = new Date().getHours();
  const part = h < 6 ? '凌晨好' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
  const m = ['一', '二', '三', '四', '五', '六', '日'][(new Date().getDay() + 6) % 7];
  return `${part} · ${new Date().getMonth() + 1}月${new Date().getDate()}日 周${m}`;
}
function fmtSleep(min: number | null): string {
  if (min == null) return '—';
  return `${Math.floor(min / 60)}h${min % 60}`;
}
function readinessTitle(score: number | null): string {
  if (score == null) return '数据接入中';
  if (score >= 80) return '已就绪 · 适合中等强度';
  if (score >= 60) return '基本就绪 · 适度活动';
  return '偏低 · 注意恢复';
}

function Empty({ text }: { text: string }) {
  return <Text style={{ fontSize: 13.5, color: C.ink3, paddingHorizontal: 16, paddingVertical: 14 }}>{text}</Text>;
}

// ── Today ────────────────────────────────────────────────────────────────
export function TodayView({ onRisk }: { onRisk?: () => void }) {
  const d = useRevaData();
  const [done, setDone] = useState<Record<string, boolean>>({});
  const doneCount = d.plan.filter(p => done[p.id]).length;
  const focus = d.abnormalLabs[0];
  return (
    <>
      <TopBar
        sub={greeting()}
        title={`${d.profileName}，今天`}
        right={<View style={s.avatar}><Text style={s.avatarText}>{d.profileName.slice(0, 1)}</Text></View>}
      />
      <ScrollView contentContainerStyle={body}>
        <View style={s.hero}>
          {d.readiness != null
            ? <ReadinessRing score={d.readiness} />
            : <View style={[s.ringPlaceholder]}><Text style={{ fontFamily: 'IBMPlexMono', fontSize: 30, color: C.focusInk2 }}>—</Text></View>}
          <View style={{ flex: 1 }}>
            <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 11, letterSpacing: 0.9, color: C.focusInk2 }}>TODAY · 恢复就绪度</Text>
            <Text style={{ fontWeight: '700', fontSize: 18, color: C.greenBright, marginTop: 4, marginBottom: 6 }}>{readinessTitle(d.readiness)}</Text>
            <Text style={{ fontSize: 13.5, lineHeight: 20, color: C.focusInk2 }}>{d.readinessNote}</Text>
          </View>
        </View>

        <View>
          <SectionLabel action={d.plan.length ? `${doneCount}/${d.plan.length} 已完成` : undefined}>今日计划</SectionLabel>
          <Card pad={0}>
            {d.plan.length ? (
              <>
                {d.plan.map((p, i) => (
                  <PlanItem key={p.id} icon={p.icon} title={p.title} sub={p.sub} done={!!done[p.id]} last={i === d.plan.length - 1} onToggle={() => setDone(x => ({ ...x, [p.id]: !x[p.id] }))} />
                ))}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 12 }}>
                  <Icon name="sparkles" size={14} color={C.green500} />
                  <Text style={{ fontSize: 12.5, color: C.ink3 }}>计划每天根据你的数据自动调整</Text>
                </View>
              </>
            ) : (
              <Empty text={d.loading ? '正在加载今日计划…' : '今日计划生成中 —— 复元会根据你的数据安排。'} />
            )}
          </Card>
        </View>

        <View>
          <SectionLabel>今日数据</SectionLabel>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <MetricTile icon="gauge" label="血压" value={d.today.bp ?? '—'} unit={d.today.bp ? 'mmHg' : ''} status="normal" />
            <MetricTile icon="footprints" label="步数" value={d.today.steps != null ? `${(d.today.steps / 1000).toFixed(1)}k` : '—'} status="info" />
            <MetricTile icon="moon" label="睡眠" value={fmtSleep(d.today.sleepMin)} status={d.today.sleepMin != null && d.today.sleepMin < 420 ? 'caution' : 'normal'} />
          </View>
        </View>

        {focus ? (
          <View>
            <SectionLabel>本阶段重点</SectionLabel>
            <Card onPress={onRisk}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: focus.status === 'risk' ? '#FBE8E4' : '#FBF1DD', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon name="trending-down" size={22} color={focus.status === 'risk' ? '#D5503A' : '#C98A1E'} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: '700', fontSize: 15.5, color: C.ink1 }}>{focus.name}</Text>
                  <Text style={{ fontSize: 13, color: C.ink2, marginTop: 2 }}>{focus.sub} · {focus.value} {focus.unit}</Text>
                </View>
                <Icon name="chevron-right" size={20} color={C.ink4} />
              </View>
            </Card>
          </View>
        ) : null}
      </ScrollView>
    </>
  );
}

// ── Data ────────────────────────────────────────────────────────────────
export function DataView({ onRisk }: { onRisk?: () => void }) {
  const d = useRevaData();
  return (
    <>
      <TopBar sub={d.examDate ? `体检 · ${d.examDate}` : '体检数据'} title="你的数据" />
      <ScrollView contentContainerStyle={body}>
        <Card><DayProgress day={d.dayInWindow ?? 1} total={90} /></Card>

        <View>
          <SectionLabel action={d.abnormalCount ? `${d.abnormalCount} 项异常` : undefined}>体检异常项</SectionLabel>
          <Card pad={0}>
            {d.abnormalLabs.length ? (
              d.abnormalLabs.map((l, i) => (
                <LabRow key={l.id} status={l.status} name={l.name} sub={l.sub} value={l.value} unit={l.unit} onPress={i === 0 ? onRisk : undefined} last={i === d.abnormalLabs.length - 1} />
              ))
            ) : (
              <Empty text={d.loading ? '正在加载体检数据…' : d.examDate ? '本次体检未见异常项。' : '还没有导入体检报告。'} />
            )}
          </Card>
        </View>

        <View>
          <SectionLabel action="近 7 天">手环数据</SectionLabel>
          <Card>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <Text style={{ fontWeight: '600', fontSize: 14, color: C.ink1 }}>静息心率</Text>
              <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 20, fontWeight: '500', color: C.green500 }}>{d.today.rhr ?? '—'} <Text style={{ fontSize: 11, color: C.ink3 }}>bpm</Text></Text>
            </View>
            {d.rhrSeries.length >= 2 ? <Sparkline points={d.rhrSeries} /> : <Text style={{ fontSize: 12.5, color: C.ink3 }}>{d.hasGarmin ? '数据积累中' : '连接手环后显示趋势'}</Text>}
          </Card>
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
            <MetricTile icon="moon" label="睡眠" value={fmtSleep(d.today.sleepMin)} status={d.today.sleepMin != null && d.today.sleepMin < 420 ? 'caution' : 'normal'} />
            <MetricTile icon="activity" label="HRV" value={d.today.hrv != null ? String(d.today.hrv) : '—'} unit={d.today.hrv != null ? 'ms' : ''} status="normal" />
            <MetricTile icon="flame" label="活动" value={d.today.activeCal != null ? String(d.today.activeCal) : '—'} unit={d.today.activeCal != null ? 'kcal' : ''} status="normal" />
          </View>
        </View>
      </ScrollView>
    </>
  );
}

// ── Me ────────────────────────────────────────────────────────────────
export function MeView() {
  const d = useRevaData();
  const devices = [
    ['watch', 'Apple Watch / Garmin', d.hasGarmin ? '已同步' : '未连接', d.hasGarmin] as const,
    ['file-text', '体检报告', d.examDate ?? '未导入', !!d.examDate] as const,
  ];
  return (
    <>
      <TopBar mark={false} title="我的" />
      <ScrollView contentContainerStyle={{ ...body, gap: 20 }}>
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 16 }}>
            <View style={[s.avatar, { width: 54, height: 54, borderRadius: 27 }]}><Text style={[s.avatarText, { fontSize: 22 }]}>{d.profileName.slice(0, 1)}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '800', fontSize: 19, color: C.ink1 }}>{d.profileName}</Text>
              <Text style={{ fontSize: 13, color: C.ink3 }}>{d.profileMeta}</Text>
            </View>
          </View>
          <DayProgress day={d.dayInWindow ?? 1} total={90} />
        </Card>

        <View>
          <SectionLabel>已连接</SectionLabel>
          <Card pad={0}>
            {devices.map(([ic, nm, sub, on], i) => (
              <View key={nm} style={[s.settingRow, i === devices.length - 1 && { borderBottomWidth: 0 }]}>
                <Icon name={ic} size={19} color={C.ink2} />
                <View style={{ flex: 1 }}><Text style={{ fontWeight: '600', fontSize: 15, color: C.ink1 }}>{nm}</Text><Text style={{ fontSize: 12.5, color: on ? C.green500 : C.ink3 }}>{sub}</Text></View>
                {on ? <Icon name="check-circle-2" size={20} color={C.green500} /> : <Button variant="ghost" size="sm">连接</Button>}
              </View>
            ))}
          </Card>
        </View>

        <View>
          <SectionLabel>设置</SectionLabel>
          <Card pad={0}>
            {([['bell', '每日提醒'], ['calendar-check', '复查提醒'], ['shield', '隐私与数据'], ['circle-help', '帮助与反馈']] as const).map(([ic, nm], i) => (
              <View key={nm} style={[s.settingRow, i === 3 && { borderBottomWidth: 0 }]}>
                <Icon name={ic} size={19} color={C.ink2} />
                <Text style={{ flex: 1, fontWeight: '600', fontSize: 15, color: C.ink1 }}>{nm}</Text>
                <Icon name="chevron-right" size={18} color={C.ink4} />
              </View>
            ))}
          </Card>
        </View>
      </ScrollView>
    </>
  );
}

// ── Risk detail (showcase) ──────────────────────────────────────────────
export function RiskDetailView({ onBack, onAgent }: { onBack: () => void; onAgent?: () => void }) {
  const series = [{ t: '基线', v: 3.8 }, { t: '4周', v: 3.6 }, { t: '8周', v: 3.4 }, { t: '12周', v: 3.1 }];
  return (
    <View style={{ flex: 1, backgroundColor: C.paper }}>
      <View style={s.detailHeader}>
        <Button variant="secondary" size="sm" icon="chevron-left" onPress={onBack}> </Button>
        <View>
          <Text style={{ fontSize: 12, fontWeight: '600', color: C.ink3 }}>心代谢风险</Text>
          <Text style={{ fontSize: 18, fontWeight: '800', color: C.ink1, letterSpacing: -0.2 }}>低密度脂蛋白 LDL-C</Text>
        </View>
      </View>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32, gap: 20 }}>
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' }}>
            <View>
              <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 12, color: C.ink3, marginBottom: 4 }}>当前值</Text>
              <Text style={{ fontFamily: 'IBMPlexMono', fontWeight: '500', fontSize: 44, color: '#D5503A' }}>3.8<Text style={{ fontSize: 16, color: C.ink3 }}> mmol/L</Text></Text>
            </View>
            <Chip status="risk">偏高</Chip>
          </View>
          <Text style={{ fontSize: 14.5, lineHeight: 23, color: C.ink2, marginTop: 14 }}>
            理想值在 3.4 以下。它是心血管风险里最值得先处理的一项——好消息是，它对饮食和运动的反应很快。
          </Text>
        </Card>
        <View>
          <SectionLabel>12 周改善预测</SectionLabel>
          <Card><TrendChart series={series} target={3.4} /></Card>
        </View>
        <Button variant="dark" size="lg" full icon="messages-square" onPress={onAgent}>问复元：怎么吃能降得更快？</Button>
      </ScrollView>
    </View>
  );
}

// ── Onboarding (flow showcase) ─────────────────────────────────────────────
export function OnboardingView({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const Dots = () => (
    <View style={{ flexDirection: 'row', gap: 7, justifyContent: 'center' }}>
      {[0, 1, 2].map(i => <View key={i} style={{ width: i === step ? 22 : 7, height: 7, borderRadius: 99, backgroundColor: i === step ? C.green500 : C.line }} />)}
    </View>
  );
  const footer = (cta: string, onCta: () => void, sub: string) => (
    <View style={{ gap: 18 }}>
      <Dots />
      <Button size="lg" full onPress={onCta}>{cta}</Button>
      <Text style={{ textAlign: 'center', fontSize: 12.5, color: C.ink3 }}>{sub}</Text>
    </View>
  );
  return (
    <View style={{ flex: 1, backgroundColor: C.paper, paddingHorizontal: 24, paddingTop: 56, paddingBottom: 36 }}>
      <View style={{ flex: 1, justifyContent: step === 0 ? 'center' : 'flex-start', gap: 24 }}>
        {step === 0 ? (
          <>
            <RevaMark size={64} />
            <View>
              <Text style={{ fontWeight: '800', fontSize: 34, lineHeight: 40, letterSpacing: -0.6, color: C.ink1 }}>体检之后，{'\n'}主动健康的 90 天。</Text>
              <Text style={{ fontSize: 16, lineHeight: 26, color: C.ink2, marginTop: 16 }}>复元把你的体检异常项，变成每天可执行的小计划，再用手环和复查数据验证它真的在改善。</Text>
            </View>
          </>
        ) : step === 1 ? (
          <View>
            <Chip status="info">第 1 步</Chip>
            <Text style={{ fontWeight: '800', fontSize: 26, color: C.ink1, marginTop: 14, marginBottom: 6, letterSpacing: -0.3 }}>导入你的体检报告</Text>
            <Text style={{ fontSize: 15, color: C.ink2, lineHeight: 23, marginBottom: 20 }}>复元会自动识别异常项，并按心代谢风险排序。</Text>
            <Card pad={0}>
              <View style={[s.planRow, { alignItems: 'center' }]}>
                <Icon name="file-text" size={18} color={C.ink3} />
                <Text style={{ fontWeight: '600', fontSize: 14, color: C.ink1, flex: 1 }}>体检报告_2026.pdf</Text>
                <Chip status="normal">已解析</Chip>
              </View>
              {LABS.map((l, i) => <LabRow key={l.id} {...l} last={i === LABS.length - 1} />)}
            </Card>
          </View>
        ) : (
          <View>
            <Chip status="info">第 2 步</Chip>
            <Text style={{ fontWeight: '800', fontSize: 26, color: C.ink1, marginTop: 14, marginBottom: 6, letterSpacing: -0.3 }}>连接你的穿戴设备</Text>
            <Text style={{ fontSize: 15, color: C.ink2, lineHeight: 23, marginBottom: 20 }}>用真实的心率、睡眠、步数校准计划，并验证改善。</Text>
            <Card pad={0}>
              {([['watch', 'Apple Watch', '已连接 · 实时同步', true], ['activity', '华为运动健康', '点击连接', false], ['gauge', 'Garmin Connect', '点击连接', false]] as const).map(([ic, nm, sub, on], i) => (
                <View key={nm} style={[s.settingRow, i === 2 && { borderBottomWidth: 0 }]}>
                  <View style={{ width: 38, height: 38, borderRadius: 11, backgroundColor: on ? C.green50 : C.paper2, alignItems: 'center', justifyContent: 'center' }}><Icon name={ic} size={19} color={on ? C.green500 : C.ink2} /></View>
                  <View style={{ flex: 1 }}><Text style={{ fontWeight: '600', fontSize: 15, color: C.ink1 }}>{nm}</Text><Text style={{ fontSize: 12.5, color: on ? C.green500 : C.ink3 }}>{sub}</Text></View>
                  {on ? <Icon name="check-circle-2" size={22} color={C.green500} /> : <Button variant="ghost" size="sm">连接</Button>}
                </View>
              ))}
            </Card>
          </View>
        )}
      </View>
      {step === 0
        ? footer('开始', () => setStep(1), '把体检异常项变成可执行的 90 天')
        : step === 1
          ? footer('继续', () => setStep(2), '支持三甲医院、美年、爱康等常见报告格式')
          : footer('进入复元', onDone, '稍后也可以在「我的」里连接')}
    </View>
  );
}

const s = StyleSheet.create({
  avatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.green50, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: C.green600, fontWeight: '700' },
  hero: { backgroundColor: C.focusBg, borderRadius: revaRadii.xl, padding: 20, flexDirection: 'row', gap: 18, alignItems: 'center', ...revaShadows.focus },
  ringPlaceholder: { width: 104, height: 104, borderRadius: 52, borderWidth: 10, borderColor: C.focusLine, alignItems: 'center', justifyContent: 'center' },
  settingRow: { flexDirection: 'row', alignItems: 'center', gap: 13, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  planRow: { flexDirection: 'row', alignItems: 'center', gap: 13, paddingHorizontal: 16, paddingVertical: 13, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  detailHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line, backgroundColor: C.paper },
});
