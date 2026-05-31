import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, Modal, KeyboardAvoidingView, Platform, TextStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { GoalResponse } from '../../services/goals';

interface Props {
  goal: GoalResponse | null;
  visible: boolean;
  onClose: () => void;
  onSubmit: (value: number, notes: string) => void;
}

export default function ProgressUpdateSheet({ goal, visible, onClose, onSubmit }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
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
          {goal && <Text style={txt.goalName}>{goal.title} ({goal.current_value ?? 0} → ? {goal.target_unit || ''})</Text>}
          <TextInput
            style={styles.input}
            placeholder={`输入新的数值 (${goal?.target_unit || ''})`}
            placeholderTextColor={c.labelTertiary}
            keyboardType="decimal-pad"
            value={value}
            onChangeText={setValue}
            autoFocus
          />
          <TextInput
            style={[styles.input, { height: 60 }]}
            placeholder="备注（可选）"
            placeholderTextColor={c.labelTertiary}
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

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    overlay: { flex: 1, justifyContent: 'flex-end' },
    backdrop: { flex: 1 },
    sheet: {
      backgroundColor: c.bgCard, borderTopLeftRadius: radii.xl, borderTopRightRadius: radii.xl,
      padding: spacing.lg, paddingBottom: 40, ...shadows.heavy,
    },
    handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: c.labelQuaternary, alignSelf: 'center', marginBottom: spacing.lg },
    input: {
      backgroundColor: c.bgPrimary, borderRadius: radii.md,
      paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
      color: c.labelPrimary, marginBottom: spacing.md,
    },
    submitBtn: {
      backgroundColor: c.brand, borderRadius: radii.md,
      paddingVertical: 14, alignItems: 'center', marginTop: spacing.sm,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, marginBottom: 4 } as TextStyle,
    goalName: { fontSize: 13, color: c.labelSecondary, marginBottom: spacing.lg } as TextStyle,
    submitText: { fontSize: 16, fontWeight: '600', color: '#fff' } as TextStyle,
  };
}
