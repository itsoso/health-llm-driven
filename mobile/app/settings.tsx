import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, Alert, ScrollView, Switch } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import api from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import { useBiometricLock } from '@/hooks/useBiometricLock';
import { colors, spacing, radii, shadows } from '@/constants/theme';

export default function SettingsScreen() {
  const router = useRouter();
  const { logout, user, isAuthenticated } = useAuth();
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const { isEnabled: bioEnabled, isSupported: bioSupported, toggleEnabled: toggleBio } = useBiometricLock(isAuthenticated);

  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: () => api.get('/profile/me').then(r => r.data), staleTime: 300_000 });
  const city = profile?.manual_location?.city || profile?.detected_location?.city || profile?.city || '未设置';

  const syncGarmin = async () => {
    setSyncing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await api.post('/data-collection/garmin/me/sync?days=1');
      Alert.alert('同步成功', 'Garmin 数据已更新');
      qc.invalidateQueries({ queryKey: ['garminToday'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
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

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>设置</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Profile */}
        <View style={styles.card}>
          <View style={styles.profileRow}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={24} color={colors.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.name}>{user?.username || (user as any)?.name || '用户'}</Text>
              <Text style={txt.email}>{user?.email || ''}</Text>
            </View>
          </View>
        </View>

        {/* Settings items */}
        <View style={styles.card}>
          <SettingRow icon="location-outline" label="当前城市" value={city} />
          <SettingRow icon="watch-outline" label="Garmin 同步"
            value={syncing ? '同步中...' : '点击同步'}
            onPress={syncGarmin} />
        </View>

        {/* Health tools */}
        <View style={styles.card}>
          <SettingRow icon="medical-outline" label="健康咨询"
            onPress={() => router.push('/consultations' as any)} />
        </View>

        {/* Notifications & Security */}
        <View style={styles.card}>
          <SettingRow icon="notifications-outline" label="推送通知"
            onPress={() => router.push('/notification-settings' as any)} />
          {bioSupported && (
            <View style={styles.settingRow}>
              <Ionicons name="finger-print-outline" size={18} color={colors.labelSecondary} />
              <Text style={txt.settingLabel}>Face ID 锁定</Text>
              <Switch value={bioEnabled} onValueChange={toggleBio}
                trackColor={{ false: colors.fill, true: colors.brand }} thumbColor="#fff" />
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
  const Wrapper = onPress ? TouchableOpacity : View;
  return (
    <Wrapper style={styles.settingRow} onPress={onPress} activeOpacity={0.6}>
      <Ionicons name={icon} size={18} color={colors.labelSecondary} />
      <Text style={txt.settingLabel}>{label}</Text>
      <Text style={txt.settingValue}>{value || ''}</Text>
      {onPress && <Ionicons name="chevron-forward" size={14} color={colors.labelTertiary} />}
    </Wrapper>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg },
  card: { backgroundColor: colors.bgCard, borderRadius: radii.lg, marginBottom: spacing.md, ...shadows.subtle },
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: spacing.lg },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandLight, alignItems: 'center', justifyContent: 'center' },
  settingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.lg, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  logoutBtn: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    paddingVertical: 14, alignItems: 'center', marginTop: spacing.lg,
    ...shadows.subtle,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  name: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary } as TextStyle,
  email: { fontSize: 13, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  settingLabel: { fontSize: 15, color: colors.labelPrimary, flex: 1 } as TextStyle,
  settingValue: { fontSize: 14, color: colors.labelTertiary } as TextStyle,
  logoutText: { fontSize: 16, fontWeight: '500', color: '#FF453A' } as TextStyle,
};
