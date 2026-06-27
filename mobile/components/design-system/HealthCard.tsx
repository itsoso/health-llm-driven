import React from 'react';
import { StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

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
          <View style={[styles.iconCircle, { backgroundColor: iconBg ?? C.green50 }]}>
            <Ionicons name={icon} size={16} color={iconColor ?? C.green500} />
          </View>
        )}
        <Text style={styles.title}>{title}</Text>
        {rightAccessory}
      </View>
      {children}
    </View>
  );
}

// Reva 设计语言:暖白 surface / ink 文字 / r-lg 18 / light-first 单态软阴影。
const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    marginBottom: revaSpacing.s3,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    marginBottom: revaSpacing.s3,
  },
  iconCircle: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 23,
    color: C.ink1,
    flex: 1,
  } as TextStyle,
});
