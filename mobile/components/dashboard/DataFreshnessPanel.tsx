/**
 * DataFreshnessPanel — 阿衡今天知道什么 / 不知道什么.
 * 用 DashboardCard 的 flat variant (无 shadow + 边框) 视觉次要化.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { getMyTwin, freshnessAgeDays } from '../../services/twin';
import { queryKeys } from '../../applib/queryKeys';
import DashboardCard, { CardCountBadge } from './DashboardCard';

type Freshness = 'fresh' | 'stale' | 'missing';

interface DataStatusItem {
  key: string;
  label: string;
  ageDays: number | null;
  freshness: Freshness;
  hint: string;
  route?: string;
  severity: number;
}

const DATA_CONFIG: Array<{
  key: 'garmin' | 'weight' | 'waist' | 'blood_pressure' | 'sleep' | 'labs' | 'diet' | 'medication';
  label: string;
  staleDays: number;
  missingSeverity: number;
  route?: string;
}> = [
  { key: 'garmin',         label: 'Garmin',  staleDays: 2,   missingSeverity: 7, route: '/settings' },
  { key: 'weight',         label: '体重',    staleDays: 7,   missingSeverity: 3, route: '/(tabs)/record' },
  { key: 'waist',          label: '腰围',    staleDays: 14,  missingSeverity: 4, route: '/(tabs)/record' },
  { key: 'blood_pressure', label: '血压',    staleDays: 7,   missingSeverity: 6, route: '/(tabs)/record' },
  { key: 'sleep',          label: '睡眠',    staleDays: 2,   missingSeverity: 5, route: '/sleep' },
  { key: 'labs',           label: '化验',    staleDays: 180, missingSeverity: 4, route: '/indicator-history' },
  { key: 'diet',           label: '饮食',    staleDays: 1,   missingSeverity: 2, route: '/diet' },
  { key: 'medication',     label: '用药',    staleDays: 2,   missingSeverity: 5 },
];

function classify(ageDays: number | null, staleDays: number): Freshness {
  if (ageDays === null) return 'missing';
  if (ageDays > staleDays) return 'stale';
  return 'fresh';
}

function ageLabel(ageDays: number | null): string {
  if (ageDays === null) return '未录入';
  if (ageDays === 0) return '今日';
  if (ageDays === 1) return '昨日';
  if (ageDays < 30) return `${ageDays} 天前`;
  if (ageDays < 365) return `${Math.floor(ageDays / 30)} 月前`;
  return `${Math.floor(ageDays / 365)} 年前`;
}

export default function DataFreshnessPanel() {
  const router = useRouter();
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);

  const { data: twin } = useQuery({
    queryKey: queryKeys.twin,
    queryFn: () => getMyTwin(),
    staleTime: 60 * 1000,
  });

  const items = useMemo<DataStatusItem[]>(() => {
    if (!twin?.freshness) return [];
    return DATA_CONFIG.map(cfg => {
      const raw = twin.freshness[cfg.key];
      const ageDays = freshnessAgeDays(raw);
      const freshness = classify(ageDays, cfg.staleDays);
      const severity = freshness === 'missing'
        ? cfg.missingSeverity
        : freshness === 'stale'
          ? Math.min(cfg.missingSeverity, Math.floor((ageDays! / cfg.staleDays) * 5))
          : 0;
      return {
        key: cfg.key, label: cfg.label, ageDays, freshness,
        hint: ageLabel(ageDays), route: cfg.route, severity,
      };
    }).sort((a, b) => b.severity - a.severity);
  }, [twin]);

  if (!twin) return null;

  const fresh = items.filter(i => i.freshness === 'fresh');
  const needAttention = items.filter(i => i.freshness !== 'fresh').slice(0, 5);
  const total = items.length;

  const title = needAttention.length > 0
    ? `数据完整度 ${fresh.length}/${total} · 待补 ${items.length - fresh.length} 项`
    : `数据齐全 ${fresh.length}/${total}`;

  return (
    <DashboardCard
      icon="pulse-outline"
      iconTint={c.bgPrimary}
      iconColor={c.brand}
      kicker="阿衡数据视野"
      title={title}
      collapsible
      defaultCollapsed={needAttention.length === 0}
      variant="flat"
      trailing={needAttention.length > 0 ? <CardCountBadge value={needAttention.length} /> : undefined}
      accessibilityLabel="阿衡数据状态"
    >
      {fresh.length > 0 && (
        <View style={styles.row}>
          <Text style={styles.rowLabel}>已知</Text>
          <Text style={styles.rowValue} numberOfLines={2}>
            {fresh.map(i => i.label).join(' · ')}
          </Text>
        </View>
      )}
      {needAttention.length > 0 && (
        <View style={styles.row}>
          <Text style={styles.rowLabel}>需补全</Text>
          <View style={styles.gapPills}>
            {needAttention.map(item => (
              <Pressable
                key={item.key}
                style={[
                  styles.gapPill,
                  item.freshness === 'missing' && { backgroundColor: c.tintRed },
                  item.freshness === 'stale'   && { backgroundColor: c.tintAmber },
                ]}
                onPress={() => item.route && router.push(item.route as any)}
                accessibilityLabel={`${item.label} ${item.hint}`}
              >
                <Ionicons
                  name={item.freshness === 'missing' ? 'alert-circle-outline' : 'time-outline'}
                  size={12}
                  color={item.freshness === 'missing' ? c.red : c.amber}
                />
                <Text style={styles.gapPillText}>
                  {item.label} · {item.hint}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}
    </DashboardCard>
  );
}

function createStyles(c: ColorPalette, _isDark: boolean) {
  return StyleSheet.create({
    row: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
    gapPills: { flex: 1, flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    gapPill: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      paddingHorizontal: 8, paddingVertical: 4, borderRadius: 10,
      backgroundColor: c.fill,
    },
    rowLabel: { width: 56, fontSize: 11, color: c.labelTertiary, paddingTop: 3 } as TextStyle,
    rowValue: { flex: 1, fontSize: 13, color: c.labelPrimary, lineHeight: 19 } as TextStyle,
    gapPillText: { fontSize: 11, color: c.labelSecondary } as TextStyle,
  });
}
