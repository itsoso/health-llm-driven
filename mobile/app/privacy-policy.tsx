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
    title: '位置、图片、语音音频和诊断数据',
    body:
      '仅当你在相关功能中主动授权并使用定位时,小巴读取精确位置来查询天气、空气质量和户外环境,不会持续或后台定位。你主动上传的图片用于生成记录草稿或分析;主动使用语音输入时,语音音频会通过已认证服务发送给云端语音识别服务以生成文字。音频不用于广告、营销或追踪。',
  },
  {
    title: '产品交互与可靠性',
    body:
      '客户端事件会与登录账号关联,用于产品交互分析和可靠性改进。必要的崩溃和性能数据默认不与账号健康身份关联;这些数据均不用于广告或营销。',
  },
  {
    title: 'AI 与第三方模型',
    body:
      '当你请求 AI 分析或对话时,系统会按最小必要原则向完成任务所需的 AI 模型服务提供上下文。模型服务只用于完成该次对话、识别、总结或建议,不用于第三方广告、营销画像或出售。',
  },
  {
    title: '安全与隔离',
    body:
      '账号、Token、健康数据和设备凭证按敏感级别处理。服务端接口必须按用户隔离数据,敏感操作保留审计记录;本地认证信息优先存放在系统安全存储中。',
  },
  {
    title: '你的控制权',
    body:
      '你可以在应用内断开设备授权,停止同步 Apple Health、Garmin 等来源。你也可以在“我 -> 账号与隐私 -> 删除账号与数据”中发起请求;App 会显示删除请求编号和处理状态,通常 7 天内完成。',
  },
  {
    title: '医疗边界',
    body:
      '小巴提供健康记录、趋势解读和生活方式建议,不提供诊断、急救分诊、处方、治疗方案或药物剂量调整。出现红旗症状或医生要求复查时,请以医生和急救服务为准。',
  },
  {
    title: '运营方与联系',
    body:
      '小巴由睿为健康运营。如需访问、更正、删除数据或撤回授权,请使用 App 内入口,或联系 support@executor.life。',
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
              这份政策说明移动端当前主要数据用途和控制方式,并与 App Store 隐私标签和权限说明保持一致。
            </Text>
            <Text style={txt.heroBody}>最近更新: 2026-08-05</Text>
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

        <Text style={txt.footer}>生效及最近更新日期: 2026-07-14</Text>
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
