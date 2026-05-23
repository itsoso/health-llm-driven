import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { radii, spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';
import {
  pushChatWithContext,
  type AgentContextPayload,
  type ChatContextRouteInput,
} from '@/utils/agentContext';

interface Props extends ChatContextRouteInput {
  label: string;
  accessibilityLabel?: string;
  style?: ViewStyle | ViewStyle[];
}

export default function AgentFeedbackLink({
  label,
  prompt,
  context,
  badge,
  newChat,
  accessibilityLabel,
  style,
}: Props) {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  return (
    <Pressable
      onPress={() => pushChatWithContext(router, {
        prompt,
        context: context as AgentContextPayload | string,
        badge,
        newChat,
      })}
      style={({ pressed }) => [
        styles.link,
        style,
        pressed && { opacity: 0.75 },
      ]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
    >
      <Ionicons name="chatbubble-ellipses-outline" size={16} color={c.brand} />
      <Text style={styles.text}>{label}</Text>
      <Ionicons name="chevron-forward" size={15} color={c.brand} />
    </Pressable>
  );
}

function createStyles(c: ReturnType<typeof useTheme>['c']) {
  return StyleSheet.create({
    link: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.brand,
      borderRadius: radii.md,
      backgroundColor: c.brandLight,
      paddingHorizontal: spacing.md,
      paddingVertical: 12,
    },
    text: {
      flex: 1,
      fontSize: 14,
      fontWeight: '600',
      color: c.brand,
    } as TextStyle,
  });
}
