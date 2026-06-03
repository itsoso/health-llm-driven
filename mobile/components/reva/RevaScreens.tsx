/**
 * 复元 Reva — screen views (Today / Data / Me / Onboarding / RiskDetail).
 *
 * Faithful RN recreation of the Reva mobile UI kit screens
 * (`docs/design/reva/ui_kits/mobile-app/screens.jsx`). Presentational, using the
 * kit's sample data (the design medium is a high-fidelity prototype). Wire to real
 * data per-screen in a follow-up; the agent tab (RevaAgentView) is already live.
 */
import React, { useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { revaColors as C, revaRadii, revaShadows } from '../../constants/revaTheme';
import {
  Button, Card, Chip, DayProgress, Icon, LabRow, MetricTile, PlanItem,
  ReadinessRing, RevaMark, SectionLabel, Sparkline, TopBar, TrendChart,
} from './RevaKit';

export const LABS = [
  { id: 'ldl', status: 'risk' as const, name: '低密度脂蛋白 LDL-C', sub: '偏高 · 优先处理', value: '3.8', unit: 'mmol/L' },
  { id: 'glu', status: 'caution' as const, name: '空腹血糖', sub: '临界 · 注意', value: '6.3', unit: 'mmol/L' },
  { id: 'bmi', status: 'caution' as const, name: '体重指数 BMI', sub: '偏高 · 注意', value: '26.4', unit: '' },
  { id: 'bp', status: 'normal' as const, name: '血压', sub: '达标', value: '122/78', unit: 'mmHg' },
  { id: 'hdl', status: 'normal' as const, name: '高密度脂蛋白 HDL-C', sub: '达标', value: '1.3', unit: 'mmol/L' },
];

const body = { padding: 16, paddingBottom: 28, gap: 22 } as const;

// ── Today ────────────────────────────────────────────────────────────────
export function TodayView({ onRisk }: { onRisk?: () => void }) {
  const plan = [
    { id: 'walk', icon: 'footprints', title: '餐后散步 20 分钟', sub: '帮助餐后血糖回落', tag: '2 次' },
    { id: 'meal', icon: 'utensils', title: '午餐用全谷物替换精米', sub: '降低 LDL-C 的关键一步' },
    { id: 'med', icon: 'pill', title: '记录今日血压', sub: '晨起静坐 5 分钟后测量' },
    { id: 'sleep', icon: 'moon', title: '23:30 前入睡', sub: '昨晚睡眠 6h12m，略偏少' },
  ];
  const [done, setDone] = useState<Record<string, boolean>>({});
  const doneCount = plan.filter(p => done[p.id]).length;
  return (
    <>
      <TopBar
        sub="晚上好 · 5月18日 周一"
        title="子衡，今天还差一点"
        right={<View style={s.avatar}><Text style={s.avatarText}>衡</Text></View>}
      />
      <ScrollView contentContainerStyle={body}>
        {/* hero focus surface */}
        <View style={s.hero}>
          <ReadinessRing score={86} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 11, letterSpacing: 0.9, color: C.focusInk2 }}>TODAY · 恢复就绪度</Text>
            <Text style={{ fontWeight: '700', fontSize: 18, color: C.greenBright, marginTop: 4, marginBottom: 6 }}>已就绪 · 适合中等强度</Text>
            <Text style={{ fontSize: 13.5, lineHeight: 20, color: C.focusInk2 }}>静息心率比上周低 4 bpm，睡眠略短。今天可以快走或骑行 30 分钟。</Text>
          </View>
        </View>

        <View>
          <SectionLabel action={`${doneCount}/${plan.length} 已完成`}>今日计划</SectionLabel>
          <Card pad={0}>
            {plan.map(p => (
              <PlanItem key={p.id} {...p} done={!!done[p.id]} onToggle={() => setDone(d => ({ ...d, [p.id]: !d[p.id] }))} />
            ))}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 12 }}>
              <Icon name="sparkles" size={14} color={C.green500} />
              <Text style={{ fontSize: 12.5, color: C.ink3 }}>计划每天根据你的数据自动调整</Text>
            </View>
          </Card>
        </View>

        <View>
          <SectionLabel>今日数据</SectionLabel>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <MetricTile icon="gauge" label="血压" value="122/78" unit="mmHg" delta="达标" status="normal" />
            <MetricTile icon="droplet" label="空腹血糖" value="6.3" unit="mmol/L" delta="↑ 临界" status="caution" />
            <MetricTile icon="footprints" label="步数" value="7.2k" delta="目标 8k" status="info" />
          </View>
        </View>

        <View>
          <SectionLabel>本阶段重点</SectionLabel>
          <Card onPress={onRisk}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: '#FBE8E4', alignItems: 'center', justifyContent: 'center' }}>
                <Icon name="trending-down" size={22} color="#D5503A" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '700', fontSize: 15.5, color: C.ink1 }}>把 LDL-C 降到 3.4 以下</Text>
                <Text style={{ fontSize: 13, color: C.ink2, marginTop: 2 }}>3.8 → 3.1 · 12 周内可明显改善</Text>
              </View>
              <Icon name="chevron-right" size={20} color={C.ink4} />
            </View>
          </Card>
        </View>
      </ScrollView>
    </>
  );
}

// ── Data ────────────────────────────────────────────────────────────────
export function DataView({ onRisk }: { onRisk?: () => void }) {
  return (
    <>
      <TopBar sub="体检 · 2026-04-11" title="你的数据" />
      <ScrollView contentContainerStyle={body}>
        <Card><DayProgress day={23} total={90} /></Card>

        <View>
          <SectionLabel action="5 项异常">体检异常项</SectionLabel>
          <Card pad={0}>
            {LABS.map((l, i) => (
              <LabRow key={l.id} {...l} onPress={l.id === 'ldl' ? onRisk : undefined} last={i === LABS.length - 1} />
            ))}
          </Card>
        </View>

        <View>
          <SectionLabel action="过去 7 天">手环数据</SectionLabel>
          <Card>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <Text style={{ fontWeight: '600', fontSize: 14, color: C.ink1 }}>静息心率</Text>
              <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 20, fontWeight: '500', color: C.green500 }}>58 <Text style={{ fontSize: 11, color: C.ink3 }}>bpm</Text></Text>
            </View>
            <Sparkline points={[64, 62, 63, 60, 61, 59, 58]} />
            <Text style={{ fontSize: 12.5, color: C.ink3, marginTop: 4 }}>↓ 4 bpm，恢复在改善</Text>
          </Card>
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
            <MetricTile icon="moon" label="睡眠" value="6h12" delta="略偏少" status="caution" />
            <MetricTile icon="activity" label="HRV" value="48" unit="ms" delta="↑ 平稳" status="normal" />
            <MetricTile icon="flame" label="活动" value="412" unit="kcal" delta="达标" status="normal" />
          </View>
        </View>
      </ScrollView>
    </>
  );
}

// ── Me ────────────────────────────────────────────────────────────────
export function MeView() {
  return (
    <>
      <TopBar mark={false} title="我的" />
      <ScrollView contentContainerStyle={{ ...body, gap: 20 }}>
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 16 }}>
            <View style={[s.avatar, { width: 54, height: 54, borderRadius: 27 }]}><Text style={[s.avatarText, { fontSize: 22 }]}>衡</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '800', fontSize: 19, color: C.ink1 }}>张子衡</Text>
              <Text style={{ fontSize: 13, color: C.ink3 }}>男 · 41 岁 · 心代谢管理中</Text>
            </View>
          </View>
          <DayProgress day={23} total={90} />
        </Card>

        <View>
          <SectionLabel>已连接设备</SectionLabel>
          <Card pad={0}>
            {([['watch', 'Apple Watch', '实时同步', true], ['file-text', '体检报告', '2026-04-11', true], ['activity', '华为运动健康', '未连接', false]] as const).map(([ic, nm, sub, on], i) => (
              <View key={nm} style={[s.settingRow, i === 2 && { borderBottomWidth: 0 }]}>
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
            {([['bell', '每日提醒', '08:00'], ['calendar-check', '复查提醒', '7月 11 日'], ['shield', '隐私与数据', ''], ['circle-help', '帮助与反馈', '']] as const).map(([ic, nm, val], i) => (
              <View key={nm} style={[s.settingRow, i === 3 && { borderBottomWidth: 0 }]}>
                <Icon name={ic} size={19} color={C.ink2} />
                <Text style={{ flex: 1, fontWeight: '600', fontSize: 15, color: C.ink1 }}>{nm}</Text>
                {val ? <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 13, color: C.ink3 }}>{val}</Text> : null}
                <Icon name="chevron-right" size={18} color={C.ink4} />
              </View>
            ))}
          </Card>
        </View>
      </ScrollView>
    </>
  );
}

// ── Risk detail (pushed sub-view) ──────────────────────────────────────────
export function RiskDetailView({ onBack, onAgent }: { onBack: () => void; onAgent?: () => void }) {
  const series = [{ t: '基线', v: 3.8 }, { t: '4周', v: 3.6 }, { t: '8周', v: 3.4 }, { t: '12周', v: 3.1 }];
  return (
    <View style={{ flex: 1, backgroundColor: C.paper }}>
      <View style={[s.detailHeader]}>
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
            你的 LDL-C 是 <Text style={{ color: C.ink1, fontWeight: '700' }}>3.8 mmol/L</Text>，理想值在 3.4 以下。它是心血管风险里最值得先处理的一项——好消息是，它对饮食和运动的反应很快。
          </Text>
        </Card>

        <View>
          <SectionLabel>12 周改善预测</SectionLabel>
          <Card><TrendChart series={series} target={3.4} /></Card>
        </View>

        <View>
          <SectionLabel>你的计划</SectionLabel>
          <Card pad={0}>
            {([['utensils', '用全谷物替换精米白面', '每天 1 餐'], ['fish', '每周 2 次深海鱼', '补充 Omega-3'], ['footprints', '每天 6,000 步以上', '已坚持 18 天']] as const).map(([ic, t, sub], i) => (
              <View key={t} style={[s.planRow, i === 2 && { borderBottomWidth: 0 }]}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: C.green50, alignItems: 'center', justifyContent: 'center' }}><Icon name={ic} size={18} color={C.green500} /></View>
                <View style={{ flex: 1 }}><Text style={{ fontWeight: '600', fontSize: 14.5, color: C.ink1 }}>{t}</Text><Text style={{ fontSize: 12.5, color: C.ink3 }}>{sub}</Text></View>
              </View>
            ))}
          </Card>
        </View>

        <Button variant="dark" size="lg" full icon="messages-square" onPress={onAgent}>问复元：怎么吃能降得更快？</Button>
      </ScrollView>
    </View>
  );
}

// ── Onboarding ─────────────────────────────────────────────────────────────
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
              {LABS.slice(0, 3).map((l, i) => <LabRow key={l.id} {...l} last={i === 2} />)}
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
        ? footer('开始', () => setStep(1), '已有 12,000+ 体检用户在复元管理健康')
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
  settingRow: { flexDirection: 'row', alignItems: 'center', gap: 13, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  planRow: { flexDirection: 'row', alignItems: 'center', gap: 13, paddingHorizontal: 16, paddingVertical: 13, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  detailHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line, backgroundColor: C.paper },
});
