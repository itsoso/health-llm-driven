/**
 * 复元 Reva — RN component kit (primitives + data widgets).
 *
 * Faithful port of the Reva mobile UI kit (`docs/design/reva/ui_kits/mobile-app/`)
 * to React Native, using `constants/revaTheme` tokens. Lucide icon names from the
 * design are mapped to @expo/vector-icons (Ionicons) — closest clinical-stroke match.
 */
import React from 'react';
import { View, Text, Pressable, StyleSheet, type ViewStyle, type StyleProp } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Path, Line, Text as SvgText, G } from 'react-native-svg';
import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaShadows,
  type RevaStatus,
} from '../../constants/revaTheme';

// ── Status table ────────────────────────────────────────────────────────────
const STATUS = {
  normal: { ...revaSemantic.normal, label: '达标' },
  caution: { ...revaSemantic.caution, label: '注意' },
  risk: { ...revaSemantic.risk, label: '偏高' },
  info: { ...revaSemantic.info, label: '数据' },
} as const;

// ── Icon: Lucide name → Ionicons ────────────────────────────────────────────
const ICON_MAP: Record<string, keyof typeof Ionicons.glyphMap> = {
  sun: 'sunny-outline', activity: 'pulse-outline', 'messages-square': 'chatbubbles-outline',
  user: 'person-outline', footprints: 'walk-outline', utensils: 'restaurant-outline',
  moon: 'moon-outline', droplet: 'water-outline', gauge: 'speedometer-outline',
  pill: 'medical-outline', sparkles: 'sparkles-outline', 'trending-down': 'trending-down-outline',
  'trending-up': 'trending-up-outline', 'chevron-right': 'chevron-forward', 'chevron-left': 'chevron-back',
  check: 'checkmark', 'check-circle-2': 'checkmark-circle', 'file-text': 'document-text-outline',
  lock: 'lock-closed-outline', watch: 'watch-outline', flame: 'flame-outline', fish: 'fish-outline',
  bell: 'notifications-outline', 'calendar-check': 'calendar-outline', shield: 'shield-checkmark-outline',
  'circle-help': 'help-circle-outline', 'arrow-up': 'arrow-up', heart: 'heart-outline',
  play: 'play', 'refresh-cw': 'refresh', 'alert-triangle': 'warning-outline',
};

export function Icon({ name, size = 22, color = C.ink2 }: { name: string; size?: number; color?: string }) {
  return <Ionicons name={ICON_MAP[name] ?? 'ellipse-outline'} size={size} color={color} />;
}

export function Dot({ status = 'normal', size = 9 }: { status?: RevaStatus; size?: number }) {
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: STATUS[status].fg }} />;
}

export function Chip({ status = 'info', children, style }: { status?: RevaStatus; children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  const s = STATUS[status];
  return (
    <View style={[k.chip, { backgroundColor: s.bg, borderColor: s.line }, style]}>
      <View style={{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: s.fg }} />
      <Text style={[k.chipText, { color: s.fg }]}>{children}</Text>
    </View>
  );
}

export function Card({ children, pad = 18, onPress, style, testID, accessibilityLabel }: { children: React.ReactNode; pad?: number; onPress?: () => void; style?: StyleProp<ViewStyle>; testID?: string; accessibilityLabel?: string }) {
  const inner = <View style={[k.card, { padding: pad }, style]}>{children}</View>;
  return onPress
    ? <Pressable onPress={onPress} testID={testID} accessibilityLabel={accessibilityLabel} accessibilityRole={accessibilityLabel ? 'button' : undefined}>{inner}</Pressable>
    : <View testID={testID}>{inner}</View>;
}

export function SectionLabel({ children, action, onAction }: { children: React.ReactNode; action?: string; onAction?: () => void }) {
  return (
    <View style={k.sectionRow}>
      <Text style={k.overline}>{children}</Text>
      {action ? (
        <Pressable onPress={onAction}><Text style={k.sectionAction}>{action}</Text></Pressable>
      ) : null}
    </View>
  );
}

type BtnVariant = 'primary' | 'secondary' | 'tertiary' | 'dark' | 'ghost';
type BtnSize = 'sm' | 'md' | 'lg';
export function Button({ children, variant = 'primary', size = 'md', icon, onPress, full }: {
  children: React.ReactNode; variant?: BtnVariant; size?: BtnSize; icon?: string; onPress?: () => void; full?: boolean;
}) {
  const pad = size === 'lg' ? { paddingVertical: 16, paddingHorizontal: 24 } : size === 'sm' ? { paddingVertical: 9, paddingHorizontal: 16 } : { paddingVertical: 14, paddingHorizontal: 22 };
  const fs = size === 'lg' ? 17 : size === 'sm' ? 14 : 16;
  const v: Record<BtnVariant, { bg: string; fg: string; border?: string }> = {
    primary: { bg: C.green500, fg: C.greenOn },
    secondary: { bg: C.surface, fg: C.ink1, border: C.lineStrong },
    tertiary: { bg: 'transparent', fg: C.green600 },
    dark: { bg: C.focusBg, fg: C.greenBright },
    ghost: { bg: C.green50, fg: C.green600 },
  };
  const vs = v[variant];
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [k.btn, pad, full && { alignSelf: 'stretch' }, {
        backgroundColor: vs.bg,
        borderWidth: vs.border ? 1.5 : 0, borderColor: vs.border,
        transform: [{ scale: pressed ? 0.97 : 1 }],
      }]}
    >
      {icon ? <Icon name={icon} size={size === 'sm' ? 16 : 18} color={vs.fg} /> : null}
      <Text style={{ color: vs.fg, fontWeight: '700', fontSize: fs }}>{children}</Text>
    </Pressable>
  );
}

export function TopBar({ title, sub, mark = true, right, dark }: { title: string; sub?: string; mark?: boolean; right?: React.ReactNode; dark?: boolean }) {
  return (
    <View style={[k.topbar, { backgroundColor: dark ? C.focusBg : C.paper, borderBottomColor: dark ? C.focusLine : C.line }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 11, flex: 1 }}>
        {mark ? <RevaMark /> : null}
        <View style={{ flex: 1 }}>
          {sub ? <Text style={{ fontSize: 12, fontWeight: '600', color: dark ? C.focusInk2 : C.ink3 }}>{sub}</Text> : null}
          <Text style={{ fontSize: 21, fontWeight: '800', letterSpacing: -0.4, color: dark ? C.focusInk1 : C.ink1 }} numberOfLines={1}>{title}</Text>
        </View>
      </View>
      {right}
    </View>
  );
}

/** Recovery-ring brand mark (the Reva motif). */
export function RevaMark({ size = 30 }: { size?: number }) {
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, borderWidth: size > 40 ? 4 : 3, borderColor: C.green500, alignItems: 'center', justifyContent: 'center' }}>
      <View style={{ position: 'absolute', top: -3, width: size * 0.23, height: size * 0.23, borderRadius: size * 0.115, backgroundColor: C.green600 }} />
      <View style={{ width: size * 0.23, height: size * 0.23, borderRadius: size * 0.115, backgroundColor: C.green500 }} />
    </View>
  );
}

const TABS = [
  { id: 'today', label: '今天', icon: 'sun' },
  { id: 'data', label: '数据', icon: 'activity' },
  { id: 'agent', label: '复元', icon: 'messages-square' },
  { id: 'me', label: '我的', icon: 'user' },
] as const;
export type RevaTab = (typeof TABS)[number]['id'];

export function TabBar({ active, onChange, bottomInset = 0 }: { active: RevaTab; onChange: (t: RevaTab) => void; bottomInset?: number }) {
  return (
    <View style={[k.tabbar, { paddingBottom: 10 + bottomInset }]}>
      {TABS.map(t => {
        const on = active === t.id;
        return (
          <Pressable key={t.id} onPress={() => onChange(t.id)} style={k.tab}>
            <Icon name={t.icon} size={23} color={on ? C.green500 : C.ink3} />
            <Text style={{ fontSize: 11, fontWeight: on ? '700' : '600', color: on ? C.green500 : C.ink3 }}>{t.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// ── Data widgets ─────────────────────────────────────────────────────────────
export function ReadinessRing({ score = 86, size = 104, stroke = 10, dark = true }: { score?: number; size?: number; stroke?: number; dark?: boolean }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - score / 100);
  const track = dark ? C.focusLine : C.green100;
  const arc = dark ? C.greenBright : C.green500;
  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size}>
        <Circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <Circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={arc} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={`${circ}`} strokeDashoffset={off}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <View style={StyleSheet.absoluteFill}>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontFamily: 'IBMPlexMono', fontWeight: '500', fontSize: size * 0.34, color: dark ? C.focusInk1 : C.ink1 }}>{score}</Text>
        </View>
      </View>
    </View>
  );
}

export function Sparkline({ points, color = C.green500, height = 44, fill = true }: { points: number[]; color?: string; height?: number; fill?: boolean }) {
  const w = 280, h = height, pad = 2;
  const min = Math.min(...points), max = Math.max(...points);
  const xs = points.map((_, i) => (i / (points.length - 1)) * w);
  const ys = points.map(v => h - pad - ((v - min) / ((max - min) || 1)) * (h - 2 * pad));
  const d = xs.map((x, i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  return (
    <Svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {fill ? <Path d={`${d} L${w},${h} L0,${h} Z`} fill={color} opacity={0.08} /> : null}
      <Path d={d} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      <Circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r={3.2} fill={color} />
    </Svg>
  );
}

export function TrendChart({ series, target, w = 320, h = 150 }: { series: { t: string; v: number }[]; target: number; w?: number; h?: number }) {
  const padL = 8, padR = 8, padT = 14, padB = 22;
  const iw = w - padL - padR, ih = h - padT - padB;
  const vals = series.map(s => s.v).concat([target]);
  const min = Math.min(...vals) * 0.96, max = Math.max(...vals) * 1.04;
  const X = (i: number) => padL + (i / (series.length - 1)) * iw;
  const Y = (v: number) => padT + (1 - (v - min) / ((max - min) || 1)) * ih;
  const line = series.map((s, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(s.v).toFixed(1)}`).join(' ');
  const ty = Y(target);
  return (
    <Svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`}>
      <Line x1={padL} x2={w - padR} y1={ty} y2={ty} stroke={C.green500} strokeWidth={1.5} strokeDasharray="4 4" opacity={0.55} />
      <SvgText x={w - padR} y={ty - 5} textAnchor="end" fontFamily="IBMPlexMono" fontSize={10} fill={C.green600}>{`理想 ≤ ${target}`}</SvgText>
      <Path d={`${line} L${X(series.length - 1)},${padT + ih} L${X(0)},${padT + ih} Z`} fill={C.green500} opacity={0.06} />
      <Path d={line} fill="none" stroke={C.green500} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      {series.map((s, i) => (
        <G key={i}>
          <Circle cx={X(i)} cy={Y(s.v)} r={i === series.length - 1 ? 4.5 : 3} fill={i === series.length - 1 ? C.green500 : '#fff'} stroke={C.green500} strokeWidth={2} />
          <SvgText x={X(i)} y={h - 6} textAnchor="middle" fontFamily="IBMPlexMono" fontSize={10} fill={C.ink3}>{s.t}</SvgText>
        </G>
      ))}
    </Svg>
  );
}

export function PlanItem({ icon, title, sub, tag, done, onToggle, last, titleLines, subLines, trailing = 'check' }: { icon: string; title: string; sub?: string; tag?: string; done?: boolean; onToggle?: () => void; last?: boolean; titleLines?: number; subLines?: number; trailing?: 'check' | 'chevron' }) {
  return (
    <Pressable onPress={onToggle} style={[k.rowItem, last && { borderBottomWidth: 0 }]}>
      <View style={[k.rowIcon, { backgroundColor: done ? C.green50 : C.paper2 }]}>
        <Icon name={icon} size={19} color={done ? C.green500 : C.ink2} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={titleLines} style={{ fontWeight: '600', fontSize: 15, color: C.ink1, textDecorationLine: done ? 'line-through' : 'none', opacity: done ? 0.55 : 1 }}>{title}</Text>
        {sub ? <Text numberOfLines={subLines} style={{ fontSize: 12.5, color: C.ink3 }}>{sub}</Text> : null}
      </View>
      {tag && !done ? <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 11, color: C.ink3 }}>{tag}</Text> : null}
      {trailing === 'chevron' ? (
        <Icon name="chevron-right" size={20} color={C.ink3} />
      ) : (
        <View style={[k.check, { borderWidth: done ? 0 : 2, borderColor: C.lineStrong, backgroundColor: done ? C.green500 : 'transparent' }]}>
          {done ? <Icon name="check" size={15} color="#fff" /> : null}
        </View>
      )}
    </Pressable>
  );
}

export function MetricTile({ icon, label, value, unit, delta, status = 'normal', onPress }: { icon: string; label: string; value: string; unit?: string; delta?: string; status?: RevaStatus; onPress?: () => void }) {
  const s = STATUS[status];
  const inner = (
    <View style={k.tile}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 9 }}>
        <Icon name={icon} size={16} color={C.ink3} />
        <Text style={{ fontSize: 12, fontWeight: '600', color: C.ink2 }} numberOfLines={1}>{label}</Text>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 3 }}>
        <Text style={{ fontFamily: 'IBMPlexMono', fontWeight: '500', fontSize: 22, color: s.fg }}>{value}</Text>
        {unit ? <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 11, color: C.ink3 }}>{unit}</Text> : null}
      </View>
      {delta ? <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 11, color: C.ink3, marginTop: 2 }}>{delta}</Text> : null}
    </View>
  );
  return onPress ? <Pressable onPress={onPress} style={{ flex: 1 }}>{inner}</Pressable> : <View style={{ flex: 1 }}>{inner}</View>;
}

export function LabRow({ status = 'normal', name, sub, value, unit, onPress, last }: { status?: RevaStatus; name: string; sub?: string; value: string; unit?: string; onPress?: () => void; last?: boolean }) {
  const s = STATUS[status];
  return (
    <Pressable onPress={onPress} disabled={!onPress} style={[k.rowItem, last && { borderBottomWidth: 0 }]}>
      <Dot status={status} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ fontWeight: '600', fontSize: 15, color: C.ink1 }}>{name}</Text>
        {sub ? <Text style={{ fontSize: 12, fontWeight: '600', color: s.fg }}>{sub}</Text> : null}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'baseline' }}>
        <Text style={{ fontFamily: 'IBMPlexMono', fontWeight: '500', fontSize: 18, color: s.fg }}>{value}</Text>
        {unit ? <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 11, color: C.ink3 }}> {unit}</Text> : null}
      </View>
      {onPress ? <Icon name="chevron-right" size={18} color={C.ink4} /> : null}
    </Pressable>
  );
}

export function DayProgress({ day = 23, total = 90 }: { day?: number; total?: number }) {
  const pct = Math.round((day / total) * 100);
  return (
    <View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 7 }}>
        <Text style={{ fontSize: 13, fontWeight: '600', color: C.ink2 }}>90 天主动管理</Text>
        <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 13, color: C.ink1 }}>{`第 ${day} / ${total} 天`}</Text>
      </View>
      <View style={{ height: 8, borderRadius: 99, backgroundColor: C.paper2, overflow: 'hidden' }}>
        <View style={{ height: '100%', width: `${pct}%`, borderRadius: 99, backgroundColor: C.green500 }} />
      </View>
    </View>
  );
}

const k = StyleSheet.create({
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, borderWidth: StyleSheet.hairlineWidth, alignSelf: 'flex-start' },
  chipText: { fontWeight: '600', fontSize: 12 },
  card: { backgroundColor: C.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, borderRadius: revaRadii.lg, ...revaShadows.md },
  sectionRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', paddingHorizontal: 4, marginBottom: 10 },
  overline: { fontWeight: '600', fontSize: 11, letterSpacing: 0.88, color: C.ink3 },
  sectionAction: { fontSize: 13, fontWeight: '600', color: C.green600 },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 999 },
  topbar: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 12, paddingBottom: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  tabbar: { flexDirection: 'row', justifyContent: 'space-around', alignItems: 'flex-start', paddingTop: 10, paddingHorizontal: 12, backgroundColor: C.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line },
  tab: { alignItems: 'center', gap: 4, paddingHorizontal: 14, paddingVertical: 4, minWidth: 56 },
  rowItem: { flexDirection: 'row', alignItems: 'center', gap: 13, paddingHorizontal: 16, paddingVertical: 13, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  rowIcon: { width: 38, height: 38, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  check: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  tile: { flex: 1, backgroundColor: C.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 13, ...revaShadows.sm },
});
