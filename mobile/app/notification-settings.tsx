import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, Switch, Alert, ScrollView, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { getSettings, updateSettings, sendTestPush, type NotificationSettings, type NotificationSettingsUpdate } from '@/services/notifications';
import { colors, spacing, radii, shadows } from '@/constants/theme';

export default function NotificationSettingsScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const [testing, setTesting] = useState(false);

  const { data: settings, isLoading } = useQuery<NotificationSettings>({
    queryKey: ['notificationSettings'],
    queryFn: getSettings,
    staleTime: 60_000,
  });

  const mutation = useMutation({
    mutationFn: (updates: NotificationSettingsUpdate) => updateSettings(updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notificationSettings'] }),
  });

  const toggle = (key: keyof NotificationSettingsUpdate, value: boolean) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    mutation.mutate({ [key]: value });
  };

  const handleTestPush = async () => {
    setTesting(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await sendTestPush();
      Alert.alert('已发送', '测试推送已发送，请检查通知');
    } catch {
      Alert.alert('发送失败', '请检查推送设置');
    } finally {
      setTesting(false);
    }
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>推送通知</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.card}>
          <ToggleRow label="启用推送" value={settings?.enabled ?? true}
            onToggle={(v) => toggle('enabled', v)} />
        </View>

        <Text style={txt.section}>通知类型</Text>
        <View style={styles.card}>
          <ToggleRow label="晨间简报" icon="sunny-outline" value={settings?.morning_briefing_enabled ?? true}
            onToggle={(v) => toggle('morning_briefing_enabled', v)} />
          <ToggleRow label="健康告警" icon="warning-outline" value={settings?.health_alert_enabled ?? true}
            onToggle={(v) => toggle('health_alert_enabled', v)} />
          <ToggleRow label="提醒事项" icon="alarm-outline" value={settings?.reminder_enabled ?? true}
            onToggle={(v) => toggle('reminder_enabled', v)} />
          <ToggleRow label="AI 建议" icon="sparkles-outline" value={settings?.ai_advice_enabled ?? true}
            onToggle={(v) => toggle('ai_advice_enabled', v)} />
        </View>

        <Text style={txt.section}>安静时段</Text>
        <View style={styles.card}>
          <InfoRow label="开始" value={settings?.quiet_hours_start || '22:00'} />
          <InfoRow label="结束" value={settings?.quiet_hours_end || '07:00'} />
        </View>

        <Text style={txt.section}>管理</Text>
        <View style={styles.card}>
          <NavRow label="提醒管理" icon="alarm-outline" onPress={() => router.push('/reminders' as any)} />
          <NavRow label="推送历史" icon="time-outline" onPress={() => router.push('/notification-history' as any)} />
        </View>

        <TouchableOpacity style={styles.testBtn} onPress={handleTestPush} disabled={testing} activeOpacity={0.7}>
          {testing ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={txt.testBtnText}>发送测试推送</Text>
          )}
        </TouchableOpacity>

        <Text style={txt.hint}>
          设备状态：{settings?.ios_bound ? '已绑定' : '未绑定'}
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function ToggleRow({ label, icon, value, onToggle }: { label: string; icon?: any; value: boolean; onToggle: (v: boolean) => void }) {
  return (
    <View style={styles.row}>
      {icon && <Ionicons name={icon} size={18} color={colors.labelSecondary} />}
      <Text style={txt.rowLabel}>{label}</Text>
      <Switch value={value} onValueChange={onToggle}
        trackColor={{ false: colors.fill, true: colors.brand }}
        thumbColor="#fff" />
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={txt.rowLabel}>{label}</Text>
      <Text style={txt.rowValue}>{value}</Text>
    </View>
  );
}

function NavRow({ label, icon, onPress }: { label: string; icon: any; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.6}>
      <Ionicons name={icon} size={18} color={colors.labelSecondary} />
      <Text style={txt.rowLabel}>{label}</Text>
      <Ionicons name="chevron-forward" size={14} color={colors.labelTertiary} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 60 },
  card: { backgroundColor: colors.bgCard, borderRadius: radii.lg, marginBottom: spacing.md, ...shadows.subtle },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.lg, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  testBtn: {
    backgroundColor: colors.brand, borderRadius: radii.lg,
    paddingVertical: 14, alignItems: 'center', marginTop: spacing.xl,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  section: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary, marginBottom: spacing.xs, marginTop: spacing.sm, marginLeft: spacing.xs } as TextStyle,
  rowLabel: { fontSize: 15, color: colors.labelPrimary, flex: 1 } as TextStyle,
  rowValue: { fontSize: 14, color: colors.labelTertiary } as TextStyle,
  testBtnText: { fontSize: 16, fontWeight: '600', color: '#fff' } as TextStyle,
  hint: { fontSize: 12, color: colors.labelTertiary, textAlign: 'center', marginTop: spacing.md } as TextStyle,
};
