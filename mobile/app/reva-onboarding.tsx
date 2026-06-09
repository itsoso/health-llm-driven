/**
 * 复元 Reva — onboarding flow route. Route: /reva-onboarding
 * Faithful recreation of the Reva 3-step onboarding; on完成 enters the hub.
 */
import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { revaColors } from '../constants/revaTheme';
import { OnboardingView } from '../components/reva/RevaScreens';
import { useRevaFonts } from '../components/reva/useRevaFonts';

export default function RevaOnboardingScreen() {
  const fontsLoaded = useRevaFonts();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: revaColors.paper }} edges={['top', 'bottom']}>
      {fontsLoaded ? (
        <OnboardingView onDone={() => router.replace('/reva')} />
      ) : (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={revaColors.green500} />
        </View>
      )}
    </SafeAreaView>
  );
}
