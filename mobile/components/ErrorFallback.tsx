import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii, typography } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';

interface Props {
  error: Error;
  isOffline?: boolean;
  onRetry?: () => void;
}

export default function ErrorFallback({ error, isOffline, onRetry }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const icon = isOffline ? 'cloud-offline' : 'warning';
  const title = isOffline ? '无法连接网络' : '加载失败';
  const message = isOffline
    ? '请检查网络连接后重试'
    : error.message || '发生了未知错误';

  return (
    <View style={styles.container} testID="error-fallback">
      <Ionicons name={icon} size={48} color={c.labelTertiary} />
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      {onRetry && (
        <TouchableOpacity style={styles.retryBtn} onPress={onRetry} testID="retry-button">
          <Ionicons name="refresh" size={16} color="#fff" />
          <Text style={styles.retryText}>重试</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    container: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: spacing.xxl,
      gap: spacing.md,
    },
    title: {
      ...typography.titleSmall,
      color: c.labelPrimary,
    } as TextStyle,
    message: {
      ...typography.bodySmall,
      color: c.labelSecondary,
      textAlign: 'center',
    },
    retryBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      backgroundColor: c.brand,
      borderRadius: radii.sm,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      marginTop: spacing.md,
    },
    retryText: {
      fontSize: 14,
      fontWeight: '600',
      color: '#fff',
    } as TextStyle,
  });
}
