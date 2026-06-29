import React from 'react';
import { Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { useTheme } from '../../hooks/useTheme';
import { useGPSOnboardingPrompt } from '../../hooks/useGPSOnboardingPrompt';
import {
  FLOATING_TAB_BAR_BAR_HEIGHT,
  FLOATING_TAB_BAR_PADDING_TOP,
  FLOATING_TAB_BAR_MIN_BOTTOM,
} from '../../hooks/useFloatingTabBarHeight';

/**
 * Phase 4 (2026-05-29): Tab 3 → 4. 加 "我" tab — settings.tsx 已是完整 hub
 * (20+ 入口) 但只能通过 EnvironmentCard 齿轮进; 暴露成 tab 解决深页"无家可回".
 * 同一组件靠 router.canGoBack() 切 "设置"/"我" 标题.
 *
 * Phase 3 (2026-05-14): Tab 2 → 3. "+" FAB 推进为第三 Tab "记录", 底部 3 个 tab
 * (今日 / 会诊 / 记录), 移除右下悬浮 "+" 按钮.
 *
 * Phase 2 (2026-05-11): Tab 收敛 4 → 2 (今日 + 会诊).
 *
 * 隐藏 (href:null, 仍可程序化导航):
 *   - alerts (内容已合并进首页, 但仍保留独立路由便于"查看全部")
 *   - record (改成首页 FAB, 但旧入口保留)
 *   - journal (低频, 移到设置或首页折叠区)
 *
 * 重新暴露:
 *   - chat (原 hidden, 现在是第二 Tab)
 *   - me (settings 复用, 现在是第四 Tab)
 *
 * 备份: 旧 layout 在 git history. 文件没动, 只改 Tabs.Screen.options.href.
 */

export default function TabLayout() {
  const { c } = useTheme();
  // 用户登录后第一次进 tabs 时, 一次性问一下 GPS 权限. 不再弹.
  const gpsPrompt = useGPSOnboardingPrompt(true);

  return (
    <View style={{ flex: 1 }}>
      <Tabs
        tabBar={(props) => <RevaTabBar {...props} />}
        screenOptions={{ headerShown: false }}
      >
        <Tabs.Screen name="index" options={createTabScreenOptions('index')} />
        <Tabs.Screen name="chat" options={createTabScreenOptions('chat')} />
        <Tabs.Screen name="record" options={createTabScreenOptions('record')} />
        <Tabs.Screen name="me" options={createTabScreenOptions('me')} />
        {/* 隐藏路由 — 文件保留, 仍可程序化导航 (router.push('/alerts') 等). */}
        <Tabs.Screen name="alerts" options={{ href: null }} />
        <Tabs.Screen name="journal" options={{ href: null }} />
      </Tabs>

      <Modal
        visible={gpsPrompt.visible}
        transparent
        animationType="fade"
        onRequestClose={gpsPrompt.onLater}
      >
        <View style={[modalStyles.backdrop, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
          <View style={[modalStyles.card, { backgroundColor: c.bgCard }]}>
            <View style={[modalStyles.iconCircle, { backgroundColor: c.brandLight }]}>
              <Ionicons name="location" size={28} color={c.brand} />
            </View>
            <Text style={[modalStyles.title, { color: c.labelPrimary }]}>
              开启自动定位?
            </Text>
            <Text style={[modalStyles.body, { color: c.labelSecondary }]}>
              用 GPS 自动定位你当前的城市, 天气 / 空气质量 / 户外运动建议会更准.
              {'\n\n'}仅在 App 使用时定位, 不会后台跟踪.
            </Text>
            <View style={modalStyles.btnRow}>
              <TouchableOpacity
                style={[modalStyles.btn, modalStyles.btnSecondary, { borderColor: c.separator }]}
                onPress={gpsPrompt.onLater}
                activeOpacity={0.7}
              >
                <Text style={[modalStyles.btnLabel, { color: c.labelSecondary }]}>以后再说</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[modalStyles.btn, { backgroundColor: c.brand }]}
                onPress={() => { gpsPrompt.onAllow(); }}
                activeOpacity={0.7}
              >
                <Text style={[modalStyles.btnLabel, { color: '#fff' }]}>允许定位</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ── Reva 浮动胶囊 Tab Bar ─────────────────────────────────
// "Liquid Glass" 风: 距边缘内缩, 圆角 = 半高 (真胶囊端), 柔光阴影; 选中态绿色软高亮 + 实心图标.
type MainTabName = 'index' | 'chat' | 'record' | 'me';

type MainTabMeta = {
  label: string;
  accessibilityLabel: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconOutline: keyof typeof Ionicons.glyphMap;
};

const MAIN_TAB_ORDER: MainTabName[] = ['index', 'chat', 'record', 'me'];

export const TAB_META: Record<MainTabName, MainTabMeta> = {
  index: {
    label: '今日',
    accessibilityLabel: '今日，查看告警、本周建议、身体快照',
    icon: 'sparkles',
    iconOutline: 'sparkles-outline',
  },
  chat: {
    label: '阿衡',
    accessibilityLabel: '阿衡，与健康参谋对话',
    icon: 'chatbubbles',
    iconOutline: 'chatbubbles-outline',
  },
  record: {
    label: '记录',
    accessibilityLabel: '记录，快速记录饮水、体重、血压、打卡',
    icon: 'add-circle',
    iconOutline: 'add-circle-outline',
  },
  me: {
    label: '我',
    accessibilityLabel: '我，设置、AI 模型、目标、化验、用药、通知',
    icon: 'person-circle',
    iconOutline: 'person-circle-outline',
  },
};

export function getMainTabLabels() {
  return MAIN_TAB_ORDER.map((name) => TAB_META[name].label);
}

export function getMainTabAccessibilityLabels() {
  return Object.fromEntries(
    MAIN_TAB_ORDER.map((name) => [name, TAB_META[name].accessibilityLabel]),
  ) as Record<MainTabName, string>;
}

function createTabScreenOptions(name: MainTabName) {
  const meta = TAB_META[name];
  return {
    title: meta.label,
    tabBarAccessibilityLabel: meta.accessibilityLabel,
    tabBarIcon: ({ color, focused }: { color: string; focused: boolean }) => (
      <Ionicons name={focused ? meta.icon : meta.iconOutline} size={name === 'record' ? 26 : 22} color={color} />
    ),
  };
}

function RevaTabBar({ state, navigation }: BottomTabBarProps) {
  const { c } = useTheme();
  const insets = useSafeAreaInsets();
  const routes = state.routes.filter((r): r is typeof r & { name: MainTabName } => r.name in TAB_META);
  const activeKey = state.routes[state.index]?.key;
  return (
    <View pointerEvents="box-none" style={[capsule.wrap, { paddingBottom: Math.max(insets.bottom, FLOATING_TAB_BAR_MIN_BOTTOM) }]}>
      <View style={[capsule.bar, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
        {routes.map((route) => {
          const meta = TAB_META[route.name];
          const focused = route.key === activeKey;
          const color = focused ? c.brand : c.labelTertiary;
          const onPress = () => {
            const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
            if (!focused && !event.defaultPrevented) navigation.navigate(route.name);
          };
          return (
            <TouchableOpacity
              key={route.key}
              accessibilityRole="button"
              accessibilityState={focused ? { selected: true } : {}}
              accessibilityLabel={meta.label}
              activeOpacity={0.7}
              onPress={onPress}
              style={[capsule.item, focused && { backgroundColor: c.brandLight }]}
            >
              <Ionicons name={focused ? meta.icon : meta.iconOutline} size={22} color={color} />
              <Text style={[capsule.label, { color, fontWeight: focused ? '700' : '500' }]} numberOfLines={1}>
                {meta.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const capsule = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: 16,
    paddingTop: FLOATING_TAB_BAR_PADDING_TOP,
  },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    height: FLOATING_TAB_BAR_BAR_HEIGHT,
    borderRadius: 28,
    paddingHorizontal: 6,
    borderWidth: 1,
    shadowColor: '#16201B',
    shadowOpacity: 0.13,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  item: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    paddingVertical: 7,
    marginHorizontal: 2,
    borderRadius: 22,
  },
  label: {
    fontSize: 10,
  },
});

const modalStyles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  card: {
    width: '100%', maxWidth: 360, borderRadius: 16, padding: 24,
    alignItems: 'center',
  },
  iconCircle: {
    width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center',
    marginBottom: 16,
  },
  title: { fontSize: 18, fontWeight: '700', marginBottom: 12, textAlign: 'center' },
  body: { fontSize: 14, lineHeight: 20, textAlign: 'center', marginBottom: 20 },
  btnRow: { flexDirection: 'row', gap: 12, width: '100%' },
  btn: { flex: 1, paddingVertical: 12, borderRadius: 8, alignItems: 'center' },
  btnSecondary: { borderWidth: 1 },
  btnLabel: { fontSize: 14, fontWeight: '600' },
});
