import React, { useMemo } from 'react';
import { StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, spacing, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

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
  title, icon, iconColor, iconBg,
  rightAccessory, children, style, accentColor,
}: Props) {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);

  return (
    <View
      style={[
        styles.card,
        accentColor && { borderLeftWidth: 3, borderLeftColor: accentColor },
        style,
      ]}
    >
      <View style={styles.header}>
        {icon && (
          <View style={[styles.iconCircle, { backgroundColor: iconBg ?? c.brandLight }]}>
            <Ionicons name={icon} size={16} color={iconColor ?? c.brand} />
          </View>
        )}
        <Text style={styles.title}>{title}</Text>
        {rightAccessory}
      </View>
      {children}
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      marginBottom: spacing.md,
      // dark mode 下 shadow 不可见, 用 hairline 边框做卡片分隔, 同 DashboardCard
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
          }),
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
      color: c.labelPrimary,
      flex: 1,
    } as TextStyle,
  });
}
