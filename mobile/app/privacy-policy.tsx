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
    title: '我们读取和记录什么',
    body:
      '为了生成健康时间线和行动建议,应用会处理你主动记录的症状、饮食、运动、睡眠、用药、补剂、化验、体检报告和基因报告摘要,以及你授权同步的 Apple Health、Garmin 等设备数据。',
  },
  {
    title: 'HealthKit 数据怎么用',
    body:
      'Apple Health / HealthKit 数据仅用于身体状态展示、自动同步、趋势复盘、提醒和个性化健康行动建议。我们不会把 HealthKit 数据用于广告、营销画像或出售给数据经纪方。',
  },
  {
    title: 'AI 与第三方模型',
    body:
      '当你请求 AI 分析或对话时,系统会按最小必要原则向所选模型提供上下文。AI 用于解释、总结和生成行动草稿,不能替代医生诊断、治疗、处方或药物剂量调整。',
  },
  {
    title: '安全与隔离',
    body:
      '账号、Token、健康数据和设备凭证按敏感级别处理。服务端接口必须按用户隔离数据,敏感操作保留审计记录;本地认证信息优先存放在系统安全存储中。',
  },
  {
    title: '你的控制权',
    body:
      '你可以在应用内断开设备授权,停止同步 Apple Health、Garmin 等来源。你也可以在“我 -> 账号与隐私”中发起删除账号与数据请求;请求会进入可审计处理流程,通常 7 天内完成。',
  },
  {
    title: '医疗边界',
    body:
      '小巴提供健康记录、趋势解读和生活方式建议,不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。出现红旗症状或医生要求复查时,请以医生和急救服务为准。',
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
              这份摘要说明移动端当前主要数据用途和控制方式。完整法律文本、App Store 隐私填报和权限说明需要保持一致。
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

        <Text style={txt.footer}>最近更新: 2026-06-28</Text>
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
