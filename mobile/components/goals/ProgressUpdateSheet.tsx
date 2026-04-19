import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, Modal, KeyboardAvoidingView, Platform, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, spacing, radii, shadows } from '@/constants/theme';
import type { GoalResponse } from '@/services/goals';

interface Props {
  goal: GoalResponse | null;
  visible: boolean;
  onClose: () => void;
  onSubmit: (value: number, notes: string) => void;
}

export default function ProgressUpdateSheet({ goal, visible, onClose, onSubmit }: Props) {
  const [value, setValue] = useState('');
  const [notes, setNotes] = useState('');

  const handleSubmit = () => {
    const v = parseFloat(value);
    if (isNaN(v)) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onSubmit(v, notes);
    setValue('');
    setNotes('');
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.overlay}>
        <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <Text style={txt.title}>更新进度</Text>
          {goal && <Text style={txt.goalName}>{goal.title} ({goal.current_value} → ? {goal.unit})</Text>}
          <TextInput
            style={styles.input}
            placeholder={`输入新的数值 (${goal?.unit || ''})`}
            placeholderTextColor={colors.labelTertiary}
            keyboardType="decimal-pad"
            value={value}
            onChangeText={setValue}
            autoFocus
          />
          <TextInput
            style={[styles.input, { height: 60 }]}
            placeholder="备注（可选）"
            placeholderTextColor={colors.labelTertiary}
            value={notes}
            onChangeText={setNotes}
            multiline
          />
          <TouchableOpacity
            style={[styles.submitBtn, !value && { opacity: 0.5 }]}
            onPress={handleSubmit}
            disabled={!value}
            activeOpacity={0.7}
          >
            <Text style={txt.submitText}>确认更新</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { flex: 1 },
  sheet: {
    backgroundColor: colors.bgCard, borderTopLeftRadius: radii.xl, borderTopRightRadius: radii.xl,
    padding: spacing.lg, paddingBottom: 40, ...shadows.heavy,
  },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.labelQuaternary, alignSelf: 'center', marginBottom: spacing.lg },
  input: {
    backgroundColor: colors.bgPrimary, borderRadius: radii.md,
    paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
    color: colors.labelPrimary, marginBottom: spacing.md,
  },
  submitBtn: {
    backgroundColor: colors.brand, borderRadius: radii.md,
    paddingVertical: 14, alignItems: 'center', marginTop: spacing.sm,
  },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, marginBottom: 4 } as TextStyle,
  goalName: { fontSize: 13, color: colors.labelSecondary, marginBottom: spacing.lg } as TextStyle,
  submitText: { fontSize: 16, fontWeight: '600', color: '#fff' } as TextStyle,
};
