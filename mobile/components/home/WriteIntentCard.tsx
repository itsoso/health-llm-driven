/**
 * WriteIntentCard —— 首页「待你确认」卡(Write 层 v0 的客户端表面)。
 *
 * Agent/规则提议「该替你写一件事」(v0:复查到点 → 提议建提醒)。用户一键【确认】才执行,
 * 或【忽略】。空态不渲染。确认 = OS 的第一个 syscall 被用户放行(冷启动先攒信任)。
 * 见 docs/design/health-os/architecture-lens.md。
 */
import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';

import { revaColors as C, revaRadii } from '../../constants/revaTheme';
import { Card, Icon, SectionLabel } from '../reva/RevaKit';
import {
  confirmWriteIntent,
  dismissWriteIntent,
  getWriteIntents,
  type WriteIntent,
} from '../../services/writeIntents';

export default function WriteIntentCard() {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);

  const q = useQuery({
    queryKey: ['write-intents'],
    queryFn: getWriteIntents,
    staleTime: 5 * 60 * 1000,
  });

  const confirm = useMutation({
    mutationFn: (id: number) => confirmWriteIntent(id),
    onMutate: (id) => setBusyId(id),
    onSuccess: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    },
    onSettled: () => {
      setBusyId(null);
      qc.invalidateQueries({ queryKey: ['write-intents'] });
    },
  });

  const dismiss = useMutation({
    mutationFn: (id: number) => dismissWriteIntent(id),
    onMutate: (id) => setBusyId(id),
    onSettled: () => {
      setBusyId(null);
      qc.invalidateQueries({ queryKey: ['write-intents'] });
    },
  });

  const items: WriteIntent[] = q.data ?? [];
  // 空态 / 出错 → 不渲染(不显示噪声卡)
  if (q.isError || items.length === 0) return null;

  // 依从打卡(每个药/补剂一条)会刷屏首页 → 折叠成 1 条摘要,点开逐条标记;
  // 其余高信号提议(复查到点 / 晨测 / 随访)仍逐条显示。
  const adherence = items.filter((it) => it.kind === 'adherence_nudge');
  const others = items.filter((it) => it.kind !== 'adherence_nudge');

  const renderRow = (it: WriteIntent, last: boolean) => {
    const busy = busyId === it.id;
    // 大多数提议用 sparkles;复购提醒(reorder_nudge)用补货箱图标,更直观。
    const iconName = it.kind === 'reorder_nudge' ? 'package' : 'sparkles';
    return (
      <View key={it.id} style={[styles.row, last && { borderBottomWidth: 0 }]}>
        <View style={styles.head}>
          <View style={styles.icon}>
            <Icon name={iconName} size={17} color={C.green600} />
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.title} numberOfLines={2}>{it.title}</Text>
            {it.description ? (
              <Text style={styles.desc} numberOfLines={2}>{it.description}</Text>
            ) : null}
          </View>
        </View>
        <View style={styles.actions}>
          {busy ? (
            <ActivityIndicator color={C.green500} style={{ marginRight: 8 }} />
          ) : (
            <>
              <Pressable
                style={({ pressed }) => [styles.confirmBtn, pressed && { opacity: 0.85 }]}
                onPress={() => confirm.mutate(it.id)}
                accessibilityRole="button"
                accessibilityLabel={`确认:${it.title}`}
              >
                <Icon name="check" size={15} color={C.greenOn} />
                <Text style={styles.confirmText}>确认</Text>
              </Pressable>
              <Pressable
                style={({ pressed }) => [styles.dismissBtn, pressed && { opacity: 0.6 }]}
                onPress={() => dismiss.mutate(it.id)}
                accessibilityRole="button"
                accessibilityLabel={`忽略:${it.title}`}
              >
                <Text style={styles.dismissText}>忽略</Text>
              </Pressable>
            </>
          )}
        </View>
      </View>
    );
  };

  const hasAdherence = adherence.length > 0;

  return (
    <View>
      <SectionLabel>待你确认</SectionLabel>
      <Card pad={0}>
        {others.map((it, i) => renderRow(it, !hasAdherence && i === others.length - 1))}
        {hasAdherence ? (
          <>
            <Pressable
              style={[styles.row, !expanded && { borderBottomWidth: 0 }]}
              onPress={() => setExpanded((v) => !v)}
              accessibilityRole="button"
              accessibilityLabel={`今日还有 ${adherence.length} 项补剂或药未记录,点击${expanded ? '收起' : '展开逐条标记'}`}
            >
              <View style={styles.head}>
                <View style={styles.icon}>
                  <Icon name="sparkles" size={17} color={C.green600} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.title} numberOfLines={1}>
                    今日还有 {adherence.length} 项补剂/药未记录
                  </Text>
                  <Text style={styles.desc} numberOfLines={1}>
                    {expanded ? '点击收起' : '已服的点开逐条「确认」;没服忽略'}
                  </Text>
                </View>
                <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color={C.ink3} />
              </View>
            </Pressable>
            {expanded
              ? adherence.map((it, i) => renderRow(it, i === adherence.length - 1))
              : null}
          </>
        ) : null}
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
    gap: 10,
  },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: 11 },
  icon: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: C.green50,
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 14.5, fontWeight: '600', color: C.ink1 },
  desc: { fontSize: 12.5, color: C.ink3, marginTop: 2 },
  actions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 10 },
  confirmBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: C.green500, borderRadius: revaRadii.pill,
    paddingHorizontal: 16, paddingVertical: 8,
  },
  confirmText: { color: C.greenOn, fontSize: 13.5, fontWeight: '600' },
  dismissBtn: { paddingHorizontal: 12, paddingVertical: 8 },
  dismissText: { color: C.ink3, fontSize: 13.5 },
});
