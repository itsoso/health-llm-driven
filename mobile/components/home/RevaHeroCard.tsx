/**
 * RevaHeroCard —— 首页深绿 Hero(Reva 重设计第 2 块,2026-06-23 翻成时间感知「现在该做什么」)。
 *
 * 主体:深色「现在该做什么」now-action 行 —— 标题 + 为什么 + 计划时点,点行走 onPressAction;
 *       可完成时右侧内联「完成」直接打卡(走调用方注入的 onComplete,复用 /agenda/complete 双轨)。
 * 支撑:右上角小就绪环(ReadinessRing)作为 SUPPORTING 上下文,不再占据主视觉。
 * 空态:无 now-item(今天安排好了 / 待同步)→ 退化成一句平静状态 + 「补齐今天记录」入口。
 *
 * 纯表现型:now-item 文案 / 就绪分 / 回调全部由 index.tsx 注入(读 /timeline/today 的 now),本组件不取数。
 * R4:文案保持 advisory(标题/why 直接透传后端 timeline,不在前端造处方/诊断措辞)。
 */
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { revaColors as C, revaRadii, revaShadows } from '../../constants/revaTheme';
import { Icon, ReadinessRing } from '../reva/RevaKit';

function readinessTitle(score: number | null): string {
  if (score == null) return '待同步';
  if (score >= 80) return '可上强度';
  if (score >= 60) return '适度活动';
  return '注意恢复';
}

function cnDate(iso?: string | null): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[2])} 月 ${Number(m[3])} 日` : iso;
}

export default function RevaHeroCard({
  readiness,
  stale,
  asOf,
  // now-action(读 /timeline/today 的 now 项;无 → 空态)
  hasNow,
  nowTitle,
  nowSubtitle,
  nowTime,
  nowLever,
  canComplete,
  completing,
  onPressAction,
  onComplete,
}: {
  readiness: number | null;
  stale?: boolean;
  asOf?: string | null;
  hasNow: boolean;
  nowTitle: string;
  nowSubtitle?: string | null;
  nowTime?: string | null;
  nowLever?: string | null;
  canComplete?: boolean;
  completing?: boolean;
  onPressAction: () => void;
  onComplete?: () => void;
}) {
  // 旧分(昨晚没同步)→ 不当「今日就绪」用,环显示「待同步」+ 标注上次值/日期。
  const showStale = Boolean(stale && readiness != null);
  const ringScore = readiness != null && !showStale ? readiness : null;
  const ringLabel = showStale ? '昨晚未同步' : readinessTitle(readiness);

  return (
    <View style={styles.hero}>
      {/* 支撑行:小就绪环 + overline,readiness 退为上下文(不再是主视觉) */}
      <View style={styles.supportRow}>
        {ringScore != null ? (
          <ReadinessRing score={ringScore} dark size={56} stroke={6} />
        ) : (
          <View style={styles.ringPlaceholder}>
            <Text style={styles.ringPlaceholderText}>待同步</Text>
          </View>
        )}
        <View style={styles.supportCopy}>
          <Text style={styles.overline}>今日恢复就绪</Text>
          <Text style={styles.supportTitle} numberOfLines={1}>
            {ringLabel}
          </Text>
          {showStale ? (
            <Text style={styles.supportNote} numberOfLines={1}>
              上次 {readiness} 分 · {cnDate(asOf)}
            </Text>
          ) : null}
        </View>
      </View>

      {/* 主体:现在该做什么(now-action),时间感知。无 now → 空态行。 */}
      {hasNow ? (
        <View style={styles.nowBlock}>
          <View style={styles.nowHead}>
            <Text style={styles.nowLever} numberOfLines={1}>
              {nowLever || '现在该做'}
            </Text>
            {nowTime ? <Text style={styles.nowTime}>{nowTime}</Text> : null}
          </View>
          <Pressable
            style={({ pressed }) => [styles.nowMain, pressed && { opacity: 0.85 }]}
            onPress={onPressAction}
            accessibilityRole="button"
            accessibilityLabel={`现在该做:${nowTitle}`}
          >
            <View style={styles.nowBody}>
              <Text style={styles.nowTitle} numberOfLines={2}>
                {nowTitle}
              </Text>
              {nowSubtitle ? (
                <Text style={styles.nowSub} numberOfLines={2}>
                  {nowSubtitle}
                </Text>
              ) : null}
            </View>
            <Icon name="chevron-right" size={18} color={C.focusInk2} />
          </Pressable>
          {canComplete ? (
            <Pressable
              style={({ pressed }) => [
                styles.completeBtn,
                completing && styles.completeBtnBusy,
                pressed && { opacity: 0.85 },
              ]}
              onPress={completing ? undefined : onComplete}
              disabled={completing}
              accessibilityRole="button"
              accessibilityLabel={`完成 ${nowTitle}`}
            >
              {completing ? (
                <ActivityIndicator size="small" color={C.focusBg} />
              ) : (
                <>
                  <Icon name="check" size={15} color={C.focusBg} />
                  <Text style={styles.completeText}>完成</Text>
                </>
              )}
            </Pressable>
          ) : null}
        </View>
      ) : (
        <Pressable
          style={({ pressed }) => [styles.emptyRow, pressed && { opacity: 0.85 }]}
          onPress={onPressAction}
          accessibilityRole="button"
          accessibilityLabel="补齐今天记录"
        >
          <View style={styles.actionIcon}>
            <Icon name="checkmark-circle" size={18} color={C.greenBright} />
          </View>
          <View style={styles.nowBody}>
            <Text style={styles.emptyLever}>今天的事都安排好了</Text>
            <Text style={styles.emptyTitle} numberOfLines={1}>
              {nowTitle}
            </Text>
          </View>
          <Icon name="chevron-right" size={18} color={C.focusInk2} />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    backgroundColor: C.focusBg,
    borderRadius: revaRadii.xl,
    padding: 20,
    gap: 16,
    ...revaShadows.focus,
  },
  // ── 支撑行(小环) ──
  supportRow: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  ringPlaceholder: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 6,
    borderColor: C.focusLine,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringPlaceholderText: { fontFamily: 'IBMPlexMono', fontSize: 10, color: C.focusInk2 },
  supportCopy: { flex: 1, minWidth: 0 },
  overline: {
    fontFamily: 'IBMPlexMono',
    fontSize: 10.5,
    letterSpacing: 0.9,
    color: C.focusInk2,
  },
  supportTitle: {
    fontFamily: 'Manrope',
    fontWeight: '700',
    fontSize: 16,
    color: C.greenBright,
    marginTop: 3,
  },
  supportNote: { fontSize: 12, lineHeight: 17, color: C.focusInk2, marginTop: 2 },
  // ── now-action 主体 ──
  nowBlock: {
    backgroundColor: C.focusBg2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    borderRadius: revaRadii.md,
    padding: 14,
    gap: 10,
  },
  nowHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 },
  nowLever: {
    flex: 1,
    minWidth: 0,
    fontFamily: 'IBMPlexMono',
    fontSize: 11,
    letterSpacing: 0.6,
    color: C.greenBright,
  },
  nowTime: { fontFamily: 'IBMPlexMono', fontSize: 13, fontWeight: '600', color: C.focusInk1 },
  nowMain: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  nowBody: { flex: 1, minWidth: 0 },
  nowTitle: { fontFamily: 'Manrope', fontWeight: '700', fontSize: 18, lineHeight: 24, color: C.focusInk1 },
  nowSub: { fontSize: 13, lineHeight: 19, color: C.focusInk2, marginTop: 4 },
  completeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: C.greenBright,
    borderRadius: revaRadii.sm,
    paddingVertical: 11,
  },
  completeBtnBusy: { opacity: 0.7 },
  completeText: { color: C.focusBg, fontWeight: '700', fontSize: 14 },
  // ── 空态行 ──
  emptyRow: {
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
  emptyLever: {
    fontFamily: 'IBMPlexMono',
    fontSize: 10.5,
    letterSpacing: 0.6,
    color: C.focusInk2,
    marginBottom: 2,
  },
  emptyTitle: { fontWeight: '700', fontSize: 15, color: C.focusInk1 },
});
