import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaFonts,
} from '@/constants/revaTheme';
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
      <Ionicons name="chatbubble-ellipses-outline" size={16} color={C.green500} />
      <Text style={styles.text}>{label}</Text>
      <Ionicons name="chevron-forward" size={15} color={C.green500} />
    </Pressable>
  );
}

// Reva 设计语言:绿色一等强调 link,暖绿底 + 绿边 + 绿字。
const styles = StyleSheet.create({
  link: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green500,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 12,
  },
  text: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '600',
    color: C.green500,
  } as TextStyle,
});
