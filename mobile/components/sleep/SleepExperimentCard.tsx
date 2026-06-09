import React, { useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  index: number;
  action: string;
  state?: 'queued' | 'done' | 'skipped';
  isSaving?: boolean;
  onTryTonight: () => void;
  onDone: () => void;
  onSkip: () => void;
}

export default function SleepExperimentCard({
  index,
  action,
  state,
  isSaving,
  onTryTonight,
  onDone,
  onSkip,
}: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.indexBadge}>
          <Text style={styles.indexText}>{index + 1}</Text>
        </View>
        <Text style={styles.actionText}>{action}</Text>
      </View>
      {state ? (
        <View style={styles.statusRow}>
          <Ionicons
            name={state === 'skipped' ? 'remove-circle-outline' : 'checkmark-circle'}
            size={14}
            color={state === 'skipped' ? c.labelTertiary : '#0A8F8F'}
          />
          <Text style={styles.statusText}>
            {state === 'queued' ? '已加入行动，明天复盘效果' : state === 'done' ? '已标记完成' : '已标记不适用'}
          </Text>
        </View>
      ) : null}
      <View style={styles.btnRow}>
        <ExperimentButton label="今晚尝试" icon="moon-outline" primary disabled={isSaving} onPress={onTryTonight} loading={isSaving} />
        <ExperimentButton label="已完成" icon="checkmark-outline" disabled={isSaving} onPress={onDone} />
        <ExperimentButton label="不适用" icon="close-outline" disabled={isSaving} onPress={onSkip} />
      </View>
    </View>
  );
}

function ExperimentButton({
  label,
  icon,
  primary,
  disabled,
  loading,
  onPress,
}: {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  primary?: boolean;
  disabled?: boolean;
  loading?: boolean;
  onPress: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  return (
    <Pressable
      style={({ pressed }) => [
        styles.button,
        primary && styles.buttonPrimary,
        pressed && !disabled && styles.buttonPressed,
        disabled && styles.buttonDisabled,
      ]}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      {loading ? (
        <ActivityIndicator size="small" color="#fff" />
      ) : (
        <Ionicons name={icon} size={13} color={primary ? '#fff' : c.brand} />
      )}
      <Text style={[styles.btnText, primary && styles.btnTextPrimary]}>{label}</Text>
    </Pressable>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    card: {
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      padding: spacing.md,
      gap: 10,
    },
    header: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
    indexBadge: {
      width: 22,
      height: 22,
      borderRadius: 11,
      backgroundColor: c.brand,
      alignItems: 'center',
      justifyContent: 'center',
    },
    statusRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
    btnRow: { flexDirection: 'row', gap: 8 },
    button: {
      flex: 1,
      minHeight: 34,
      borderRadius: radii.sm,
      borderWidth: 1,
      borderColor: c.brandLight,
      backgroundColor: c.bgCard,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 4,
    },
    buttonPrimary: { backgroundColor: c.brand, borderColor: c.brand },
    buttonPressed: { opacity: 0.82 },
    buttonDisabled: { opacity: 0.55 },
    indexText: { fontSize: 12, fontWeight: '800', color: '#fff' },
    actionText: { flex: 1, fontSize: 14, lineHeight: 20, fontWeight: '600', color: c.labelPrimary },
    statusText: { fontSize: 12, color: c.labelSecondary },
    btnText: { fontSize: 12, fontWeight: '700', color: c.brand },
    btnTextPrimary: { color: '#fff' },
  });
}
