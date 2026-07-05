import React from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
  revaSpacing,
} from '../constants/revaTheme';

type InsightRoute =
  | '/my-progress'
  | '/weekly-briefing'
  | '/monthly-reports'
  | '/metabolic-profile'
  | '/intervention-cycle'
  | '/biological-age'
  | '/longevity-next'
  | '/liver-trend'
  | '/indicator-history';

type InsightItem = {
  title: string;
  subtitle: string;
  route: InsightRoute;
  icon: React.ComponentProps<typeof Ionicons>['name'];
  tone: 'green' | 'blue' | 'amber' | 'rose';
};

type InsightGroup = {
  title: string;
  subtitle: string;
  items: InsightItem[];
};

const TONE: Record<InsightItem['tone'], { fg: string; bg: string }> = {
  green: { fg: C.green500, bg: C.green50 },
  blue: { fg: '#2F6F9F', bg: '#EAF3F8' },
  amber: { fg: '#9A661E', bg: '#F7EFE2' },
  rose: { fg: '#A34E64', bg: '#F7E9ED' },
};

const INSIGHT_GROUPS: InsightGroup[] = [
  {
    title: '进展与闭环',
    subtitle: '看小巴建议是否真的带来改善。',
    items: [
      {
        title: '我的进度',
        subtitle: '建议接受、完成、验证和改善追踪',
        route: '/my-progress',
        icon: 'trending-up',
        tone: 'green',
      },
      {
        title: '本周建议',
        subtitle: '本周复盘、优先行动和风险提醒',
        route: '/weekly-briefing',
        icon: 'calendar-outline',
        tone: 'blue',
      },
      {
        title: '月度复盘',
        subtitle: '长期趋势、执行质量和下月重点',
        route: '/monthly-reports',
        icon: 'file-tray-full-outline',
        tone: 'amber',
      },
    ],
  },
  {
    title: '代谢与抗衰',
    subtitle: '把长期健康画像收束到可验证的下一步。',
    items: [
      {
        title: '代谢健康画像',
        subtitle: '体重、血压、血糖、血脂和生活方式画像',
        route: '/metabolic-profile',
        icon: 'pulse-outline',
        tone: 'green',
      },
      {
        title: '代谢干预 · 90 天',
        subtitle: '阶段目标、行动节奏和验证指标',
        route: '/intervention-cycle',
        icon: 'refresh-outline',
        tone: 'blue',
      },
      {
        title: '生物年龄',
        subtitle: '用可追踪指标解释当前衰老风险',
        route: '/biological-age',
        icon: 'hourglass-outline',
        tone: 'amber',
      },
      {
        title: '抗衰下一步',
        subtitle: '优先补最能提升判断力的数据',
        route: '/longevity-next',
        icon: 'leaf-outline',
        tone: 'green',
      },
      {
        title: '肝脏趋势',
        subtitle: '肝功能相关指标和行动建议复盘',
        route: '/liver-trend',
        icon: 'medical-outline',
        tone: 'rose',
      },
    ],
  },
  {
    title: '指标与趋势',
    subtitle: '从单项趋势进入小巴解读和后续追问。',
    items: [
      {
        title: '指标趋势',
        subtitle: '体重、血压、HRV、睡眠等历史趋势',
        route: '/indicator-history',
        icon: 'analytics-outline',
        tone: 'blue',
      },
    ],
  },
];

export default function InsightsScreen() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="返回"
        >
          <Ionicons name="chevron-back" size={24} color={C.ink1} />
        </Pressable>
        <Text style={txt.headerTitle}>健康分析</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.intro}>
          <Text style={txt.kicker}>Insights</Text>
          <Text style={txt.title}>长期分析放在这里，今日只保留当下行动。</Text>
          <Text style={txt.subtitle}>
            这些入口用于复盘、趋势和长期画像；首页今日继续交给小巴按情境动态生成。
          </Text>
        </View>

        {INSIGHT_GROUPS.map(group => (
          <View key={group.title} style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={txt.sectionTitle}>{group.title}</Text>
              <Text style={txt.sectionSubtitle}>{group.subtitle}</Text>
            </View>
            <View style={styles.card}>
              {group.items.map((item, index) => (
                <InsightRow
                  key={item.route}
                  item={item}
                  isLast={index === group.items.length - 1}
                  onPress={() => openInsightRoute(router, item.route)}
                />
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function openInsightRoute(router: ReturnType<typeof useRouter>, route: InsightRoute) {
  switch (route) {
    case '/my-progress':
      router.push('/my-progress' as any);
      break;
    case '/weekly-briefing':
      router.push('/weekly-briefing' as any);
      break;
    case '/monthly-reports':
      router.push('/monthly-reports' as any);
      break;
    case '/metabolic-profile':
      router.push('/metabolic-profile' as any);
      break;
    case '/intervention-cycle':
      router.push('/intervention-cycle' as any);
      break;
    case '/biological-age':
      router.push('/biological-age' as any);
      break;
    case '/longevity-next':
      router.push('/longevity-next' as any);
      break;
    case '/liver-trend':
      router.push('/liver-trend' as any);
      break;
    case '/indicator-history':
      router.push('/indicator-history' as any);
      break;
  }
}

function InsightRow({
  item,
  isLast,
  onPress,
}: {
  item: InsightItem;
  isLast: boolean;
  onPress: () => void;
}) {
  const tone = TONE[item.tone];
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        !isLast && styles.rowDivider,
        pressed && styles.pressed,
      ]}
      accessibilityRole="button"
    >
      <View style={[styles.iconBox, { backgroundColor: tone.bg }]}>
        <Ionicons name={item.icon} size={18} color={tone.fg} />
      </View>
      <View style={styles.rowText}>
        <Text style={txt.rowTitle}>{item.title}</Text>
        <Text style={txt.rowSubtitle} numberOfLines={2}>{item.subtitle}</Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={C.ink3} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper2 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s2,
  },
  backBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
  },
  headerSpacer: { width: 40 },
  content: {
    paddingHorizontal: revaSpacing.s5,
    paddingBottom: 120,
  },
  intro: {
    paddingTop: revaSpacing.s3,
    paddingBottom: revaSpacing.s3,
  },
  section: {
    marginTop: revaSpacing.s4,
  },
  sectionHeader: {
    marginBottom: revaSpacing.s2,
    gap: 3,
  },
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    overflow: 'hidden',
    ...revaShadows.sm,
  },
  row: {
    minHeight: 72,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: revaSpacing.s5,
    paddingVertical: 12,
  },
  rowDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  iconBox: {
    width: 36,
    height: 36,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowText: {
    flex: 1,
    minWidth: 0,
  },
  pressed: {
    opacity: 0.72,
  },
});

const txt = {
  headerTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 17,
    fontWeight: '600',
    color: C.ink1,
    flex: 1,
    textAlign: 'center',
  } as TextStyle,
  kicker: {
    fontFamily: revaFonts.mono,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0,
    color: C.green500,
    textTransform: 'uppercase',
  } as TextStyle,
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 24,
    lineHeight: 31,
    fontWeight: '800',
    color: C.ink1,
    marginTop: 6,
  } as TextStyle,
  subtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 21,
    color: C.ink2,
    marginTop: 8,
  } as TextStyle,
  sectionTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 16,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  sectionSubtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink3,
  } as TextStyle,
  rowTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  rowSubtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink3,
    marginTop: 3,
  } as TextStyle,
};
