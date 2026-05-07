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
        <View style={styles.center}>
          <Ionicons name="alarm-outline" size={48} color={c.labelTertiary} />
          <Text style={txt.empty}>暂无提醒</Text>
          <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
            <Text style={txt.addBtnText}>添加提醒</Text>
          </TouchableOpacity>
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
    backgroundColor: c.brand, borderRadius: radii.lg,
    paddingHorizontal: spacing.xxl, paddingVertical: 12,
  },
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
  empty: { fontSize: 15, color: c.labelTertiary } as TextStyle,
  addBtnText: { fontSize: 15, fontWeight: '600', color: '#fff' } as TextStyle,
  templateName: { fontSize: 15, fontWeight: '500', color: c.labelPrimary } as TextStyle,
  templateTimes: { fontSize: 13, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  customLabel: { fontSize: 13, color: c.labelSecondary } as TextStyle,
});
