/**
 * RevaHeroCard —— 首页深绿 Hero(Reva 重设计第 2 块)。
 *
 * 左:ReadinessRing(深色就绪环,真实就绪分;null → 「待同步」)。
 * 右:overline「今日恢复就绪」+ 一句状态。
 * 底:「现在只做一件事」深色子面行,点击走调用方给的 onPressAction。
 *
 * 纯表现型:就绪分 / 状态 / 动作文案 + 回调全部由 index.tsx 注入,本组件不取数。
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { revaColors as C, revaRadii, revaShadows } from '../../constants/revaTheme';
import { Icon, ReadinessRing } from '../reva/RevaKit';

function readinessTitle(score: number | null): string {
  if (score == null) return '待同步';
  if (score >= 80) return '可上强度';
  if (score >= 60) return '适度活动';
  return '注意恢复';
}

function readinessNote(score: number | null, note?: string | null): string {
  if (note) return note;
  if (score == null) return '连接手环后,复元用真实数据校准就绪度';
  if (score >= 80) return 'HRV · 睡眠 · 电量俱佳';
  if (score >= 60) return '状态尚可,留意训练负荷';
  return '优先睡眠和低强度恢复';
}

export default function RevaHeroCard({
  readiness,
  note,
  actionTitle,
  actionLever,
  onPressAction,
}: {
  readiness: number | null;
  note?: string | null;
  actionTitle: string;
  actionLever?: string | null;
  onPressAction: () => void;
}) {
  return (
    <View style={styles.hero}>
      <View style={styles.topRow}>
        {readiness != null ? (
          <ReadinessRing score={readiness} dark size={96} />
        ) : (
          <View style={styles.ringPlaceholder}>
            <Text style={styles.ringPlaceholderText}>待同步</Text>
          </View>
        )}
        <View style={styles.copy}>
          <Text style={styles.overline}>今日恢复就绪</Text>
          <Text style={styles.title} numberOfLines={1}>
            {readinessTitle(readiness)}
          </Text>
          <Text style={styles.note} numberOfLines={2}>
            {readinessNote(readiness, note)}
          </Text>
        </View>
      </View>

      <Pressable
        style={({ pressed }) => [styles.actionRow, pressed && { opacity: 0.85 }]}
        onPress={onPressAction}
        accessibilityRole="button"
        accessibilityLabel={`现在只做一件事:${actionTitle}`}
      >
        <View style={styles.actionIcon}>
          <Icon name="play" size={16} color={C.greenBright} />
        </View>
        <View style={styles.actionBody}>
          <Text style={styles.actionLever}>{actionLever || '现在只做一件事'}</Text>
          <Text style={styles.actionTitle} numberOfLines={1}>
            {actionTitle}
          </Text>
        </View>
        <Icon name="chevron-right" size={18} color={C.focusInk2} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    backgroundColor: C.focusBg,
    borderRadius: revaRadii.xl,
    padding: 20,
    gap: 18,
    ...revaShadows.focus,
  },
  topRow: { flexDirection: 'row', gap: 18, alignItems: 'center' },
  ringPlaceholder: {
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 10,
    borderColor: C.focusLine,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringPlaceholderText: { fontFamily: 'IBMPlexMono', fontSize: 14, color: C.focusInk2 },
  copy: { flex: 1, minWidth: 0 },
  overline: {
    fontFamily: 'IBMPlexMono',
    fontSize: 11,
    letterSpacing: 0.9,
    color: C.focusInk2,
  },
  title: {
    fontFamily: 'Manrope',
    fontWeight: '700',
    fontSize: 19,
    color: C.greenBright,
    marginTop: 5,
    marginBottom: 6,
  },
  note: { fontSize: 13.5, lineHeight: 20, color: C.focusInk2 },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: C.focusBg2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    borderRadius: revaRadii.md,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  actionIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: C.focusLine,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionBody: { flex: 1, minWidth: 0 },
  actionLever: {
    fontFamily: 'IBMPlexMono',
    fontSize: 10.5,
    letterSpacing: 0.6,
    color: C.focusInk2,
    marginBottom: 2,
  },
  actionTitle: { fontWeight: '700', fontSize: 15, color: C.focusInk1 },
});
