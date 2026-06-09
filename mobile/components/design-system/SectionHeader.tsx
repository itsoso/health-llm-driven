import React from 'react';
import { View, StyleSheet } from 'react-native';
import { spacing } from '../../constants/theme';
import AppText from './AppText';

interface Props {
  title: string;
  action?: string;
  onAction?: () => void;
}

// 2026-05-31: 之前静态 import colors → 暗色不切换 (audit 第 2 类). 改走 AppText (useTheme).
export default function SectionHeader({ title, action, onAction }: Props) {
  return (
    <View style={styles.row}>
      <AppText variant="titleMedium">{title}</AppText>
      {action ? (
        <AppText variant="bodySmall" tone="brand" onPress={onAction}>
          {action} &gt;
        </AppText>
      ) : null}
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
});
