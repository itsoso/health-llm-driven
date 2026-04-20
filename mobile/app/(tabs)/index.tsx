import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList, StyleSheet,
  KeyboardAvoidingView, Platform, ActivityIndicator, TextStyle, Image,
  Alert, Modal, Pressable, Animated, RefreshControl, Keyboard, ScrollView, Clipboard,
  GestureResponderEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-native-markdown-display';
import ReAnimated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming } from 'react-native-reanimated';
import { streamChat, getConversations, getConversationMessages, deleteConversation, type ChatMessage, type StreamEvent } from '@/services/chat';
import { useMediaPicker } from '@/hooks/useMediaPicker';
import { useVoiceRecording } from '@/hooks/useVoiceRecording';
import api from '@/services/api';
import { getSafetyReport } from '@/services/safety';
import HomeHeader from '@/components/dashboard/HomeHeader';
import { dispatchCard, renderCard, renderServerCards } from '@/components/chat/cards';
import { colors, spacing, radii, shadows } from '@/constants/theme';

function BrandCircle({ size, children, style }: { size: number; children: React.ReactNode; style?: any }) {
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }, style]}>
      {children}
    </View>
  );
}

interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  imageUri?: string;
  isBriefing?: boolean;
  cardType?: string;
  cardData?: any;
}

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function PulsingDot() {
  const opacity = useSharedValue(1);
  React.useEffect(() => {
    opacity.value = withRepeat(withTiming(0.3, { duration: 600 }), -1, true);
  }, [opacity]);
  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return <ReAnimated.View style={[styles.recDot, animStyle]} />;
}

export default function HomeScreen() {
  const router = useRouter();
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const { pendingImage, setPendingImage, pickImage, takePhoto, pickFile: pickFileMedia } = useMediaPicker();
  const [showMenu, setShowMenu] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [syncing, setSyncing] = useState(false);
  const cancelYRef = useRef<number | null>(null);

  const voice = useVoiceRecording({
    onTranscript: (text) => setInput(text),
  });
  const [conversationId, setConversationId] = useState<number | undefined>(undefined);
  const [refreshing, setRefreshing] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const qc = useQueryClient();
  const flatListRef = useRef<FlatList>(null);
  const isNearBottom = useRef(true);
  const plusRotation = useRef(new Animated.Value(0)).current;

  // Load latest conversation on mount
  useEffect(() => {
    (async () => {
      try {
        const convs = await getConversations();
        if (convs.length > 0) {
          const latestId = convs[0].id;
          setConversationId(latestId);
          const msgs = await getConversationMessages(latestId);
          if (msgs.length > 0) {
            const restored: UIMessage[] = msgs.map((m: any, i: number) => ({
              id: `hist-${m.id || i}`,
              role: m.role,
              content: m.content,
            }));
            setMessages(restored);

            // Re-dispatch cards for user messages to restore dynamic cards
            const userMsgs = restored.filter(m => m.role === 'user' && m.content);
            for (const um of userMsgs) {
              try {
                const card = await dispatchCard({
                  query: um.content,
                  query_lower: um.content.toLowerCase(),
                  toolsUsed: new Set(),
                  data: {},
                  api,
                });
                if (card) {
                  setMessages(prev => {
                    const idx = prev.findIndex(m => m.id === um.id);
                    if (idx < 0) return prev;
                    const existingCard = prev.find((m, j) => j > idx && m.cardType);
                    if (existingCard) return prev;
                    const cardMsg: UIMessage = {
                      id: `card-${um.id}`,
                      role: 'assistant',
                      content: '',
                      cardType: card.type,
                      cardData: card.data,
                    };
                    const insertAt = Math.min(idx + 2, prev.length);
                    return [...prev.slice(0, insertAt), cardMsg, ...prev.slice(insertAt)];
                  });
                }
              } catch {}
            }
          }
        }
      } catch { /* ignore */ }
    })();
  }, []);

  // Scroll to bottom when keyboard appears
  useEffect(() => {
    const showSub = Keyboard.addListener('keyboardDidShow', () => {
      setKeyboardVisible(true);
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    });
    const hideSub = Keyboard.addListener('keyboardDidHide', () => {
      setKeyboardVisible(false);
    });
    return () => { showSub.remove(); hideSub.remove(); };
  }, []);

  // ── Data queries ──
  const { data: scoreData } = useQuery({ queryKey: ['healthScore'], queryFn: () => api.get(`/health-score/daily/me?target_date=${today()}`).then(r => r.data), staleTime: 120_000 });
  const { data: garminData } = useQuery({ queryKey: ['garminToday'], queryFn: () => api.get(`/daily-health/garmin/me?start_date=${today()}&end_date=${today()}`).then(r => r.data), staleTime: 120_000 });
  const { data: weatherData } = useQuery({ queryKey: ['weather'], queryFn: () => api.get('/environment/weather').then(r => r.data), staleTime: 300_000 });
  const { data: aqiData } = useQuery({ queryKey: ['aqi'], queryFn: () => api.get('/environment/air-quality').then(r => r.data), staleTime: 300_000 });
  const { data: safetyData } = useQuery({ queryKey: ['safety'], queryFn: getSafetyReport, staleTime: 300_000 });
  const { data: profileData } = useQuery({ queryKey: ['profile'], queryFn: () => api.get('/profile/me').then(r => r.data), staleTime: 600_000 });
  const { data: forecastData } = useQuery({ queryKey: ['forecast'], queryFn: () => api.get('/environment/weather/forecast?days=2').then(r => r.data).catch(() => null), staleTime: 300_000 });

  const score = scoreData?.total_score ?? 0;
  const garmin = Array.isArray(garminData) && garminData.length > 0 ? garminData[0] : null;
  const weather = weatherData?.weather ?? weatherData;
  const city = profileData?.manual_location?.city || profileData?.detected_location?.city || profileData?.city || '';
  const weatherText = `${city} ${weather?.temperature != null ? Math.round(weather.temperature) + '°C' : ''} ${weather?.weather || ''}`.trim();
  const tomorrowFc = forecastData?.forecasts?.[1];
  const tomorrowText = tomorrowFc ? `明天 ${tomorrowFc.weather} ${tomorrowFc.temp_min}~${tomorrowFc.temp_max}°C` : undefined;

  // High-priority alerts only
  const criticalAlerts = (safetyData?.alerts || []).filter((a: any) => {
    const sev = typeof a.severity === 'string' ? a.severity : a.severity?.label;
    return sev === 'critical' || sev === 'high';
  });

  const briefingInjected = useRef(false);

  // ── Send ──
  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text || input).trim();
    const hasImage = !!pendingImage;
    if (!msg && !hasImage) return;
    if (isStreaming) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    setInput('');
    const finalMsg = msg || (hasImage ? '请分析这张图片' : '');
    const userMsg: UIMessage = { id: nextId(), role: 'user', content: finalMsg, imageUri: pendingImage?.uri };
    const aId = nextId();
    const aiMsg: UIMessage = { id: aId, role: 'assistant', content: '', streaming: true };

    setMessages(prev => [...prev, userMsg, aiMsg]);
    setIsStreaming(true);
    const imgData = pendingImage;
    setPendingImage(null);

    // Slow response indicator
    let gotFirstToken = false;
    const slowTimer = setTimeout(() => {
      if (!gotFirstToken) {
        setMessages(prev => prev.map(m => m.id === aId && !m.content ? { ...m, content: '⏳ AI 正在思考中...' } : m));
      }
    }, 8000);

    try {
      const toolsUsed: Set<string> = new Set();
      for await (const evt of streamChat(finalMsg, conversationId, imgData?.base64, imgData?.type)) {
        if (evt.type === 'token' || evt.type === 'tool') {
          if (!gotFirstToken) { gotFirstToken = true; clearTimeout(slowTimer); setMessages(prev => prev.map(m => m.id === aId && m.content === '⏳ AI 正在思考中...' ? { ...m, content: '' } : m)); }
          setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content.replace('⏳ AI 正在思考中...', '') + (evt.content || '') } : m));
          // Track all tools called (from both tool_call and tool_result)
          if (evt.toolName) toolsUsed.add(evt.toolName);
        } else if (evt.type === 'done') {
          if (evt.conversationId && !conversationId) setConversationId(evt.conversationId);
          // ── 动态卡片系统: 1) 后端主动下发优先 2) 本地 registry 兜底 ──
          const serverCards = renderServerCards((evt as any).cards);
          if (serverCards.length > 0) {
            // ≥2 张卡合并成 cards_group (iPad 双列, iPhone 单列)
            const single = serverCards.length === 1 ? serverCards[0] : {
              type: 'cards_group', data: { cards: serverCards },
            };
            setMessages(prev => [
              ...prev,
              { id: nextId(), role: 'assistant' as const, content: '',
                cardType: single.type, cardData: single.data },
            ]);
          } else {
            const g = Array.isArray(garminData) && garminData.length > 0 ? garminData[0] : null;
            const card = await dispatchCard({
              query: finalMsg,
              query_lower: finalMsg.toLowerCase(),
              toolsUsed,
              data: {
                garmin: g,
                score: scoreData,
                weather: weatherData,
                aqi: aqiData,
                profile: profileData,
              },
              api,
            });
            if (card) {
              setMessages(prev => [...prev, {
                id: nextId(), role: 'assistant', content: '',
                cardType: card.type, cardData: card.data,
              }]);
            }
          }
        } else if (evt.type === 'error') {
          setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content + `\n❌ ${evt.content}` } : m));
        }
      }
    } catch (err: any) {
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: m.content || `[错误] ${err?.message || '请求失败'}` } : m));
    } finally {
      clearTimeout(slowTimer);
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, streaming: false } : m));
      setIsStreaming(false);
    }
  }, [input, isStreaming, pendingImage, conversationId]);

  // ── Media ──
  const toggleMenu = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const toOpen = !showMenu;
    setShowMenu(toOpen);
    Animated.spring(plusRotation, { toValue: toOpen ? 1 : 0, useNativeDriver: true, friction: 8 }).start();
  };

  const handlePickImage = useCallback(async () => {
    setShowMenu(false);
    await pickImage();
  }, [pickImage]);

  const handleTakePhoto = useCallback(async () => {
    setShowMenu(false);
    await takePhoto();
  }, [takePhoto]);

  const handlePickFile = useCallback(async () => {
    setShowMenu(false);
    const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true });
    if (!result.canceled && result.assets[0]) setInput(`请分析文件：${result.assets[0].name}`);
  }, []);

  // ── Voice — long-press to record, release to transcribe (DeepSeek style) ──
  const handleVoicePressIn = useCallback((e: GestureResponderEvent) => {
    cancelYRef.current = e.nativeEvent.pageY;
    voice.startRecording();
  }, [voice]);

  const handleVoicePressOut = useCallback((e: GestureResponderEvent) => {
    const startY = cancelYRef.current;
    const endY = e.nativeEvent.pageY;
    if (startY != null && startY - endY > 60) {
      voice.cancelRecording();
    } else {
      voice.stopAndTranscribe();
    }
    cancelYRef.current = null;
  }, [voice]);

  // ── Render ──
  const renderMessage = useCallback(({ item }: { item: UIMessage }) => {
    const isUser = item.role === 'user';

    // Inline card messages (no bubble, just the card) — 走动态卡片系统
    if (item.cardType && item.cardData) {
      const rendered = renderCard({ type: item.cardType, data: item.cardData });
      if (rendered) {
        return (
          <View style={[styles.msgRow, styles.msgRowAI]}>
            <View style={{ width: 36 }} />
            {rendered}
          </View>
        );
      }
    }

    return (
      <View style={[styles.msgRow, isUser ? styles.msgRowUser : styles.msgRowAI]}>
        {!isUser && (
          <BrandCircle size={28} style={{ marginRight: 8 }}>
            <Ionicons name="sparkles" size={12} color="#fff" />
          </BrandCircle>
        )}
        {isUser ? (
          <TouchableOpacity style={[styles.bubble, styles.bubbleUser]} activeOpacity={0.8}
            onLongPress={() => { Clipboard.setString(item.content); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('已复制'); }}>
            {item.imageUri && <Image source={{ uri: item.imageUri }} style={styles.msgImage} resizeMode="cover" />}
            <Text selectable style={txt.bubbleUser}>{item.content}</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[styles.bubble, styles.bubbleAI]} activeOpacity={0.8}
            onLongPress={() => { Clipboard.setString(item.content); Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); Alert.alert('已复制'); }}>
            <Markdown style={mdStyles}>{item.content || ' '}</Markdown>
            {item.streaming && <ActivityIndicator size="small" color={colors.brand} style={{ marginTop: 4 }} />}
          </TouchableOpacity>
        )}
      </View>
    );
  }, []);

  const canSend = (input.trim() || pendingImage) && !isStreaming;
  const rotate = plusRotation.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '45deg'] });

  // Quick vitals for mini indicators below status bar
  const sleepH = garmin?.total_sleep_duration ? (garmin.total_sleep_duration / 60).toFixed(1) : '--';
  const steps = garmin?.steps ?? '--';
  const hrVal = garmin?.resting_heart_rate ?? '--';
  const batteryCurrent = garmin?.body_battery_current;
  const batteryPeak = garmin?.body_battery_most_charged;
  const batteryVal = batteryCurrent != null && batteryPeak != null
    ? `${batteryCurrent}/${batteryPeak}`
    : `${batteryCurrent ?? batteryPeak ?? '--'}`;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Home Header Card */}
      <HomeHeader
        score={score}
        city={city}
        temperature={weather?.temperature}
        weatherDesc={weather?.weather}
        aqiValue={aqiData?.aqi}
        pm25={aqiData?.pm25}
        tomorrowWeather={tomorrowFc?.weather}
        tomorrowTempRange={tomorrowFc ? `${tomorrowFc.temp_min}~${tomorrowFc.temp_max}°C` : undefined}
        sleep={`${sleepH}h`}
        sleepScore={garmin?.sleep_score}
        steps={typeof steps === 'number' ? steps.toLocaleString() : `${steps}`}
        hr={`${hrVal}`}
        battery={`${batteryVal}`}
        batteryCurrent={batteryCurrent}
        batteryPeak={batteryPeak}
        onSettings={() => router.push('/settings' as any)}
        onNewChat={() => { setMessages([]); setConversationId(undefined); briefingInjected.current = false; }}
        onHistory={() => {
          setShowHistory(true);
          getConversations().then(convs => setConversations(convs)).catch(() => setConversations([]));
        }}
      />

      {/* Critical alerts */}
      {criticalAlerts.length > 0 && (
        <View style={styles.alertBanner}>
          <Ionicons name="warning" size={16} color="#FF453A" />
          <Text style={txt.alertText} numberOfLines={2}>
            {criticalAlerts[0].title}: {criticalAlerts[0].message}
          </Text>
        </View>
      )}

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={0}>
        {/* Messages */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={item => item.id}
          renderItem={renderMessage}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={async () => {
              setRefreshing(true);
              // Sync Garmin first, then refresh all data
              try { await api.post('/data-collection/garmin/me/sync?days=1'); } catch {}
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
              {/* Generate briefing button */}
              <TouchableOpacity style={styles.briefingBtn} onPress={() => sendMessage('今天健康如何？给我一份简报')} activeOpacity={0.7}>
                <Ionicons name="sparkles-outline" size={16} color={colors.brand} />
                <Text style={txt.briefingBtnText}>生成今日健康简报</Text>
              </TouchableOpacity>
              <View style={styles.sugRow}>
                {['记录喝了杯水', '分析睡眠质量', '吃了鱼油', '最近HRV趋势'].map(s => (
                  <TouchableOpacity key={s} style={styles.sugChip} onPress={() => sendMessage(s)}>
                    <Text style={txt.sugText}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          }
        />

        {/* Pending image */}
        {pendingImage && (
          <View style={styles.previewBar}>
            <Image source={{ uri: pendingImage.uri }} style={styles.previewImg} />
            <Text style={txt.previewText}>图片已选择</Text>
            <TouchableOpacity onPress={() => setPendingImage(null)}>
              <Ionicons name="close-circle" size={20} color={colors.red} />
            </TouchableOpacity>
          </View>
        )}

        {/* Recording overlay */}
        {voice.isRecording && (
          <View style={styles.recordBar}>
            <PulsingDot />
            <Text style={txt.recText}>
              {Math.floor(voice.durationMs / 1000)}s · 松手发送，上滑取消
            </Text>
          </View>
        )}
        {voice.isTranscribing && (
          <View style={styles.recordBar}>
            <ActivityIndicator size="small" color={colors.brand} />
            <Text style={[txt.recText, { color: colors.brand }]}>识别中...</Text>
          </View>
        )}

        {/* Input bar — ChatGPT style: + | [input ... 🎤 ⬆] */}
        <View style={styles.inputBar}>
          <TouchableOpacity onPress={toggleMenu} style={styles.plusBtn}>
            <Ionicons name={showMenu ? 'close' : 'add'} size={22} color={colors.labelPrimary} />
          </TouchableOpacity>
          <View style={styles.inputWrap}>
            <TextInput
              style={styles.textInput}
              placeholder="有问题，尽管问"
              placeholderTextColor={colors.labelTertiary}
              value={input}
              onChangeText={setInput}
              onSubmitEditing={() => sendMessage()}
              returnKeyType="send"
              multiline
              maxLength={2000}
            />
            <View style={styles.inputActions}>
              {canSend ? (
                <TouchableOpacity onPress={() => sendMessage()} style={styles.inlineSendBtn}>
                  <Ionicons name="arrow-up-circle" size={28} color={colors.brand} />
                </TouchableOpacity>
              ) : (
                <TouchableOpacity
                  onPressIn={handleVoicePressIn}
                  onPressOut={handleVoicePressOut}
                  delayLongPress={0}
                  style={[styles.inlineVoiceBtn, voice.isRecording && styles.inlineVoiceBtnActive]}
                >
                  <Ionicons name={voice.isRecording ? 'mic' : 'mic-outline'} size={20} color={voice.isRecording ? '#fff' : colors.labelTertiary} />
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>
        {!keyboardVisible && <View style={{ height: 83 }} />}
      </KeyboardAvoidingView>

      {/* Conversation history */}
      <Modal visible={showHistory} transparent animationType="slide" onRequestClose={() => setShowHistory(false)}>
        <Pressable style={styles.menuOverlay} onPress={() => setShowHistory(false)}>
          <Pressable style={styles.menuSheet} onPress={e => e.stopPropagation()}>
            <View style={styles.menuHandle} />
            <Text style={{ fontSize: 17, fontWeight: '600', color: colors.labelPrimary, marginBottom: 12 }}>对话历史</Text>
            {conversations.length === 0 ? (
              <Text style={{ fontSize: 14, color: colors.labelTertiary, textAlign: 'center', paddingVertical: 20 }}>加载中...</Text>
            ) : (
              <ScrollView style={{ maxHeight: 400 }}>
                {conversations.slice(0, 20).map((item: any) => (
                  <TouchableOpacity
                    key={item.id}
                    style={{ paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator, flexDirection: 'row', alignItems: 'center' }}
                    onPress={async () => {
                      setShowHistory(false);
                      setConversationId(item.id);
                      try {
                        const msgs = await getConversationMessages(item.id);
                        const restored: UIMessage[] = msgs.map((m: any, i: number) => ({ id: `h-${m.id || i}`, role: m.role, content: m.content }));
                        setMessages(restored);
                        const userMsgs = restored.filter(m => m.role === 'user' && m.content);
                        for (const um of userMsgs) {
                          try {
                            const card = await dispatchCard({ query: um.content, query_lower: um.content.toLowerCase(), toolsUsed: new Set(), data: {}, api });
                            if (card) {
                              setMessages(prev => {
                                const idx = prev.findIndex(m => m.id === um.id);
                                if (idx < 0 || prev.find((m, j) => j > idx && m.cardType)) return prev;
                                const cardMsg: UIMessage = { id: `card-${um.id}`, role: 'assistant', content: '', cardType: card.type, cardData: card.data };
                                const insertAt = Math.min(idx + 2, prev.length);
                                return [...prev.slice(0, insertAt), cardMsg, ...prev.slice(insertAt)];
                              });
                            }
                          } catch {}
                        }
                      } catch {}
                    }}
                    activeOpacity={0.6}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 15, color: colors.labelPrimary }} numberOfLines={1}>{item.title || `对话 #${item.id}`}</Text>
                      <Text style={{ fontSize: 12, color: colors.labelTertiary, marginTop: 2 }}>{item.created_at?.slice(0, 10) || ''}</Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => {
                        Alert.alert('删除对话', `确定删除「${item.title || '对话'}」？`, [
                          { text: '取消', style: 'cancel' },
                          { text: '删除', style: 'destructive', onPress: async () => {
                            await deleteConversation(item.id);
                            setConversations(prev => prev.filter((c: any) => c.id !== item.id));
                            if (conversationId === item.id) { setMessages([]); setConversationId(undefined); }
                          }},
                        ]);
                      }}
                      hitSlop={8} style={{ padding: 8 }}
                    >
                      <Ionicons name="trash-outline" size={16} color={colors.red} />
                    </TouchableOpacity>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Plus menu */}
      <Modal visible={showMenu} transparent animationType="slide" onRequestClose={toggleMenu}>
        <Pressable style={styles.menuOverlay} onPress={toggleMenu}>
          <Pressable style={styles.menuSheet} onPress={e => e.stopPropagation()}>
            <View style={styles.menuHandle} />
            <MenuItem icon="camera-outline" label="拍照" desc="拍摄食物或健康数据" onPress={handleTakePhoto} />
            <MenuItem icon="image-outline" label="相册" desc="选择图片发送分析" onPress={handlePickImage} />
            <MenuItem icon="document-outline" label="文件" desc="上传文档或报告" onPress={handlePickFile} />
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

function MenuItem({ icon, label, desc, onPress }: { icon: any; label: string; desc: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.menuItem} onPress={onPress} activeOpacity={0.6}>
      <View style={styles.menuIconWrap}>
        <Ionicons name={icon} size={20} color={colors.labelPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={txt.menuLabel}>{label}</Text>
        <Text style={txt.menuDesc}>{desc}</Text>
      </View>
    </TouchableOpacity>
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
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    backgroundColor: colors.bgPrimary,
  },
  plusBtn: {
    width: 34, height: 34, borderRadius: 17,
    backgroundColor: colors.bgCard, borderWidth: 1, borderColor: colors.separator,
    alignItems: 'center', justifyContent: 'center',
  },
  inputWrap: {
    flex: 1, flexDirection: 'row', alignItems: 'flex-end',
    backgroundColor: colors.bgCard, borderRadius: 22,
    borderWidth: 1, borderColor: colors.separator,
    paddingLeft: 14, paddingRight: 4, paddingVertical: 4,
  },
  textInput: {
    flex: 1, fontSize: 15, maxHeight: 90, color: colors.labelPrimary,
    paddingTop: 6, paddingBottom: 6,
  },
  inputActions: {
    flexDirection: 'row', alignItems: 'center', paddingBottom: 2,
  },
  inlineSendBtn: { padding: 2 },
  inlineVoiceBtn: {
    width: 30, height: 30, borderRadius: 15,
    alignItems: 'center', justifyContent: 'center',
  },
  inlineVoiceBtnActive: {
    backgroundColor: '#FF453A',
  },
  previewBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: 4,
    backgroundColor: colors.bgCard,
  },
  previewImg: { width: 36, height: 36, borderRadius: 6 },
  recordBar: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: spacing.lg, paddingVertical: 6,
    backgroundColor: '#FFF0F0',
  },
  recDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#FF453A' },
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
  menuOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', justifyContent: 'flex-end' },
  menuSheet: {
    backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingHorizontal: spacing.xl, paddingBottom: 40, paddingTop: 8,
  },
  menuHandle: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: colors.labelQuaternary,
    alignSelf: 'center', marginBottom: spacing.lg,
  },
  menuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.separator,
  },
  menuIconWrap: {
    width: 38, height: 38, borderRadius: 12, backgroundColor: colors.bgPrimary,
    alignItems: 'center', justifyContent: 'center',
  },
});

const txt = {
  bubbleUser: { fontSize: 15, lineHeight: 22, color: '#fff' } as TextStyle,
  alertText: { fontSize: 13, color: '#FF453A', flex: 1, lineHeight: 18 } as TextStyle,
  vitalVal: { fontSize: 12, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  welcomeTitle: { fontSize: 20, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  welcomeSub: { fontSize: 14, color: colors.labelSecondary, marginTop: 4 } as TextStyle,
  sugText: { fontSize: 13, color: colors.brand } as TextStyle,
  briefingBtnText: { fontSize: 14, fontWeight: '600', color: colors.brand } as TextStyle,
  previewText: { fontSize: 12, color: colors.labelSecondary, flex: 1 } as TextStyle,
  recText: { fontSize: 13, color: '#FF453A', flex: 1 } as TextStyle,
  menuLabel: { fontSize: 16, fontWeight: '500', color: colors.labelPrimary } as TextStyle,
  menuDesc: { fontSize: 12, color: colors.labelSecondary, marginTop: 1 } as TextStyle,
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
