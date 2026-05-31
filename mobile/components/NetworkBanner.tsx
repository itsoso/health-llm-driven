import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { useNetworkStatus } from '../hooks/useNetworkStatus';

export default function NetworkBanner() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { isOnline } = useNetworkStatus();

  if (isOnline) return null;

  return (
    <View style={styles.banner} testID="network-banner">
      <Ionicons name="cloud-offline" size={14} color="#fff" />
      <Text style={styles.text}>离线模式 — 显示缓存数据</Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    banner: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: c.labelSecondary,
      paddingVertical: spacing.xs + 2,
    },
    text: {
      fontSize: 12,
      fontWeight: '600',
      color: '#fff',
    } as TextStyle,
  });
}
