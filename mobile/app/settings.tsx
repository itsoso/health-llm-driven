import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, Alert, ScrollView, Switch } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import api from '../services/api';
import { getAccountDeletionRequest, requestAccountDeletion } from '../services/auth';
import { connectionStatusSummary, fetchDataConnections } from '../services/dataConnections';
import { useAuth } from '../hooks/useAuth';
import { useBiometricLock } from '../hooks/useBiometricLock';
import { useAppUpdate } from '../hooks/useAppUpdate';
import { invalidateHealthSnapshot, queryKeys } from '../applib/queryKeys';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import { APP_DISPLAY_NAME } from '../constants/brand';
import { AppleHealthRow } from '../components/AppleHealthRow';
import { getReleaseCapabilities } from '../config/releaseCapabilities';
import { getNativeVersionLabel } from '../services/appUpdate';

export default function SettingsScreen() {
  const router = useRouter();
  const { logout, user, isAuthenticated } = useAuth();
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const [deletionRequesting, setDeletionRequesting] = useState(false);
  const releaseCapabilities = getReleaseCapabilities();
  const { status: updateStatus, checkNow: checkForUpdate, applyUpdate } = useAppUpdate();
  const { isEnabled: bioEnabled, isSupported: bioSupported, toggleEnabled: toggleBio } = useBiometricLock(isAuthenticated);

  const { data: profile } = useQuery({ queryKey: queryKeys.profile, queryFn: () => api.get('/profile/me').then(r => r.data), staleTime: 600_000 });
  // 2026-05-16: 之前一直显示老 manual_city 是因为没看 use_manual_location flag —
  // GPS 自动同步会把 flag 切 false 但不清旧 manual_city, 导致用户在杭州但显示"北京".
  // 正确优先级: 手动模式开启 → manual; 否则用 detected (region 比 city 友好,
  // qweather 给的 city 常是区/县名 "海淀"/"余杭", region 是"北京市"/"杭州市").
  const city = useMemo(() => {
    const useManual = profile?.use_manual_location === true;
    if (useManual && profile?.manual_location?.city) return profile.manual_location.city;
    const detected = profile?.detected_location;
    if (detected?.region) return detected.region.replace(/[市省]$/, '');
    if (detected?.city) return detected.city;
    if (profile?.city) return profile.city;
    return '未设置';
  }, [profile]);

  const { data: garminStatus, refetch: refetchGarminStatus } = useQuery({
    queryKey: ['garminStatus'],
    queryFn: () => api.get('/data-collection/garmin/me/credential-status').then(r => r.data),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
  const { data: dataConnections } = useQuery({
    queryKey: ['data-connections'],
    queryFn: fetchDataConnections,
    staleTime: 120_000,
  });
  const { data: deletionRequest } = useQuery({
    queryKey: ['accountDeletionRequest'],
    queryFn: getAccountDeletionRequest,
    staleTime: 60_000,
  });

  const syncGarmin = async () => {
    setSyncing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await api.post('/data-collection/garmin/me/sync?days=1');
      Alert.alert('同步成功', 'Garmin 数据已更新');
      await invalidateHealthSnapshot(qc);
      refetchGarminStatus();
    } catch {
      Alert.alert('同步失败', '请稍后再试');
    } finally {
      setSyncing(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('退出登录', '确定要退出吗？', [
      { text: '取消', style: 'cancel' },
      { text: '退出', style: 'destructive', onPress: () => logout() },
    ]);
  };

  const handleRequestAccountDeletion = () => {
    if (deletionRequest?.status === 'requested' || deletionRequest?.status === 'processing') {
      Alert.alert(
        '删除请求处理中',
        `请求编号 #${deletionRequest.request_id ?? '-'}，当前状态：${deletionRequest.status === 'processing' ? '人工处理中' : '已提交'}。通常会在 7 天内完成。`,
        [{ text: '知道了' }],
      );
      return;
    }
    if (deletionRequest?.status === 'completed') {
      Alert.alert(
        '删除已完成',
        `请求编号 #${deletionRequest.request_id ?? '-'} 已完成。当前登录会话失效后，此账号将无法继续登录。`,
        [{ text: '知道了' }],
      );
      return;
    }
    if (deletionRequest?.status === 'rejected') {
      Alert.alert(
        '删除请求需要处理',
        `请求编号 #${deletionRequest.request_id ?? '-'} 未能完成，请联系 support@executor.life。`,
        [{ text: '知道了' }],
      );
      return;
    }
    Alert.alert(
      '删除账号与数据',
      '提交后我们会在 7 天内处理账号、健康数据和设备连接删除请求。你可以留在“账号与隐私”查看进度。完成后账号将无法继续登录。',
      [
        { text: '取消', style: 'cancel' },
        {
          text: deletionRequesting ? '提交中...' : '确认提交',
          style: 'destructive',
          onPress: async () => {
            if (deletionRequesting) return;
            setDeletionRequesting(true);
            try {
              const result = await requestAccountDeletion();
              Alert.alert(
                '删除请求已提交',
                result.message || `请求 #${result.request_id ?? '-'} 已记录,预计 ${result.estimated_completion_days ?? 7} 天内完成处理。`,
                [{ text: '知道了' }],
              );
              await qc.invalidateQueries({ queryKey: ['accountDeletionRequest'] });
            } catch {
              Alert.alert('提交失败', '删除请求没有保存成功,请稍后重试。');
            } finally {
              setDeletionRequesting(false);
            }
          },
        },
      ],
    );
  };

  const showSiriInfo = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    Alert.alert(
      'Siri 语音记录',
      `登录后即可使用 Siri 语音记录健康数据：\n\n• "嘿 Siri，用 ${APP_DISPLAY_NAME} 记录喝了500ml水"\n• "嘿 Siri，告诉 ${APP_DISPLAY_NAME} 吃了一个苹果"\n\n首次使用时 Siri 会请求授权。`,
      [{ text: '知道了' }],
    );
  };

  const handleCheckForUpdate = async () => {
    if (updateStatus === 'checking' || updateStatus === 'downloading' || updateStatus === 'applying') return;
    if (updateStatus === 'ready') {
      await applyUpdate();
      return;
    }

    const result = await checkForUpdate({ force: true });
    if (result === 'ready') {
      Alert.alert('更新已准备好', '新版本已经下载，是否现在重新打开应用？', [
        { text: '稍后', style: 'cancel' },
        { text: '立即更新', onPress: () => void applyUpdate() },
      ]);
    } else if (result === 'current') {
      Alert.alert('已是最新版本', '当前没有需要下载的更新。');
    } else if (result === 'disabled') {
      Alert.alert('当前无法在线更新', '开发版本或本地调试模式请通过 USB 或开发服务器更新。');
    } else if (result === 'failed') {
      Alert.alert('检查失败', '网络或更新服务暂时不可用，请稍后重试。');
    }
  };

  const updateStatusLabel = (() => {
    if (updateStatus === 'checking') return '检查中...';
    if (updateStatus === 'downloading') return '下载中...';
    if (updateStatus === 'ready') return '立即应用';
    if (updateStatus === 'applying') return '更新中...';
    if (updateStatus === 'failed') return '重新检查';
    return '手动检查';
  })();

  // 同一组件被 /settings (stack) 和 (tabs)/me 共用. tab 模式下没"上一级"
  // 可回, 隐藏返回按钮; stack 模式 (env card 齿轮 push) 保留.
  const canGoBack = router.canGoBack();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        {canGoBack ? (
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} accessibilityRole="button" accessibilityLabel="返回">
            <Ionicons name="chevron-back" size={24} color={C.ink1} />
          </TouchableOpacity>
        ) : (
          // Agent-native shell: 「我」tab 无底部 Tab Bar, 左上给回主屏(小巴)出口。
          <TouchableOpacity
            onPress={() => router.navigate('/(tabs)/chat')}
            style={styles.backBtn}
            accessibilityRole="button"
            accessibilityLabel="返回小巴"
            accessibilityHint="回到与小巴的对话主屏"
          >
            <Ionicons name="chevron-back" size={24} color={C.green500} />
          </TouchableOpacity>
        )}
        <Text style={txt.title}>{canGoBack ? '设置' : '我'}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Profile */}
        <View style={styles.card}>
          <View style={styles.profileRow}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={24} color={C.green500} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.name}>{user?.username || (user as any)?.name || '用户'}</Text>
              <Text style={txt.email}>{user?.email || ''}</Text>
            </View>
          </View>
        </View>

        <Text style={txt.sectionLabel}>数据连接</Text>
        <View style={styles.card}>
          <LocationSettingsRow city={city} useManual={profile?.use_manual_location === true}
            onPress={() => router.push('/location' as any)} />
          <GarminStatusRow status={garminStatus} syncing={syncing} onSync={syncGarmin} />
          <AppleHealthRow onSyncComplete={() => invalidateHealthSnapshot(qc)} />
          <SettingRow icon="key-outline" label="数据连接与授权"
            value={connectionStatusSummary(dataConnections)}
            onPress={() => router.push('/data-connections' as any)} />
          <SettingRow icon="git-compare-outline" label="数据来源"
            onPress={() => router.push('/device-sources' as any)} />
        </View>

        <Text style={txt.sectionLabel}>健康档案</Text>
        <View style={styles.card}>
          <SettingRow icon="document-text-outline" label="化验记录"
            onPress={() => router.push('/medical-exams' as any)} />
          <SettingRow icon="cloud-upload-outline" label="导入体检报告"
            onPress={() => router.push('/import' as any)} />
          <SettingRow icon="medkit-outline" label="用药管理"
            onPress={() => router.push('/medications' as any)} />
          <SettingRow icon="cube-outline" label="补剂库存"
            onPress={() => router.push('/supplement-inventory' as any)} />
          <SettingRow icon="cellular-outline" label="我的基因"
            onPress={() => router.push('/genetic-report' as any)} />
          <SettingRow icon="flag-outline" label="健康目标"
            onPress={() => router.push('/goals' as any)} />
        </View>

        <Text style={txt.sectionLabel}>复盘与计划</Text>
        <View style={styles.card}>
          <SettingRow icon="today-outline" label="今日议程"
            onPress={() => router.push('/agenda' as any)} />
          <SettingRow icon="time-outline" label="今日时间轴 · 工作时间"
            onPress={() => router.push('/day-schedule' as any)} />
          <SettingRow icon="calendar-outline" label="日历 · 日程 + 多源管理"
            onPress={() => router.push('/calendar' as any)} />
          <SettingRow icon="analytics-outline" label="健康分析"
            value="进展 / 代谢 / 趋势"
            onPress={() => router.push('/insights' as any)} />
          <SettingRow icon="medical-outline" label="医生回路"
            onPress={() => router.push('/doctor-loop' as any)} />
        </View>

        <Text style={txt.sectionLabel}>通知与安全</Text>
        <View style={styles.card}>
          <SettingRow icon="warning-outline" label="安全告警"
            onPress={() => router.push('/alerts' as any)} />
          <SettingRow icon="notifications-outline" label="推送通知"
            onPress={() => router.push('/notification-settings' as any)} />
          <SettingRow icon="eye-outline" label="科学用眼 (20-20-20)"
            onPress={() => router.push('/eye-care' as any)} />
          <SettingRow icon="volume-high-outline" label="语音风格"
            onPress={() => router.push('/voice-style' as any)} />
          {releaseCapabilities.siri ? (
            <SettingRow icon="mic-outline" label="Siri 语音记录"
              value="使用说明"
              onPress={showSiriInfo} />
          ) : null}
          {bioSupported && (
            <View style={styles.settingRow}>
              <Ionicons name="finger-print-outline" size={18} color={C.ink2} />
              <Text style={txt.settingLabel}>Face ID 锁定</Text>
              <Switch value={bioEnabled} onValueChange={toggleBio}
                trackColor={{ false: C.line, true: C.green500 }} thumbColor="#fff" />
            </View>
          )}
        </View>

        <Text style={txt.sectionLabel}>账号与隐私</Text>
        <View style={styles.card}>
          <SettingRow icon="key-outline" label="账号安全"
            value={(user as any)?.has_password ? '修改密码' : '设置密码'}
            onPress={() => router.push('/account-security' as any)} />
          <SettingRow icon="shield-checkmark-outline" label="隐私政策"
            onPress={() => router.push('/privacy-policy' as any)} />
          <SettingRow icon="people-outline" label="家庭健康"
            onPress={() => router.push('/family' as any)} />
          <SettingRow icon="reader-outline" label="健康日记"
            onPress={() => router.push('/journal' as any)} />
          <SettingRow icon="document-text-outline" label="硬性指令"
            onPress={() => router.push('/directives' as any)} />
          <SettingRow icon="pulse-outline" label="数据自检"
            onPress={() => router.push('/data-integrity' as any)} />
          <SettingRow icon="trash-outline" label="删除账号与数据"
            value={deletionRequesting
              ? '提交中...'
              : deletionRequest?.status === 'processing'
                ? '处理中'
                : deletionRequest?.status === 'requested'
                  ? '已提交'
                  : deletionRequest?.status === 'completed'
                    ? '已完成'
                    : deletionRequest?.status === 'rejected'
                      ? '需联系支持'
                  : '请求删除'}
            destructive
            onPress={handleRequestAccountDeletion} />
        </View>

        {releaseCapabilities.advancedSettings ? (
          <>
          <Text style={txt.sectionLabel}>高级与实验</Text>
          <View style={styles.card}>
          <SettingRow icon="sparkles-outline" label="AI 模型"
            onPress={() => router.push('/llm-preference' as any)} />
          <SettingRow icon="person-outline" label="AI 教练风格"
            onPress={() => router.push('/coach-persona' as any)} />
          <SettingRow icon="sparkles-outline" label="AI 对我的画像"
            onPress={() => router.push('/ai-profile' as any)} />
          <SettingRow icon="bookmark-outline" label="AI 关于你的笔记"
            onPress={() => router.push('/memory' as any)} />
          <SettingRow icon="medical-outline" label="健康咨询"
            onPress={() => router.push('/consultations' as any)} />
          <SettingRow icon="ribbon-outline" label="处方查原研药"
            onPress={() => router.push('/prescription-scan' as any)} />
          <SettingRow icon="barbell-outline" label="运动记录"
            onPress={() => router.push('/workout-list' as any)} />
          <SettingRow icon="list-outline" label="多药梳理"
            onPress={() => router.push('/deprescribing' as any)} />
          <SettingRow icon="people-circle-outline" label="社会连接自评"
            onPress={() => router.push('/connection-checkin' as any)} />
          <SettingRow icon="time-outline" label="健康事件流"
            onPress={() => router.push('/timeline' as any)} />
          {releaseCapabilities.rokid ? (
            <>
              <SettingRow icon="scan-outline" label="Rokid 眼镜健康模式"
                onPress={() => router.push('/rokid-health' as any)} />
              <SettingRow icon="body-outline" label="Rokid 俯卧撑计数"
                onPress={() => router.push('/rokid-pushup-coach' as any)} />
              <SettingRow icon="shield-checkmark-outline" label="Rokid 自检"
                onPress={() => router.push('/rokid-diagnostics' as any)} />
            </>
          ) : null}
          </View>
          </>
        ) : null}

        <Text style={txt.sectionLabel}>应用</Text>
        <View style={styles.card}>
          <SettingRow icon="cloud-download-outline" label="检查更新"
            value={updateStatusLabel}
            onPress={() => void handleCheckForUpdate()} />
          <SettingRow icon="information-circle-outline" label="版本" value={getNativeVersionLabel()} />
          {releaseCapabilities.advancedSettings ? (
            <SettingRow icon="bug-outline" label="App 诊断"
              onPress={() => router.push('/app-diagnostics' as any)} />
          ) : null}
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout} activeOpacity={0.7}>
          <Text style={txt.logoutText}>退出登录</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function SettingRow({
  icon,
  label,
  value,
  onPress,
  destructive = false,
}: {
  icon: any;
  label: string;
  value?: string;
  onPress?: () => void;
  destructive?: boolean;
}) {
  const Wrapper = onPress ? TouchableOpacity : View;
  const color = destructive ? revaSemantic.risk.fg : C.ink2;
  return (
    <Wrapper
      style={styles.settingRow}
      onPress={onPress}
      activeOpacity={0.6}
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={onPress ? label : undefined}
      accessibilityValue={onPress && value ? { text: value } : undefined}
    >
      <Ionicons name={icon} size={18} color={color} />
      <Text style={[txt.settingLabel, destructive && { color }]}>{label}</Text>
      <Text style={[txt.settingValue, destructive && { color }]}>{value || ''}</Text>
      {onPress && <Ionicons name="chevron-forward" size={14} color={C.ink3} />}
    </Wrapper>
  );
}

function LocationSettingsRow({ city, useManual, onPress }: { city: string; useManual: boolean; onPress: () => void }) {
  const mode = useManual ? '手动城市' : 'GPS 自动';

  return (
    <TouchableOpacity style={styles.locationRow} onPress={onPress} activeOpacity={0.72}
      accessibilityRole="button"
      accessibilityLabel={`GPS / 城市定位, 当前城市 ${city}, ${mode}`}>
      <View style={styles.locationIconBox}>
        <Ionicons name="navigate-outline" size={18} color={C.green500} />
      </View>
      <View style={styles.locationCopy}>
        <Text style={txt.locationTitle} numberOfLines={1}>GPS / 城市定位</Text>
        <Text style={txt.locationHint}>用于天气 / 空气质量 / 户外建议</Text>
      </View>
      <View style={styles.locationStatus}>
        <Text style={txt.locationCity} numberOfLines={1}>{city}</Text>
        <Text style={txt.locationMode} numberOfLines={1}>{mode}</Text>
      </View>
      <Ionicons name="chevron-forward" size={14} color={C.ink3} />
    </TouchableOpacity>
  );
}

function GarminStatusRow({
  status,
  syncing,
  onSync,
}: {
  status: any;
  syncing: boolean;
  onSync: () => void;
}) {
  const health = status?.health as 'healthy' | 'stale' | 'error' | 'unbound' | undefined;
  const mins = status?.minutes_since_last_sync as number | null | undefined;
  const safeMins = typeof mins === 'number' && Number.isFinite(mins)
    ? Math.max(0, Math.floor(mins))
    : null;

  const dot =
    health === 'healthy' ? revaSemantic.normal.fg :
    health === 'stale' ? revaSemantic.caution.fg :
    health === 'error' ? revaSemantic.risk.fg :
    C.ink3;

  const statusText = (() => {
    if (syncing) return '同步中...';
    if (!status) return '...';
    if (health === 'unbound') return '未绑定';
    if (health === 'error') {
      if (status.requires_mfa) return '需 MFA 验证';
      if (!status.credentials_valid) return '凭证失效';
      return `${status.error_count} 次失败`;
    }
    if (safeMins == null) return '从未同步';
    if (safeMins < 1) return '刚刚同步';
    if (safeMins < 60) return `${safeMins} 分钟前`;
    if (safeMins < 60 * 24) return `${Math.floor(safeMins / 60)} 小时前`;
    return `${Math.floor(safeMins / (60 * 24))} 天前`;
  })();

  return (
    <TouchableOpacity style={styles.settingRow} onPress={onSync} activeOpacity={0.6} disabled={syncing}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="watch-outline" size={18} color={C.ink2} />
        <View style={{
          width: 8, height: 8, borderRadius: 4, backgroundColor: dot,
        }} />
      </View>
      <Text style={txt.settingLabel}>Garmin</Text>
      <Text style={[txt.settingValue, health === 'error' && { color: revaSemantic.risk.fg }]}>{statusText}</Text>
      <Ionicons name={syncing ? 'refresh' : 'chevron-forward'} size={14} color={C.ink3} />
    </TouchableOpacity>
  );
}

// Reva 设计语言(Claude Design handoff):暖白 paper / surface 卡 / ink 文字 / 活力绿 / r-lg 18 / 数字等宽 mono。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper2 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: revaSpacing.s4, paddingVertical: revaSpacing.s2 },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: revaSpacing.s5 },
  card: { backgroundColor: C.surface, borderRadius: revaRadii.lg, marginBottom: revaSpacing.s4, ...revaShadows.sm },
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: revaSpacing.s5 },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: C.green50, alignItems: 'center', justifyContent: 'center' },
  settingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: revaSpacing.s5, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line,
  },
  locationRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: revaSpacing.s5, paddingVertical: 13,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line,
  },
  locationIconBox: {
    width: 28, height: 28, borderRadius: revaRadii.sm,
    alignItems: 'center', justifyContent: 'center', backgroundColor: C.green50,
  },
  locationCopy: { flex: 1, minWidth: 0 },
  locationStatus: { width: 74, alignItems: 'flex-end', gap: 3 },
  logoutBtn: {
    backgroundColor: C.surface, borderRadius: revaRadii.lg,
    paddingVertical: 14, alignItems: 'center', marginTop: revaSpacing.s5,
    ...revaShadows.sm,
  },
});

// 数字/版本号走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。破坏性操作(登出)用 risk 红。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, flex: 1, textAlign: 'center' } as TextStyle,
  name: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1 } as TextStyle,
  email: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, marginTop: 2 } as TextStyle,
  settingLabel: { fontFamily: revaFonts.sans, fontSize: 15, color: C.ink1, flex: 1 } as TextStyle,
  settingValue: { fontFamily: revaFonts.sans, fontSize: 14, color: C.ink3 } as TextStyle,
  sectionLabel: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600', letterSpacing: 0.6, color: C.ink3, marginLeft: revaSpacing.s1, marginBottom: revaSpacing.s1, marginTop: revaSpacing.s1 } as TextStyle,
  locationTitle: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '700', color: C.ink1, flexShrink: 1 } as TextStyle,
  locationHint: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, marginTop: 3 } as TextStyle,
  locationMode: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600', color: C.green500 } as TextStyle,
  locationCity: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.ink2 } as TextStyle,
  logoutText: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '500', color: revaSemantic.risk.fg } as TextStyle,
};
