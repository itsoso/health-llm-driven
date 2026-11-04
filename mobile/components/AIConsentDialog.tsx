import React, { useEffect, useRef, useSyncExternalStore } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, Linking, Alert } from 'react-native';
import { usePathname, useRouter, useRootNavigationState } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../hooks/useTheme';
import { getConsentPresentation, subscribeConsentPresentation } from '../services/aiConsentPresentation';

export function AIConsentDialog() {
  const presentation = useSyncExternalStore(subscribeConsentPresentation, getConsentPresentation, getConsentPresentation);
  const { c } = useTheme();
  if (!presentation) return null;
  const { policy, mode, choose } = presentation;
  const managing = mode === 'manage';
  return (
      <SafeAreaView style={[styles.screen, { backgroundColor: c.bgPrimary }]}>
        <View style={styles.heading}>
          <Text accessibilityRole="header" style={[styles.title, { color: c.labelPrimary }]}>AI 数据共享</Text>
          <Text style={[styles.body, { color: c.labelSecondary }]}>{managing ? '当前账号已授权，可随时撤回。' : '使用 AI 前，请单独确认。登录或系统权限不代表同意共享。'}</Text>
        </View>
        <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
          <Text style={[styles.section, { color: c.labelPrimary }]}>谁接收数据</Text>
          {policy.recipients.map(recipient => <View key={recipient.id} style={styles.recipient}>
            <Text style={[styles.name, { color: c.labelPrimary }]}>{recipient.name}</Text>
            <Text style={[styles.body, { color: c.labelSecondary }]}>{recipient.purpose}</Text>
          </View>)}
          <Text style={[styles.section, { color: c.labelPrimary }]}>发送哪些数据</Text>
          {policy.data_types.map(type => <Text key={type} style={[styles.body, { color: c.labelSecondary }]}>• {type}</Text>)}
          <Text style={[styles.section, { color: c.labelPrimary }]}>用于什么</Text>
          <Text style={[styles.body, { color: c.labelSecondary }]}>{policy.purpose}</Text>
          <Text style={[styles.section, { color: c.labelPrimary }]}>由你控制</Text>
          <Text style={[styles.body, { color: c.labelSecondary }]}>仅在同意并保存授权后发送。暂不使用仍可查看和管理非 AI 记录、隐私与账号。你可在“设置 → AI 数据共享”撤回，停止后续发送；已发送的数据无法自动收回。HealthKit、麦克风和系统语音权限另行申请。</Text>
          <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL('https://health.executor.life/privacy').catch(() => Alert.alert('无法打开隐私政策', '请稍后重试，或在个人中心查看隐私政策。')); }} style={styles.link}>
            <Text style={[styles.name, { color: c.brand }]}>查看完整隐私政策</Text>
          </Pressable>
        </ScrollView>
        <View style={[styles.actions, { borderTopColor: c.separator }]}>
          <Pressable accessibilityRole="button" onPress={() => choose(managing ? 'keep' : 'decline')} style={[styles.button, { backgroundColor: c.bgCard }]}>
            <Text style={[styles.name, { color: c.labelPrimary }]}>{managing ? '保持授权并返回' : '暂不使用'}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => choose(managing ? 'revoke' : 'accept')} style={[styles.button, { backgroundColor: c.brand }]}>
            <Text style={[styles.name, { color: c.bgCard }]}>{managing ? '撤回授权' : '同意并继续'}</Text>
          </Pressable>
        </View>
      </SafeAreaView>
  );
}
const styles = StyleSheet.create({
  screen: { flex: 1 }, heading: { padding: 24, gap: 12 }, title: { fontSize: 24, fontWeight: '700' },
  scroll: { flex: 1 }, content: { paddingHorizontal: 24, paddingBottom: 24, gap: 12 },
  section: { fontSize: 18, fontWeight: '700', marginTop: 12 }, name: { fontSize: 16, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 25 }, recipient: { gap: 6 }, link: { paddingVertical: 12 },
  actions: { padding: 20, gap: 12, borderTopWidth: StyleSheet.hairlineWidth },
  button: { minHeight: 48, padding: 14, borderRadius: 12, alignItems: 'center' },
});

export function AIConsentNavigation() {
  const presentation = useSyncExternalStore(subscribeConsentPresentation, getConsentPresentation, getConsentPresentation);
  const router = useRouter();
  const path = usePathname();
  const navigation = useRootNavigationState();
  const opening = useRef(false);
  useEffect(() => {
    if (!navigation?.key) return;
    if (presentation && path !== '/ai-consent' && !opening.current) {
      opening.current = true;
      router.push('/ai-consent');
    } else if (!presentation && path === '/ai-consent') {
      opening.current = false;
      if (router.canGoBack()) router.back(); else router.replace('/(tabs)/chat');
    } else if (path === '/ai-consent' || !presentation) {
      opening.current = false;
    }
  }, [presentation, path, navigation?.key, router]);
  return null;
}
