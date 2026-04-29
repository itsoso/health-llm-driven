import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, TextStyle,
  Alert, RefreshControl, Keyboard, Modal, Pressable, useWindowDimensions,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getConversations, deleteConversation } from '../../services/chat';
import api from '../../services/api';
import { getSafetyReport } from '../../services/safety';
import HomeHeader from '../../components/dashboard/HomeHeader';
import TodayCoachPanel from '../../components/dashboard/TodayCoachPanel';
import AgentAgendaPanel from '../../components/dashboard/AgentAgendaPanel';
import DataFreshnessPanel from '../../components/dashboard/DataFreshnessPanel';
import ChatInputBar from '../../components/chat/ChatInputBar';
import ConversationSheet from '../../components/chat/ConversationSheet';
import BrandCircle from '../../components/chat/BrandCircle';
import ChatBubble from '../../components/chat/ChatBubble';
import { useChatEngine, type UIMessage } from '../../hooks/useChatEngine';
import { useTodayCoach } from '../../hooks/useTodayCoach';
import { useAgentAgenda } from '../../hooks/useAgentAgenda';
import type { TodayCoachFocus } from '../../services/todayCoach';
import type { AgentAgendaItem } from '../../services/agentAgenda';
import { invalidateHealthSnapshot, queryKeys } from '../../applib/queryKeys';
import { colors, spacing, radii } from '../../constants/theme';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function HomeScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const convs = await getConversations();
      setConversations(convs);
    } catch (e: any) {
      setHistoryError(e?.message ? `加载失败: ${e.message.slice(0, 60)}` : '加载失败，检查网络');
    } finally {
      setHistoryLoading(false);
    }
  }, []);
  const [refreshing, setRefreshing] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  const [viewingImage, setViewingImage] = useState<string | null>(null);

  // ── Data queries ──
  const { data: scoreData, isLoading: scoreLoading } = useQuery({ queryKey: queryKeys.healthScore, queryFn: () => api.get(`/health-score/daily/me?target_date=${today()}`).then(r => r.data), staleTime: 120_000 });
  const { data: garminData, isLoading: garminLoading } = useQuery({ queryKey: queryKeys.garminToday, queryFn: () => api.get(`/daily-health/garmin/me?start_date=${today()}&end_date=${today()}`).then(r => r.data), staleTime: 120_000 });
  const { data: weatherData } = useQuery({ queryKey: queryKeys.weather, queryFn: () => api.get('/environment/weather').then(r => r.data), staleTime: 300_000 });
  const { data: aqiData } = useQuery({ queryKey: queryKeys.aqi, queryFn: () => api.get('/environment/air-quality').then(r => r.data), staleTime: 300_000 });
  const { data: safetyData } = useQuery({ queryKey: queryKeys.safety, queryFn: getSafetyReport, staleTime: 300_000 });
  const { data: profileData } = useQuery({ queryKey: queryKeys.profile, queryFn: () => api.get('/profile/me').then(r => r.data), staleTime: 600_000 });
  const { data: forecastData } = useQuery({ queryKey: queryKeys.forecast, queryFn: () => api.get('/environment/weather/forecast?days=2').then(r => r.data).catch(() => null), staleTime: 300_000 });
  const todayCoach = useTodayCoach();
  const agentAgenda = useAgentAgenda();
  const insets = useSafeAreaInsets();
  // tab bar(49) + bottom safe area: iPhone home indicator=83, iPad=49, home button=49
  const kbOffset = Platform.OS === 'ios' ? 49 + insets.bottom : 0;

  const contextData = useMemo(() => ({
    garmin: Array.isArray(garminData) && garminData.length > 0 ? garminData[0] : null,
    score: scoreData, weather: weatherData, aqi: aqiData, profile: profileData,
  }), [garminData, scoreData, weatherData, aqiData, profileData]);

  const chat = useChatEngine({ contextData });

  // Load conversation on mount
  useEffect(() => { chat.loadLatestConversation(); }, []);

  // Scroll to bottom when keyboard appears
  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => {
      setKeyboardVisible(true);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => setKeyboardVisible(false));
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  // Derived data
  const score = scoreData?.total_score ?? 0;
  const garmin = Array.isArray(garminData) && garminData.length > 0 ? garminData[0] : null;
  const weather = weatherData?.weather ?? weatherData;
  const city = profileData?.manual_location?.city || profileData?.detected_location?.city || profileData?.city || '';
  const tomorrowFc = forecastData?.forecasts?.[1];
  const criticalAlerts = (safetyData?.alerts || []).filter((a: any) => {
    const sev = typeof a.severity === 'string' ? a.severity : a.severity?.label;
    return sev === 'critical' || sev === 'high';
  });

  const sleepH = garmin?.total_sleep_duration ? (garmin.total_sleep_duration / 60).toFixed(1) : '--';
  const steps = garmin?.steps ?? '--';
  const hrVal = garmin?.resting_heart_rate ?? '--';
  const batteryCurrent = garmin?.body_battery_current;
  const batteryPeak = garmin?.body_battery_most_charged;
  const batteryVal = batteryCurrent != null && batteryPeak != null
    ? `${batteryCurrent}/${batteryPeak}` : `${batteryCurrent ?? batteryPeak ?? '--'}`;

  // ── Send handler (wraps chat engine) ──
  const handleSend = useCallback((text: string, images?: any) => {
    chat.sendMessage(text, images);
  }, [chat.sendMessage]);

  const handleTodayCoachAction = useCallback((focus: TodayCoachFocus) => {
    if (focus.actionRoute) {
      router.push(focus.actionRoute as any);
      return;
    }
    handleSend('今天健康如何？给我一份简报', null);
  }, [handleSend, router]);

  const handleAgendaItem = useCallback((item: AgentAgendaItem) => {
    if (item.route) router.push(item.route as any);
  }, [router]);

  // ── Render message ──
  const renderMessage = useCallback(({ item }: { item: UIMessage | { id: string; type: 'date'; label: string } | { id: string; type: 'load-more' } }) => {
    if ((item as any).type === 'date') {
      return (
        <View style={styles.dateDivider}>
          <View style={styles.dateLine} />
          <Text style={txt.dateText}>{(item as any).label}</Text>
          <View style={styles.dateLine} />
        </View>
      );
    }
    if ((item as any).type === 'load-more') {
      return (
        <TouchableOpacity style={styles.loadMoreBtn} onPress={chat.loadMoreHistory} activeOpacity={0.7}>
          <Ionicons name="chevron-up" size={14} color={colors.brand} />
          <Text style={txt.loadMoreText}>查看更早</Text>
        </TouchableOpacity>
      );
    }
    return <ChatBubble item={item as UIMessage} onViewImage={setViewingImage} />;
  }, [chat.loadMoreHistory]);

  // 在消息之间插入日期分割条
  const itemsWithDateDividers = useMemo(() => {
    const out: (UIMessage | { id: string; type: 'date'; label: string } | { id: string; type: 'load-more' })[] = [];
    if (chat.hasMoreHistory && chat.messages.length > 0) {
      out.push({ id: 'load-more', type: 'load-more' });
    }
    let lastDay: string | null = null;
    for (const m of chat.messages) {
      const createdAt = (m as any).createdAt;
      if (createdAt) {
        const d = new Date(createdAt);
        const dayKey = `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`;
        if (dayKey !== lastDay) {
          const weekday = ['日','一','二','三','四','五','六'][d.getDay()];
          out.push({
            id: `date-${dayKey}`,
            type: 'date',
            label: `${d.getMonth()+1}-${d.getDate()} 周${weekday}`,
          });
          lastDay = dayKey;
        }
      }
      out.push(m);
    }
    return out;
  }, [chat.messages, chat.hasMoreHistory]);

  const { width: windowWidth, height: windowHeight } = useWindowDimensions();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <HomeHeader
        score={score} city={city}
        temperature={weather?.temperature} weatherDesc={weather?.weather}
        aqiValue={aqiData?.aqi} pm25={aqiData?.pm25}
        tomorrowWeather={tomorrowFc?.weather}
        tomorrowTempRange={tomorrowFc ? `${tomorrowFc.temp_min}~${tomorrowFc.temp_max}°C` : undefined}
        sleep={`${sleepH}h`} sleepScore={garmin?.sleep_score}
        steps={typeof steps === 'number' ? steps.toLocaleString() : `${steps}`}
        hr={`${hrVal}`} battery={`${batteryVal}`}
        batteryCurrent={batteryCurrent} batteryPeak={batteryPeak}
        isLoading={scoreLoading || garminLoading}
        onSettings={() => router.push('/settings' as any)}
        onNewChat={chat.newChat}
        onHistory={() => {
          setShowHistory(true);
          loadHistory();
        }}
      />

      <TodayCoachPanel
        focus={todayCoach.data}
        isLoading={todayCoach.isLoading}
        onAction={handleTodayCoachAction}
      />

      <DataFreshnessPanel />

      <AgentAgendaPanel
        agenda={agentAgenda.data}
        onOpenItem={handleAgendaItem}
      />

      {/* 告警 banner: 只在 TodayCoach 不是 risk 态时显示 (避免和上面 TodayCoach 重复同一条 alert) */}
      {criticalAlerts.length > 0 && todayCoach.data?.status !== 'risk' && (
        <View style={styles.alertBanner} accessibilityRole="alert">
          <Ionicons name="warning" size={16} color="#FF453A" />
          <Text style={txt.alertText} numberOfLines={2}>{criticalAlerts[0].title}: {criticalAlerts[0].message}</Text>
        </View>
      )}

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={kbOffset}>
        <FlatList
          ref={flatListRef}
          data={itemsWithDateDividers}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={async () => {
              setRefreshing(true);
              try { await api.post('/data-collection/garmin/me/sync?days=1'); } catch { console.warn('Garmin sync failed'); }
              await Promise.all([
                invalidateHealthSnapshot(qc),
                qc.invalidateQueries({ queryKey: queryKeys.weather }),
                qc.invalidateQueries({ queryKey: queryKeys.aqi }),
                qc.invalidateQueries({ queryKey: queryKeys.forecast }),
              ]);
              setRefreshing(false);
            }} tintColor={colors.brand} />
          }
          contentContainerStyle={styles.msgList}
          onContentSizeChange={() => { if (isNearBottom.current) flatListRef.current?.scrollToEnd({ animated: true }); }}
          onScroll={(e) => { const { layoutMeasurement, contentOffset, contentSize } = e.nativeEvent; isNearBottom.current = contentSize.height - contentOffset.y - layoutMeasurement.height < 120; }}
          scrollEventThrottle={100}
          ListEmptyComponent={
            <View style={styles.welcome}>
              <BrandCircle size={56} style={{ marginBottom: 12 }}>
                <Ionicons name="sparkles" size={24} color="#fff" />
              </BrandCircle>
              <Text style={txt.welcomeTitle}>健康助理</Text>
              <Text style={txt.welcomeSub}>说点什么，或试试这些</Text>
              <TouchableOpacity style={styles.briefingBtn} onPress={() => handleSend('今天健康如何？给我一份简报', null)} activeOpacity={0.7} accessibilityLabel="生成今日健康简报">
                <Ionicons name="sparkles-outline" size={16} color={colors.brand} />
                <Text style={txt.briefingBtnText}>生成今日健康简报</Text>
              </TouchableOpacity>
              <View style={styles.sugRow}>
                {['记录喝了杯水', '分析睡眠质量', '吃了鱼油', '最近HRV趋势'].map(s => (
                  <TouchableOpacity key={s} style={styles.sugChip} onPress={() => handleSend(s, null)} accessibilityLabel={s}>
                    <Text style={txt.sugText}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          }
        />

        <ChatInputBar onSend={handleSend} isStreaming={chat.isStreaming} />
        {!keyboardVisible && <View style={{ height: 83 }} />}
      </KeyboardAvoidingView>

      <Modal visible={!!viewingImage} transparent animationType="fade" onRequestClose={() => setViewingImage(null)}>
        <Pressable style={styles.imageViewerOverlay} onPress={() => setViewingImage(null)}>
          {viewingImage && (
            <Image
              source={{ uri: viewingImage }}
              style={{ width: windowWidth - 32, height: windowHeight * 0.7 }}
              contentFit="contain"
            />
          )}
          <TouchableOpacity style={styles.imageViewerClose} onPress={() => setViewingImage(null)}>
            <Ionicons name="close-circle" size={32} color="#fff" />
          </TouchableOpacity>
        </Pressable>
      </Modal>

      <ConversationSheet
        visible={showHistory}
        onClose={() => setShowHistory(false)}
        conversations={conversations}
        setConversations={setConversations}
        currentConversationId={chat.conversationId}
        loading={historyLoading}
        error={historyError}
        onRetry={loadHistory}
        onSelectConversation={async (id) => {
          try { await chat.loadConversation(id); } catch { Alert.alert('加载失败', '无法加载对话内容'); }
        }}
        onDeleteConversation={async (id) => {
          await deleteConversation(id);
          setConversations(prev => prev.filter((c: any) => c.id !== id));
          if (chat.conversationId === id) chat.newChat();
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  alertBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginHorizontal: spacing.lg, marginBottom: 6,
    backgroundColor: '#FFF0F0', borderRadius: radii.md,
    padding: spacing.sm, borderLeftWidth: 3, borderLeftColor: '#FF453A',
  },
  msgList: { padding: spacing.md, paddingBottom: 4 },
  imageViewerOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center', alignItems: 'center',
  },
  imageViewerClose: {
    position: 'absolute', top: 60, right: 20,
  },
  welcome: { alignItems: 'center', paddingTop: 80 },
  briefingBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.brandLight, borderRadius: radii.full,
    paddingHorizontal: 18, paddingVertical: 10, marginTop: 16, marginBottom: 8,
  },
  sugRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 20, justifyContent: 'center', paddingHorizontal: spacing.xl },
  sugChip: {
    backgroundColor: colors.bgCard, borderRadius: radii.full,
    paddingHorizontal: 14, paddingVertical: 8,
    borderWidth: 1, borderColor: colors.separator,
  },
  dateDivider: {
    flexDirection: 'row', alignItems: 'center',
    marginVertical: 12, paddingHorizontal: spacing.md,
  },
  dateLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.separator },
  loadMoreBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    alignSelf: 'center', paddingVertical: 8, paddingHorizontal: 14,
    marginBottom: 8, backgroundColor: colors.brandLight, borderRadius: radii.full,
  },
});

const txt = {
  alertText: { fontSize: 13, color: '#FF453A', flex: 1, lineHeight: 18 } as TextStyle,
  welcomeTitle: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4 } as TextStyle,
  sugText: { fontSize: 13, color: colors.brand } as TextStyle,
  briefingBtnText: { fontSize: 14, fontWeight: '600', color: colors.brand } as TextStyle,
  dateText: { fontSize: 11, color: colors.labelTertiary, paddingHorizontal: 10, fontWeight: '500' } as TextStyle,
  loadMoreText: { fontSize: 12, color: colors.brand, fontWeight: '500' } as TextStyle,
};
