import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Platform, useColorScheme } from 'react-native';
import { colors, darkColors } from '@/constants/theme';

export default function TabLayout() {
  const scheme = useColorScheme();
  const c = scheme === 'dark' ? darkColors : colors;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: c.brand,
        tabBarInactiveTintColor: c.labelTertiary,
        tabBarLabelStyle: styles.tabLabel,
        tabBarStyle: {
          ...styles.tabBar,
          backgroundColor: scheme === 'dark' ? 'rgba(28,28,30,0.95)' : 'rgba(255,255,255,0.95)',
          borderTopColor: c.separator,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: '首页',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'sparkles' : 'sparkles-outline'} size={22} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: '行动',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'clipboard' : 'clipboard-outline'} size={22} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="record"
        options={{
          title: '记录',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons name={focused ? 'grid' : 'grid-outline'} size={22} color={color} />
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
