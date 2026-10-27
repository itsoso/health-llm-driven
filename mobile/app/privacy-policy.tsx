import { backOrChat } from '../utils/backOrChat';
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
      '天气、空气质量和户外环境功能仅在你主动授权并使用时读取当次精确位置；每日 GPS 行程另需你每天主动开启。你主动上传的图片用于生成记录草稿或分析;主动使用语音输入时,语音音频会通过已认证服务发送给云端语音识别服务以生成文字。音频不用于广告、营销或追踪。',
  },
  {
    title: '可选城市足迹与分享',
    body:
      '“这一路”中的城市足迹由你为已有记录确认城市和日期。点击单次定位时，设备读取位置并通过系统地理编码服务解析城市；城市标注接口只保存确认后的城市，不保存精确坐标，也不会修改天气定位。拒绝定位仍可手动填写，历史照片不会自动套用当前位置。你可以更正或删除单条足迹；撤回定位权限不会自动删除已确认内容。分享前请核对城市和照片里的地址、人脸、二维码；只导出你选择的片段，默认不带聊天原文、健康指标和精确时间。已保存到相册或交给外部 App 的图片无法由我们自动撤回。',
  },
  {
    title: '可选每日 GPS 行程',
    body:
      '每日 GPS 行程默认关闭；仅支持此功能的新版应用可使用。你需每天主动开启并确认用途和保留期限，再单独授予系统定位权限，次日不会自动重启。开启当天，锁屏或切到后台仍会尽力采集；系统调度、信号和权限可能造成缺口，不保证连续实时。采集截止为开启时区当天结束，最长 24 小时；系统休眠时，任务会在下次回调或打开应用时停止，截止后的新位置不保存。采集的精确坐标、采样时间、定位精度和可用速度用于私人行程复盘。原始轨迹和修正内容加密暂存本机并同步至按账号隔离的云端，路线、停留、估算里程和交通方式复盘按需生成。行程数据不发送给 AI，不用于广告、营销或公开分享，也不用于健康推断。',
  },
  {
    title: '每日行程的保留与删除',
    body:
      '轨迹与复盘从开启时起保留 1 或 7 天（默认 7 天）。到期后不可读取，服务器随后定时物理清理；本机在下次运行时清理到期副本。暂停、结束或撤回定位权限会停止后续采集，不会自动删除历史行程。删除行程会清除其原始点、修正和复盘；离线时会显示云端删除尚未确认。删除或到期后，仅保留防止重复请求恢复已删除行程的随机请求标识和必要安全审计，不含 GPS、地点名称或轨迹内容，随账号删除处理。',
  },
  {
    title: '可选餐厅地点查询',
    body:
      '在饮食分享地点编辑器中，你可单独同意本次高德地图查询：定位时，经小气候服务器向高德地图发送当次精确坐标；搜索时，仅发送主动提交的搜索词和城市（如有）。用途是查找附近餐厅和地址，不向高德发送账号标识、照片或健康记录。小气候不保存查询坐标、搜索词或候选，不用于广告或追踪。系统定位权限不代表同意第三方查询；拒绝仍可手填。关闭编辑器、撤回本次查询或切到后台会停止后续查询；已发出的请求无法收回。附近餐厅只是候选，不是到店证明；历史餐食不会自动使用当前位置。地点名称经你确认后才放入分享图片和文字，不写入饮食记录或足迹。',
  },
  {
    title: '产品交互与可靠性',
    body:
      '客户端事件会与登录账号关联,用于产品交互分析和可靠性改进。必要的崩溃和性能数据默认不与账号健康身份关联;这些数据均不用于广告或营销。',
  },
  {
    title: 'AI 与第三方模型',
    body:
      '首次使用前,App 会单独展示第三方 AI 模型服务的接收方、数据和用途。当前接收方为阿里云百炼（含通义千问、语音及图像模型）;采用 Apple 系统语音识别时,语音可能由设备或 Apple 服务器处理。只有明确同意并保存授权后,才会发送本次任务所需的对话、主动提交的图片/文件/语音及相关健康记录、个人资料和对话上下文。登录或同意隐私政策不代表同意 AI 共享。模型服务不用于第三方广告、营销画像或出售。',
  },
  {
    title: '安全与隔离',
    body:
      '账号、Token、健康数据和设备凭证按敏感级别处理。服务端接口必须按用户隔离数据,敏感操作保留审计记录;本地认证信息优先存放在系统安全存储中。',
  },
  {
    title: '你的控制权',
    body:
      '你可以在“设置 -> AI 数据共享”查看和撤回 AI 授权。拒绝或撤回后停止后续第三方 AI 共享,仍可查看和管理非 AI 记录、隐私与账号;已发送的数据无法自动收回。你可以断开设备授权以停止同步,也可在“我 -> 账号与隐私 -> 删除账号与数据”发起删除请求;App 会显示删除请求编号和处理状态,通常 7 天内完成。',
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
        <TouchableOpacity onPress={() => backOrChat(router)} style={styles.iconButton} accessibilityRole="button" accessibilityLabel="返回">
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
              这份政策说明主要数据用途和控制方式。具体功能是否可用，以所安装的应用版本和你的授权状态为准。
            </Text>
            <Text style={txt.heroBody}>最近更新: 2026-10-18</Text>
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

        <Text style={txt.footer}>生效日期: 2026-08-05 · 最近更新: 2026-10-18</Text>
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
