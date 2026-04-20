import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, TextStyle, Image,
  Alert, RefreshControl, Keyboard,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as Clipboard from 'expo-clipboard';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-native-markdown-display';
import { getConversations, deleteConversation } from '@/services/chat';
import api from '@/services/api';
import { getSafetyReport } from '@/services/safety';
import HomeHeader from '@/components/dashboard/HomeHeader';
import ChatInputBar from '@/components/chat/ChatInputBar';
import ConversationSheet from '@/components/chat/ConversationSheet';
import { renderCard } from '@/components/chat/cards';
import { useChatEngine, type UIMessage } from '@/hooks/useChatEngine';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function BrandCircle({ size, children, style }: { size: number; children: React.ReactNode; style?: any }) {
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }, style]}>
      {children}
    </View>
  );
}

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function HomeScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);

  // ── Data queries ──
  const { data: scoreData } = useQuery({ queryKey: ['healthScore'], queryFn: () => api.get(`/health-score/daily/me?target_date=${today()}`).then(r => r.data), staleTime: 120_000 });
  const { data: garminData } = useQuery({ queryKey: ['garminToday'], queryFn: () => api.get(`/daily-health/garmin/me?start_date=${today()}&end_date=${today()}`).then(r => r.data), staleTime: 120_000 });
  const { data: weatherData } = useQuery({ queryKey: ['weather'], queryFn: () => api.get('/environment/weather').then(r => r.data), staleTime: 300_000 });
  const { data: aqiData } = useQuery({ queryKey: ['aqi'], queryFn: () => api.get('/environment/air-quality').then(r => r.data), staleTime: 300_000 });
  const { data: safetyData } = useQuery({ queryKey: ['safety'], queryFn: getSafetyReport, staleTime: 300_000 });
  const { data: profileData } = useQuery({ queryKey: ['profile'], queryFn: () => api.get('/profile/me').then(r => r.data), staleTime: 600_000 });
  const { data: forecastData } = useQuery({ queryKey: ['forecast'], queryFn: () => api.get('/environment/weather/forecast?days=2').then(r => r.data).catch(() => null), staleTime: 300_000 });

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
  const handleSend = useCallback((text: string, image?: any) => {
    chat.sendMessage(text, image);
  }, [chat.sendMessage]);

  // ── Render message ──
  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const isUser = item.role === 'user';
    if (item.cardType && item.cardData) {
      const rendered = renderCard({ type: item.cardType, data: item.cardData });
      if (rendered) return <View style={[styles.msgRow, styles.msgRowAI]}><View style={{ width: 36 }} />{rendered}</View>;
    }
    return (
      <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
        {!isUser && <BrandCircle size={28} style={{ marginRight: 8 }}><Ionicons name="sparkles" size={12} color="#fff" /></BrandCircle>}
        {isUser ? (
          <TouchableOpacity style={[styles.bubble, styles.bubbleUser]} activeOpacity={0.8}
            onLongPress={() => { Clipboard.setStringAsync(item.content); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('已复制'); }}
            accessibilityRole="text" accessibilityLabel={`你: ${item.content}`}>
            {item.imageUri && <Image source={{ uri: item.imageUri }} style={styles.msgImage} resizeMode="cover" />}
            <Text selectable style={txt.bubbleUser}>{item.content}</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[styles.bubble, styles.bubbleAI]} activeOpacity={0.8}
            onLongPress={() => { Clipboard.setStringAsync(item.content); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('已复制'); }}
            accessibilityRole="text" accessibilityLabel={`AI: ${item.content}`}>
            <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
            {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 4 }} />}
          </TouchableOpacity>
        )}
      </View>
    );
  }, []);

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
        onSettings={() => router.push('/settings' as any)}
        onNewChat={chat.newChat}
        onHistory={() => {
          setShowHistory(true);
          getConversations().then(convs => setConversations(convs)).catch(() => setConversations([]));
        }}
      />

      {criticalAlerts.length > 0 && (
        <View style={styles.alertBanner} accessibilityRole="alert">
          <Ionicons name="warning" size={16} color="#FF453A" />
          <Text style={txt.alertText} numberOfLines={2}>{criticalAlerts[0].title}: {criticalAlerts[0].message}</Text>
        </View>
      )}

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={0}>
        <FlatList
          ref={flatListRef}
          data={chat.messages}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={async () => {
              setRefreshing(true);
              try { await api.post('/data-collection/garmin/me/sync?days=1'); } catch { console.warn('Garmin sync failed'); }
              await Promise.all([
                qc.invalidateQueries({ queryKey: ['healthScore'] }),
                qc.invalidateQueries({ queryKey: ['garminToday'] }),
                qc.invalidateQueries({ queryKey: ['weather'] }),
                qc.invalidateQueries({ queryKey: ['aqi'] }),
                qc.invalidateQueries({ queryKey: ['safety'] }),
                qc.invalidateQueries({ queryKey: ['forecast'] }),
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

      <ConversationSheet
        visible={showHistory}
        onClose={() => setShowHistory(false)}
        conversations={conversations}
        setConversations={setConversations}
        currentConversationId={chat.conversationId}
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
  msgRow: { flexDirection: 'row', marginBottom: 10, alignItems: 'flex-end' },
  msgRowUser: { justifyContent: 'flex-end' },
  msgRowAI: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '80%', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8 },
  bubbleUser: { backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  bubbleAI: { backgroundColor: '#fff', borderBottomLeftRadius: 4, ...shadows.subtle },
  msgImage: { width: 160, height: 120, borderRadius: 10, marginBottom: 4 },
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
});

const txt = {
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  alertText: { fontSize: 13, color: '#FF453A', flex: 1, lineHeight: 18 } as TextStyle,
  welcomeTitle: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4 } as TextStyle,
  sugText: { fontSize: 13, color: colors.brand } as TextStyle,
  briefingBtnText: { fontSize: 14, fontWeight: '600', color: colors.brand } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 22, color: colors.labelPrimary },
  heading2: { fontSize: 16, fontWeight: '700', color: colors.labelPrimary, marginTop: 6, marginBottom: 2 },
  heading3: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 4 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 2 },
  list_item: { flexDirection: 'row', marginVertical: 1 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 3, fontFamily: 'Menlo', fontSize: 13, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 6, padding: 8, fontFamily: 'Menlo', fontSize: 12, marginVertical: 4 },
  paragraph: { marginVertical: 2 },
  link: { color: colors.brand },
});
