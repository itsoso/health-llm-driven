import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography, spacing, radii, shadows } from '@/constants/theme';

interface Props {
  title: string;
  icon?: keyof typeof Ionicons.glyphMap;
  iconColor?: string;
  iconBg?: string;
  rightAccessory?: React.ReactNode;
  children: React.ReactNode;
  style?: ViewStyle;
  accentColor?: string;
}

export default function HealthCard({
  title, icon, iconColor = colors.brand, iconBg = colors.brandLight,
  rightAccessory, children, style, accentColor,
}: Props) {
  return (
    <View style={[styles.card, accentColor && { borderLeftWidth: 3, borderLeftColor: accentColor }, style]}>
      <View style={styles.header}>
        {icon && (
          <View style={[styles.iconCircle, { backgroundColor: iconBg }]}>
            <Ionicons name={icon} size={16} color={iconColor} />
          </View>
        )}
        <Text style={styles.title}>{title}</Text>
        {rightAccessory}
      </View>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    ...shadows.subtle,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  iconCircle: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    ...typography.titleSmall,
    color: colors.labelPrimary,
    flex: 1,
  },
});
