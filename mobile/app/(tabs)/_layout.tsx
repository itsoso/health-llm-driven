import React from 'react';
import { View } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Platform } from 'react-native';
import { useTheme } from '../../hooks/useTheme';

/**
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
 *
 * 备份: 旧 layout 在 git history. 文件没动, 只改 Tabs.Screen.options.href.
 */

export default function TabLayout() {
  const { c, isDark } = useTheme();

  return (
    <View style={{ flex: 1 }}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: c.brand,
          tabBarInactiveTintColor: c.labelTertiary,
          tabBarLabelStyle: styles.tabLabel,
          tabBarStyle: {
            ...styles.tabBar,
            backgroundColor: isDark ? 'rgba(28,28,30,0.95)' : 'rgba(255,255,255,0.95)',
            borderTopColor: c.separator,
          },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: '今日',
            tabBarAccessibilityLabel: '今日，查看告警、本周建议、身体快照',
            tabBarIcon: ({ color, focused }) => (
              <Ionicons name={focused ? 'sparkles' : 'sparkles-outline'} size={22} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="chat"
          options={{
            title: '私教',
            tabBarAccessibilityLabel: '私教，与健康 Agent 对话',
            tabBarIcon: ({ color, focused }) => (
              <Ionicons name={focused ? 'chatbubbles' : 'chatbubbles-outline'} size={22} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="record"
          options={{
            title: '记录',
            tabBarAccessibilityLabel: '记录，快速记录饮水、体重、血压、打卡',
            tabBarIcon: ({ color, focused }) => (
              <Ionicons name={focused ? 'add-circle' : 'add-circle-outline'} size={26} color={color} />
            ),
          }}
        />
        {/* 隐藏路由 — 文件保留, 仍可程序化导航 (router.push('/alerts') 等). */}
        <Tabs.Screen name="alerts" options={{ href: null }} />
        <Tabs.Screen name="journal" options={{ href: null }} />
      </Tabs>
    </View>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    position: 'absolute' as const,
    borderTopWidth: 0.5,
    elevation: 0,
    height: Platform.OS === 'ios' ? 83 : 60,
    paddingBottom: Platform.OS === 'ios' ? 34 : 8,
    paddingTop: 6,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: '600',
  },
});
