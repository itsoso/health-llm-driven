import React from 'react';
import { Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../hooks/useTheme';
import { useGPSOnboardingPrompt } from '../../hooks/useGPSOnboardingPrompt';

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
  const { c } = useTheme();
  // 用户登录后第一次进 tabs 时, 一次性问一下 GPS 权限. 不再弹.
  const gpsPrompt = useGPSOnboardingPrompt(true);

  return (
    <View style={{ flex: 1 }}>
      <Tabs
        // 小巴 chat 是 agent-native 主屏。
        initialRouteName="chat"
        // 无底部 Tab Bar：二级屏靠 chat 里的入口 + 各自顶部「返回小巴」导航。
        tabBar={() => null}
        screenOptions={{ headerShown: false }}
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
    label: '小巴',
    accessibilityLabel: '小巴，与忠实的健康守护者对话',
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
    layout: 'docked',
    overlaysContent: false,
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
