import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Platform } from 'react-native';

type TabIcon = keyof typeof Ionicons.glyphMap;

const TAB_CONFIG: {
  name: string;
  title: string;
  icon: TabIcon;
  iconFocused: TabIcon;
}[] = [
  {
    name: 'index',
    title: '仪表盘',
    icon: 'heart-outline',
    iconFocused: 'heart',
  },
  {
    name: 'alerts',
    title: '告警',
    icon: 'warning-outline',
    iconFocused: 'warning',
  },
  {
    name: 'record',
    title: '记录',
    icon: 'add-circle-outline',
    iconFocused: 'add-circle',
  },
  {
    name: 'cards',
    title: '计划',
    icon: 'clipboard-outline',
    iconFocused: 'clipboard',
  },
  {
    name: 'chat',
    title: 'AI',
    icon: 'chatbubble-ellipses-outline',
    iconFocused: 'chatbubble-ellipses',
  },
];

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#007AFF',
        tabBarInactiveTintColor: '#8E8E93',
        tabBarStyle: {
          backgroundColor: '#FDFBF7',
          borderTopColor: '#E5E5EA',
          borderTopWidth: 0.5,
          height: Platform.OS === 'ios' ? 88 : 60,
          paddingBottom: Platform.OS === 'ios' ? 28 : 8,
          paddingTop: 8,
        },
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: '600',
        },
        headerStyle: {
          backgroundColor: '#FDFBF7',
        },
        headerTitleStyle: {
          fontWeight: '700',
          fontSize: 17,
          color: '#1C1C1E',
        },
        headerShadowVisible: false,
      }}
    >
      {TAB_CONFIG.map(({ name, title, icon, iconFocused }) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title,
            tabBarIcon: ({ focused, color, size }) => (
              <Ionicons
                name={focused ? iconFocused : icon}
                size={size}
                color={color}
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
