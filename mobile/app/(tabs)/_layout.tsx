import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Platform } from 'react-native';
import { colors } from '../../constants/theme';

// App body 当前未做完整 dark mode (HomeHeader/卡片都用 light tokens),
// 强制 tab bar 也走 light, 否则 dark mode 下 body 是浅色 + tab bar 是深色 → 视觉割裂.
export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.labelTertiary,
        tabBarLabelStyle: styles.tabLabel,
        tabBarStyle: {
          ...styles.tabBar,
          backgroundColor: 'rgba(255,255,255,0.95)',
          borderTopColor: colors.separator,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: '首页',
          tabBarAccessibilityLabel: '首页，查看健康概览',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'sparkles' : 'sparkles-outline'} size={22} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: '行动',
          tabBarAccessibilityLabel: '行动，查看安全告警与今日建议',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'clipboard' : 'clipboard-outline'} size={22} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="record"
        options={{
          title: '记录',
          tabBarAccessibilityLabel: '记录，快速打卡健康数据',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'grid' : 'grid-outline'} size={22} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="journal"
        options={{
          title: '记忆',
          tabBarAccessibilityLabel: '记忆，AI 案例时间线与 SOAP 记录',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'book' : 'book-outline'} size={22} color={color} />
          ),
        }}
      />
      {/* chat.tsx kept as hidden route — accessible programmatically but not in tab bar */}
      <Tabs.Screen name="chat" options={{ href: null }} />
    </Tabs>
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
