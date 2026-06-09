/**
 * 复元 Reva — app hub (navigation entry). Hosts the four Reva tabs
 * (今天 / 数据 / 复元 / 我的) with the design's bottom TabBar; routes to the
 * Risk-detail sub-view and the onboarding flow. Route: /reva
 *
 * Today/Data/Me are faithful presentational recreations of the Reva UI kit;
 * the 复元 tab is the live agent (real streaming). Reachable e.g. via
 * router.push('/reva') — add a permanent entry point when promoting Reva.
 */
import React, { useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { revaColors as C } from '../constants/revaTheme';
import { TabBar, type RevaTab } from '../components/reva/RevaKit';
import { DataView, MeView, RiskDetailView, TodayView } from '../components/reva/RevaScreens';
import { RevaAgentView } from '../components/reva/RevaAgentView';
import { useRevaFonts } from '../components/reva/useRevaFonts';

export default function RevaHub() {
  const [tab, setTab] = useState<RevaTab>('today');
  const [risk, setRisk] = useState(false);
  const insets = useSafeAreaInsets();
  const fontsLoaded = useRevaFonts();

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, backgroundColor: C.paper, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={C.green500} />
      </View>
    );
  }

  // Risk detail is a pushed sub-view over the whole hub.
  if (risk) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top', 'bottom']}>
        <RiskDetailView onBack={() => setRisk(false)} onAgent={() => { setRisk(false); setTab('agent'); }} />
      </SafeAreaView>
    );
  }

  const agent = tab === 'agent';
  return (
    <View style={{ flex: 1, backgroundColor: agent ? C.paper : C.paper }}>
      {/* Content area respects the top inset; agent provides its own composer. */}
      <SafeAreaView style={{ flex: 1 }} edges={['top']}>
        {tab === 'today' && <TodayView onRisk={() => setRisk(true)} />}
        {tab === 'data' && <DataView onRisk={() => setRisk(true)} />}
        {tab === 'agent' && <RevaAgentView />}
        {tab === 'me' && <MeView />}
      </SafeAreaView>
      <TabBar active={tab} onChange={setTab} bottomInset={insets.bottom} />
    </View>
  );
}
