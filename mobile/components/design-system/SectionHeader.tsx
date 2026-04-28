import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, typography, spacing } from '../../constants/theme';

interface Props {
  title: string;
  action?: string;
  onAction?: () => void;
}

export default function SectionHeader({ title, action, onAction }: Props) {
  return (
    <View style={styles.row}>
      <Text style={styles.title}>{title}</Text>
      {action && (
        <Text style={styles.action} onPress={onAction}>{action} &gt;</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
    paddingHorizontal: 2,
  },
  title: {
    ...typography.titleMedium,
    color: colors.labelPrimary,
  },
  action: {
    ...typography.bodySmall,
    color: colors.brand,
  },
});
