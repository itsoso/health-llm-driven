/**
 * 复元 Reva — Agent (分析对话) standalone route. Thin wrapper around the shared
 * RevaAgentView (also used by the Reva hub's 复元 tab). Route: /reva-agent
 */
import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { revaColors } from '../constants/revaTheme';
import { RevaAgentView } from '../components/reva/RevaAgentView';
import { useRevaFonts } from '../components/reva/useRevaFonts';

export default function RevaAgentScreen() {
  const fontsLoaded = useRevaFonts();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: revaColors.paper }} edges={['top', 'bottom']}>
      {fontsLoaded ? (
        <RevaAgentView />
      ) : (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={revaColors.green500} />
        </View>
      )}
    </SafeAreaView>
  );
}
