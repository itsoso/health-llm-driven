import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, Switch, Alert, ScrollView, ActivityIndicator, Modal } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import { getSettings, updateSettings, sendTestPush, type NotificationSettings, type NotificationSettingsUpdate } from '../services/notifications';
import { colors, spacing, radii, shadows } from '../constants/theme';

export default function NotificationSettingsScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const [testing, setTesting] = useState(false);
  const [editing, setEditing] = useState<null | 'start' | 'end'>(null);

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

  const setQuietTime = (key: 'quiet_hours_start' | 'quiet_hours_end', value: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    mutation.mutate({ [key]: value });
    setEditing(null);
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
        <Text style={txt.hintSmall}>此时段内非紧急推送会被抑制，只有危及生命的严重告警才会送达。</Text>
        <View style={styles.card}>
          <TimeRow label="开始" value={settings?.quiet_hours_start || '22:00'}
            onPress={() => setEditing('start')} />
          <TimeRow label="结束" value={settings?.quiet_hours_end || '08:30'}
            onPress={() => setEditing('end')} />
        </View>

        <Text style={txt.section}>告警严重度</Text>
        <Text style={txt.hintSmall}>低于此级别的健康告警不推送。critical 级永远推送，不受此设置限制。</Text>
        <View style={styles.card}>
          <SeverityPicker
            current={settings?.alert_severity_threshold || 'warning'}
            onPick={(v) => toggle('alert_severity_threshold' as any, v as any)}
          />
        </View>

        {(settings?.alert_rule_opt_outs?.length ?? 0) > 0 && (
          <>
            <Text style={txt.section}>已静音的规则</Text>
            <Text style={txt.hintSmall}>这些规则命中时不会推送。点击"取消静音"恢复。</Text>
            <View style={styles.card}>
              {(settings?.alert_rule_opt_outs || []).map((rid) => (
                <View key={rid} style={styles.row}>
                  <Ionicons name="volume-mute-outline" size={18} color={colors.labelSecondary} />
                  <Text style={[txt.rowLabel, { fontSize: 13 }]} numberOfLines={1}>
                    {rid}
                  </Text>
                  <TouchableOpacity
                    onPress={() => {
                      const next = (settings?.alert_rule_opt_outs || []).filter(r => r !== rid);
                      mutation.mutate({ alert_rule_opt_outs: next });
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    }}
                  >
                    <Text style={{ color: colors.brand, fontSize: 13 }}>取消静音</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          </>
        )}

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

      <TimePickerModal
        visible={editing !== null}
        title={editing === 'start' ? '选择开始时间' : '选择结束时间'}
        options={editing === 'start' ? START_PRESETS : END_PRESETS}
        current={editing === 'start'
          ? (settings?.quiet_hours_start || '22:00')
          : (settings?.quiet_hours_end || '08:30')}
        onPick={(v) => setQuietTime(
          editing === 'start' ? 'quiet_hours_start' : 'quiet_hours_end',
          v,
        )}
        onClose={() => setEditing(null)}
      />
    </SafeAreaView>
  );
}

const START_PRESETS = ['21:00', '21:30', '22:00', '22:30', '23:00', '23:30', '00:00'];
const END_PRESETS = ['06:00', '06:30', '07:00', '07:30', '08:00', '08:30', '09:00', '09:30', '10:00'];

function TimePickerModal({
  visible, title, options, current, onPick, onClose,
}: {
  visible: boolean;
  title: string;
  options: string[];
  current: string;
  onPick: (value: string) => void;
  onClose: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={onClose}>
        <View style={styles.modalCard}>
          <Text style={txt.modalTitle}>{title}</Text>
          <View style={styles.chipGrid}>
            {options.map((opt) => {
              const selected = opt === current;
              return (
                <TouchableOpacity
                  key={opt}
                  style={[styles.chip, selected && styles.chipSelected]}
                  onPress={() => onPick(opt)}
                  activeOpacity={0.7}
                >
                  <Text style={[txt.chipText, selected && txt.chipTextSelected]}>
                    {opt}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TouchableOpacity onPress={onClose} style={styles.modalClose}>
            <Text style={txt.modalCloseText}>取消</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

function TimeRow({ label, value, onPress }: { label: string; value: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.6}>
      <Text style={txt.rowLabel}>{label}</Text>
      <Text style={txt.rowValue}>{value}</Text>
      <Ionicons name="chevron-forward" size={14} color={colors.labelTertiary} />
    </TouchableOpacity>
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

function NavRow({ label, icon, onPress }: { label: string; icon: any; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.6}>
      <Ionicons name={icon} size={18} color={colors.labelSecondary} />
      <Text style={txt.rowLabel}>{label}</Text>
      <Ionicons name="chevron-forward" size={14} color={colors.labelTertiary} />
    </TouchableOpacity>
  );
}

function SeverityPicker({ current, onPick }: {
  current: 'info' | 'warning' | 'critical';
  onPick: (v: 'info' | 'warning' | 'critical') => void;
}) {
  const options: Array<{
    v: 'info' | 'warning' | 'critical';
    label: string;
    hint: string;
    color: string;
  }> = [
    { v: 'info', label: '全部', hint: '所有告警都推送 (含轻微信息)', color: '#8E8E93' },
    { v: 'warning', label: '中度及以上', hint: '推荐: 过滤 info 级噪音', color: '#FF9500' },
    { v: 'critical', label: '仅危急', hint: '只推送 critical 级告警', color: '#FF3B30' },
  ];
  return (
    <View>
      {options.map(o => {
        const active = current === o.v;
        return (
          <TouchableOpacity
            key={o.v}
            style={[styles.row, active && { backgroundColor: colors.fill + '55' }]}
            onPress={() => onPick(o.v)}
            activeOpacity={0.6}
          >
            <View style={{
              width: 20, height: 20, borderRadius: 10, borderWidth: 2,
              borderColor: active ? o.color : colors.labelTertiary,
              backgroundColor: active ? o.color : 'transparent',
              justifyContent: 'center', alignItems: 'center',
            }}>
              {active && <Ionicons name="checkmark" size={12} color="#fff" />}
            </View>
            <View style={{ flex: 1, marginLeft: 4 }}>
              <Text style={txt.rowLabel}>{o.label}</Text>
              <Text style={[txt.hintSmall, { marginTop: 2 }]}>{o.hint}</Text>
            </View>
          </TouchableOpacity>
        );
      })}
    </View>
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
  modalBackdrop: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center', alignItems: 'center', padding: spacing.lg,
  },
  modalCard: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, width: '100%', maxWidth: 360,
  },
  chipGrid: {
    flexDirection: 'row', flexWrap: 'wrap', gap: 10,
    marginTop: spacing.md, marginBottom: spacing.md,
  },
  chip: {
    paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: radii.md, backgroundColor: colors.fill,
  },
  chipSelected: {
    backgroundColor: colors.brand,
  },
  modalClose: {
    alignItems: 'center', paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  section: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary, marginBottom: spacing.xs, marginTop: spacing.sm, marginLeft: spacing.xs } as TextStyle,
  rowLabel: { fontSize: 15, color: colors.labelPrimary, flex: 1 } as TextStyle,
  rowValue: { fontSize: 14, color: colors.labelTertiary } as TextStyle,
  testBtnText: { fontSize: 16, fontWeight: '600', color: '#fff' } as TextStyle,
  hint: { fontSize: 12, color: colors.labelTertiary, textAlign: 'center', marginTop: spacing.md } as TextStyle,
  hintSmall: { fontSize: 11, color: colors.labelTertiary, marginLeft: spacing.xs, marginBottom: spacing.xs, lineHeight: 16 } as TextStyle,
  modalTitle: { fontSize: 16, fontWeight: '600', color: colors.labelPrimary, textAlign: 'center' } as TextStyle,
  chipText: { fontSize: 15, color: colors.labelPrimary } as TextStyle,
  chipTextSelected: { color: '#fff', fontWeight: '600' } as TextStyle,
  modalCloseText: { fontSize: 15, color: colors.labelSecondary } as TextStyle,
};
