import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useQueryClient } from '@tanstack/react-query';
import { recordWater, deleteWater } from '../../services/records';
import { invalidateRecordMutation } from '../../applib/queryKeys';
import { useToast } from '../../hooks/useToast';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

// 一键饮水量 (ml)。record.tsx 一键饮水复用同一 recordWater/deleteWater 出口 (R4 白名单内).
const WATER_QUICK_ML = 250;
// 撤销条自动消失时长 (ms)。
const WATER_UNDO_TIMEOUT_MS = 5000;

// 记录托盘：5 个快捷入口。
//   拍照记餐 → /diet?capture=photo（record.tsx「拍一下」同路由）
//   饮水 → 一键 +250ml (乐观写 + 撤销), 非路由; 长按/更多 仍进完整记录屏
//   体重 → /body-measurements（record.tsx「体重腰围」同路由）
//   用药 → /medications（用药管理屏）
//   更多 → /(tabs)/record（完整记录屏）
type TrayEntry = {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  a11y: string;
};

const RECORD_TRAY: TrayEntry[] = [
  { key: 'diet', label: '拍照记餐', icon: 'camera-outline', route: '/diet?capture=photo', a11y: '拍照记录餐食' },
  { key: 'water', label: '饮水', icon: 'water-outline', route: '/(tabs)/record', a11y: '记录饮水' },
  { key: 'weight', label: '体重', icon: 'body-outline', route: '/body-measurements', a11y: '记录体重' },
  { key: 'medication', label: '用药', icon: 'medical-outline', route: '/medications', a11y: '记录用药' },
  { key: 'more', label: '更多', icon: 'ellipsis-horizontal', route: '/(tabs)/record', a11y: '更多记录方式' },
];

/**
 * 聊天底部记录托盘。
 * 饮水项走一键乐观写 (+250ml) + 内联撤销条 (~5s 自动消失);
 * 复用 services/records 的 recordWater/deleteWater (与 record.tsx 同一出口)。
 * 失败 fail-loud: haptic error + toast, 不伪造成功。
 */
export default function RecordTray() {
  const qc = useQueryClient();
  const toast = useToast();
  // 撤销条状态: 有值 = 刚记了一笔饮水, 展示 "+250ml ✓ 撤销"; 无值 = 隐藏.
  const [waterUndo, setWaterUndo] = useState<{ id: number; amount: number } | null>(null);
  const [waterLogging, setWaterLogging] = useState(false);
  const undoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearUndoTimer = useCallback(() => {
    if (undoTimerRef.current) {
      clearTimeout(undoTimerRef.current);
      undoTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => clearUndoTimer(), [clearUndoTimer]);

  const handleWaterQuickLog = useCallback(async () => {
    if (waterLogging) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setWaterLogging(true);
    try {
      const rec = await recordWater(WATER_QUICK_ML);
      await invalidateRecordMutation(qc);
      clearUndoTimer();
      setWaterUndo({ id: rec.id, amount: WATER_QUICK_ML });
      undoTimerRef.current = setTimeout(() => setWaterUndo(null), WATER_UNDO_TIMEOUT_MS);
    } catch {
      // fail-loud: 让用户知道没记上, 不留下假成功状态.
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      toast.show('饮水记录失败，请重试', 'error');
    } finally {
      setWaterLogging(false);
    }
  }, [waterLogging, qc, clearUndoTimer, toast]);

  const handleUndoWater = useCallback(async () => {
    const pending = waterUndo;
    if (!pending) return;
    clearUndoTimer();
    setWaterUndo(null);
    Haptics.selectionAsync().catch(() => {});
    try {
      await deleteWater(pending.id);
      await invalidateRecordMutation(qc);
    } catch {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      toast.show('撤销失败，请到记录页删除', 'error');
    }
  }, [waterUndo, clearUndoTimer, qc, toast]);

  const handleEntryPress = useCallback((entry: TrayEntry) => {
    if (entry.key === 'water') {
      void handleWaterQuickLog();
      return;
    }
    // 栈路由必须 push:navigate 会复用栈里已有实例(diet 的 captureConsumedRef 已耗尽
    // + capture 参数 effect 不重发)→ 落页不开相机(founder 真机实测 bug)。
    // tab 路由 ('/(tabs)/…') 保持 navigate(tab 不该叠实例)。
    if (entry.route.startsWith('/(tabs)')) {
      router.navigate(entry.route as any);
    } else {
      router.push(entry.route as any);
    }
  }, [handleWaterQuickLog]);

  return (
    <View>
      {waterUndo ? (
        <View style={styles.undoBar} accessibilityRole="alert">
          <Ionicons name="checkmark-circle" size={15} color={C.green500} />
          <Text maxFontSizeMultiplier={1.2} style={txt.undoText}>
            +{waterUndo.amount}ml 已记录
          </Text>
          <TouchableOpacity
            onPress={handleUndoWater}
            hitSlop={8}
            style={styles.undoBtn}
            accessibilityRole="button"
            accessibilityLabel="撤销饮水记录"
          >
            <Text maxFontSizeMultiplier={1.2} style={txt.undoBtn}>撤销</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      <View style={styles.recordTray} accessibilityRole="toolbar">
        {RECORD_TRAY.map((entry) => (
          <TouchableOpacity
            key={entry.key}
            style={styles.recordTrayItem}
            onPress={() => handleEntryPress(entry)}
            // 饮水长按仍进完整记录屏 (自定义量/饮品类型).
            onLongPress={entry.key === 'water' ? () => router.navigate(entry.route as any) : undefined}
            activeOpacity={0.72}
            accessibilityRole="button"
            accessibilityLabel={entry.a11y}
            accessibilityState={entry.key === 'water' ? { busy: waterLogging } : undefined}
          >
            <View style={styles.recordTrayIcon}>
              <Ionicons name={entry.icon} size={17} color={C.green600} />
            </View>
            <Text maxFontSizeMultiplier={1.15} style={txt.recordTrayLabel} numberOfLines={1}>
              {entry.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  undoBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: revaSpacing.s4,
    marginBottom: 6,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 8,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    ...revaShadows.sm,
  },
  undoBtn: {
    marginLeft: 'auto',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  recordTray: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 4,
    marginHorizontal: revaSpacing.s4,
    marginBottom: 6,
    paddingHorizontal: 4,
    paddingVertical: 8,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  recordTrayItem: {
    flex: 1,
    alignItems: 'center',
    gap: 4,
    paddingVertical: 2,
  },
  recordTrayIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
});

const txt = {
  recordTrayLabel: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700', color: C.ink2 } as TextStyle,
  undoText: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.green700 } as TextStyle,
  undoBtn: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '800', color: C.green500 } as TextStyle,
};
