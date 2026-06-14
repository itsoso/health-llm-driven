/**
 * MetabolicEntryCard —— 首页「代谢健康」显眼入口 (Personal Health OS 代谢闭环).
 *
 * 之前代谢画像/90天干预只埋在「我」设置 hub 里, discoverability 差。这里把它提到
 * 首页:有进行中的干预周期就显示「第 N / 90 天」, 否则引导「看风险 · 开始干预」。
 * 点击进 /metabolic-profile(画像front door, 内含进入 90 天干预的 CTA)。
 *
 * 三态都诚实: 加载中 / 进行中(显示天数) / 未开始。失败静默退化为"未开始"引导。
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import { useActiveCycle } from '../../hooks/useHealthOs';
import type { OutcomeMetric } from '../../services/healthOs';

function daysBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  if (Number.isNaN(da) || Number.isNaN(db)) return null;
  return Math.round((db - da) / 86400000);
}

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '待定';
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10);
}

function pickPrimaryOutcome(outcomes: OutcomeMetric[] = []): OutcomeMetric | null {
  return outcomes.find((o) => o.status !== 'met') ?? outcomes[0] ?? null;
}

function outcomeLine(outcome: OutcomeMetric | null): string {
  if (!outcome) return '先锁定体检基线，再追踪复查变化';
  const unit = outcome.unit ? ` ${outcome.unit}` : '';
  return `${outcome.display} ${fmt(outcome.baseline_value)} → ${fmt(outcome.target_value)}${unit}`;
}

export default function MetabolicEntryCard() {
  const { c } = useTheme();
  const router = useRouter();
  const { data: cycle, isLoading } = useActiveCycle();

  const active = cycle?.status === 'active';
  const total = active ? (daysBetween(cycle?.start_date, cycle?.planned_end_date) ?? 90) : 90;
  const elapsed = active ? (daysBetween(cycle?.start_date, new Date().toISOString()) ?? 0) : 0;
  const day = active ? Math.max(1, Math.min(total, elapsed + 1)) : null;
  const daysLeft = active ? Math.max(0, daysBetween(new Date().toISOString(), cycle?.planned_end_date) ?? 0) : null;
  const primaryOutcome = active ? pickPrimaryOutcome(cycle?.outcomes ?? []) : null;
  const completed = active ? (cycle?.outcomes ?? []).filter((o) => o.status === 'met').length : 0;

  const icon: keyof typeof Ionicons.glyphMap = active ? 'flag' : 'pulse-outline';
  const iconColor = active ? c.green : c.brand;
  const tint = active ? c.tintGreen : c.brandLight;
  const stageText = isLoading
    ? '正在同步周期'
    : active && day != null
      ? `第 ${day} / ${total} 天`
      : '尚未开始';
  const recheckText = active && daysLeft != null
    ? `复查倒计时 ${daysLeft} 天`
    : '看风险 · 开始 90 天干预';
  const targetText = isLoading ? '读取体检和行动目标中' : outcomeLine(primaryOutcome);
  const a11y = active ? '查看 90 天健康周期' : '代谢健康，查看代谢风险并开始 90 天干预';
  const route = active ? '/intervention-cycle' : '/metabolic-profile';

  return (
    <Pressable
      testID="home-health-cycle-cockpit"
      onPress={() => router.push(route as any)}
      style={({ pressed }) => [styles.card, { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed ? 0.78 : 1 }]}
      accessibilityRole="button"
      accessibilityLabel={a11y}
    >
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: tint }]} testID="home-metabolic-entry-card">
          <Ionicons name={icon} size={17} color={iconColor} />
        </View>
        <View style={styles.headerText}>
          <Text maxFontSizeMultiplier={1.25} style={[styles.kicker, { color: c.labelTertiary }]}>中年代谢健康</Text>
          <Text maxFontSizeMultiplier={1.25} style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1}>
            90 天健康周期
          </Text>
        </View>
        <View style={[styles.stagePill, { backgroundColor: active ? c.tintGreen : c.fill }]}>
          <Text maxFontSizeMultiplier={1.15} style={[styles.stageText, { color: active ? c.green : c.labelSecondary }]} numberOfLines={1}>
            {stageText}
          </Text>
        </View>
      </View>

      <View style={styles.body}>
        <Text maxFontSizeMultiplier={1.3} style={[styles.target, { color: c.labelPrimary }]} numberOfLines={1}>
          {targetText}
        </Text>
        <View style={styles.metaRow}>
          <Text maxFontSizeMultiplier={1.2} style={[styles.meta, { color: c.labelSecondary }]} numberOfLines={1}>
            {recheckText}
          </Text>
          {active && completed > 0 ? (
            <Text maxFontSizeMultiplier={1.2} style={[styles.meta, { color: c.green }]} numberOfLines={1}>
              {completed} 项已达标
            </Text>
          ) : null}
        </View>
      </View>

      <View style={styles.footer}>
        <Text maxFontSizeMultiplier={1.2} style={[styles.footerText, { color: c.labelTertiary }]} numberOfLines={1}>
          今日行动和复查结果会回流到这个周期
        </Text>
        <Ionicons name="chevron-forward" size={15} color={c.labelTertiary} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
    gap: 10,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  iconWrap: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, minWidth: 0 },
  kicker: { fontSize: 11, fontWeight: '700' },
  title: { fontSize: 17, fontWeight: '900', marginTop: 1 },
  stagePill: { paddingHorizontal: 9, paddingVertical: 5, borderRadius: 999, maxWidth: 126 },
  stageText: { fontSize: 11, fontWeight: '800' },
  body: { gap: 5 },
  target: { fontSize: 14, fontWeight: '800' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  meta: { fontSize: 12, fontWeight: '700' },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 18 },
  footerText: { flex: 1, fontSize: 11, fontWeight: '600' },
});
