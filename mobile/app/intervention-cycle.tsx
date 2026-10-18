/** /intervention-cycle — 代谢干预周期 + 复查对比 (Personal Health OS P2, 交互稿②④). */
import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { revaColors as C } from '../constants/revaTheme';
import { InterventionCycleView } from '../components/reva/HealthOsScreens';
import { useRevaFonts } from '../components/reva/useRevaFonts';
import { TopBar } from '../components/reva/RevaKit';
import { useRouter } from 'expo-router';
import { backOrChat } from '../utils/backOrChat';

export default function InterventionCycleRoute() {
  const fontsLoaded = useRevaFonts();
  const router = useRouter();
  if (!fontsLoaded) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
        <TopBar title="干预周期" onBack={() => backOrChat(router)} />
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={C.green500} />
        </View>
      </SafeAreaView>
    );
  }
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
      <InterventionCycleView />
    </SafeAreaView>
  );
}
