import React, { useCallback, useEffect, useMemo } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { type ColorPalette, useTheme } from '../../hooks/useTheme';

export default function SharedDeepLinkScreen() {
  const { shareToken } = useLocalSearchParams<{ shareToken?: string }>();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const openChat = useCallback(() => {
    const token = typeof shareToken === 'string' ? shareToken : '';
    router.replace({
      pathname: '/(tabs)/chat',
      params: token
        ? {
            badge: '分享内容',
            prompt: `打开这条健康分享：https://health.executor.life/shared/${token}`,
          }
        : undefined,
    } as any);
  }, [shareToken]);

  useEffect(() => {
    const timer = setTimeout(openChat, 250);
    return () => clearTimeout(timer);
  }, [openChat]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Ionicons name="sparkles" size={28} color={c.brand} />
        <Text style={styles.title}>正在打开小巴</Text>
        <Text style={styles.subtitle}>如果没有自动跳转, 可以手动进入对话继续查看。</Text>
        <ActivityIndicator color={c.brand} style={styles.spinner} />
        <TouchableOpacity style={styles.button} onPress={openChat} activeOpacity={0.85}>
          <Text style={styles.buttonText}>进入 App</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    container: {
      flex: 1,
      justifyContent: 'center',
      padding: 24,
      backgroundColor: c.bgPrimary,
    },
    card: {
      alignItems: 'center',
      borderRadius: 18,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      backgroundColor: c.bgCard,
      padding: 24,
    },
    title: {
      marginTop: 12,
      fontSize: 18,
      fontWeight: '700',
      color: c.labelPrimary,
    },
    subtitle: {
      marginTop: 8,
      textAlign: 'center',
      fontSize: 13,
      lineHeight: 20,
      color: c.labelSecondary,
    },
    spinner: {
      marginTop: 18,
    },
    button: {
      marginTop: 18,
      borderRadius: 14,
      backgroundColor: c.brand,
      paddingHorizontal: 24,
      paddingVertical: 12,
    },
    buttonText: {
      color: '#fff',
      fontSize: 15,
      fontWeight: '700',
    },
  });
}
