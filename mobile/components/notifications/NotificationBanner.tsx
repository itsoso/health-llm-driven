import React, { useEffect, useRef, useState } from 'react';
import { Text, StyleSheet, TextStyle, TouchableOpacity } from 'react-native';
import Animated, { useSharedValue, useAnimatedStyle, withSpring, withDelay, runOnJS } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import type { Notification } from 'expo-notifications';
import { setOnForegroundNotification } from '@/hooks/useNotifications';
import { colors, spacing, radii, shadows } from '@/constants/theme';

const AUTO_DISMISS_MS = 4000;

export default function NotificationBanner({ onTap }: { onTap?: (n: Notification) => void }) {
  const insets = useSafeAreaInsets();
  const [current, setCurrent] = useState<Notification | null>(null);
  const translateY = useSharedValue(-120);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setOnForegroundNotification((n) => {
      setCurrent(n);
      translateY.value = withSpring(0, { damping: 18, stiffness: 160 });
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => dismiss(), AUTO_DISMISS_MS);
    });
    return () => {
      setOnForegroundNotification(null);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const dismiss = () => {
    translateY.value = withSpring(-120, { damping: 18 }, () => {
      runOnJS(setCurrent)(null);
    });
  };

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
  }));

  if (!current) return null;

  const title = current.request.content.title || '通知';
  const body = current.request.content.body || '';

  return (
    <Animated.View style={[styles.banner, { top: insets.top + 4 }, animStyle]}>
      <TouchableOpacity
        style={styles.inner}
        onPress={() => {
          dismiss();
          onTap?.(current);
        }}
        activeOpacity={0.85}
      >
        <Ionicons name="notifications" size={20} color={colors.brand} />
        <Text style={txt.title} numberOfLines={1}>{title}</Text>
        <Text style={txt.body} numberOfLines={2}>{body}</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: 'absolute', left: spacing.md, right: spacing.md, zIndex: 9999,
  },
  inner: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    flexDirection: 'column', gap: 2,
    ...shadows.medium,
  },
});

const txt = {
  title: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 4 } as TextStyle,
  body: { fontSize: 13, color: colors.labelSecondary } as TextStyle,
};
