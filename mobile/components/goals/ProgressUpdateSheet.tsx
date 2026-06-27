import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, Modal, KeyboardAvoidingView, Platform } from 'react-native';
import * as Haptics from 'expo-haptics';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';
import type { GoalResponse } from '../../services/goals';

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
          <Text style={styles.title}>更新进度</Text>
          {goal && <Text style={styles.goalName}>{goal.title} ({goal.current_value ?? 0} → ? {goal.target_unit || ''})</Text>}
          <TextInput
            style={styles.input}
            placeholder={`输入新的数值 (${goal?.target_unit || ''})`}
            placeholderTextColor={C.ink3}
            keyboardType="decimal-pad"
            value={value}
            onChangeText={setValue}
            autoFocus
          />
          <TextInput
            style={[styles.input, styles.notesInput]}
            placeholder="备注（可选）"
            placeholderTextColor={C.ink3}
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
            <Text style={styles.submitText}>确认更新</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// Reva 设计语言:暖白 surface sheet / r-xl 圆角 / 数字录入走等宽 mono / 软阴影。
const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { flex: 1 },
  sheet: {
    backgroundColor: C.surface, borderTopLeftRadius: revaRadii.xl, borderTopRightRadius: revaRadii.xl,
    padding: revaSpacing.s4, paddingBottom: 40, ...revaShadows.lg,
  },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: C.ink4, alignSelf: 'center', marginBottom: revaSpacing.s4 },
  input: {
    backgroundColor: C.paper2, borderRadius: revaRadii.md,
    paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, fontFamily: revaFonts.mono,
    color: C.ink1, marginBottom: revaSpacing.s3,
  },
  notesInput: { fontFamily: revaFonts.sans, height: 60 },
  submitBtn: {
    backgroundColor: C.green500, borderRadius: revaRadii.md,
    paddingVertical: 14, alignItems: 'center', marginTop: revaSpacing.s2,
  },
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1, marginBottom: 4 },
  goalName: { fontFamily: revaFonts.mono, fontSize: 13, color: C.ink2, marginBottom: revaSpacing.s4 },
  submitText: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: '#fff' },
});
