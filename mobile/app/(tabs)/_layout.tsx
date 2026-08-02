import React from 'react';
import { View } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C } from '../../constants/revaTheme';

/**
 * Phase 5 (2026-07-03): Agent-native shell. 移除底部 Tab Bar, 小巴(chat) 成为主屏
 * (initialRouteName="chat" + tabBar 渲染 null)。今日/记录/我 降级为二级屏, 靠 chat 里
 * 的 avatar / 今日简报条 / 记录托盘 进入, 各二级屏顶部有「返回小巴」。
 *   - 保留全部 Tabs.Screen + TAB_META + getMainTab* 导出 (深链契约: router.push('/(tabs)/chat')
 *     / 通知路由 / 分享深链 均依赖这些 segment, 不能静默改)。
 *
 * Phase 4 (2026-05-29): Tab 3 → 4. 加 "我" tab.
 * Phase 3 (2026-05-14): Tab 2 → 3. "+" FAB 推进为第三 Tab "记录".
 * Phase 2 (2026-05-11): Tab 收敛 4 → 2 (今日 + 会诊).
 *
 * 隐藏 (href:null, 仍可程序化导航): alerts / journal.
 * 备份: 旧带 bar 的 layout 在 git history.
 */

// expo-router 的权威 initial-route 配置: <Tabs initialRouteName> 单独用不可靠
// (实测冷启动仍落 index), unstable_settings 才是文档路径, 同时充当深链 anchor。
export const unstable_settings = {
  initialRouteName: 'chat',
};

export default function TabLayout() {
  return (
    <View style={{ flex: 1 }}>
      <Tabs
        // 小巴 chat 是 agent-native 主屏。
        initialRouteName="chat"
        // 无底部 Tab Bar：二级屏靠 chat 里的入口 + 各自顶部「返回小巴」导航。
        tabBar={() => null}
        screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: C.paper } }}
      >
        {/* index = 纯 Redirect → chat (expo-router "/" 永远落 index, 见 index.tsx 注释)。 */}
        <Tabs.Screen name="index" options={createTabScreenOptions('index')} />
        <Tabs.Screen name="chat" options={createTabScreenOptions('chat')} />
        {/* 原「今日」屏实体, 从 index.tsx 挪来 — chat 顶部今日简报条指向这里。 */}
        <Tabs.Screen name="today" options={{ title: '今日' }} />
        <Tabs.Screen name="record" options={createTabScreenOptions('record')} />
        <Tabs.Screen name="me" options={createTabScreenOptions('me')} />
        {/* 隐藏路由 — 文件保留, 仍可程序化导航 (router.push('/alerts') 等). */}
        <Tabs.Screen name="alerts" options={{ href: null }} />
        <Tabs.Screen name="journal" options={{ href: null }} />
      </Tabs>

    </View>
  );
}

export function getColdStartPermissionPrompts(): string[] {
  return [];
}

// ── 小巴 agent-native shell 路由契约 ───────────────────────
// 底部 Tab Bar 已移除;这些 route segment 只作为深链/通知/二级页入口保留。
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
    label: '小巴',
    accessibilityLabel: '小巴，与忠实的健康参谋对话',
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

// 路由 segment 是深链契约 (router.push('/(tabs)/chat')、通知路由、分享深链均依赖),
// 导出只读快照供测试钉死, 防止静默改名.
export function getMainTabRouteNames(): MainTabName[] {
  return [...MAIN_TAB_ORDER];
}

export function getMainTabAccessibilityLabels() {
  return Object.fromEntries(
    MAIN_TAB_ORDER.map((name) => [name, TAB_META[name].accessibilityLabel]),
  ) as Record<MainTabName, string>;
}

export function getMainTabBarPresentation(name?: MainTabName) {
  return {
    layout: 'hidden',
    overlaysContent: false,
    visible: false,
    primaryEntry: 'chat',
  } as const;
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
