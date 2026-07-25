import { configureSentryForAppMode, Sentry, SENTRY_ENABLED } from '../applib/sentry';

import React, { useEffect, useMemo } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { focusManager } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { queryClient, persistOptions } from '../applib/queryClient';
import { useAuth } from '../hooks/useAuth';
import { AppSessionProvider, useAppSession } from '../hooks/useAppSession';
import { ToastProvider } from '../hooks/useToast';
import { AppUpdateProvider } from '../hooks/useAppUpdate';
import { useNotifications } from '../hooks/useNotifications';
import { useEyeBreakReminders } from '../hooks/useEyeBreakReminders';
import { useBiometricLock } from '../hooks/useBiometricLock';
import { useGPSAutoRefresh } from '../hooks/useGPSAutoRefresh';
import { useDeviceTimezoneSync } from '../hooks/useDeviceTimezoneSync';
import { useHealthKitForegroundSync } from '../hooks/useHealthKitForegroundSync';
import { useRevaFonts } from '../components/reva/useRevaFonts';
import AppLockScreen from '../components/AppLockScreen';
import NotificationBanner from '../components/notifications/NotificationBanner';
import AppUpdateBanner from '../components/updates/AppUpdateBanner';
import RootErrorBoundary from '../components/RootErrorBoundary';
import LoginScreen from './login';
// Side-effect import: TaskManager.defineTask 必须在 module load 时跑 (React 树挂载前).
import { registerBackgroundLocationTask } from '../services/backgroundLocationTask';
import { getReleaseCapabilities } from '../config/releaseCapabilities';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { loadDietPhotoDraft } from '../services/dietPhotoDraftStorage';
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
  const { isAuthenticated, user } = useAuth();
  const { session, isLoading } = useAppSession();
  const cloudActive = session?.mode === 'cloud_account' && isAuthenticated;
  const { isLocked, authenticate } = useBiometricLock(cloudActive);
  const releaseCapabilities = getReleaseCapabilities();

  useNotifications(cloudActive);
  useGPSAutoRefresh(cloudActive);
  useDeviceTimezoneSync(cloudActive);
  useHealthKitForegroundSync(cloudActive && !isLocked);
  // 科学用眼 20-20-20: 根级挂一次, 让「滚动当日重排」在 App 回前台时跑,
  // 无需用户停留在设置屏 (eye-care.tsx 另用同一 hook 做 UI 状态)。
  useEyeBreakReminders(cloudActive);

  // iOS BackgroundFetch — best-effort 后台位置刷新. 已授权才注册.
  // 这里跑 effect 是因为权限授予 (通过 onboarding modal) 后才能注册.
  useEffect(() => {
    if (cloudActive && releaseCapabilities.backgroundLocation) {
      registerBackgroundLocationTask();
    }
  }, [cloudActive, releaseCapabilities.backgroundLocation]);

  useEffect(() => {
    if (!cloudActive || !user?.id) return;
    void loadDietPhotoDraft(user.id).catch((error) => {
      console.warn('[DietPhotoDraft] startup expiry check failed', error);
    });
  }, [cloudActive, user?.id]);

  useEffect(() => {
    if (cloudActive && isLocked) {
      authenticate();
    }
  }, [authenticate, isLocked, cloudActive]);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={c.brand} />
      </View>
    );
  }

  if (!session) {
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
            不支持 formSheet 的环境回退为整屏 modal (仍是「盖在聊天上、下滑关」语义)。 */}
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
        <Stack.Screen
          name="agenda"
          options={{ headerShown: false, gestureEnabled: true }}
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
        <Stack.Screen name="community" options={{ headerShown: false, presentation: 'modal' }} />
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
      <AppUpdateBanner />
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
        <AppSessionProvider>
          <ToastProvider>
            <ModeAwareProviders>
              {/* dark mode 下卡片用 darkColors, 状态栏 auto 让系统按背景选 icon 颜色 */}
              <StatusBar style="auto" />
              <AppContent />
            </ModeAwareProviders>
          </ToastProvider>
        </AppSessionProvider>
      </RootErrorBoundary>
    </PersistQueryClientProvider>
    </GestureHandlerRootView>
  );
}

function ModeAwareProviders({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    configureSentryForAppMode('cloud');
  }, []);

  return <AppUpdateProvider>{children}</AppUpdateProvider>;
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
