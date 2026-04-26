import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadows, spacing } from '@/constants/theme';
import type { DataPrompt } from '@/services/dataHealth';

interface Props {
  prompt: DataPrompt;
  onPress?: () => void;
  onDismiss?: () => void;
}

const META: Record<DataPrompt['severity'], { icon: keyof typeof Ionicons.glyphMap; color: string; bg: string }> = {
  blocking: { icon: 'alert-circle', color: '#FF453A', bg: '#FFE8E6' },
  useful: { icon: 'information-circle', color: '#FF9F0A', bg: '#FFF5E6' },
  optional: { icon: 'ellipse-outline', color: '#0A8F8F', bg: '#E6F5F5' },
};

export default function DataPromptCard({ prompt, onPress, onDismiss }: Props) {
  const meta = META[prompt.severity];

  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && onPress && styles.cardPressed]}
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={prompt.title}
    >
      <View style={[styles.iconWrap, { backgroundColor: meta.bg }]}>
        <Ionicons name={meta.icon} size={16} color={meta.color} />
      </View>
      <View style={styles.content}>
        <Text style={txt.title}>{prompt.title}</Text>
        <Text style={txt.body} numberOfLines={2}>{prompt.body}</Text>
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={16} color={colors.labelTertiary} /> : null}
      {onDismiss ? (
        <Pressable
          hitSlop={8}
          style={styles.dismiss}
          onPress={event => {
            event?.stopPropagation?.();
            onDismiss();
          }}
          accessibilityRole="button"
          accessibilityLabel="暂时忽略"
        >
          <Ionicons name="close" size={14} color={colors.labelTertiary} />
        </Pressable>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.md,
    marginBottom: 8,
    ...shadows.subtle,
  },
  cardPressed: { opacity: 0.86 },
  iconWrap: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  content: { flex: 1 },
  dismiss: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
});

const txt = {
  title: { fontSize: 14, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  body: { fontSize: 12, color: colors.labelSecondary, lineHeight: 17, marginTop: 2 } as TextStyle,
};
