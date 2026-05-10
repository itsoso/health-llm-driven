import React, { useState, useEffect, useRef, useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle, ViewStyle, TouchableOpacity, LayoutAnimation, Animated } from 'react-native';
import * as Haptics from 'expo-haptics';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

function Shimmer({ width, height = 12, c }: { width: number; height?: number; c: ColorPalette }) {
  const opacity = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ]),
    );
    anim.start();
    return () => anim.stop();
  }, []);
  return <Animated.View style={{ width, height, borderRadius: height / 2, backgroundColor: c.separator, opacity }} />;
}

interface Props {
  score: number;
  city?: string;
  temperature?: number | null;
  weatherDesc?: string;
  aqiValue?: number | null;
  pm25?: number | null;
  tomorrowWeather?: string;
  tomorrowTempRange?: string;
  sleep?: string;
  sleepScore?: number | null;
  steps?: string;
  hr?: string;
  battery?: string;
  batteryCurrent?: number | null;
  batteryPeak?: number | null;
  isLoading?: boolean;
  onSettings?: () => void;
  onNewChat?: () => void;
  onHistory?: () => void;
  onSymptom?: () => void;
  onImport?: () => void;
  onLiveRun?: () => void;
}

function getAqiColor(v: number | null | undefined, c: ColorPalette): string {
  if (!v) return c.labelTertiary;
  if (v <= 50) return c.green;
  if (v <= 100) return c.amber;
  return c.red;
}

function sc(score: number, c: ColorPalette): string {
  if (score >= 80) return c.green;
  if (score >= 60) return c.amber;
  return c.red;
}

export default function HomeHeader({
  score, city, temperature, weatherDesc, aqiValue, pm25,
  tomorrowWeather, tomorrowTempRange, sleep, sleepScore, steps, hr, battery,
  batteryCurrent, batteryPeak, isLoading,
  onSettings, onNewChat, onHistory, onSymptom, onImport, onLiveRun,
}: Props) {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const [collapsed, setCollapsed] = useState(false);
  // 实时时钟: 每 30s 刷一次, 只存时间展示字符串, 不触发其他重渲
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    // 对齐整分钟边界: 算距离下一个整分钟的毫秒数, 之后再每 60s 更新
    let interval: ReturnType<typeof setInterval> | null = null;
    const msToNextMin = (60 - new Date().getSeconds()) * 1000;
    const firstTimer = setTimeout(() => {
      setNow(new Date());
      interval = setInterval(() => setNow(new Date()), 60_000);
    }, msToNextMin);
    return () => {
      clearTimeout(firstTimer);
      if (interval) clearInterval(interval);
    };
  }, []);
  const hour = now.getHours();
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
  const timeStr = `${String(hour).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const dateStr = `${now.getMonth() + 1}月${now.getDate()}日 ${['周日', '周一', '周二', '周三', '周四', '周五', '周六'][now.getDay()]}`;

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setCollapsed(!collapsed);
  };

  const ringSize = collapsed ? 28 : 52;
  const sw = collapsed ? 3 : 4;
  const r = (ringSize - sw) / 2;
  const cc = 2 * Math.PI * r;
  const off = cc * (1 - Math.min(score / 100, 1));

  // Collapsed mini bar
  if (collapsed) {
    return (
      <View style={styles.miniBar}>
        <TouchableOpacity onPress={toggle} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }} activeOpacity={0.7}>
          <View style={{ width: ringSize, height: ringSize, alignItems: 'center', justifyContent: 'center' }}>
            <Svg width={ringSize} height={ringSize}>
              <Defs><LinearGradient id="miniG" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor={c.brand} /><Stop offset="1" stopColor={c.green} /></LinearGradient></Defs>
              <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke={c.bgPrimary} strokeWidth={sw} fill="none" />
              <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="url(#miniG)" strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={cc} strokeDashoffset={off} transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`} />
            </Svg>
            <Text style={{ position: 'absolute', fontSize: 9, fontWeight: '800', color: sc(score, c) }}>{score}</Text>
          </View>
          <Text style={styles.miniTime}>{timeStr}</Text>
          <Text style={styles.miniWeather} numberOfLines={1}>{city} {temperature != null ? `${Math.round(temperature)}°` : ''} {weatherDesc || ''}</Text>
          <MiniVital color={c.purple} value={sleep || '--'} />
          <MiniVital color={c.pink} value={hr || '--'} />
          <MiniVital color={c.green} value={battery || '--'} />
        </TouchableOpacity>
        {onLiveRun && (
          <TouchableOpacity onPress={(e) => { e.stopPropagation(); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onLiveRun(); }} style={styles.miniAction} hitSlop={10} activeOpacity={0.6}>
            <Ionicons name="walk-outline" size={15} color={c.brand} />
          </TouchableOpacity>
        )}
        {onHistory && (
          <TouchableOpacity onPress={(e) => { e.stopPropagation(); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onHistory(); }} style={styles.miniAction} hitSlop={10} activeOpacity={0.6}>
            <Ionicons name="chatbubbles-outline" size={15} color={c.labelTertiary} />
          </TouchableOpacity>
        )}
        {onSymptom && (
          <TouchableOpacity onPress={(e) => { e.stopPropagation(); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onSymptom(); }} style={styles.miniAction} hitSlop={10} activeOpacity={0.6}>
            <Ionicons name="medkit-outline" size={15} color={c.labelTertiary} />
          </TouchableOpacity>
        )}
        {onImport && (
          <TouchableOpacity onPress={(e) => { e.stopPropagation(); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onImport(); }} style={styles.miniAction} hitSlop={10} activeOpacity={0.6}>
            <Ionicons name="cloud-upload-outline" size={15} color={c.labelTertiary} />
          </TouchableOpacity>
        )}
        {onNewChat && (
          <TouchableOpacity onPress={(e) => { e.stopPropagation(); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onNewChat(); }} style={styles.miniAction} hitSlop={10} activeOpacity={0.6}>
            <Ionicons name="create-outline" size={15} color={c.labelTertiary} />
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={toggle} style={styles.miniAction} hitSlop={8} activeOpacity={0.6}>
          <Ionicons name="chevron-down" size={14} color={c.labelTertiary} />
        </TouchableOpacity>
      </View>
    );
  }

  // Expanded card
  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ flex: 1 }}>
              <Text style={styles.greeting}>{greeting}</Text>
              <View style={styles.timeLine}>
                <Text style={styles.timeText}>{timeStr}</Text>
                <Text style={styles.dateText}>  {dateStr}</Text>
              </View>
            </View>
            {onLiveRun && (
              <TouchableOpacity onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onLiveRun(); }} style={styles.actionBtn} hitSlop={8} activeOpacity={0.6}>
                <Ionicons name="walk-outline" size={18} color={c.brand} />
              </TouchableOpacity>
            )}
            {onHistory && (
              <TouchableOpacity onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onHistory(); }} style={styles.actionBtn} hitSlop={8} activeOpacity={0.6}>
                <Ionicons name="chatbubbles-outline" size={18} color={c.labelTertiary} />
              </TouchableOpacity>
            )}
            {onSymptom && (
              <TouchableOpacity onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onSymptom(); }} style={styles.actionBtn} hitSlop={8} activeOpacity={0.6}>
                <Ionicons name="medkit-outline" size={18} color={c.labelTertiary} />
              </TouchableOpacity>
            )}
            {onImport && (
              <TouchableOpacity onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onImport(); }} style={styles.actionBtn} hitSlop={8} activeOpacity={0.6}>
                <Ionicons name="cloud-upload-outline" size={18} color={c.labelTertiary} />
              </TouchableOpacity>
            )}
            {onNewChat && (
              <TouchableOpacity onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); onNewChat(); }} style={styles.actionBtn} hitSlop={8} activeOpacity={0.6}>
                <Ionicons name="create-outline" size={18} color={c.labelTertiary} />
              </TouchableOpacity>
            )}
            {onSettings && (
              <TouchableOpacity onPress={onSettings} style={styles.actionBtn} hitSlop={8} activeOpacity={0.6}>
                <Ionicons name="settings-outline" size={18} color={c.labelTertiary} />
              </TouchableOpacity>
            )}
          </View>
          <View style={styles.weatherRow}>
            <Ionicons name="location-outline" size={12} color={c.brand} />
            <Text style={styles.weatherMain}>
              {city || '--'} {temperature != null ? `${Math.round(temperature)}°C` : ''} {weatherDesc || ''}
            </Text>
          </View>
          <View style={styles.subRow}>
            {aqiValue != null && (
              <View style={styles.aqiTag}>
                <View style={[styles.aqiDot, { backgroundColor: getAqiColor(aqiValue, c) }]} />
                <Text style={[styles.aqiText, { color: getAqiColor(aqiValue, c) }]}>AQI {aqiValue}</Text>
                {pm25 != null && <Text style={styles.pm25}>PM2.5 {Math.round(pm25)}</Text>}
              </View>
            )}
            {tomorrowWeather && (
              <Text style={styles.tomorrow}>明天 {tomorrowWeather} {tomorrowTempRange}</Text>
            )}
          </View>
        </View>

        <View style={styles.ringWrap}>
          <Svg width={ringSize} height={ringSize}>
            <Defs><LinearGradient id="hdrG" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor={c.brand} /><Stop offset="1" stopColor={c.green} /></LinearGradient></Defs>
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke={c.bgPrimary} strokeWidth={sw} fill="none" />
            <Circle cx={ringSize / 2} cy={ringSize / 2} r={r} stroke="url(#hdrG)" strokeWidth={sw} fill="none" strokeLinecap="round" strokeDasharray={cc} strokeDashoffset={off} transform={`rotate(-90 ${ringSize / 2} ${ringSize / 2})`} />
          </Svg>
          <View style={styles.ringCenter}>
            <Text style={[styles.scoreNum, { color: sc(score, c) }]}>{score}</Text>
            <Text style={styles.scoreLabel}>健康</Text>
          </View>
        </View>
      </View>

      <View style={styles.vitalsRow}>
        {isLoading ? (
          <View style={{ flex: 1, flexDirection: 'row', justifyContent: 'space-around', paddingVertical: 4 }}>
            <Shimmer width={40} height={14} c={c} />
            <Shimmer width={40} height={14} c={c} />
            <Shimmer width={40} height={14} c={c} />
            <Shimmer width={40} height={14} c={c} />
          </View>
        ) : (<>
          <Vital icon="moon-outline" color={c.purple} label={sleepScore ? `睡眠 ${sleepScore}分` : '睡眠'} value={sleep || '--'} c={c} />
          <View style={styles.vDivider} />
          <Vital icon="footsteps-outline" color={c.orange} label="步数" value={steps || '--'} c={c} />
          <View style={styles.vDivider} />
          <Vital icon="heart-outline" color={c.pink} label="心率" value={hr || '--'} c={c} />
          <View style={styles.vDivider} />
          <Vital icon="battery-charging-outline" color={c.green}
            label={batteryPeak != null ? `峰值 ${batteryPeak}` : '电量'}
            value={batteryCurrent != null ? `${batteryCurrent}` : (battery || '--')}
            c={c} />
        </>)}
      </View>

      <TouchableOpacity style={styles.collapseBtn} onPress={toggle} activeOpacity={0.6}>
        <Ionicons name="chevron-up" size={16} color={c.labelTertiary} />
      </TouchableOpacity>
    </View>
  );
}

function Vital({ icon, color, label, value, c }: { icon: any; color: string; label: string; value: string; c: ColorPalette }) {
  return (
    <View style={{ flex: 1, alignItems: 'center', gap: 2 }}>
      <Ionicons name={icon} size={14} color={color} />
      <Text style={{ fontSize: 15, fontWeight: '700', fontVariant: ['tabular-nums'], color }}>{value}</Text>
      <Text style={{ fontSize: 10, color: c.labelTertiary }}>{label}</Text>
    </View>
  );
}

function MiniVital({ color, value }: { color: string; value: string }) {
  return <Text style={{ fontSize: 12, fontWeight: '700', fontVariant: ['tabular-nums'], color }}>{value}</Text>;
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.xl,
      padding: spacing.lg,
      marginHorizontal: spacing.lg,
      marginTop: spacing.sm,
      marginBottom: spacing.sm,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 2 },
            shadowOpacity: 0.08,
            shadowRadius: 8,
            elevation: 2,
          }),
    },
    miniBar: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      backgroundColor: c.bgCard,
      borderRadius: radii.full,
      marginHorizontal: spacing.lg,
      marginTop: spacing.sm,
      marginBottom: spacing.sm,
      paddingHorizontal: 12,
      paddingVertical: 8,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06,
            shadowRadius: 3,
            elevation: 1,
          }),
    },
    miniAction: { padding: 4 },
    topRow: { flexDirection: 'row', alignItems: 'flex-start' },
    weatherRow: { flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 4 },
    subRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
    aqiTag: { flexDirection: 'row', alignItems: 'center', gap: 4 },
    aqiDot: { width: 6, height: 6, borderRadius: 3 },
    ringWrap: { width: 52, height: 52, alignItems: 'center', justifyContent: 'center' },
    ringCenter: { position: 'absolute', alignItems: 'center' },
    vitalsRow: {
      flexDirection: 'row', alignItems: 'center',
      paddingTop: spacing.md, marginTop: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator,
    },
    vDivider: { width: StyleSheet.hairlineWidth, height: 28, backgroundColor: c.separator },
    actionBtn: { padding: 8, minWidth: 36, minHeight: 36, alignItems: 'center', justifyContent: 'center' },
    collapseBtn: { alignItems: 'center', paddingTop: 6 },
    greeting: { fontSize: 22, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    timeLine: { marginTop: 2, flexDirection: 'row', alignItems: 'baseline' } as ViewStyle,
    timeText: { fontSize: 14, fontWeight: '700', color: c.brand, fontVariant: ['tabular-nums'] as const } as TextStyle,
    dateText: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    weatherMain: { fontSize: 13, color: c.labelPrimary } as TextStyle,
    aqiText: { fontSize: 11, fontWeight: '600' } as TextStyle,
    pm25: { fontSize: 10, color: c.labelSecondary } as TextStyle,
    tomorrow: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    scoreNum: { fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
    scoreLabel: { fontSize: 8, fontWeight: '500', color: c.labelTertiary, marginTop: -2 } as TextStyle,
    miniWeather: { fontSize: 12, color: c.labelSecondary, flex: 1 } as TextStyle,
    miniTime: { fontSize: 13, fontWeight: '700', color: c.brand, fontVariant: ['tabular-nums'] as const } as TextStyle,
  });
}
