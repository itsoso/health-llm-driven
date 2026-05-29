import React from 'react';
import { Modal, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../hooks/useTheme';
import { useGPSOnboardingPrompt } from '../../hooks/useGPSOnboardingPrompt';

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
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: c.brand,
          tabBarInactiveTintColor: c.labelTertiary,
          tabBarLabelStyle: styles.tabLabel,
          tabBarStyle: {
            ...styles.tabBar,
            backgroundColor: c.bgCard,
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
        <Tabs.Screen
          name="me"
          options={{
            title: '我',
            tabBarAccessibilityLabel: '我，设置、AI 模型、目标、化验、用药、通知',
            tabBarIcon: ({ color, focused }) => (
              <Ionicons name={focused ? 'person-circle' : 'person-circle-outline'} size={22} color={color} />
            ),
          }}
        />
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

const styles = StyleSheet.create({
  tabBar: {
    position: 'absolute' as const,
    borderTopWidth: 0.5,
    elevation: 0,
    height: Platform.OS === 'ios' ? 83 : 60,
    paddingBottom: Platform.OS === 'ios' ? 34 : 8,
    paddingTop: 6,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: -4 },
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: '600',
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
