import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, Alert, ScrollView, Switch } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { useBiometricLock } from '../hooks/useBiometricLock';
import { invalidateHealthSnapshot, queryKeys } from '../applib/queryKeys';
import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';

export default function SettingsScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const { logout, user, isAuthenticated } = useAuth();
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const { isEnabled: bioEnabled, isSupported: bioSupported, toggleEnabled: toggleBio } = useBiometricLock(isAuthenticated);

  const { data: profile } = useQuery({ queryKey: queryKeys.profile, queryFn: () => api.get('/profile/me').then(r => r.data), staleTime: 600_000 });
  const city = profile?.manual_location?.city || profile?.detected_location?.city || profile?.city || '未设置';

  const { data: garminStatus, refetch: refetchGarminStatus } = useQuery({
    queryKey: ['garminStatus'],
    queryFn: () => api.get('/data-collection/garmin/me/credential-status').then(r => r.data),
    staleTime: 60_000,
    refetchInterval: 120_000,
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

  const showSiriInfo = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    Alert.alert(
      'Siri 语音记录',
      '登录后即可使用 Siri 语音记录健康数据：\n\n• "嘿 Siri，用 HealthPilot 记录喝了500ml水"\n• "嘿 Siri，告诉 HealthPilot 吃了一个苹果"\n\n首次使用时 Siri 会请求授权。',
      [{ text: '知道了' }],
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>设置</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Profile */}
        <View style={styles.card}>
          <View style={styles.profileRow}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={24} color={c.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.name}>{user?.username || (user as any)?.name || '用户'}</Text>
              <Text style={txt.email}>{user?.email || ''}</Text>
            </View>
          </View>
        </View>

        {/* AI 模型 — 置顶 */}
        <View style={styles.card}>
          <SettingRow icon="sparkles-outline" label="AI 模型"
            onPress={() => router.push('/admin-llm' as any)} />
          <SettingRow icon="person-outline" label="AI 教练风格"
            onPress={() => router.push('/coach-persona' as any)} />
          <SettingRow icon="cellular-outline" label="我的基因"
            onPress={() => router.push('/genetic-report' as any)} />
        </View>

        {/* Settings items */}
        <View style={styles.card}>
          <SettingRow icon="location-outline" label="当前城市" value={city} />
          <GarminStatusRow status={garminStatus} syncing={syncing} onSync={syncGarmin} />
        </View>

        {/* Health tools */}
        <View style={styles.card}>
          <SettingRow icon="medical-outline" label="健康咨询"
            onPress={() => router.push('/consultations' as any)} />
          <SettingRow icon="barbell-outline" label="运动记录"
            onPress={() => router.push('/workout-list' as any)} />
          <SettingRow icon="flag-outline" label="健康目标"
            onPress={() => router.push('/goals' as any)} />
          <SettingRow icon="document-text-outline" label="硬性指令"
            onPress={() => router.push('/directives' as any)} />
          <SettingRow icon="sparkles-outline" label="AI 对我的画像"
            onPress={() => router.push('/ai-profile' as any)} />
          <SettingRow icon="bookmark-outline" label="AI 关于你的笔记"
            onPress={() => router.push('/memory' as any)} />
          <SettingRow icon="document-text-outline" label="化验记录"
            onPress={() => router.push('/medical-exams' as any)} />
          <SettingRow icon="calendar-outline" label="月度复盘"
            onPress={() => router.push('/monthly-reports' as any)} />
          <SettingRow icon="medical-outline" label="医生回路"
            onPress={() => router.push('/doctor-loop' as any)} />
          <SettingRow icon="location-outline" label="位置设置"
            onPress={() => router.push('/location' as any)} />
          <SettingRow icon="time-outline" label="健康事件流"
            onPress={() => router.push('/timeline' as any)} />
          <SettingRow icon="medkit-outline" label="用药管理"
            onPress={() => router.push('/medications' as any)} />
          <SettingRow icon="people-outline" label="家庭健康"
            onPress={() => router.push('/family' as any)} />
        </View>

        {/* Notifications & Siri & Security */}
        <View style={styles.card}>
          <SettingRow icon="notifications-outline" label="推送通知"
            onPress={() => router.push('/notification-settings' as any)} />
          <SettingRow icon="volume-high-outline" label="语音风格"
            onPress={() => router.push('/voice-style' as any)} />
          <SettingRow icon="mic-outline" label="Siri 语音记录"
            value="使用说明"
            onPress={showSiriInfo} />
          {bioSupported && (
            <View style={styles.settingRow}>
              <Ionicons name="finger-print-outline" size={18} color={c.labelSecondary} />
              <Text style={txt.settingLabel}>Face ID 锁定</Text>
              <Switch value={bioEnabled} onValueChange={toggleBio}
                trackColor={{ false: c.fill, true: c.brand }} thumbColor="#fff" />
            </View>
          )}
        </View>

        <View style={styles.card}>
          <SettingRow icon="information-circle-outline" label="版本" value="1.0.0" />
          <SettingRow icon="shield-checkmark-outline" label="隐私政策" onPress={() => {}} />
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout} activeOpacity={0.7}>
          <Text style={txt.logoutText}>退出登录</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function SettingRow({ icon, label, value, onPress }: { icon: any; label: string; value?: string; onPress?: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const Wrapper = onPress ? TouchableOpacity : View;
  return (
    <Wrapper style={styles.settingRow} onPress={onPress} activeOpacity={0.6}>
      <Ionicons name={icon} size={18} color={c.labelSecondary} />
      <Text style={txt.settingLabel}>{label}</Text>
      <Text style={txt.settingValue}>{value || ''}</Text>
      {onPress && <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />}
    </Wrapper>
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
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const health = status?.health as 'healthy' | 'stale' | 'error' | 'unbound' | undefined;
  const mins = status?.minutes_since_last_sync as number | null | undefined;

  const dot =
    health === 'healthy' ? '#30D158' :
    health === 'stale' ? '#FF9F0A' :
    health === 'error' ? '#FF453A' :
    c.labelTertiary;

  const statusText = (() => {
    if (syncing) return '同步中...';
    if (!status) return '...';
    if (health === 'unbound') return '未绑定';
    if (health === 'error') {
      if (status.requires_mfa) return '需 MFA 验证';
      if (!status.credentials_valid) return '凭证失效';
      return `${status.error_count} 次失败`;
    }
    if (mins == null) return '从未同步';
    if (mins < 60) return `${mins} 分钟前`;
    if (mins < 60 * 24) return `${Math.floor(mins / 60)} 小时前`;
    return `${Math.floor(mins / (60 * 24))} 天前`;
  })();

  return (
    <TouchableOpacity style={styles.settingRow} onPress={onSync} activeOpacity={0.6} disabled={syncing}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="watch-outline" size={18} color={c.labelSecondary} />
        <View style={{
          width: 8, height: 8, borderRadius: 4, backgroundColor: dot,
        }} />
      </View>
      <Text style={txt.settingLabel}>Garmin</Text>
      <Text style={[txt.settingValue, health === 'error' && { color: '#FF453A' }]}>{statusText}</Text>
      <Ionicons name={syncing ? 'refresh' : 'chevron-forward'} size={14} color={c.labelTertiary} />
    </TouchableOpacity>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  card: { backgroundColor: c.bgCard, borderRadius: radii.lg, marginBottom: spacing.md, ...shadows.subtle },
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: spacing.lg },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: c.brandLight, alignItems: 'center', justifyContent: 'center' },
  settingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.lg, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator,
  },
  logoutBtn: {
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    paddingVertical: 14, alignItems: 'center', marginTop: spacing.lg,
    ...shadows.subtle,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  name: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  email: { fontSize: 13, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  settingLabel: { fontSize: 15, color: c.labelPrimary, flex: 1 } as TextStyle,
  settingValue: { fontSize: 14, color: c.labelTertiary } as TextStyle,
  logoutText: { fontSize: 16, fontWeight: '500', color: '#FF453A' } as TextStyle,
});
