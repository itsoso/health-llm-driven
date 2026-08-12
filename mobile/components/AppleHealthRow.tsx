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
import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import {
  isHealthKitAvailable,
  requestPermissions,
  syncRecentDays,
  backfillAll,
  getHealthKitAuthorized,
  persistHealthKitAuthorized,
  getHealthKitLastSync,
  persistHealthKitLastSync,
  type BackfillProgress,
} from '../services/appleHealth';
import { ensureHealthKitServerConsent } from '../services/dataConnections';
import {
  revaColors as C,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';

interface Props {
  onSyncComplete?: () => void;
}

type State = 'idle' | 'syncing' | 'error';

export function AppleHealthRow({ onSyncComplete }: Props) {
  const [state, setState] = useState<State>('idle');
  const [authorized, setAuthorized] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<Date | null>(null);
  const [progress, setProgress] = useState<BackfillProgress | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // 挂载时 rehydrate 持久化的授权状态 + 最近同步时间。
  // 修复"授权后仍显示未授权":authorized 本是纯本地 state,导航离开/冷启即丢,
  // 而 iOS 不暴露 read 授权状态无法直接查 → 用持久化标记还原。
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [auth, lastTs] = await Promise.all([
        getHealthKitAuthorized(),
        getHealthKitLastSync(),
      ]);
      if (cancelled) return;
      if (auth) setAuthorized(true);
      if (lastTs) setLastSyncAt(new Date(lastTs));
    })();
    return () => { cancelled = true; };
  }, []);

  const dotColor = (() => {
    if (state === 'syncing') return revaSemantic.caution.fg;
    if (state === 'error') return revaSemantic.risk.fg;
    if (authorized && lastSyncAt) return revaSemantic.normal.fg;
    return C.ink3;
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
      await ensureHealthKitServerConsent();
      const { totalImported, errors, coverage } = await syncRecentDays(7);
      const now = new Date();
      setLastSyncAt(now);
      setState('idle');
      // 同步成功即说明已授权(initHealthKit 通过);读到数据更是铁证 → 持久化授权 + 时间
      const readAny = coverage.steps + coverage.hr + coverage.hrv + coverage.spo2 + coverage.sleep > 0;
      if (readAny || totalImported > 0) setAuthorized(true);
      persistHealthKitAuthorized();
      persistHealthKitLastSync(now.getTime());
      // 列出每项本机读到几天 —— 某项为 0 = HealthKit 没给(权限没勾/设备没录),不是上传失败
      const cov = `本机读取(近${coverage.days}天): 步数${coverage.steps} 心率${coverage.hr} HRV${coverage.hrv} 血氧${coverage.spo2} 睡眠${coverage.sleep}`;
      const zeros: string[] = [];
      if (coverage.spo2 === 0) zeros.push('血氧');
      if (coverage.sleep === 0) zeros.push('睡眠');
      const hint = zeros.length > 0
        ? `\n\n${zeros.join('/')} 读到 0 天 —— 多半是「健康」App 没给本 App 这些读取权限,或手表未记录(部分地区 Apple Watch 血氧被停用)。请到 设置 > 健康 > 数据访问与设备 检查授权。`
        : '';
      // 有未识别来源(如 RingConn 在健康里的名字没收录)→ 显示真名,反馈后补映射即可
      const unknownHint = coverage.unknownSources.length > 0
        ? `\n\n⚠️ 检测到未识别的数据来源:「${coverage.unknownSources.join('」「')}」—— 请把这个名字反馈给开发者,加入映射后该设备将被单独识别。`
        : '';
      Alert.alert(
        '同步完成',
        `已导入 ${totalImported} 天数据\n${cov}${errors.length > 0 ? `\n${errors.length} 条错误` : ''}${hint}${unknownHint}`,
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
      await ensureHealthKitServerConsent();
      const { totalImported, errors } = await backfillAll((p) => setProgress(p));
      const now = new Date();
      setLastSyncAt(now);
      setState('idle');
      setAuthorized(true);
      persistHealthKitAuthorized();
      persistHealthKitLastSync(now.getTime());
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
      await ensureHealthKitServerConsent();
      setAuthorized(true);
      persistHealthKitAuthorized();  // 持久化 → 重挂载/冷启不再回退"未授权"
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
      accessibilityRole="button"
      accessibilityLabel={`Apple Health，${statusText}`}
      accessibilityState={{ disabled: state === 'syncing' }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="heart-outline" size={18} color={C.ink2} />
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dotColor }} />
      </View>
      <Text style={styles.label}>Apple Health</Text>
      <Text numberOfLines={1} style={[styles.value, state === 'error' && { color: revaSemantic.risk.fg }]}>{statusText}</Text>
      {state === 'syncing' ? (
        <ActivityIndicator size="small" color={C.ink3} />
      ) : (
        <Ionicons name="chevron-forward" size={14} color={C.ink3} />
      )}
    </TouchableOpacity>
  );
}

// Reva 设计语言:暖白 surface 行 / ink 文字 / 三步临床语义状态点。镜像 settings.tsx settingRow。
const styles = StyleSheet.create({
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: 52,
    paddingHorizontal: revaSpacing.s5,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  label: { fontFamily: revaFonts.sans, fontSize: 15, color: C.ink1, flex: 1 },
  value: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3, flexShrink: 1, maxWidth: '42%' },
});
