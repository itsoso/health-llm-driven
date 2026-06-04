/** /metabolic-profile — 代谢健康画像 (Personal Health OS P2, 交互稿①). */
import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { revaColors as C } from '../constants/revaTheme';
import { MetabolicProfileView } from '../components/reva/HealthOsScreens';
import { useRevaFonts } from '../components/reva/useRevaFonts';

export default function MetabolicProfileRoute() {
  const fontsLoaded = useRevaFonts();
  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, backgroundColor: C.paper, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={C.green500} />
      </View>
    );
  }
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
      <MetabolicProfileView />
    </SafeAreaView>
  );
}
