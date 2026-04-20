import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/hooks/useAuth';
import { ToastProvider } from '@/hooks/useToast';
import { useNotifications } from '@/hooks/useNotifications';
import { useBiometricLock } from '@/hooks/useBiometricLock';
import NotificationBanner from '@/components/notifications/NotificationBanner';
import NetworkBanner from '@/components/NetworkBanner';
import LoginScreen from '@/app/login';
import { colors } from '@/constants/theme';
import {
  View,
  Text,
  ActivityIndicator,
  StyleSheet,
  AppState,
  Platform,
  TouchableOpacity,
  TextStyle,
  useColorScheme,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = {
  initialRouteName: '(tabs)',
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 60_000,
    },
  },
});

function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  return (
    <View style={styles.lockContainer}>
      <Ionicons name="lock-closed" size={48} color="#0A8F8F" />
      <Text style={styles.lockTitle}>HealthPilot</Text>
      <TouchableOpacity style={styles.unlockBtn} onPress={onUnlock} activeOpacity={0.7}>
        <Ionicons name="finger-print" size={22} color="#fff" />
        <Text style={styles.unlockText}>解锁</Text>
      </TouchableOpacity>
    </View>
  );
}

function AppContent() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isLocked, authenticate } = useBiometricLock(isAuthenticated);

  useNotifications(isAuthenticated);

  useEffect(() => {
    if (isAuthenticated && isLocked) {
      authenticate();
    }
  }, [isLocked, isAuthenticated]);

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.brand} />
      </View>
    );
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  if (isLocked) {
    return <LockScreen onUnlock={authenticate} />;
  }

  return (
    <>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="settings" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="notification-settings" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="reminders" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="notification-history" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="consultations" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="consultations/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="sleep" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="workout-list" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="workout-detail" options={{ headerShown: false }} />
        <Stack.Screen name="diet" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="goals" options={{ headerShown: false, presentation: 'modal' }} />
        <Stack.Screen name="indicator-history" options={{ headerShown: false, presentation: 'modal' }} />
      </Stack>
      <NotificationBanner />
      <NetworkBanner />
    </>
  );
}

export default function RootLayout() {
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
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <StatusBar style="auto" />
          <AppContent />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FDFBF7',
  },
  lockContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F2F2F7',
    gap: 16,
  },
  lockTitle: {
    fontSize: 22,
    fontWeight: '600',
    color: '#1C1C1E',
  } as TextStyle,
  unlockBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#0A8F8F',
    borderRadius: 12,
    paddingHorizontal: 24,
    paddingVertical: 12,
    marginTop: 16,
  },
  unlockText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  } as TextStyle,
});
