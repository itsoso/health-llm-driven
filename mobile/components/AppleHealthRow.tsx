/**
 * Apple Health 状态行 — 镜像 GarminStatusRow 风格
 *
 * 状态点:
 *  - 灰: 未授权 / 未同步过
 *  - 绿: 已同步 (有 lastSync 时间)
 *  - 黄: 同步中 (spinner)
 *  - 红: 错误
 *
 * 点击行为:
 *  - 未授权 → requestPermissions
 *  - 已授权 → 弹菜单 (近 7 天 / 全量回填)
 */
import React, { useState, useMemo, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import {
  isHealthKitAvailable,
  requestPermissions,
  syncRecentDays,
  backfillAll,
  type BackfillProgress,
} from '../services/appleHealth';
import { spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

interface Props {
  onSyncComplete?: () => void;
}

type State = 'idle' | 'syncing' | 'error';

export function AppleHealthRow({ onSyncComplete }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const [state, setState] = useState<State>('idle');
  const [authorized, setAuthorized] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<Date | null>(null);
  const [progress, setProgress] = useState<BackfillProgress | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const dotColor = (() => {
    if (state === 'syncing') return '#FF9F0A';
    if (state === 'error') return '#FF453A';
    if (authorized && lastSyncAt) return '#30D158';
    return c.labelTertiary;
  })();

  const statusText = (() => {
    if (state === 'syncing') {
      if (progress) {
        return `${progress.currentMonth} (${progress.monthsDone}/${progress.totalMonths})`;
      }
      return '同步中...';
    }
    if (state === 'error') return errorMsg ?? '错误';
    if (!isHealthKitAvailable()) return '仅 iOS 可用';
    if (!authorized) return '未授权';
    if (!lastSyncAt) return '从未同步';
    const mins = Math.floor((Date.now() - lastSyncAt.getTime()) / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return `${mins} 分钟前`;
    if (mins < 60 * 24) return `${Math.floor(mins / 60)} 小时前`;
    return `${Math.floor(mins / (60 * 24))} 天前`;
  })();

  const doRecentSync = useCallback(async () => {
    setState('syncing');
    setErrorMsg(null);
    setProgress(null);
    try {
      const { totalImported, errors, coverage } = await syncRecentDays(7);
      setLastSyncAt(new Date());
      setState('idle');
      // 列出每项本机读到几天 —— 某项为 0 = HealthKit 没给(权限没勾/设备没录),不是上传失败
      const cov = `本机读取(近${coverage.days}天): 步数${coverage.steps} 心率${coverage.hr} HRV${coverage.hrv} 血氧${coverage.spo2} 睡眠${coverage.sleep}`;
      const zeros: string[] = [];
      if (coverage.spo2 === 0) zeros.push('血氧');
      if (coverage.sleep === 0) zeros.push('睡眠');
      const hint = zeros.length > 0
        ? `\n\n${zeros.join('/')} 读到 0 天 —— 多半是「健康」App 没给本 App 这些读取权限,或手表未记录(部分地区 Apple Watch 血氧被停用)。请到 设置 > 健康 > 数据访问与设备 检查授权。`
        : '';
      Alert.alert(
        '同步完成',
        `已导入 ${totalImported} 天数据\n${cov}${errors.length > 0 ? `\n${errors.length} 条错误` : ''}${hint}`,
      );
      onSyncComplete?.();
    } catch (e: any) {
      setErrorMsg(e?.message ?? '同步失败');
      setState('error');
    }
  }, [onSyncComplete]);

  const doBackfill = useCallback(async () => {
    setState('syncing');
    setErrorMsg(null);
    setProgress(null);
    try {
      const { totalImported, errors } = await backfillAll((p) => setProgress(p));
      setLastSyncAt(new Date());
      setState('idle');
      Alert.alert(
        '回填完成',
        `共导入 ${totalImported} 条记录${errors.length > 0 ? `\n${errors.length} 条错误` : ''}`,
      );
      onSyncComplete?.();
    } catch (e: any) {
      setErrorMsg(e?.message ?? '回填失败');
      setState('error');
    }
  }, [onSyncComplete]);

  const handleAuthorize = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await requestPermissions();
      setAuthorized(true);
      // 授权后立即同步近 7 天
      doRecentSync();
    } catch (e: any) {
      setErrorMsg(e?.message ?? '授权失败');
      setState('error');
    }
  }, [doRecentSync]);

  const onPress = useCallback(() => {
    if (Platform.OS !== 'ios') {
      Alert.alert('不可用', 'Apple Health 仅在 iPhone 上可用');
      return;
    }
    if (state === 'syncing') return;
    if (!authorized) {
      handleAuthorize();
      return;
    }
    Alert.alert('Apple Health', '选择同步方式', [
      { text: '近 7 天', onPress: doRecentSync },
      {
        text: '全部历史',
        onPress: () =>
          Alert.alert(
            '全量回填',
            '将读取 HealthKit 中所有历史数据并上传,可能需要数分钟。',
            [
              { text: '取消', style: 'cancel' },
              { text: '开始', onPress: doBackfill },
            ],
          ),
      },
      { text: '取消', style: 'cancel' },
    ]);
  }, [authorized, state, handleAuthorize, doRecentSync, doBackfill]);

  return (
    <TouchableOpacity
      style={styles.settingRow}
      onPress={onPress}
      activeOpacity={0.6}
      disabled={state === 'syncing'}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="heart-outline" size={18} color={c.labelSecondary} />
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dotColor }} />
      </View>
      <Text style={styles.label}>Apple Health</Text>
      <Text style={[styles.value, state === 'error' && { color: '#FF453A' }]}>{statusText}</Text>
      {state === 'syncing' ? (
        <ActivityIndicator size="small" color={c.labelTertiary} />
      ) : (
        <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
      )}
    </TouchableOpacity>
  );
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    settingRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      paddingHorizontal: spacing.lg,
      paddingVertical: 14,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: c.separator,
    },
    label: { fontSize: 15, color: c.labelPrimary, flex: 1 },
    value: { fontSize: 14, color: c.labelTertiary },
  });
