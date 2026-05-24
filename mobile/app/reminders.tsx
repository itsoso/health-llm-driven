import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, FlatList, Alert, ActivityIndicator, Modal, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Swipeable } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';
import {
  getReminders, getReminderTemplates, createReminder, deleteReminder, updateReminder,
  type Reminder, type ReminderTemplate,
} from '../services/notifications';
import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';

export default function RemindersScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);

  const { data: reminders = [], isLoading } = useQuery({
    queryKey: ['reminders'],
    queryFn: getReminders,
    staleTime: 60_000,
  });

  const deleteMut = useMutation({
    mutationFn: deleteReminder,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reminders'] }),
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateReminder(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reminders'] }),
  });

  const handleDelete = (id: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert('删除提醒', '确定要删除吗？', [
      { text: '取消', style: 'cancel' },
      { text: '删除', style: 'destructive', onPress: () => deleteMut.mutate(id) },
    ]);
  };

  const renderRight = (id: number) => (
    <TouchableOpacity style={styles.swipeDelete} onPress={() => handleDelete(id)}>
      <Ionicons name="trash-outline" size={20} color="#fff" />
    </TouchableOpacity>
  );

  const renderItem = ({ item }: { item: Reminder }) => (
    <Swipeable renderRightActions={() => renderRight(item.id)}>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={txt.name}>{item.name}</Text>
          <Text style={txt.times}>{item.reminder_times.join(', ')}</Text>
        </View>
        <TouchableOpacity
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            toggleMut.mutate({ id: item.id, enabled: !item.enabled });
          }}
        >
          <Ionicons
            name={item.enabled ? 'checkmark-circle' : 'ellipse-outline'}
            size={24}
            color={item.enabled ? c.brand : c.labelTertiary}
          />
        </TouchableOpacity>
      </View>
    </Swipeable>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>提醒管理</Text>
        <TouchableOpacity onPress={() => setShowAdd(true)} style={styles.backBtn}>
          <Ionicons name="add" size={24} color={c.brand} />
        </TouchableOpacity>
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
      ) : reminders.length === 0 ? (
        <View style={styles.emptyWrap}>
          <View style={styles.emptyCard}>
            <View style={styles.emptyIcon}>
              <Ionicons name="alarm-outline" size={26} color={c.brand} />
            </View>
            <Text style={txt.emptyTitle}>先放 1 个不会漏的提醒</Text>
            <Text style={txt.emptyBody}>
              这里适合放固定节律任务。少量、明确、可执行，比一次加很多提醒更稳定。
            </Text>
            <View style={styles.templatePreview}>
              {EMPTY_REMINDER_HINTS.map((hint) => (
                <View key={hint.title} style={styles.hintRow}>
                  <View style={[styles.hintDot, { backgroundColor: hint.color }]} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={txt.hintTitle}>{hint.title}</Text>
                    <Text style={txt.hintMeta}>{hint.meta}</Text>
                  </View>
                </View>
              ))}
            </View>
            <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)} activeOpacity={0.75}>
              <Ionicons name="add-circle-outline" size={18} color="#fff" />
              <Text style={txt.addBtnText}>添加提醒</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={() => router.push('/notification-settings' as any)}>
              <Text style={txt.secondaryBtnText}>先检查推送设置</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <FlatList
          data={reminders}
          keyExtractor={(r) => String(r.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
        />
      )}

      <AddReminderModal visible={showAdd} onClose={() => setShowAdd(false)} />
    </SafeAreaView>
  );
}

function AddReminderModal({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();
  const [selectedTemplate, setSelectedTemplate] = useState<ReminderTemplate | null>(null);
  const [customTime, setCustomTime] = useState('');

  const { data: templates = [] } = useQuery({
    queryKey: ['reminderTemplates'],
    queryFn: getReminderTemplates,
    enabled: visible,
    staleTime: 300_000,
  });

  const createMut = useMutation({
    mutationFn: createReminder,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reminders'] });
      onClose();
      setSelectedTemplate(null);
      setCustomTime('');
    },
  });

  const handleCreate = () => {
    if (!selectedTemplate) return;
    const times = customTime
      ? customTime.split(',').map((t) => t.trim()).filter(Boolean)
      : selectedTemplate.default_times;

    createMut.mutate({
      reminder_type: selectedTemplate.type,
      name: selectedTemplate.name,
      reminder_times: times,
      message: selectedTemplate.default_message,
    });
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.backBtn}>
            <Text style={{ fontSize: 16, color: c.labelSecondary }}>取消</Text>
          </TouchableOpacity>
          <Text style={txt.title}>添加提醒</Text>
          <TouchableOpacity onPress={handleCreate} style={styles.backBtn} disabled={!selectedTemplate}>
            <Text style={{ fontSize: 16, color: selectedTemplate ? c.brand : c.labelTertiary }}>添加</Text>
          </TouchableOpacity>
        </View>

        <FlatList
          data={templates}
          keyExtractor={(t) => t.type}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[styles.templateRow, selectedTemplate?.type === item.type && styles.templateSelected]}
              onPress={() => setSelectedTemplate(item)}
              activeOpacity={0.6}
            >
              <Text style={txt.templateName}>{item.name}</Text>
              <Text style={txt.templateTimes}>默认: {item.default_times.join(', ')}</Text>
            </TouchableOpacity>
          )}
        />

        {selectedTemplate && (
          <View style={styles.customTimeBox}>
            <Text style={txt.customLabel}>自定义时间（逗号分隔，如 07:30, 19:00）</Text>
            <TextInput
              style={styles.input}
              value={customTime}
              onChangeText={setCustomTime}
              placeholder={selectedTemplate.default_times.join(', ')}
              placeholderTextColor={c.labelTertiary}
            />
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
}

const EMPTY_REMINDER_HINTS = [
  { title: '早晨记录', meta: '起床后 10 分钟内补齐体重 / 血压', color: '#30D158' },
  { title: '用药 / 补剂', meta: '固定时间提醒, 避免重复或漏服', color: '#FF9F0A' },
  { title: '睡前恢复', meta: '睡前 30 分钟降低刺激和屏幕', color: '#AF52DE' },
];

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.md },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 60, height: 40, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg },
  row: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    paddingHorizontal: spacing.lg, paddingVertical: 14,
    marginBottom: spacing.sm, ...shadows.subtle,
  },
  swipeDelete: {
    backgroundColor: '#FF453A', width: 64, borderRadius: radii.lg,
    justifyContent: 'center', alignItems: 'center', marginBottom: spacing.sm,
  },
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: c.brand, borderRadius: radii.lg,
    paddingHorizontal: spacing.xxl, paddingVertical: 12,
  },
  secondaryBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
  },
  emptyWrap: {
    flex: 1,
    padding: spacing.lg,
    paddingTop: spacing.xl,
  },
  emptyCard: {
    backgroundColor: c.bgCard,
    borderRadius: radii.xl,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadows.subtle,
  },
  emptyIcon: {
    width: 48,
    height: 48,
    borderRadius: radii.lg,
    backgroundColor: c.tintTeal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  templatePreview: {
    gap: spacing.xs,
    paddingVertical: spacing.xs,
  },
  hintRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 9,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  hintDot: { width: 8, height: 8, borderRadius: 4 },
  templateRow: {
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    paddingHorizontal: spacing.lg, paddingVertical: 14,
    marginBottom: spacing.sm, ...shadows.subtle,
    borderWidth: 2, borderColor: 'transparent',
  },
  templateSelected: { borderColor: c.brand },
  customTimeBox: { padding: spacing.lg },
  input: {
    backgroundColor: c.bgCard, borderRadius: radii.md,
    paddingHorizontal: spacing.md, paddingVertical: 12,
    fontSize: 15, color: c.labelPrimary, marginTop: spacing.xs,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  name: { fontSize: 15, fontWeight: '500', color: c.labelPrimary } as TextStyle,
  times: { fontSize: 13, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  emptyTitle: { fontSize: 20, lineHeight: 25, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  emptyBody: { fontSize: 14, lineHeight: 21, color: c.labelSecondary } as TextStyle,
  addBtnText: { fontSize: 15, fontWeight: '600', color: '#fff' } as TextStyle,
  secondaryBtnText: { fontSize: 14, fontWeight: '600', color: c.brand } as TextStyle,
  hintTitle: { fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  hintMeta: { fontSize: 12, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  templateName: { fontSize: 15, fontWeight: '500', color: c.labelPrimary } as TextStyle,
  templateTimes: { fontSize: 13, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  customLabel: { fontSize: 13, color: c.labelSecondary } as TextStyle,
});
