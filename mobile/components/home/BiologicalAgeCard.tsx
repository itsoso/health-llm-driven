/**
 * BiologicalAgeCard —— 首页"身体年龄"卡 (抗衰 MVP Step 3).
 *
 * 把 Twin 的 PhenoAge(Levine 2018 表型年龄)露在首页 —— 抗衰产品的北极星指标。
 * 数据链:体检 9 项血检 → twin.labs.phenotypic_age(后端 #47/#48 已落地)。
 *
 * 三态都诚实(对齐 OutcomeWinCard 风格 + LongevitySpecialist 纪律):
 *   - ok:大数字"身体年龄 47" + delta 徽章(年轻=绿/偏老=橙)+ claim_boundary 小字(必须呈现)
 *   - incomplete:列缺失血检项,引导去补检,不假装有结果
 *   - error:加载失败,下拉重试,不退化成 0
 *
 * 不在卡里宣称"逆龄/治疗";claim_boundary 跟随展示(证据纪律)。
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import type { PhenoAgeView } from '../../services/twinHelpers';
import type { BioAgeWin } from '../../services/myProgress';

interface Props {
  view: PhenoAgeView | null | undefined;
  win?: BioAgeWin | null; // 12 周 N-of-1 评分出的生物年龄改善(信任时刻)
  isError?: boolean;
  onPress?: () => void;
}

export default function BiologicalAgeCard({ view, win, isError, onPress }: Props) {
  const { c, s } = useTheme();

  // ── error
  if (isError) {
    return (
      <Shell c={c} onPress={onPress} a11y="身体年龄加载失败，下拉重试">
        <IconBubble bg={c.fill}>
          <Ionicons name="cloud-offline-outline" size={16} color={c.labelTertiary} />
        </IconBubble>
        <View style={styles.textWrap}>
          <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.4}>
            身体年龄加载失败
          </Text>
          <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1} maxFontSizeMultiplier={1.4}>
            下拉重试
          </Text>
        </View>
      </Shell>
    );
  }

  // ── incomplete:无 PhenoAge,引导补检
  if (!view || view.status !== 'ok' || view.phenotypicAge == null) {
    const miss = view?.missingLabels ?? [];
    const sub =
      miss.length > 0
        ? `补 ${miss.length} 项血检即可测算:${miss.slice(0, 4).join('/')}${miss.length > 4 ? '…' : ''}`
        : '上传一次完整体检血检报告即可测算';
    return (
      <Shell c={c} onPress={onPress} a11y={`测出你的身体年龄，${sub}`}>
        <IconBubble bg={c.brandLight}>
          <Ionicons name="flask-outline" size={16} color={c.brand} />
        </IconBubble>
        <View style={styles.textWrap}>
          <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.4}>
            测出你的身体年龄
          </Text>
          <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={2} maxFontSizeMultiplier={1.3}>
            {sub}
          </Text>
        </View>
        {onPress ? <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} /> : null}
      </Shell>
    );
  }

  // ── ok:有 PhenoAge
  const pa = view.phenotypicAge;
  const delta = view.deltaYears;
  const chrono = view.chronoAge;

  // delta 方向:<0 年轻(绿) / >0 偏老(橙) / ~0 中性
  let tone = s.success;
  let deltaText = '';
  let a11yDelta = '';
  if (delta != null) {
    if (delta <= -0.5) {
      tone = s.success;
      deltaText = `年轻 ${Math.abs(delta).toFixed(1)} 岁`;
      a11yDelta = `比实足年龄年轻 ${Math.abs(delta).toFixed(1)} 岁`;
    } else if (delta >= 0.5) {
      tone = s.warning;
      deltaText = `偏老 ${delta.toFixed(1)} 岁`;
      a11yDelta = `比实足年龄偏老 ${delta.toFixed(1)} 岁`;
    } else {
      tone = s.neutral ?? s.success;
      deltaText = '与实足相当';
      a11yDelta = '与实足年龄相当';
    }
  }

  const a11y =
    `身体年龄 ${pa} 岁` +
    (chrono != null ? `，实足 ${chrono} 岁` : '') +
    (a11yDelta ? `，${a11yDelta}` : '');

  return (
    <Shell c={c} onPress={onPress} a11y={a11y} testID="home-biological-age-card">
      <View style={styles.bigWrap}>
        <Text style={[styles.bigNum, { color: c.labelPrimary }]} maxFontSizeMultiplier={1.2}>
          {Math.round(pa)}
        </Text>
        <Text style={[styles.bigUnit, { color: c.labelTertiary }]} maxFontSizeMultiplier={1.2}>
          岁
        </Text>
      </View>
      <View style={styles.textWrap}>
        <View style={styles.titleRow}>
          <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
            身体年龄
          </Text>
          {deltaText ? (
            <View style={[styles.badge, { backgroundColor: tone.bg }]}>
              <Text style={[styles.badgeText, { color: tone.fg }]} maxFontSizeMultiplier={1.2}>
                {deltaText}
              </Text>
            </View>
          ) : null}
        </View>
        <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
          {chrono != null ? `实足 ${chrono} 岁 · ` : ''}基于血检(PhenoAge)
        </Text>
        {win && win.deltaYears > 0 ? (
          <View style={[styles.winRow, { backgroundColor: s.success.bg }]}>
            <Ionicons name="trending-down" size={12} color={s.success.fg} />
            <Text style={[styles.winText, { color: s.success.fg }]} numberOfLines={1} maxFontSizeMultiplier={1.2}>
              干预后 {win.baseline}→{win.actual} · 年轻 {win.deltaYears.toFixed(1)} 岁
            </Text>
          </View>
        ) : null}
        {view.claimBoundary ? (
          <Text style={[styles.boundary, { color: c.labelQuaternary ?? c.labelTertiary }]} numberOfLines={2} maxFontSizeMultiplier={1.2}>
            {view.claimBoundary}
          </Text>
        ) : null}
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} /> : null}
    </Shell>
  );
}

// ── 小组件 ──
function Shell({
  c,
  onPress,
  a11y,
  testID,
  children,
}: {
  c: any;
  onPress?: () => void;
  a11y: string;
  testID?: string;
  children: React.ReactNode;
}) {
  return (
    <Pressable
      testID={testID ?? 'home-biological-age-card'}
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed && onPress ? 0.78 : 1 },
      ]}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={a11y}
    >
      {children}
    </Pressable>
  );
}

function IconBubble({ bg, children }: { bg: string; children: React.ReactNode }) {
  return <View style={[styles.iconWrap, { backgroundColor: bg }]}>{children}</View>;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
  },
  iconWrap: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  bigWrap: { flexDirection: 'row', alignItems: 'baseline', minWidth: 44 },
  bigNum: { fontSize: 32, fontWeight: '900', letterSpacing: -1 },
  bigUnit: { fontSize: 13, fontWeight: '700', marginLeft: 1 },
  textWrap: { flex: 1, gap: 2, minWidth: 0 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 14, fontWeight: '800' },
  sub: { fontSize: 11, fontWeight: '500' },
  boundary: { fontSize: 10, fontWeight: '400', lineHeight: 13, marginTop: 1 },
  winRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 8,
    marginTop: 3,
  },
  winText: { fontSize: 11, fontWeight: '800' },
  badge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 8 },
  badgeText: { fontSize: 11, fontWeight: '800' },
});
