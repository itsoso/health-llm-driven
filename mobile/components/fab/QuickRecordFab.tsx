/**
 * QuickRecordFab —— 全局悬浮按钮 (Phase 2 P2-4, 2026-05-11 修).
 *
 * 短按 → 跳 /(tabs)/record 聚合记录页
 * 长按 → /voice-chat?intent=record (LLM 解析自然语言)
 *
 * 早期版本 (~30min 前) 弹 ActionSheet 列饮水/体重/血压/打卡 4 项, 但 mobile/app/
 * 没有这些独立路由 (全在 record.tsx 里), 全是死链 → 用户报"找不到页面". 已改最简版.
 */

import React from 'react';
import { Platform, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useTheme } from '../../hooks/useTheme';

export default function QuickRecordFab() {
  const router = useRouter();
  const { c } = useTheme();

  const onShortPress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    router.push('/(tabs)/record' as any);
  };

  const onLongPress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    router.push({ pathname: '/voice-chat' as any, params: { intent: 'record' } });
  };

  return (
    <TouchableOpacity
      accessibilityLabel="快速记录, 短按进记录页, 长按语音"
      accessibilityRole="button"
      activeOpacity={0.85}
      onPress={onShortPress}
      onLongPress={onLongPress}
      delayLongPress={350}
      style={[styles.fab, { backgroundColor: c.brand }]}
    >
      <Ionicons name="add" size={28} color="#fff" />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 20,
    bottom: Platform.OS === 'ios' ? 100 : 76,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
  },
});
