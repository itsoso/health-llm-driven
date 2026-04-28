/**
 * DataFreshnessPanel — Agent 今天知道什么 / 不知道什么.
 *
 * 产品作用: 在首页顶部告诉用户 Agent 的数据视野:
 *   ✓ 已有: Garmin 1h ago / 今日体重 30 min ago
 *   ⚠ 陈旧: 血压 11 天前 / 化验 6 个月前
 *   ✗ 缺失: 基因数据
 *
 * 好处:
 * - 用户主动补数据 → grader 不再在陈旧数据上盲评
 * - Agent 建议前先自己说明知识边界 → 产品"谦虚感"
 * - 复用 Twin.freshness 分区, 零额外后端工作
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { colors, spacing, radii } from '../../constants/theme';
import { getMyTwin, freshnessAgeDays } from '../../services/twin';
import { queryKeys } from '../../applib/queryKeys';

type Freshness = 'fresh' | 'stale' | 'missing';

interface DataStatusItem {
  key: string;
  label: string;
  ageDays: number | null;  // null = 缺失
  freshness: Freshness;
  hint: string;
  route?: string;
  severity: number;  // 0-9, 越大越显眼
}

// 每类数据的阈值配置 — 超过 stale_days 就提醒补录
const DATA_CONFIG: Array<{
  key: 'garmin' | 'weight' | 'labs' | 'diet' | 'medication';
  label: string;
  staleDays: number;     // 多少天前变 stale
  missingSeverity: number;  // 缺失时的显眼度
  route?: string;
}> = [
  { key: 'garmin',     label: 'Garmin',    staleDays: 2,  missingSeverity: 7, route: '/settings' },
  { key: 'weight',     label: '体重',       staleDays: 7,  missingSeverity: 3, route: '/(tabs)/record' },
  { key: 'labs',       label: '化验',       staleDays: 180, missingSeverity: 4, route: '/indicator-history' },
  { key: 'diet',       label: '饮食',       staleDays: 1,  missingSeverity: 2, route: '/diet' },
  { key: 'medication', label: '用药',       staleDays: 2,  missingSeverity: 5 },
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
  const { data: twin } = useQuery({
    queryKey: queryKeys.twin,
    queryFn: () => getMyTwin(),
    staleTime: 60 * 1000,  // 1min client cache, 后端已 5min
  });

  const items = useMemo<DataStatusItem[]>(() => {
    if (!twin?.freshness) return [];
    return DATA_CONFIG.map(cfg => {
      const raw = twin.freshness[cfg.key];
      const ageDays = freshnessAgeDays(raw);
      const freshness = classify(ageDays, cfg.staleDays);
      const severity = freshness === 'missing' ? cfg.missingSeverity :
                       freshness === 'stale'   ? Math.min(cfg.missingSeverity, Math.floor((ageDays! / cfg.staleDays) * 5)) :
                       0;
      return {
        key: cfg.key,
        label: cfg.label,
        ageDays,
        freshness,
        hint: ageLabel(ageDays),
        route: cfg.route,
        severity,
      };
    }).sort((a, b) => b.severity - a.severity);
  }, [twin]);

  if (!twin) return null;

  const fresh = items.filter(i => i.freshness === 'fresh');
  const needAttention = items.filter(i => i.freshness !== 'fresh').slice(0, 3);

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <Text style={styles.knowLabel}>Agent 已知</Text>
        <Text style={styles.knowValue} numberOfLines={1}>
          {fresh.length > 0
            ? fresh.map(i => i.label).join(' · ')
            : '数据 尚未同步'}
        </Text>
      </View>
      {needAttention.length > 0 && (
        <View style={styles.row}>
          <Text style={styles.gapLabel}>需补全</Text>
          <View style={styles.gapPills}>
            {needAttention.map(item => (
              <Pressable
                key={item.key}
                style={[
                  styles.gapPill,
                  item.freshness === 'missing' && styles.gapPillMissing,
                  item.freshness === 'stale'   && styles.gapPillStale,
                ]}
                onPress={() => item.route && router.push(item.route as any)}
                accessibilityLabel={`${item.label} ${item.hint}`}
              >
                <Ionicons
                  name={item.freshness === 'missing' ? 'alert-circle-outline' : 'time-outline'}
                  size={12}
                  color={item.freshness === 'missing' ? '#FF453A' : '#FF9F0A'}
                />
                <Text style={styles.gapPillText}>
                  {item.label} · {item.hint}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    gap: 6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  knowLabel: {
    fontSize: 11,
    color: colors.labelTertiary,
    width: 56,
  },
  knowValue: {
    flex: 1,
    fontSize: 12,
    color: colors.labelSecondary,
  },
  gapLabel: {
    fontSize: 11,
    color: colors.labelTertiary,
    width: 56,
  },
  gapPills: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  gapPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    backgroundColor: colors.fill,
  },
  gapPillMissing: {
    backgroundColor: 'rgba(255, 69, 58, 0.12)',
  },
  gapPillStale: {
    backgroundColor: 'rgba(255, 159, 10, 0.12)',
  },
  gapPillText: {
    fontSize: 11,
    color: colors.labelSecondary,
  },
});
