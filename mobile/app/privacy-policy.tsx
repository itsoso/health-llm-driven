import React, { useMemo } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

const sections = [
  {
    title: '我们收集什么',
    body:
      '为了生成健康建议,应用会处理你主动记录的症状、饮食、运动、睡眠、用药、补剂、化验、基因报告摘要,以及你授权同步的 Apple Health、Garmin、Rokid 等设备数据。',
  },
  {
    title: '这些数据怎么用',
    body:
      '数据用于健康时间线、提醒、风险提示、复盘、模型个性化和跨设备一致性检查。位置与天气信息只用于空气质量、户外运动、睡眠环境和日程提醒等健康场景。',
  },
  {
    title: 'AI 与第三方模型',
    body:
      '当你请求 AI 分析时,系统会按最小必要原则向所选模型提供上下文。我们不会把你的个人健康数据出售给广告平台或数据经纪方。',
  },
  {
    title: '安全与隔离',
    body:
      '账号、Token、健康数据和设备凭证按敏感级别处理。服务端接口必须按用户隔离数据,敏感操作保留审计记录;本地认证信息优先存放在系统安全存储中。',
  },
  {
    title: '你的控制权',
    body:
      '你可以在系统设置或应用内断开设备授权,停止同步 Apple Health、Garmin、Rokid 等来源。需要导出、删除或更正数据时,可通过应用内反馈或注册邮箱联系处理。',
  },
];

export default function PrivacyPolicyScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconButton} accessibilityRole="button" accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>隐私政策</Text>
        <View style={styles.iconButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons name="shield-checkmark-outline" size={24} color={c.brand} />
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={txt.heroTitle}>健康数据优先按最小必要原则使用</Text>
            <Text style={txt.heroBody}>
              这份摘要说明移动端当前主要数据用途和控制方式。正式上线、接入支付或面向更多用户前,仍需要同步完整法律文本。
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          {sections.map((section, index) => (
            <View key={section.title} style={[styles.section, index > 0 && styles.sectionBorder]}>
              <Text style={txt.sectionTitle}>{section.title}</Text>
              <Text style={txt.sectionBody}>{section.body}</Text>
            </View>
          ))}
        </View>

        <Text style={txt.footer}>最近更新: 2026-06-23</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  iconButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
  hero: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'flex-start',
    backgroundColor: c.brandLight,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    padding: spacing.lg,
  },
  heroIcon: {
    width: 40,
    height: 40,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.bgCard,
  },
  card: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    overflow: 'hidden',
  },
  section: { paddingHorizontal: spacing.lg, paddingVertical: spacing.lg, gap: 6 },
  sectionBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '700', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  heroTitle: { fontSize: 16, fontWeight: '800', color: c.labelPrimary, lineHeight: 22 } as TextStyle,
  heroBody: { fontSize: 13, fontWeight: '500', color: c.labelSecondary, lineHeight: 20, marginTop: 6 } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sectionBody: { fontSize: 14, fontWeight: '500', color: c.labelSecondary, lineHeight: 21 } as TextStyle,
  footer: { fontSize: 12, fontWeight: '600', color: c.labelTertiary, textAlign: 'center', lineHeight: 18 } as TextStyle,
});
