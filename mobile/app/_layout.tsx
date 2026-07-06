// Sentry: side-effect import. Must be the very first import so that
// Sentry.init runs before any other code (including other imports)
// executes — see mobile/applib/sentry.ts for rationale.
import { Sentry, SENTRY_ENABLED } from '../applib/sentry';

import React, { useEffect, useMemo } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { focusManager } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { queryClient, persistOptions } from '../applib/queryClient';
import { AuthProvider, useAuth } from '../hooks/useAuth';
import { ToastProvider } from '../hooks/useToast';
import { useNotifications } from '../hooks/useNotifications';
import { useEyeBreakReminders } from '../hooks/useEyeBreakReminders';
import { useBiometricLock } from '../hooks/useBiometricLock';
import { useGPSAutoRefresh } from '../hooks/useGPSAutoRefresh';
import { useDeviceTimezoneSync } from '../hooks/useDeviceTimezoneSync';
import { useHealthKitForegroundSync } from '../hooks/useHealthKitForegroundSync';
import { useRevaFonts } from '../components/reva/useRevaFonts';
import AppLockScreen from '../components/AppLockScreen';
import NotificationBanner from '../components/notifications/NotificationBanner';
import NetworkBanner from '../components/NetworkBanner';
import RootErrorBoundary from '../components/RootErrorBoundary';
import LoginScreen from './login';
// Side-effect import: TaskManager.defineTask 必须在 module load 时跑 (React 树挂载前).
import { registerBackgroundLocationTask } from '../services/backgroundLocationTask';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import {
  View,
  ActivityIndicator,
  StyleSheet,
  AppState,
  Platform,
} from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = {
  initialRouteName: '(tabs)',
};

function AppContent() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { isAuthenticated, isLoading } = useAuth();
  const { isLocked, authenticate } = useBiometricLock(isAuthenticated);

  useNotifications(isAuthenticated);
  useGPSAutoRefresh(isAuthenticated);
  useDeviceTimezoneSync(isAuthenticated);
  useHealthKitForegroundSync(isAuthenticated && !isLocked);
  // 科学用眼 20-20-20: 根级挂一次, 让「滚动当日重排」在 App 回前台时跑,
  // 无需用户停留在设置屏 (eye-care.tsx 另用同一 hook 做 UI 状态)。
  useEyeBreakReminders(isAuthenticated);

  // iOS BackgroundFetch — best-effort 后台位置刷新. 已授权才注册.
  // 这里跑 effect 是因为权限授予 (通过 onboarding modal) 后才能注册.
  useEffect(() => {
    if (isAuthenticated) {
      registerBackgroundLocationTask();
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated && isLocked) {
      authenticate();
    }
  }, [authenticate, isLocked, isAuthenticated]);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={c.brand} />
      </View>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  if (isLocked) {
    return <AppLockScreen onUnlock={authenticate} />;
  }

  return (
    <>
      {/* 全局默认 headerShown: false — 任何新增 route 也不会意外露出 Expo stack 默认 header (e.g. "< (tabs)  timeline") */}
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        {/* 今日半屏 sheet — iOS 原生 formSheet 从聊天上滑出 (刀④, 2026-07-06)。
            sheetAllowedDetents [0.5, 1]: 半高瞥待办, 拖到顶看全部; 抓手 + 下滑关全原生。
            Android 上 formSheet 回退为整屏 modal (仍是「盖在聊天上、下滑关」语义)。 */}
        <Stack.Screen
          name="today-sheet"
          options={{
            headerShown: false,
            presentation: 'formSheet',
            sheetAllowedDetents: [0.5, 1],
            sheetInitialDetentIndex: 0,
            sheetGrabberVisible: true,
            sheetCornerRadius: 20,
            gestureEnabled: true,
          }}
        />
        <Stack.Screen name="settings" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="account-security" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="memory" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="medical-exams" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="medical-exam-detail" options={{ headerShown: false }} />
        <Stack.Screen name="notification-settings" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="reminders" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="notification-history" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="consultations" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="consultations/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="sleep" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="sleep-spo2-analysis" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="workout-list" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="workout-detail" options={{ headerShown: false }} />
        <Stack.Screen name="diet" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="body-measurements" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="goals" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="directives" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="indicator-history" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="trace/index" options={{ headerShown: false }} />
        <Stack.Screen name="trace/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="voice-chat" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="timeline" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="medications" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="family" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="location" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="voice-style" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="eye-care" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="doctor-loop" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="monthly-reports" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="ai-profile" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="admin-llm" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="symptom-record" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="live-run" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="live-run/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="episode/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="import" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="knowledge/entity" options={{ headerShown: false }} />
        <Stack.Screen name="guided-task" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="rokid-pushup-coach" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="fitness-plan" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="exercise-guide/[key]" options={{ headerShown: false }} />
      </Stack>
      <NotificationBanner />
      <NetworkBanner />
    </>
  );
}

function RootLayout() {
  useRevaFonts();

  // Connect AppState to React Query for auto-refetch on foreground
  useEffect(() => {
    const sub = AppState.addEventListener('change', (status) => {
      if (Platform.OS !== 'web') {
        focusManager.setFocused(status === 'active');
      }
    });
    return () => sub.remove();
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <RootErrorBoundary>
        <AuthProvider>
          <ToastProvider>
            {/* dark mode 下卡片用 darkColors, 状态栏 auto 让系统按背景选 icon 颜色 */}
            <StatusBar style="auto" />
            <AppContent />
          </ToastProvider>
        </AuthProvider>
      </RootErrorBoundary>
    </PersistQueryClientProvider>
    </GestureHandlerRootView>
  );
}

// Sentry.wrap: 自动捕获未处理异常 + Profiler. 未配置 DSN 时是 noop.
export default SENTRY_ENABLED ? Sentry.wrap(RootLayout) : RootLayout;

const createStyles = (c: ColorPalette) => StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: c.bgPrimary,
  },
});
