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

  return (
    <View>
      <SectionLabel>待你确认</SectionLabel>
      <Card pad={0}>
        {items.map((it, i) => {
          const busy = busyId === it.id;
          const last = i === items.length - 1;
          return (
            <View key={it.id} style={[styles.row, last && { borderBottomWidth: 0 }]}>
              <View style={styles.head}>
                <View style={styles.icon}>
                  <Icon name="sparkles" size={17} color={C.green600} />
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
        })}
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
