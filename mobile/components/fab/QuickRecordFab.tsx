/**
 * QuickRecordFab —— 全局悬浮按钮 (Phase 2 P2-4).
 *
 * 短按 → 弹 ActionSheet 列出 4 项高频 (饮水 / 体重 / 血压 / 打卡) + "更多"
 * 长按 → 直接跳 voice-chat (LLM 解析自然语言录入)
 *
 * 用法: 在 Tab Layout 里 <QuickRecordFab /> 套在 Tabs 外面 (绝对定位)
 */

import React, { useState } from 'react';
import { ActionSheetIOS, Platform, StyleSheet, TouchableOpacity, View, Pressable, Modal, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useTheme } from '../../hooks/useTheme';

const QUICK_OPTIONS = [
  { key: 'water', label: '饮水', icon: 'water-outline', path: '/water' },
  { key: 'weight', label: '体重', icon: 'fitness-outline', path: '/weight' },
  { key: 'bp', label: '血压', icon: 'heart-outline', path: '/blood-pressure' },
  { key: 'checkin', label: '打卡', icon: 'checkmark-circle-outline', path: '/checkin' },
] as const;

type QuickKey = (typeof QUICK_OPTIONS)[number]['key'];

export default function QuickRecordFab() {
  const router = useRouter();
  const { c } = useTheme();
  const [androidSheetOpen, setAndroidSheetOpen] = useState(false);

  const open = (path: string) => {
    Haptics.selectionAsync().catch(() => {});
    router.push(path as any);
  };

  const showSheet = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});

    const options = [...QUICK_OPTIONS.map(o => o.label), '更多记录', '取消'];
    const cancelIndex = options.length - 1;
    const moreIndex = options.length - 2;

    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          options,
          cancelButtonIndex: cancelIndex,
          title: '快速记录',
        },
        (idx) => {
          if (idx === cancelIndex || idx === undefined) return;
          if (idx === moreIndex) {
            router.push('/record' as any);
            return;
          }
          open(QUICK_OPTIONS[idx].path);
        },
      );
    } else {
      setAndroidSheetOpen(true);
    }
  };

  const longPressVoice = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    router.push({
      pathname: '/voice-chat' as any,
      params: { intent: 'record' },
    });
  };

  return (
    <>
      <TouchableOpacity
        accessibilityLabel="快速记录, 短按选项, 长按语音"
        accessibilityRole="button"
        activeOpacity={0.85}
        onPress={showSheet}
        onLongPress={longPressVoice}
        delayLongPress={350}
        style={[styles.fab, { backgroundColor: c.brand }]}
      >
        <Ionicons name="add" size={28} color="#fff" />
      </TouchableOpacity>

      {/* Android 自实现 sheet (ActionSheetIOS 仅 iOS) */}
      {Platform.OS === 'android' && (
        <Modal
          transparent
          visible={androidSheetOpen}
          animationType="slide"
          onRequestClose={() => setAndroidSheetOpen(false)}
        >
          <Pressable style={styles.androidScrim} onPress={() => setAndroidSheetOpen(false)} />
          <View style={[styles.androidSheet, { backgroundColor: c.bgCard }]}>
            <Text style={[styles.androidTitle, { color: c.labelTertiary }]}>快速记录</Text>
            {QUICK_OPTIONS.map(o => (
              <TouchableOpacity
                key={o.key}
                style={styles.androidRow}
                onPress={() => {
                  setAndroidSheetOpen(false);
                  open(o.path);
                }}
              >
                <Ionicons name={o.icon as any} size={20} color={c.brand} />
                <Text style={[styles.androidRowText, { color: c.labelPrimary }]}>{o.label}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity
              style={styles.androidRow}
              onPress={() => {
                setAndroidSheetOpen(false);
                router.push('/record' as any);
              }}
            >
              <Ionicons name="ellipsis-horizontal" size={20} color={c.labelTertiary} />
              <Text style={[styles.androidRowText, { color: c.labelPrimary }]}>更多记录</Text>
            </TouchableOpacity>
          </View>
        </Modal>
      )}
    </>
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
  androidScrim: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  androidSheet: {
    paddingTop: 16,
    paddingBottom: 32,
    paddingHorizontal: 12,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
  },
  androidTitle: { textAlign: 'center', fontSize: 12, fontWeight: '600', marginBottom: 8 },
  androidRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingVertical: 14,
    paddingHorizontal: 8,
  },
  androidRowText: { fontSize: 16, fontWeight: '500' },
});
