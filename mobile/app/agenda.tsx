/**
 * 今日议程页 —— 消费后端 /agenda/today(R1)。
 *
 * 一处可见「今天该做什么」:三域协议待办(饮水/用药/饮食)+ 到期复查;
 * 协议项可一键「完成」(双轨协议轨 → 经 /agenda/complete 写真实业务记录)。
 *
 * 入口:Today / 设置 跳转。后端能力首次在手机可见可用。
 */
import React, { useMemo } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator, RefreshControl,
  Alert, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { useAgendaToday, useCompleteAgendaItem, useSeedDemo } from '../hooks/useAgenda';
import { isProtocolActionable, MANUAL_CAPTURE, type AgendaItem } from '../services/agenda';

const TYPE_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  hydration: 'water-outline',
  medication: 'medkit-outline',
  diet: 'restaurant-outline',
  sleep: 'moon-outline',
  training: 'barbell-outline',
  checkup: 'calendar-outline',
  data_quality: 'git-compare-outline',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '待完成', completed: '已完成', skipped: '已跳过', due: '待复查', overdue: '已逾期',
  info: '今日建议',
};

const LIGHT_COLOR: Record<string, string> = {
  green: '#34C759', yellow: '#FFCC00', red: '#FF3B30',
};

export default function AgendaScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data, isLoading, isError, refetch, isRefetching } = useAgendaToday();
  const complete = useCompleteAgendaItem();
  const seed = useSeedDemo();

  const onComplete = (item: AgendaItem) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    complete.mutate({ source: item.source });
  };

  // 手工轨:弹量/剂量输入 → 带 value 完成(写同一份记录、同一议程事件)。
  const onManual = (item: AgendaItem) => {
    const cfg = MANUAL_CAPTURE[item.type];
    if (!cfg) { onComplete(item); return; }
    const submit = (text?: string) => {
      const raw = (text ?? '').trim();
      let value: Record<string, unknown> | undefined;
      if (raw) {
        value = { [cfg.valueKey]: cfg.numeric ? Number(raw) : raw };
        if (cfg.numeric && Number.isNaN(value[cfg.valueKey] as number)) {
          Alert.alert('请输入数字'); return;
        }
      }
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
      complete.mutate({ source: item.source, track: 'manual', value });
    };
    if (Platform.OS === 'ios') {
      Alert.prompt(item.title, cfg.prompt, submit, 'plain-text', '',
        cfg.numeric ? 'numeric' : 'default');
    } else {
      // Android 无 Alert.prompt:退回手工轨默认完成(量留空)。
      submit();
    }
  };

  const statusColor = (status: string): string => {
    if (status === 'completed') return c.brand;
    if (status === 'overdue') return c.red;
    return c.labelTertiary;
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>今日议程</Text>
        {data ? <Text style={styles.subtitle}>{data.agenda_date} · {data.count} 项</Text> : null}
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
      ) : isError ? (
        <View style={styles.center}>
          <Text style={styles.muted}>加载失败</Text>
          <TouchableOpacity onPress={() => refetch()}><Text style={styles.retry}>重试</Text></TouchableOpacity>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
        >
          {(data?.items ?? []).length === 0 ? (
            <View style={styles.center}>
              <Text style={styles.muted}>今天没有待办</Text>
              <TouchableOpacity
                style={styles.seedBtn}
                disabled={seed.isPending}
                onPress={() => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
                  seed.mutate();
                }}
              >
                <Text style={styles.seedBtnText}>
                  {seed.isPending ? '生成中…' : '一键试用(水杯协议 + 登记胃溃疡)'}
                </Text>
              </TouchableOpacity>
            </View>
          ) : (
            (data?.items ?? []).map((item, idx) => (
              <View key={`${item.source.object_type}-${item.source.object_id}-${idx}`} style={styles.card}>
                <Ionicons
                  name={TYPE_ICON[item.type] ?? 'ellipse-outline'}
                  size={22}
                  color={item.status === 'overdue' ? c.red : c.brand}
                  style={styles.icon}
                />
                <View style={styles.cardBody}>
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  <Text style={[styles.cardStatus, { color: statusColor(item.status) }]}>
                    {STATUS_LABEL[item.status] ?? item.status}
                    {item.next_due ? ` · ${item.next_due}` : ''}
                  </Text>
                  {item.detail ? <Text style={styles.cardDetail}>{item.detail}</Text> : null}
                </View>
                {item.type === 'training' && item.light ? (
                  <View style={styles.lightWrap}>
                    <View style={[styles.lightDot, { backgroundColor: LIGHT_COLOR[item.light] ?? c.labelTertiary }]} />
                    {typeof item.readiness_score === 'number' && item.readiness_score > 0 ? (
                      <Text style={styles.lightScore}>{item.readiness_score}</Text>
                    ) : null}
                  </View>
                ) : isProtocolActionable(item) ? (
                  <View style={styles.actions}>
                    {MANUAL_CAPTURE[item.type] ? (
                      <TouchableOpacity
                        style={styles.manualBtn}
                        disabled={complete.isPending}
                        onPress={() => onManual(item)}
                      >
                        <Text style={styles.manualBtnText}>手工</Text>
                      </TouchableOpacity>
                    ) : null}
                    <TouchableOpacity
                      style={styles.doneBtn}
                      disabled={complete.isPending}
                      onPress={() => onComplete(item)}
                    >
                      <Ionicons name="checkmark" size={18} color="#fff" />
                    </TouchableOpacity>
                  </View>
                ) : item.status === 'completed' ? (
                  <Ionicons name="checkmark-circle" size={24} color={c.brand} />
                ) : null}
              </View>
            ))
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.bgPrimary },
    header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
    title: { fontSize: 24, fontWeight: '700', color: c.labelPrimary },
    subtitle: { fontSize: 13, color: c.labelSecondary, marginTop: spacing.xs },
    center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: spacing.xxxl },
    muted: { color: c.labelSecondary, fontSize: 14 },
    retry: { color: c.brand, fontSize: 14, marginTop: spacing.sm },
    list: { padding: spacing.lg, gap: spacing.md },
    card: {
      flexDirection: 'row', alignItems: 'center', backgroundColor: c.bgCard,
      borderRadius: radii.lg, padding: spacing.lg, gap: spacing.md, ...shadows.subtle,
    },
    icon: { width: 24, textAlign: 'center' },
    cardBody: { flex: 1 },
    cardTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary },
    cardStatus: { fontSize: 13, marginTop: 2 },
    cardDetail: { fontSize: 12, color: c.labelTertiary, marginTop: 2 },
    actions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    doneBtn: {
      width: 36, height: 36, borderRadius: radii.full, backgroundColor: c.brand,
      alignItems: 'center', justifyContent: 'center',
    },
    manualBtn: {
      paddingHorizontal: spacing.md, height: 36, borderRadius: radii.full,
      borderWidth: 1, borderColor: c.brand, alignItems: 'center', justifyContent: 'center',
    },
    manualBtnText: { color: c.brand, fontSize: 13, fontWeight: '600' },
    lightWrap: { alignItems: 'center', width: 36, gap: 2 },
    lightDot: { width: 16, height: 16, borderRadius: radii.full },
    lightScore: { fontSize: 11, fontWeight: '600', color: c.labelSecondary },
    seedBtn: {
      marginTop: spacing.lg, backgroundColor: c.brand,
      paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radii.full,
    },
    seedBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  });
}
