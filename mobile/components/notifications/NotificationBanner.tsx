import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Text, StyleSheet, TextStyle, TouchableOpacity } from 'react-native';
import Animated, { useSharedValue, useAnimatedStyle, withSpring, runOnJS } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import type { Notification } from 'expo-notifications';
import { setOnForegroundNotification } from '../../hooks/useNotifications';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

const AUTO_DISMISS_MS = 4000;

export default function NotificationBanner({ onTap }: { onTap?: (n: Notification) => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const insets = useSafeAreaInsets();
  const [current, setCurrent] = useState<Notification | null>(null);
  const translateY = useSharedValue(-120);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentIdentifierRef = useRef<string | null>(null);

  const clearCurrentIfMatching = useCallback((identifier: string) => {
    setCurrent((value) => {
      if (value?.request.identifier !== identifier) return value;
      currentIdentifierRef.current = null;
      return null;
    });
  }, []);

  const dismiss = useCallback((identifier?: string | null) => {
    const targetIdentifier = identifier || currentIdentifierRef.current;
    if (!targetIdentifier) return;
    translateY.value = withSpring(-120, { damping: 18 }, (finished) => {
      if (finished) {
        runOnJS(clearCurrentIfMatching)(targetIdentifier);
      }
    });
  }, [clearCurrentIfMatching, translateY]);

  useEffect(() => {
    setOnForegroundNotification((n) => {
      const identifier = n.request.identifier;
      currentIdentifierRef.current = identifier;
      setCurrent(n);
      translateY.value = withSpring(0, { damping: 18, stiffness: 160 });
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => dismiss(identifier), AUTO_DISMISS_MS);
    });
    return () => {
      setOnForegroundNotification(null);
      if (timerRef.current) clearTimeout(timerRef.current);
      currentIdentifierRef.current = null;
    };
  }, [dismiss, translateY]);

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
          const tappedNotification = current;
          dismiss(tappedNotification.request.identifier);
          onTap?.(tappedNotification);
        }}
        activeOpacity={0.85}
      >
        <Ionicons name="notifications" size={20} color={c.brand} />
        <Text style={styles.title} numberOfLines={1}>{title}</Text>
        <Text style={styles.body} numberOfLines={2}>{body}</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    banner: {
      position: 'absolute', left: spacing.md, right: spacing.md, zIndex: 9999,
    },
    inner: {
      backgroundColor: c.bgCard, borderRadius: radii.lg,
      paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
      flexDirection: 'column', gap: 2,
      ...shadows.medium,
    },
    title: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, marginTop: 4 } as TextStyle,
    body: { fontSize: 13, color: c.labelSecondary } as TextStyle,
  });
}
